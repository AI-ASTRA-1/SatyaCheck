"""Signals that are not speech, for asking what the detector actually responds to.

The question these exist to answer: does the model give high scores to audio that is
not synthetic speech at all, simply because it is unlike ASVspoof? If it does, its
positive class is "not-ASVspoof" rather than "synthetic", and no amount of channel
augmentation moves a decision boundary that is in the wrong place.

Every generator is seeded and pure, so a probe row regenerates from the repo with no
audio asset to lose. The music bed is synthesised rather than taken from a file for
the same reason, and because the only music on this machine has vocals in it, which
would confound a non-speech probe with sung speech.

These are probes, not augmentations. Nothing here goes near training data.
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000

#: Amplitude of the noise probes, as a standard deviation of the waveform. 0.05 is
#: ordinary speech level, so a high score cannot be blamed on loudness. The model is
#: level-invariant by construction (per-window unit variance), but stating the level
#: costs nothing and forestalls the question.
NOISE_SIGMA = 0.05

#: Amplitude of the near-silence probe. Small enough to be inaudible, large enough
#: that the input is not exactly zero, which would divide by a zero standard
#: deviation inside the model's normalisation.
DITHER_SIGMA = 1e-4


def white_noise(
    samples: int, rng: np.random.Generator, sigma: float = NOISE_SIGMA
) -> np.ndarray:
    """Gaussian white noise. Flat spectrum, no structure of any kind."""
    return rng.normal(0.0, sigma, samples).astype(np.float32)


def pink_noise(
    samples: int, rng: np.random.Generator, sigma: float = NOISE_SIGMA
) -> np.ndarray:
    """1/f noise, shaped in the frequency domain then scaled to `sigma`.

    Pink rather than white because speech has a falling spectrum, so pink noise is
    the noise that is spectrally closest to speech while carrying none of its
    structure. If white and pink score differently, spectral tilt is part of what
    the model reads.
    """
    spectrum = np.fft.rfft(rng.normal(0.0, 1.0, samples))
    frequencies = np.fft.rfftfreq(samples, 1.0 / SAMPLE_RATE)
    # Bin 0 is DC. Dividing by sqrt(f) there is a division by zero and the result is
    # an offset, not a colour, so it is dropped rather than scaled.
    shaping = np.zeros_like(frequencies)
    shaping[1:] = 1.0 / np.sqrt(frequencies[1:])
    shaped = np.fft.irfft(spectrum * shaping, n=samples)
    return _to_sigma(shaped, sigma)


def silence_dither(
    samples: int, rng: np.random.Generator, sigma: float = DITHER_SIGMA
) -> np.ndarray:
    """Near-silence. Not exact zeros, which would be a degenerate input."""
    return rng.normal(0.0, sigma, samples).astype(np.float32)


#: Root frequencies for the music bed, one per repetition. Ordinary musical pitches
#: (A2 through E3), listed rather than drawn so the five repetitions differ from each
#: other in a way a reader can see.
_MUSIC_ROOTS = (110.0, 123.5, 146.8, 164.8, 196.0)

#: A minor triad plus the octave, as frequency ratios on the root.
_CHORD_RATIOS = (1.0, 1.2, 1.5, 2.0)

#: Relative amplitude of harmonics 1 to 4 of each chord tone.
_HARMONIC_GAINS = (1.0, 0.5, 0.25, 0.125)


def music(
    samples: int, rng: np.random.Generator, sigma: float = NOISE_SIGMA
) -> np.ndarray:
    """A synthesised instrumental chord bed. Harmonic, pitched, and not speech.

    Structured non-speech audio, which the noise probes are not. It has harmonics,
    vibrato and an amplitude envelope, so it exercises whatever the model reads from
    periodic structure, without a vocal tract anywhere near it.

    Deliberately no vocals: a sung line is speech, and a probe that contains speech
    cannot answer a question about non-speech.
    """
    index = int(rng.integers(0, len(_MUSIC_ROOTS)))
    root = _MUSIC_ROOTS[index]
    t = np.arange(samples, dtype=np.float64) / SAMPLE_RATE

    # Vibrato as phase modulation, a few Hz at a fraction of a semitone, which is
    # what an instrument does and a pure tone does not.
    vibrato_hz = 4.0 + float(rng.uniform(-1.0, 1.0))
    vibrato = 0.003 * np.sin(2 * np.pi * vibrato_hz * t)

    bed = np.zeros(samples, dtype=np.float64)
    for ratio in _CHORD_RATIOS:
        phase_offset = float(rng.uniform(0, 2 * np.pi))
        for harmonic, gain in enumerate(_HARMONIC_GAINS, start=1):
            frequency = root * ratio * harmonic
            if frequency >= SAMPLE_RATE / 2:
                # Above Nyquist it would alias into an inharmonic partial, which is
                # a synthesis artifact rather than music.
                break
            bed += gain * np.sin(
                2 * np.pi * frequency * t * (1.0 + vibrato) + phase_offset
            )

    # A slow swell, so the level is not constant for four seconds.
    envelope = 0.7 + 0.3 * np.sin(2 * np.pi * 0.25 * t + float(rng.uniform(0, 6.28)))
    return _to_sigma(bed * envelope, sigma)


def _to_sigma(x: np.ndarray, sigma: float) -> np.ndarray:
    """Scale to a target standard deviation. Zero-variance input stays zero."""
    current = float(x.std())
    if current == 0.0:
        return np.zeros_like(x, dtype=np.float32)
    return (x * (sigma / current)).astype(np.float32)


def segments(x: np.ndarray, count: int, window: int) -> list[np.ndarray]:
    """`count` windows at evenly spaced starts across `x`.

    Starts are spread across the whole file rather than taken from the front,
    because the score depends on where a window starts: one 6 s clip spans 0.0024 to
    0.9972 across four positions (`ml/README.md`). Sampling only the beginning would
    measure the beginning.

    Windows overlap when the file is too short to hold `count` of them end to end.
    That is reported by the caller rather than hidden; overlapping draws from one
    file are not independent.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    if x.size < window:
        raise ValueError(f"{x.size} samples is shorter than one {window} window")
    if count == 1:
        return [x[:window]]
    last_start = x.size - window
    starts = np.linspace(0, last_start, count).round().astype(int)
    return [x[s : s + window] for s in starts]


def overlap_fraction(length: int, count: int, window: int) -> float:
    """How much consecutive segments overlap, 0.0 when they are disjoint."""
    if count < 2:
        return 0.0
    hop = (length - window) / (count - 1)
    return max(0.0, 1.0 - hop / window)


#: The four non-speech conditions, by name. `genuine_studio` and `genuine_phone` are
#: not here because they are drawn from real files rather than generated.
GENERATORS = {
    "white_noise": white_noise,
    "pink_noise": pink_noise,
    "music": music,
    "silence_dither": silence_dither,
}
