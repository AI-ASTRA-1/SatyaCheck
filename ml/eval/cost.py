"""Cost-weighted detection cost.

The point `AGENTS.md` insists on: missing a fraud and annoying a real customer are
not equally bad mistakes, and which is worse depends on the deployment. A bank is not
a family. So the costs are parameters, and every reported figure carries the cost
model that produced it.

This is the standard normalised detection cost function:

    DCF(t) = C_miss * P_target * P_miss(t) + C_fa * (1 - P_target) * P_fa(t)
    normalised by min(C_miss * P_target, C_fa * (1 - P_target))

Normalising against the best trivial system means **1.0 is the score of a detector
that does nothing useful**, either by accepting everything or rejecting everything.
Above 1.0 is worse than useless. That is the property that makes the number honest.

**What this is not.** `AGENTS.md` asks for cost-weighted metrics to the ASVspoof 5
standard. That challenge uses its own specific cost function and parameters, which a
human should confirm against `arXiv:2408.08739` before any figure is published under
that name. This module is a general, documented DCF with the parameters exposed. Do
not label its output "ASVspoof 5 min-DCF" without that check.

Terminology, since the two sides get swapped constantly:
  miss   = a spoof accepted as genuine. A clone got through.
  false alarm = a genuine speaker rejected. We warned about a real person.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .eer import BONAFIDE, det_curve


@dataclass(frozen=True)
class CostModel:
    """Costs and prior for one deployment. Report this alongside any DCF."""

    name: str

    #: Cost of letting a clone through.
    cost_miss: float = 1.0

    #: Cost of flagging a genuine caller.
    cost_false_alarm: float = 1.0

    #: Prior probability that a given call is an attack. Genuinely small in
    #: deployment, which is what makes false alarms dominate the error budget.
    prior_attack: float = 0.05

    def describe(self) -> str:
        return (
            f"{self.name}(C_miss={self.cost_miss}, C_fa={self.cost_false_alarm}, "
            f"P_attack={self.prior_attack})"
        )


#: Equal costs, high attack prior. Useful for comparing models, not for deployment.
BALANCED = CostModel("balanced", cost_miss=1.0, cost_false_alarm=1.0, prior_attack=0.5)

#: A bank: letting a fraudulent transfer through costs far more than one annoyed
#: customer, but attacks are rare, so false alarms still dominate the total.
BANK = CostModel("bank", cost_miss=10.0, cost_false_alarm=1.0, prior_attack=0.01)

#: A consumer app: a warning the user learns to dismiss destroys the product, so a
#: false alarm is weighted comparatively heavily.
CONSUMER = CostModel("consumer", cost_miss=5.0, cost_false_alarm=2.0, prior_attack=0.005)

PRESETS = {model.name: model for model in (BALANCED, BANK, CONSUMER)}


def _normaliser(model: CostModel) -> float:
    """Cost of the better trivial system: accept everything, or reject everything."""
    return min(
        model.cost_miss * model.prior_attack,
        model.cost_false_alarm * (1.0 - model.prior_attack),
    )


def detection_cost(
    miss_rate: float | np.ndarray,
    false_alarm_rate: float | np.ndarray,
    model: CostModel = BALANCED,
) -> float | np.ndarray:
    """Normalised DCF at a given operating point."""
    raw = (
        model.cost_miss * model.prior_attack * np.asarray(miss_rate)
        + model.cost_false_alarm * (1.0 - model.prior_attack) * np.asarray(false_alarm_rate)
    )
    normaliser = _normaliser(model)
    if normaliser <= 0.0:
        raise ValueError(f"degenerate cost model: {model.describe()}")
    result = raw / normaliser
    return float(result) if np.isscalar(miss_rate) and np.isscalar(false_alarm_rate) else result


def min_detection_cost(
    scores: np.ndarray, labels: np.ndarray, model: CostModel = BALANCED
) -> tuple[float, float]:
    """Minimum normalised DCF over all thresholds, and the threshold achieving it.

    This is an oracle number: it assumes the threshold was chosen with knowledge of
    the test set. Report it as a floor on what the system could do, never as what a
    deployed system will do with a threshold picked in advance.

    Do not be alarmed if several cost models report the **same** value: the models
    differ only in how they weight the false-alarm term, so whenever the optimum sits
    at zero false alarms they all collapse to the miss rate. That is common when
    false alarms are weighted heavily (`bank`, `consumer`) or when the bonafide count
    is small enough that the first non-zero false-alarm rate is already expensive.
    """
    false_rejects, false_accepts, thresholds = det_curve(scores, labels)
    if false_rejects.size == 0:
        return float("nan"), float("nan")

    # false_reject = genuine rejected = false alarm; false_accept = spoof through = miss.
    costs = detection_cost(false_accepts, false_rejects, model)
    index = int(np.argmin(costs))
    return float(np.asarray(costs)[index]), float(thresholds[index])


def summarise(scores: np.ndarray, labels: np.ndarray) -> str:
    """One block carrying EER and every cost model, so neither travels alone."""
    from .eer import compute_eer

    eer, eer_threshold = compute_eer(scores, labels)
    counts = {
        "bonafide": int((np.asarray(labels) == BONAFIDE).sum()),
        "spoof": int((np.asarray(labels) != BONAFIDE).sum()),
    }
    lines = [
        f"n = {counts['bonafide']} bonafide, {counts['spoof']} spoof",
        f"EER          {eer * 100:6.2f}%  (threshold {eer_threshold:.4f})",
    ]
    for model in PRESETS.values():
        value, threshold = min_detection_cost(scores, labels, model)
        lines.append(
            f"min-DCF      {value:6.3f}   {model.describe()}  (threshold {threshold:.4f})"
        )
    lines.append(
        "min-DCF is normalised: 1.0 means no better than a system that always "
        "answers the same way."
    )
    return "\n".join(lines)
