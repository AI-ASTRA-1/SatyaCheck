"""Level and dynamic-range augmentation.

This module exists because of a measurement, not a hunch. On 2026-09-07 the
pretrained AASIST checkpoint was swept over fixed active-speech RMS targets:

    clip              0.010   0.020   0.040   0.080   0.160
    genuine speaker   0.024   0.141   0.396   0.640   0.873
    synthetic clip    0.010   0.018   0.205   0.740   0.999

Every row is essentially the same function of level, and below 0.160 the synthetic
clip scores lower than the genuine speakers. A model trained on a corpus recorded at
consistent level never learns to ignore level, so at inference it reads loudness as
evidence of synthesis. Real calls arrive at wildly varying levels.

`random_gain` is the fix, and it is the cheapest augmentation in the set: no codec,
no resampling, one multiply. `compress` covers the other half, since handsets and
networks apply dynamic range compression that changes the shape of the envelope
rather than only its scale.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GainPreset:
    """A named compressor setting, so a result can name the curve that produced it."""

    name: str
    threshold_db: float
    ratio: float
    attack_ms: float
    release_ms: float
    makeup_db: float


# Attack times are deliberately short. A slow attack lets onsets through
# unattenuated for the length of the attack, which raises the peak-to-RMS ratio
# instead of lowering it: the opposite of compression, and measurably so.

#: Light touch, roughly a handset being polite about it.
MILD_HANDSET = GainPreset("mild_handset", -24.0, 2.0, 1.0, 150.0, 3.0)

#: What a phone voice-recorder app tends to do: obvious, audible levelling.
AGGRESSIVE_RECORDER = GainPreset("aggressive_recorder", -30.0, 6.0, 0.5, 80.0, 9.0)

#: Broadcast-style, the most severe of the three.
BROADCAST = GainPreset("broadcast", -35.0, 10.0, 0.2, 60.0, 12.0)

PRESETS = {p.name: p for p in (MILD_HANDSET, AGGRESSIVE_RECORDER, BROADCAST)}


def _db_to_linear(db: float | np.ndarray) -> np.ndarray:
    return np.asarray(10.0 ** (np.asarray(db) / 20.0), dtype=np.float32)


def random_gain(
    samples: np.ndarray,
    rng: np.random.Generator,
    *,
    min_db: float = -20.0,
    max_db: float = 6.0,
) -> np.ndarray:
    """Scale by a random gain in [min_db, max_db], clipping at full scale.

    The single most important augmentation in this package, per the measurement in
    the module docstring. Applied on its own it teaches level invariance, which the
    pretrained checkpoints conspicuously lack.
    """
    x = np.asarray(samples, dtype=np.float32)
    gain = float(rng.uniform(min_db, max_db))
    return np.clip(x * _db_to_linear(gain), -1.0, 1.0).astype(np.float32)


def compress(
    samples: np.ndarray,
    preset: GainPreset = AGGRESSIVE_RECORDER,
    sample_rate: int = 16000,
) -> np.ndarray:
    """Feed-forward dynamic range compression with makeup gain.

    Envelope follower with separate attack and release, a hard-knee gain computer,
    then makeup gain. Deliberately simple: the point is to move the envelope in a
    phone-like way, not to model any particular device.
    """
    x = np.asarray(samples, dtype=np.float32)
    if x.size == 0:
        return x.copy()

    attack = float(np.exp(-1.0 / max(sample_rate * preset.attack_ms / 1000.0, 1.0)))
    release = float(np.exp(-1.0 / max(sample_rate * preset.release_ms / 1000.0, 1.0)))

    # Envelope follower. Sequential by nature: attack and release differ, so the
    # coefficient depends on whether the signal is rising or falling.
    magnitude = np.abs(x)
    envelope = np.empty_like(magnitude)
    current = 0.0
    for i in range(magnitude.shape[0]):
        target = magnitude[i]
        coeff = attack if target > current else release
        current = coeff * current + (1.0 - coeff) * target
        envelope[i] = current

    envelope_db = 20.0 * np.log10(np.maximum(envelope, 1e-9))
    over = envelope_db - preset.threshold_db
    reduction_db = np.where(over > 0.0, over * (1.0 / preset.ratio - 1.0), 0.0)

    gained = x * _db_to_linear(reduction_db + preset.makeup_db)

    # The envelope lags a transient by roughly the attack time, so an onset is
    # briefly under-attenuated and makeup gain can push it past full scale. Real
    # compressors overshoot the same way, but clipping here would replace the effect
    # we are modelling with a different one, so scale back if it would occur.
    peak = float(np.abs(gained).max())
    if peak > 1.0:
        gained = gained / peak
    return gained.astype(np.float32)


def crest_factor_db(samples: np.ndarray) -> float:
    """Peak over RMS in dB, measured on active speech.

    Measured over the whole buffer instead, a clip that is half silence reports a
    huge crest factor no matter what was done to it, and compression appears to make
    the number worse. The measurement has to ignore silence for the same reason the
    SNR measurement does.
    """
    from ml.augment.noise import active_speech_rms

    x = np.asarray(samples, dtype=np.float32)
    if x.size == 0:
        return 0.0
    # 99.9th percentile rather than the maximum. A single-sample transient is not
    # what "peak level" means here, and using max() makes the measure hostage to
    # one sample of compressor overshoot.
    peak = float(np.percentile(np.abs(x), 99.9) + 1e-12)
    return 20.0 * float(np.log10(peak / active_speech_rms(x)))
