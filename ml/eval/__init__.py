"""Detection metrics.

`AGENTS.md`: report cost-weighted metrics, not a bare EER, because missing a fraud
and annoying a real customer are not equally bad mistakes. An EER quoted on its own
is the single easiest way to overstate a detector, since it reports the one operating
point where both error types are equal, and that is never where the system runs.
"""

from .cost import CostModel, detection_cost, min_detection_cost
from .eer import compute_eer, det_curve

__all__ = [
    "CostModel",
    "compute_eer",
    "det_curve",
    "detection_cost",
    "min_detection_cost",
]
