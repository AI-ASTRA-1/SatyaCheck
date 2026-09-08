"""Choosing which windows of a file to score, and saying so when the choice is poor.

Silence does not score like speech, so averaging it in produces a confidently wrong
number. This module picks speech-active windows and, importantly, reports *how* it
had to pick them, so a caller can distinguish a clean measurement from a salvaged one.

The ordinary path is unchanged from the original implementation in `sweep.py`:
non-overlapping windows, each kept when more than `ACTIVITY_FLOOR` of its 20 ms
frames clear a gate set relative to the file's own speech level. Every figure already
recorded in `ml/README.md` came through that path and is unaffected by this module.

What is new is the fallback. A clip of roughly six seconds holds exactly one window on
a non-overlapping grid, and if that single window straddles a pause it is dropped and
the file scores `nan`. That happened to `sadhguru_deepfake` in the IFD samples. A
`nan` reads as a tooling failure, so the file gets quietly excluded from a table
rather than counted, which is the worst of the available outcomes. The fallbacks below
recover a score where speech genuinely exists and label it `sparse` so the weaker
basis travels with the number.

Callers get two fields, and the distinction is load-bearing. `status` is the fine
grained account of how the windows were found. `vad_status` is the coarse `PASS`
or `FAIL` that says whether a score exists at all. When it is `FAIL` there is no
score, and callers must carry `None` rather than substituting a number: a missing
score and a high score are different facts, and `nan` is neither.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: 20 ms at 16 kHz, the frame the activity gate works on.
FRAME_SAMPLES = 320

#: A window must be at least this fraction speech to be scored on the ordinary path.
ACTIVITY_FLOOR = 0.4

#: Gate height as a fraction of a robust "loud speech" level. Percentile rather than
#: max, so one click or thump cannot raise the bar for the whole file.
GATE_FRACTION = 0.15

#: Statuses a caller may see. `ok` is the ordinary path; `sparse` means the score came
#: from a fallback and rests on less speech; `short` means the file was shorter than
#: one analysis window and was tiled; `no_speech` means no score was produced.
STATUS_OK = "ok"
STATUS_SPARSE = "sparse"
STATUS_SHORT = "short"
STATUS_NO_SPEECH = "no_speech"

#: The coarse gate result a caller records alongside a score. `FAIL` means no score
#: was produced and none should be invented; a missing score and a high score are
#: different facts and must never be collapsed into one number.
VAD_PASS = "PASS"
VAD_FAIL = "FAIL"


@dataclass(frozen=True)
class WindowSelection:
    """Windows to score, plus how they were arrived at."""

    windows: list[np.ndarray]
    status: str
    speech_seconds: float
    #: Why the selection came out the way it did. Always set when nothing was
    #: selected, because "no score" without a reason reads as a tooling failure and
    #: gets the file quietly dropped from a table rather than counted.
    reason: str = ""

    @property
    def scored(self) -> bool:
        return bool(self.windows)

    @property
    def vad_status(self) -> str:
        """`PASS` when a score can be produced, `FAIL` when it cannot."""
        return VAD_PASS if self.windows else VAD_FAIL


def _frame_gate(x: np.ndarray) -> tuple[np.ndarray, float]:
    """Per-frame RMS and the gate height, both relative to this file."""
    usable = x[: len(x) // FRAME_SAMPLES * FRAME_SAMPLES]
    if usable.size == 0:
        return np.empty(0, dtype=np.float32), 0.0
    rms = np.sqrt((usable.reshape(-1, FRAME_SAMPLES) ** 2).mean(axis=1) + 1e-12)
    gate = max(float(np.percentile(rms, 95)) * GATE_FRACTION, 1e-4)
    return rms, gate


def speech_seconds(x: np.ndarray) -> float:
    """Seconds of speech-active audio, by the same gate the windowing uses."""
    rms, gate = _frame_gate(np.asarray(x, dtype=np.float32))
    if rms.size == 0:
        return 0.0
    return float((rms > gate).sum()) * FRAME_SAMPLES / 16000.0


def _active_fraction(chunk: np.ndarray, gate: float) -> float:
    frames = chunk[: len(chunk) // FRAME_SAMPLES * FRAME_SAMPLES]
    if frames.size == 0:
        return 0.0
    rms = np.sqrt((frames.reshape(-1, FRAME_SAMPLES) ** 2).mean(axis=1))
    return float((rms > gate).mean())


def _tile_to(x: np.ndarray, target: int) -> np.ndarray:
    if x.size == 0:
        return np.zeros(target, dtype=np.float32)
    return np.tile(x, target // x.size + 1)[:target].astype(np.float32)


def select_windows(x: np.ndarray, window_samples: int) -> WindowSelection:
    """Speech-active windows, with a status describing how they were found.

    Order of attempts, each only reached when the previous found nothing:

    1. Non-overlapping windows above the floor. The original behaviour, `ok`.
    2. Overlapping windows on a quarter hop. A window that straddles a pause on the
       fixed grid often has a well-aligned neighbour a fraction of a window away.
    3. The single most speech-active window position. Used only when speech exists
       but never fills a window, which is a real recording rather than a failure.

    A file shorter than one window is tiled to fill one, as the scorers themselves do
    with short input, and reported as `short`.
    """
    x = np.asarray(x, dtype=np.float32)
    duration_s = x.size / 16000.0
    rms, gate = _frame_gate(x)
    if rms.size == 0 or not np.any(rms > gate):
        return WindowSelection(
            [],
            STATUS_NO_SPEECH,
            0.0,
            f"no 20 ms frame cleared the activity gate, duration_s={duration_s:.3f}",
        )

    active_s = speech_seconds(x)

    if x.size < window_samples:
        return WindowSelection(
            [_tile_to(x, window_samples)],
            STATUS_SHORT,
            active_s,
            f"duration_s={duration_s:.3f} shorter than one "
            f"{window_samples / 16000.0:.3f} s window, tiled to fill it",
        )

    # 1. The ordinary path, byte-identical to the original implementation.
    ordinary = [
        x[i * window_samples : (i + 1) * window_samples]
        for i in range(x.size // window_samples)
    ]
    kept = [c for c in ordinary if _active_fraction(c, gate) > ACTIVITY_FLOOR]
    if kept:
        return WindowSelection(
            kept,
            STATUS_OK,
            active_s,
            f"{len(kept)} of {len(ordinary)} windows above floor {ACTIVITY_FLOOR}",
        )

    # 2. Overlapping search on a quarter hop.
    hop = max(window_samples // 4, 1)
    overlapped = [
        x[start : start + window_samples]
        for start in range(0, x.size - window_samples + 1, hop)
    ]
    kept = [c for c in overlapped if _active_fraction(c, gate) > ACTIVITY_FLOOR]
    if kept:
        return WindowSelection(
            kept,
            STATUS_SPARSE,
            active_s,
            f"no window on the fixed grid cleared floor {ACTIVITY_FLOOR}, "
            f"{len(kept)} recovered on a quarter hop",
        )

    # 3. Best available position. Speech exists, it simply never fills a window.
    if overlapped:
        best = max(overlapped, key=lambda c: _active_fraction(c, gate))
        ratio = _active_fraction(best, gate)
        return WindowSelection(
            [best],
            STATUS_SPARSE,
            active_s,
            f"speech_ratio={ratio:.3f} below floor {ACTIVITY_FLOOR}, "
            f"scored the single most speech-active window",
        )

    return WindowSelection(
        [],
        STATUS_NO_SPEECH,
        active_s,
        f"speech_s={active_s:.3f} never fills a "
        f"{window_samples / 16000.0:.3f} s window",
    )
