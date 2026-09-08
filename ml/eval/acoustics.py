"""Channel statistics of a waveform, for asking which one the score tracks.

Every measure here is a property of the recording rather than of the speech: how
loud the noise is, how much bandwidth survived, where the spectral energy sits. If
the detector's score is driven by the acquisition channel rather than by synthesis,
one of these should predict it.

Two rules the implementations follow, both learned the hard way in `ml/README.md`:

**Measure on speech, not on the whole file.** A clip with a long silent lead-in has a
different centroid and a different crest factor from the same speech without it, and
the difference says nothing about the channel. Where a statistic is about the speech,
it is computed over speech-active frames only.

**Level is not a channel statistic.** The model is level-invariant by construction
(per-window unit variance), so absolute loudness must not sneak in through the back
door. `crest_factor_db` and `snr_db` are ratios; `noise_floor_dbfs` is absolute and
is labelled as such.
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000

#: 20 ms, the same frame the activity gate uses, so "speech-active" means the same
#: thing here as it does when a window is selected for scoring.
FRAME = 320

#: Frames at or below this percentile of frame energy are treated as the noise floor,
#: and at or above the other as speech. Percentiles rather than a fixed threshold,
#: because these clips span 40 dB of level.
NOISE_PERCENTILE = 20
SPEECH_PERCENTILE = 90

_EPS = 1e-12


def frames(x: np.ndarray, size: int = FRAME) -> np.ndarray:
    usable = x[: len(x) // size * size]
    if usable.size == 0:
        return np.zeros((0, size), dtype=np.float32)
    return usable.reshape(-1, size)


def frame_rms(x: np.ndarray, size: int = FRAME) -> np.ndarray:
    block = frames(x, size)
    if block.size == 0:
        return np.zeros(0)
    return np.sqrt((block**2).mean(axis=1) + _EPS)


def _db(value: float) -> float:
    return float(20.0 * np.log10(max(value, _EPS)))


def noise_floor_dbfs(x: np.ndarray) -> float:
    """Median level of the quietest fifth of frames, in dBFS. Absolute, not a ratio."""
    rms = frame_rms(x)
    if rms.size == 0:
        return _db(0.0)
    quiet = rms[rms <= np.percentile(rms, NOISE_PERCENTILE)]
    return _db(float(np.median(quiet)) if quiet.size else float(rms.min()))


def speech_level_dbfs(x: np.ndarray) -> float:
    """Median level of the loudest tenth of frames, in dBFS."""
    rms = frame_rms(x)
    if rms.size == 0:
        return _db(0.0)
    loud = rms[rms >= np.percentile(rms, SPEECH_PERCENTILE)]
    return _db(float(np.median(loud)) if loud.size else float(rms.max()))


def snr_db(x: np.ndarray) -> float:
    """Speech level over noise floor. A ratio, so it survives a gain change."""
    return speech_level_dbfs(x) - noise_floor_dbfs(x)


def crest_factor_db(x: np.ndarray) -> float:
    """Peak over RMS, in dB. Falls when a compressor or a limiter has been applied.

    `ml/README.md` records that this does not separate our clips, which is why it is
    here: a statistic already known not to work is a useful control among ones that
    might.
    """
    if x.size == 0:
        return 0.0
    return _db(float(np.abs(x).max())) - _db(float(np.sqrt((x**2).mean())))


def _speech_spectrum(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean magnitude spectrum over speech-active frames, and its frequency axis."""
    block = frames(x)
    if block.size == 0:
        return np.zeros(0), np.zeros(0)
    rms = np.sqrt((block**2).mean(axis=1) + _EPS)
    active = block[rms >= np.percentile(rms, NOISE_PERCENTILE)]
    if active.size == 0:
        active = block
    window = np.hanning(active.shape[1])
    spectrum = np.abs(np.fft.rfft(active * window, axis=1)).mean(axis=0)
    return np.fft.rfftfreq(active.shape[1], 1.0 / SAMPLE_RATE), spectrum


def spectral_centroid_hz(x: np.ndarray) -> float:
    """Energy-weighted mean frequency of the speech. Brightness, in one number."""
    freqs, spectrum = _speech_spectrum(x)
    total = float(spectrum.sum())
    if total <= _EPS:
        return 0.0
    return float((freqs * spectrum).sum() / total)


def effective_bandwidth_hz(x: np.ndarray, fraction: float = 0.99) -> float:
    """Frequency below which `fraction` of the speech energy sits.

    The number that separates a narrowband telephone channel from full-band audio,
    without assuming where the cutoff is. G.711 lands near 3400 Hz, a 16 kHz capture
    near 8000 Hz.
    """
    freqs, spectrum = _speech_spectrum(x)
    if spectrum.size == 0:
        return 0.0
    power = spectrum**2
    cumulative = np.cumsum(power)
    total = float(cumulative[-1])
    if total <= _EPS:
        return 0.0
    index = int(np.searchsorted(cumulative, fraction * total))
    return float(freqs[min(index, freqs.size - 1)])


def clipping_fraction(x: np.ndarray) -> float:
    """Share of samples at full scale. Nonlinear distortion, not a channel property."""
    if x.size == 0:
        return 0.0
    return float((np.abs(x) >= 0.999).mean())


#: Every statistic, by the column name it gets in the CSV. Ordered so the ones the
#: brief names come first.
STATISTICS = {
    "snr_db": snr_db,
    "effective_bandwidth_hz": effective_bandwidth_hz,
    "noise_floor_dbfs": noise_floor_dbfs,
    "spectral_centroid_hz": spectral_centroid_hz,
    "crest_factor_db": crest_factor_db,
    "speech_level_dbfs": speech_level_dbfs,
    "clipping_fraction": clipping_fraction,
}


def describe(x: np.ndarray) -> dict[str, float]:
    """Every statistic for one waveform."""
    return {name: float(fn(x)) for name, fn in STATISTICS.items()}


def _ranks(values: np.ndarray) -> np.ndarray:
    """Average ranks, so ties do not bias a rank correlation."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(values.size, dtype=np.float64)
    # Average the ranks within each group of equal values.
    unique, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    if counts.max() > 1:
        sums = np.zeros(unique.size)
        np.add.at(sums, inverse, ranks)
        ranks = (sums / counts)[inverse]
    return ranks


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Rank correlation. Robust to the monotone-but-not-linear relationships here."""
    if a.size < 3:
        return float("nan")
    return pearson(_ranks(a), _ranks(b))
