"""Additive noise at a controlled SNR.

The SNR is measured on **active speech**, not on the whole buffer. A clip that is
half silence would otherwise get roughly 3 dB more noise than requested, and the
error scales with however much silence each clip happens to contain, so a per-SNR
curve built that way is measuring the silence distribution as much as the noise.

`AGENTS.md`: train on noisy audio as well as clean. Retraining on noise recovered
roughly 10 to 15 percentage points in the harder conditions (NTU Singapore, ID not
verified).
"""

from __future__ import annotations

import numpy as np

#: 20 ms at 16 kHz. The gate operates on frames, not samples, because a single
#: sample says nothing about whether someone is speaking.
_FRAME = 320

#: Frames quieter than this fraction of the loudest frame are treated as silence.
_ACTIVITY_FLOOR = 0.05


def active_speech_rms(samples: np.ndarray, frame: int = _FRAME) -> float:
    """RMS over frames that carry speech, ignoring silence.

    A crude energy gate, deliberately. Anything cleverer becomes a voice activity
    detector with its own failure modes, and this only needs to avoid the gross
    error of averaging silence into the signal level.
    """
    x = np.asarray(samples, dtype=np.float32)
    if x.size < frame:
        return float(np.sqrt(np.mean(x**2)) + 1e-12)

    usable = x[: x.size // frame * frame].reshape(-1, frame)
    frame_rms = np.sqrt((usable**2).mean(axis=1) + 1e-12)
    keep = frame_rms > (frame_rms.max() * _ACTIVITY_FLOOR)
    selected = usable[keep] if keep.any() else usable
    return float(np.sqrt((selected**2).mean()) + 1e-12)


def white_noise(length: int, rng: np.random.Generator) -> np.ndarray:
    return rng.normal(0.0, 1.0, length).astype(np.float32)


def pink_noise(length: int, rng: np.random.Generator) -> np.ndarray:
    """1/f noise, closer to room and street noise than white is."""
    white = rng.normal(0.0, 1.0, length)
    spectrum = np.fft.rfft(white)
    frequencies = np.arange(spectrum.size)
    frequencies[0] = 1
    spectrum = spectrum / np.sqrt(frequencies)
    shaped = np.fft.irfft(spectrum, n=length)
    return (shaped / (np.std(shaped) + 1e-12)).astype(np.float32)


def add_noise_at_snr(
    samples: np.ndarray,
    snr_db: float,
    rng: np.random.Generator,
    *,
    noise: np.ndarray | None = None,
) -> np.ndarray:
    """Mix noise in so that active speech sits `snr_db` above it.

    `noise` may be a recorded noise sample, for example the room tone captured at the
    head of a recording session, in which case it is tiled or truncated to length.
    Otherwise pink noise is generated.
    """
    x = np.asarray(samples, dtype=np.float32)
    if x.size == 0:
        return x.copy()

    if noise is None:
        n = pink_noise(x.size, rng)
    else:
        n = np.asarray(noise, dtype=np.float32)
        if n.size == 0:
            raise ValueError("noise sample is empty")
        if n.size < x.size:
            n = np.tile(n, x.size // n.size + 1)
        n = n[: x.size]

    speech_rms = active_speech_rms(x)
    noise_rms = float(np.sqrt(np.mean(n**2)) + 1e-12)
    target_noise_rms = speech_rms / (10.0 ** (snr_db / 20.0))

    mixed = x + n * (target_noise_rms / noise_rms)
    return np.clip(mixed, -1.0, 1.0).astype(np.float32)


def measured_snr_db(clean: np.ndarray, noisy: np.ndarray) -> float:
    """SNR of a mix, for tests and reporting. Measured the same way it was applied."""
    clean = np.asarray(clean, dtype=np.float32)
    noise = np.asarray(noisy, dtype=np.float32) - clean
    speech_rms = active_speech_rms(clean)
    noise_rms = float(np.sqrt(np.mean(noise**2)) + 1e-12)
    return 20.0 * float(np.log10(speech_rms / noise_rms))
