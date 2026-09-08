"""Equal error rate and the DET curve it comes from.

Scores are **bonafide scores**: higher means more likely genuine. Labels are 1 for
bonafide, 0 for spoof. That convention comes from the published ASVspoof evaluation
code and is kept throughout so a score never has to be mentally flipped.

The full curve is returned, not only the crossing point, because the EER is a single
point on it and the interesting operating points for this product are elsewhere: a
bank cares about the false alarm rate at a fixed miss rate, not about where the two
happen to be equal.
"""

from __future__ import annotations

import numpy as np

BONAFIDE = 1


def det_curve(
    scores: np.ndarray, labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (false_reject_rate, false_accept_rate, thresholds).

    A false reject is a genuine speaker called synthetic, which is the false positive
    the product cares most about. A false accept is a clone that got through.
    """
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels)
    if scores.shape != labels.shape:
        raise ValueError(f"scores {scores.shape} and labels {labels.shape} differ")

    bonafide_total = float((labels == BONAFIDE).sum())
    spoof_total = float((labels != BONAFIDE).sum())
    if bonafide_total == 0 or spoof_total == 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty

    order = np.argsort(scores, kind="mergesort")
    scores, labels = scores[order], labels[order]

    # Threshold sweeps upward. Everything at or below it is declared spoof, so the
    # false reject rate is the fraction of bonafide already passed, and the false
    # accept rate is the fraction of spoof still above.
    false_rejects = np.cumsum(labels == BONAFIDE) / bonafide_total
    false_accepts = 1.0 - (np.cumsum(labels != BONAFIDE) / spoof_total)

    # Prepend the operating point where nothing is rejected.
    false_rejects = np.concatenate([[0.0], false_rejects])
    false_accepts = np.concatenate([[1.0], false_accepts])
    thresholds = np.concatenate([[scores[0] - 1.0], scores])
    return false_rejects, false_accepts, thresholds


def compute_eer(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    """Equal error rate and the threshold at which it occurs.

    Returns (nan, nan) when one class is absent, rather than a number that looks
    like a result.
    """
    false_rejects, false_accepts, thresholds = det_curve(scores, labels)
    if false_rejects.size == 0:
        return float("nan"), float("nan")

    index = int(np.argmin(np.abs(false_rejects - false_accepts)))
    eer = float((false_rejects[index] + false_accepts[index]) / 2.0)
    return eer, float(thresholds[index])


def false_accept_at_false_reject(
    scores: np.ndarray, labels: np.ndarray, target_false_reject: float
) -> tuple[float, float]:
    """How many clones get through, at a false-alarm rate the deployment tolerates.

    This is usually the number a customer actually asks for: "if I accept flagging
    one genuine call in a hundred, how many fakes do you catch?"
    """
    false_rejects, false_accepts, thresholds = det_curve(scores, labels)
    if false_rejects.size == 0:
        return float("nan"), float("nan")
    index = int(np.searchsorted(false_rejects, target_false_reject, side="left"))
    index = min(index, false_rejects.size - 1)
    return float(false_accepts[index]), float(thresholds[index])
