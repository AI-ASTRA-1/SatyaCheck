"""The H+4 decision rules, and the diagnostic that keeps them honest.

The five rules are applied in order, first match wins, exactly as agreed. They are
written as code rather than read off a table at 3am because ordered first-match-wins
is easy to get wrong by eye.

**Why there is a diagnostic as well.** Rules 3 and 4 are told apart by
`delta_spoof`, and `delta_spoof` is bounded by how high the spoof scores already
were: a clip at 0.85 cannot rise by 0.40 against a ceiling of 1.0. So a saturated
spoof class produces a small `delta_spoof` whatever the channel does, which reads as
Rule 3's "spoof stayed put" when the truth may be Rule 4's "everything moved". Those
two lead to opposite decisions.

`headroom_traversed` removes the ceiling from the comparison. For a clip at `a` that
moved to `b`, it asks what fraction of the distance from `a` to 1.0 was covered. A
clip with no headroom is excluded rather than divided by nearly zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Rule 1. Above this, the positive class is "not-ASVspoof" rather than "synthetic".
S_OOD_CEILING = 0.85

#: Rule 2, from ML-2's dsp.csv.
DELTA_DSP_FLOOR = 0.40

#: Rules 3, 4 and 5.
GENUINE_MOVED = 0.40
SPOOF_STAYED = 0.15
GENUINE_UNMOVED = 0.15

#: A clip needs at least this much room below 1.0 for `headroom_traversed` to mean
#: anything. Below it the ratio is dominated by measurement noise.
MIN_HEADROOM = 0.10

BRANCH_RETRAIN = "A RETRAIN"
BRANCH_NO_RETRAIN = "B NO RETRAIN"
BRANCH_CAPTURE_FIX = "C CAPTURE FIX"


@dataclass(frozen=True)
class Inputs:
    s_ood: float | None = None
    delta_genuine_phone: float | None = None
    delta_spoof_phone: float | None = None
    delta_dsp: float | None = None


@dataclass(frozen=True)
class Verdict:
    rule: int | None
    branch: str | None
    reason: str
    skipped: list[str] = field(default_factory=list)

    @property
    def decided(self) -> bool:
        return self.branch is not None


def apply_rules(inputs: Inputs) -> Verdict:
    """The five rules, in order, first match wins.

    A rule whose input was not measured is skipped and recorded as skipped, never
    treated as not firing. "We did not measure it" and "it did not fire" are
    different facts and the second would silently hand the decision to a later rule.
    """
    skipped: list[str] = []

    if inputs.s_ood is None:
        skipped.append("1 (S_ood not measured)")
    elif inputs.s_ood > S_OOD_CEILING:
        return Verdict(
            1,
            BRANCH_NO_RETRAIN,
            f"S_ood {inputs.s_ood:.4f} above {S_OOD_CEILING}: the positive class is "
            "not-ASVspoof, not synthetic",
            skipped,
        )

    if inputs.delta_dsp is None:
        skipped.append("2 (delta_dsp not measured, owned by ML-2)")
    elif inputs.delta_dsp > DELTA_DSP_FLOOR:
        return Verdict(
            2,
            BRANCH_CAPTURE_FIX,
            f"delta_dsp {inputs.delta_dsp:+.4f} above {DELTA_DSP_FLOOR}: device "
            "processing is a major contributor and capture is the cheaper fix",
            skipped,
        )

    genuine, spoof = inputs.delta_genuine_phone, inputs.delta_spoof_phone
    if genuine is None or spoof is None:
        skipped.append("3, 4, 5 (transplant deltas not measured)")
        return Verdict(None, None, "not enough measured to decide", skipped)

    if genuine > GENUINE_MOVED and spoof < SPOOF_STAYED:
        return Verdict(
            3,
            BRANCH_RETRAIN,
            f"delta_genuine {genuine:+.4f} above {GENUINE_MOVED} and delta_spoof "
            f"{spoof:+.4f} below {SPOOF_STAYED}: the channel moves genuine only",
            skipped,
        )
    if genuine > GENUINE_MOVED and spoof > GENUINE_MOVED:
        return Verdict(
            4,
            BRANCH_NO_RETRAIN,
            f"delta_genuine {genuine:+.4f} and delta_spoof {spoof:+.4f} both above "
            f"{GENUINE_MOVED}: the whole distribution moved",
            skipped,
        )
    if genuine < GENUINE_UNMOVED:
        return Verdict(
            5,
            BRANCH_NO_RETRAIN,
            f"delta_genuine {genuine:+.4f} below {GENUINE_UNMOVED}: the transplant "
            "did not reproduce the failure, the cue is something else",
            skipped,
        )

    return Verdict(
        None,
        None,
        f"no rule matches: delta_genuine {genuine:+.4f}, delta_spoof {spoof:+.4f}",
        skipped,
    )


def headroom_traversed(before: float, after: float) -> float | None:
    """Fraction of the distance from `before` to 1.0 that `after` covers.

    1.0 means the clip went all the way to the ceiling. Negative means it moved down.
    `None` when the clip started too close to 1.0 for the ratio to carry meaning.
    """
    headroom = 1.0 - before
    if headroom < MIN_HEADROOM:
        return None
    return (after - before) / headroom


#: A clip is "saturated" when it covered more than this share of its headroom.
SATURATED = 0.5


@dataclass(frozen=True)
class ClassHeadroom:
    """How the clips of one class that had room to move actually moved.

    Deliberately not a bare mean. On one device the two spoof clips with headroom
    covered +1.00 and -0.90 of it, which averages to +0.05 and describes neither.
    The count and the range are what carry the information.
    """

    fractions: list[float]

    @property
    def n(self) -> int:
        return len(self.fractions)

    @property
    def saturated(self) -> int:
        return sum(1 for f in self.fractions if f > SATURATED)

    @property
    def low(self) -> float | None:
        return min(self.fractions) if self.fractions else None

    @property
    def high(self) -> float | None:
        return max(self.fractions) if self.fractions else None

    @property
    def mostly_saturated(self) -> bool:
        """More than half the clips with room went most of the way to 1.0."""
        return self.n > 0 and self.saturated * 2 > self.n

    def describe(self) -> str:
        if not self.fractions:
            return "no clip had headroom"
        return (
            f"{self.saturated}/{self.n} covered more than {SATURATED:.0%} of their "
            f"headroom, range {self.low:+.2f} to {self.high:+.2f}"
        )


@dataclass(frozen=True)
class Saturation:
    """Whether the channel moves everything toward 1.0 regardless of class."""

    #: Correlation between a clip's starting score and how far it moved. Strongly
    #: negative means the move is explained by distance from the ceiling.
    correlation: float
    genuine: ClassHeadroom
    spoof: ClassHeadroom

    @property
    def both_classes_saturate(self) -> bool:
        """True when both classes mostly travel their headroom toward 1.0.

        This is the Rule 4 signature that `delta_spoof` cannot express once the
        spoof class is already near the ceiling.
        """
        return self.genuine.mostly_saturated and self.spoof.mostly_saturated


def saturation(
    observations: list[tuple[float, float, str]],
) -> Saturation | None:
    """`observations` are (before, after, label) with label genuine or spoof."""
    if len(observations) < 3:
        return None

    import numpy as np

    before = np.array([o[0] for o in observations])
    delta = np.array([o[1] - o[0] for o in observations])
    correlation = (
        float(np.corrcoef(before, delta)[0, 1]) if before.std() > 0 else 0.0
    )

    per_class: dict[str, list[float]] = {"genuine": [], "spoof": []}
    for start, end, label in observations:
        fraction = headroom_traversed(start, end)
        if fraction is not None and label in per_class:
            per_class[label].append(fraction)

    return Saturation(
        correlation=correlation,
        genuine=ClassHeadroom(sorted(per_class["genuine"])),
        spoof=ClassHeadroom(sorted(per_class["spoof"])),
    )
