"""Room acoustics: the cue that was missing, and the one that broke the detector.

Measured 2026-09-08 on 12 known-bonafide ASVspoof eval utterances, scored with the
fine-tuned checkpoint that achieves 2.12% EER on that same eval split:

    as-is                    P(synthetic) 0.005
    light reverb                          0.207
    room reverb                           0.426
    big room                              0.651
    microphone tilt only                  0.018

Reverb alone moves known-genuine audio from 0.005 to 0.651. Spectral tilt does not
move it at all, so the cue is specifically **room reflections**.

Why that mattered: ASVspoof bonafide is close-mic studio speech with almost no
reverberation, and every spoof in it is synthesised from that same clean material.
A model trained only on that learns "no room implies genuine". Real speech recorded
by a person in an actual room therefore reads as synthetic, while TTS output, which
is anechoic by construction, reads as genuine. That produced an inverted detector:
a real speaker scored 0.910 while a commercial clone of him scored 0.808.

Applied to **both classes**, for the same reason watermarks go on both classes or
neither: augmenting only the bonafide side would teach the model to treat reverb as
evidence of authenticity, which is the same mistake with the sign flipped.
"""

from __future__ import annotations

import numpy as np

#: Reverberation time in seconds: how long reflections take to decay 60 dB.
#: Roughly 0.2 s is a soft furnished room, 0.6 s a bare hard-walled one.
DEFAULT_RT60_RANGE = (0.15, 0.7)

#: Reflections are quieter than the direct path. Keeps the first arrival dominant,
#: which is what makes the response a room rather than shaped noise.
_REFLECTION_GAIN = 0.35

#: Fraction of the output that is the reverberant signal. 0 is dry, 1 is all
#: reflections. Real speech recorded at arm's length sits low.
DEFAULT_WET_RANGE = (0.15, 0.6)


def synthetic_rir(
    rt60: float,
    rng: np.random.Generator,
    sample_rate: int = 16000,
    *,
    direct_delay_ms: float = 2.0,
) -> np.ndarray:
    """A synthetic room impulse response: exponentially decaying noise.

    Not a measured room, and it does not need to be. The model has never seen any
    decaying reflection pattern, so the point is to introduce the phenomenon with
    varied decay times rather than to reproduce one specific room. Using measured
    RIR corpora would be better and is a later improvement.
    """
    length = max(int(sample_rate * rt60 * 1.5), 16)
    direct = min(int(sample_rate * direct_delay_ms / 1000.0), length - 1)

    impulse = np.zeros(length, dtype=np.float32)

    # Nothing arrives before the direct sound. Filling from sample 0 puts
    # reflections ahead of the source, which is not a room, and can make them
    # louder than the direct path.
    tail = np.arange(length - direct) / sample_rate
    decay = np.exp(-6.907755 * tail / max(rt60, 1e-3))

    # Reflections are attenuated relative to the direct path, so the first arrival
    # stays the loudest as it does in any real room.
    impulse[direct:] = (
        rng.normal(0.0, 1.0, length - direct).astype(np.float32) * decay * _REFLECTION_GAIN
    )
    impulse[direct] = 1.0

    peak = float(np.abs(impulse).max())
    return (impulse / peak).astype(np.float32) if peak > 0 else impulse


def apply_reverb(
    samples: np.ndarray,
    rng: np.random.Generator,
    *,
    rt60: float | None = None,
    wet: float | None = None,
    sample_rate: int = 16000,
) -> np.ndarray:
    """Convolve with a synthetic room, mixing wet and dry. Length is preserved.

    FFT convolution rather than `np.convolve`, which is O(n*m) and far too slow for
    a 4 s window against a 0.7 s impulse inside a training loop.
    """
    x = np.asarray(samples, dtype=np.float32)
    if x.size == 0:
        return x.copy()

    if rt60 is None:
        rt60 = float(rng.uniform(*DEFAULT_RT60_RANGE))
    if wet is None:
        wet = float(rng.uniform(*DEFAULT_WET_RANGE))

    impulse = synthetic_rir(rt60, rng, sample_rate)

    size = 1 << int(np.ceil(np.log2(x.size + impulse.size - 1)))
    convolved = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(impulse, size), size)
    convolved = convolved[: x.size].astype(np.float32)

    # Match the wet signal's level to the dry one before mixing, so the amount of
    # room does not double as a change in loudness.
    dry_rms = float(np.sqrt(np.mean(x**2)) + 1e-12)
    wet_rms = float(np.sqrt(np.mean(convolved**2)) + 1e-12)
    convolved *= dry_rms / wet_rms

    mixed = (1.0 - wet) * x + wet * convolved

    # Restore the original level. Dry and reverberant signals are only partly
    # correlated, so mixing them changes RMS by up to -9 dB, worst at wet=0.5.
    # Left uncorrected, "amount of room" would also mean "quieter", and level is a
    # cue this model has already been caught using. Reverb must vary the acoustics
    # and nothing else; random_gain owns level.
    mixed_rms = float(np.sqrt(np.mean(mixed**2)) + 1e-12)
    mixed *= dry_rms / mixed_rms

    peak = float(np.abs(mixed).max())
    if peak > 1.0:
        mixed = mixed / peak
    return mixed.astype(np.float32)


def reverberation_gain_db(dry: np.ndarray, wet: np.ndarray) -> float:
    """Late-energy ratio between two signals, for tests and reporting.

    A reverberated signal carries more energy in its tail than the dry one, so this
    rises with rt60. It is a proxy, not an acoustic measurement.
    """
    def tail_ratio(x: np.ndarray) -> float:
        x = np.asarray(x, dtype=np.float32)
        if x.size < 320:
            return 0.0
        frames = x[: x.size // 320 * 320].reshape(-1, 320)
        energy = (frames**2).mean(axis=1) + 1e-12
        loud = energy.max()
        # Fraction of frames sitting in the decay region rather than silence.
        return float(((energy > loud * 1e-4) & (energy < loud * 0.1)).mean())

    return 20.0 * float(np.log10((tail_ratio(wet) + 1e-6) / (tail_ratio(dry) + 1e-6)))
