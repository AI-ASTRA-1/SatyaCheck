"""Find where a known clip occurs inside a longer recording of it.

The replay session was captured as one continuous take per device, which is the
right way to do it: nothing is touched between clips, so the controls hold by
construction. It leaves the problem of cutting ten clips back out.

Silence detection cannot do this. Speech has pauses in it, so an energy gate finds
sixteen runs in a take that contains ten clips, and it cannot say which run belongs
to which clip or what order they were played in.

Correlating against the originals can. The acoustic path changes the spectrum and
destroys phase, but it leaves the **amplitude envelope** largely intact: the pattern
of loud and quiet over seconds is a property of the speech, not of the room. So the
match runs on log-energy envelopes rather than on waveforms, and it is normalised, so
a level difference between the original and the replay cannot move the peak.

Nothing here assumes the playback order.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000

#: Envelope frame hop, 10 ms. Alignment is therefore accurate to 10 ms, which is
#: nothing against a 4.0375 s analysis window.
HOP = 160

#: Floor inside the log, so silence maps to a finite value instead of -inf.
_FLOOR = 1e-6


def envelope(x: np.ndarray, hop: int = HOP) -> np.ndarray:
    """Log RMS energy per frame. The shape of the speech over time."""
    usable = x[: len(x) // hop * hop]
    if usable.size == 0:
        return np.zeros(0, dtype=np.float64)
    rms = np.sqrt((usable.reshape(-1, hop) ** 2).mean(axis=1) + _FLOOR)
    return np.log(rms).astype(np.float64)


def _sliding_stats(x: np.ndarray, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Mean and standard deviation of every `width`-long window of `x`."""
    ones = np.concatenate([[0.0], np.cumsum(x)])
    squares = np.concatenate([[0.0], np.cumsum(x * x)])
    count = x.size - width + 1
    total = ones[width:] - ones[:count]
    total_squares = squares[width:] - squares[:count]
    mean = total / width
    variance = np.maximum(total_squares / width - mean * mean, 0.0)
    return mean, np.sqrt(variance)


def normalized_cross_correlation(long: np.ndarray, short: np.ndarray) -> np.ndarray:
    """Correlation of `short` against every position in `long`, in [-1, 1].

    Normalised at every offset, not once globally, so a quiet stretch of the take
    cannot beat a well-matched loud one just by being closer to the overall mean.
    """
    if short.size == 0 or long.size < short.size:
        return np.zeros(0, dtype=np.float64)

    width = short.size
    size = 1 << int(long.size + width - 1).bit_length()
    products = np.fft.irfft(
        np.fft.rfft(long, size) * np.fft.rfft(short[::-1], size), size
    )
    dot = products[width - 1 : width - 1 + long.size - width + 1]

    window_mean, window_sd = _sliding_stats(long, width)
    short_mean = float(short.mean())
    short_sd = float(short.std())

    numerator = dot - width * window_mean * short_mean
    denominator = width * window_sd * short_sd
    # A constant window has zero variance and no defined correlation. Zero is the
    # honest answer there, and it keeps the peak search from finding a divide.
    return np.divide(
        numerator, denominator, out=np.zeros_like(numerator), where=denominator > 1e-12
    )


@dataclass(frozen=True)
class Match:
    """Where a clip was found, and how well."""

    #: Sample offset into the recording.
    offset: int
    #: Peak normalised correlation, in [-1, 1]. Above ~0.5 is a confident match.
    score: float
    #: Second-highest peak outside the winning region. A margin close to zero means
    #: the match is ambiguous even if `score` is high.
    runner_up: float

    @property
    def start_s(self) -> float:
        return self.offset / SAMPLE_RATE

    @property
    def margin(self) -> float:
        return self.score - self.runner_up


def find_clip(recording: np.ndarray, clip: np.ndarray, hop: int = HOP) -> Match | None:
    """Locate `clip` inside `recording`. `None` when it is not long enough to hold it."""
    long = envelope(recording, hop)
    short = envelope(clip, hop)
    correlation = normalized_cross_correlation(long, short)
    if correlation.size == 0:
        return None

    peak = int(np.argmax(correlation))
    score = float(correlation[peak])

    # Exclude a window either side of the peak before looking for the runner-up.
    # Neighbouring offsets correlate almost as well by construction, and counting
    # one of those as a rival would make every match look ambiguous.
    guard = max(short.size // 2, 1)
    masked = correlation.copy()
    masked[max(0, peak - guard) : peak + guard + 1] = -1.0
    runner_up = float(masked.max()) if masked.size else -1.0

    return Match(offset=peak * hop, score=score, runner_up=runner_up)


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Whether two [start, end) sample spans intersect."""
    return a[0] < b[1] and b[0] < a[1]
