"""The H+4 rules, and the diagnostic that stops them being misread.

This is the code that decides which branch the workstream takes, so the tests are
about the ways it could hand back a confident wrong answer: an unmeasured input
treated as a non-firing rule, a later rule matching because an earlier one was
silently skipped, and the Rule 3 / Rule 4 confusion that a score ceiling creates.
"""

from __future__ import annotations

import pytest

from ml.eval.gate import (
    BRANCH_CAPTURE_FIX,
    BRANCH_NO_RETRAIN,
    BRANCH_RETRAIN,
    ClassHeadroom,
    Inputs,
    apply_rules,
    headroom_traversed,
    saturation,
)


class TestRuleOrder:
    def test_rule_1_wins_over_everything_else(self) -> None:
        # S_ood high and the transplant looking like Rule 3. Rule 1 is first.
        verdict = apply_rules(
            Inputs(s_ood=0.95, delta_genuine_phone=0.5, delta_spoof_phone=0.05)
        )
        assert verdict.rule == 1
        assert verdict.branch == BRANCH_NO_RETRAIN

    def test_rule_2_wins_over_the_transplant_rules(self) -> None:
        verdict = apply_rules(
            Inputs(
                s_ood=0.01,
                delta_dsp=0.6,
                delta_genuine_phone=0.5,
                delta_spoof_phone=0.05,
            )
        )
        assert verdict.rule == 2
        assert verdict.branch == BRANCH_CAPTURE_FIX

    def test_rule_3_when_genuine_moves_and_spoof_does_not(self) -> None:
        verdict = apply_rules(
            Inputs(s_ood=0.01, delta_genuine_phone=0.5, delta_spoof_phone=0.05)
        )
        assert verdict.rule == 3
        assert verdict.branch == BRANCH_RETRAIN

    def test_rule_4_when_both_classes_move(self) -> None:
        verdict = apply_rules(
            Inputs(s_ood=0.01, delta_genuine_phone=0.5, delta_spoof_phone=0.5)
        )
        assert verdict.rule == 4
        assert verdict.branch == BRANCH_NO_RETRAIN

    def test_rule_5_when_the_transplant_reproduces_nothing(self) -> None:
        verdict = apply_rules(
            Inputs(s_ood=0.01, delta_genuine_phone=0.05, delta_spoof_phone=0.02)
        )
        assert verdict.rule == 5
        assert verdict.branch == BRANCH_NO_RETRAIN

    def test_the_gap_between_the_rules_is_undetermined_not_a_default(self) -> None:
        # genuine between 0.15 and 0.40 matches no rule. Falling through to a branch
        # would be inventing a decision the rules do not support.
        verdict = apply_rules(
            Inputs(s_ood=0.01, delta_genuine_phone=0.30, delta_spoof_phone=0.15)
        )
        assert verdict.rule is None
        assert verdict.branch is None
        assert not verdict.decided


class TestUnmeasuredIsNotUnfired:
    def test_a_missing_s_ood_is_skipped_and_recorded(self) -> None:
        verdict = apply_rules(
            Inputs(delta_genuine_phone=0.5, delta_spoof_phone=0.05)
        )
        assert verdict.rule == 3
        assert any("S_ood" in s for s in verdict.skipped)

    def test_a_missing_delta_dsp_is_skipped_and_recorded(self) -> None:
        verdict = apply_rules(
            Inputs(s_ood=0.01, delta_genuine_phone=0.5, delta_spoof_phone=0.05)
        )
        assert any("delta_dsp" in s for s in verdict.skipped)

    def test_missing_transplant_deltas_decide_nothing(self) -> None:
        verdict = apply_rules(Inputs(s_ood=0.01))
        assert verdict.branch is None
        assert any("transplant" in s for s in verdict.skipped)

    def test_a_measured_zero_is_not_the_same_as_missing(self) -> None:
        # 0.0 is a measurement and must reach the rules; None must not.
        assert apply_rules(
            Inputs(s_ood=0.01, delta_genuine_phone=0.0, delta_spoof_phone=0.0)
        ).rule == 5
        assert apply_rules(Inputs(s_ood=0.01)).rule is None


class TestHeadroom:
    def test_a_clip_going_all_the_way_to_one_covers_its_headroom(self) -> None:
        assert headroom_traversed(0.0, 1.0) == pytest.approx(1.0)
        assert headroom_traversed(0.5, 1.0) == pytest.approx(1.0)

    def test_half_the_distance_is_a_half(self) -> None:
        assert headroom_traversed(0.0, 0.5) == pytest.approx(0.5)

    def test_moving_down_is_negative(self) -> None:
        assert headroom_traversed(0.85, 0.71) < 0

    def test_a_clip_with_no_room_returns_none_rather_than_dividing(self) -> None:
        # 0.9995 has 0.0005 of headroom. A ratio there is noise amplified 2000x.
        assert headroom_traversed(0.9995, 0.9996) is None


class TestClassHeadroomIsNotAMean:
    def test_opposite_movements_are_not_averaged_away(self) -> None:
        # The real iPhone spoof pair: +1.00 and -0.90. A mean says +0.05 and
        # describes neither clip.
        both = ClassHeadroom([-0.90, 1.00])
        assert both.saturated == 1
        assert both.n == 2
        assert both.low == pytest.approx(-0.90)
        assert both.high == pytest.approx(1.00)
        assert not both.mostly_saturated

    def test_a_majority_saturating_is_reported_as_such(self) -> None:
        assert ClassHeadroom([0.93, 0.99, 1.00]).mostly_saturated

    def test_an_empty_class_says_so(self) -> None:
        empty = ClassHeadroom([])
        assert empty.n == 0
        assert not empty.mostly_saturated
        assert "no clip had headroom" in empty.describe()

    def test_describe_carries_the_range_not_just_a_count(self) -> None:
        text = ClassHeadroom([-0.90, 1.00]).describe()
        assert "-0.90" in text and "+1.00" in text


class TestSaturationSignature:
    @staticmethod
    def everything_converges() -> list[tuple[float, float, str]]:
        """Both classes travel their headroom to 1.0. The Rule 4 signature."""
        return [
            (0.03, 0.999, "genuine"),
            (0.46, 0.999, "genuine"),
            (0.005, 0.93, "genuine"),
            (0.13, 0.999, "spoof"),
            (0.20, 0.995, "spoof"),
            (0.9995, 0.9996, "spoof"),
        ]

    def test_convergence_shows_as_a_strong_negative_correlation(self) -> None:
        signature = saturation(self.everything_converges())
        assert signature is not None
        assert signature.correlation < -0.9

    def test_both_classes_saturating_is_detected(self) -> None:
        signature = saturation(self.everything_converges())
        assert signature is not None
        assert signature.both_classes_saturate

    def test_a_genuine_only_shift_does_not_look_like_saturation(self) -> None:
        # The real Rule 3 shape: genuine rises, spoof stays where it was.
        signature = saturation(
            [
                (0.03, 0.95, "genuine"),
                (0.05, 0.97, "genuine"),
                (0.20, 0.21, "spoof"),
                (0.30, 0.28, "spoof"),
            ]
        )
        assert signature is not None
        assert not signature.both_classes_saturate

    def test_a_clip_with_no_headroom_is_excluded_from_its_class(self) -> None:
        signature = saturation(self.everything_converges())
        assert signature is not None
        # The 0.9995 spoof has no room and must not be counted either way.
        assert signature.spoof.n == 2

    def test_too_few_observations_return_nothing(self) -> None:
        assert saturation([(0.1, 0.9, "genuine")]) is None


class TestTheRuleFourTrap:
    """A saturated spoof class makes Rule 4 look like Rule 3.

    This is the failure the diagnostic exists for, reproduced with the real numbers.
    """

    def test_the_rules_alone_call_the_iphone_result_rule_3(self) -> None:
        verdict = apply_rules(
            Inputs(s_ood=0.0009, delta_genuine_phone=0.4928, delta_spoof_phone=0.1239)
        )
        assert verdict.rule == 3
        assert verdict.branch == BRANCH_RETRAIN

    def test_but_a_spoof_at_0_85_cannot_produce_a_rule_4_delta(self) -> None:
        # Rule 4 needs delta_spoof > 0.40. Four of the five deepfakes start at 0.85
        # or above, so their largest possible delta is 0.15.
        for start in (0.85, 0.9995, 0.9995, 0.9995):
            assert 1.0 - start < 0.40

    def test_the_spoof_clip_with_room_saturated_like_the_genuine_ones(self) -> None:
        # sadhguru_deepfake, 0.1279 to 0.9994 on both devices. A channel that only
        # moved genuine audio could not do this.
        assert headroom_traversed(0.1279, 0.9994) > 0.99
