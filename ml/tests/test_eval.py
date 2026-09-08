"""Tests for the detection metrics.

A metric that is quietly wrong returns a plausible number rather than an error, and
every claim in the report would then rest on it. So these use cases whose answers can
be worked out by hand.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.eval.cost import (
    BALANCED,
    BANK,
    PRESETS,
    CostModel,
    detection_cost,
    min_detection_cost,
    summarise,
)
from ml.eval.eer import compute_eer, det_curve, false_accept_at_false_reject

BONAFIDE, SPOOF = 1, 0


def separated(n: int = 500, gap: float = 6.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    scores = np.concatenate([rng.normal(gap, 1.0, n), rng.normal(0.0, 1.0, n)])
    labels = np.concatenate([np.full(n, BONAFIDE), np.full(n, SPOOF)])
    return scores, labels


class TestEer:
    def test_perfect_separation_is_zero(self) -> None:
        scores = np.array([0.0, 0.1, 0.2, 5.0, 5.1, 5.2])
        labels = np.array([SPOOF, SPOOF, SPOOF, BONAFIDE, BONAFIDE, BONAFIDE])
        eer, _ = compute_eer(scores, labels)
        assert eer == pytest.approx(0.0, abs=1e-9)

    def test_inverted_detector_is_near_one(self) -> None:
        scores = np.array([0.0, 0.1, 0.2, 5.0, 5.1, 5.2])
        labels = np.array([BONAFIDE, BONAFIDE, BONAFIDE, SPOOF, SPOOF, SPOOF])
        eer, _ = compute_eer(scores, labels)
        assert eer > 0.9

    def test_random_scores_are_about_half(self) -> None:
        rng = np.random.default_rng(0)
        scores = rng.normal(0.0, 1.0, 6000)
        labels = np.array([BONAFIDE, SPOOF] * 3000)
        eer, _ = compute_eer(scores, labels)
        assert eer == pytest.approx(0.5, abs=0.04)

    def test_single_class_is_nan_not_a_number(self) -> None:
        eer, threshold = compute_eer(np.array([1.0, 2.0]), np.array([BONAFIDE, BONAFIDE]))
        assert np.isnan(eer) and np.isnan(threshold)

    def test_mismatched_shapes_raise(self) -> None:
        with pytest.raises(ValueError):
            det_curve(np.array([1.0, 2.0]), np.array([BONAFIDE]))

    def test_curve_rates_are_monotone_and_bounded(self) -> None:
        false_rejects, false_accepts, _ = det_curve(*separated())
        assert np.all(np.diff(false_rejects) >= -1e-12)
        assert np.all(np.diff(false_accepts) <= 1e-12)
        assert false_rejects.min() >= 0.0 and false_rejects.max() <= 1.0
        assert false_accepts.min() >= 0.0 and false_accepts.max() <= 1.0

    def test_false_accept_at_a_chosen_false_reject(self) -> None:
        """The number a bank actually asks for."""
        scores, labels = separated(gap=4.0)
        loose, _ = false_accept_at_false_reject(scores, labels, 0.10)
        strict, _ = false_accept_at_false_reject(scores, labels, 0.01)
        # Tolerating fewer false alarms must let more spoofs through.
        assert strict >= loose


class TestDetectionCost:
    def test_perfect_system_costs_zero(self) -> None:
        assert detection_cost(0.0, 0.0, BALANCED) == pytest.approx(0.0)

    def test_trivial_systems_cost_about_one(self) -> None:
        """Normalisation means a useless detector scores 1.0, which is the point."""
        for model in PRESETS.values():
            reject_everything = detection_cost(0.0, 1.0, model)
            accept_everything = detection_cost(1.0, 0.0, model)
            assert min(reject_everything, accept_everything) == pytest.approx(1.0, abs=1e-9)

    def test_asymmetric_costs_penalise_the_expensive_error(self) -> None:
        expensive_miss = CostModel("m", cost_miss=100.0, cost_false_alarm=1.0, prior_attack=0.5)
        missing = detection_cost(0.2, 0.0, expensive_miss)
        false_alarming = detection_cost(0.0, 0.2, expensive_miss)
        assert missing > false_alarming

    def test_min_dcf_beats_or_matches_any_single_point(self) -> None:
        scores, labels = separated(gap=3.0)
        best, _ = min_detection_cost(scores, labels, BANK)
        false_rejects, false_accepts, _ = det_curve(scores, labels)
        every = detection_cost(false_accepts, false_rejects, BANK)
        assert best == pytest.approx(float(np.min(every)), abs=1e-9)

    def test_better_separation_gives_lower_cost(self) -> None:
        easy_scores, easy_labels = separated(gap=8.0)
        hard_scores, hard_labels = separated(gap=1.0)
        easy, _ = min_detection_cost(easy_scores, easy_labels, BALANCED)
        hard, _ = min_detection_cost(hard_scores, hard_labels, BALANCED)
        assert easy < hard

    def test_degenerate_model_raises(self) -> None:
        with pytest.raises(ValueError):
            detection_cost(0.1, 0.1, CostModel("bad", prior_attack=0.0, cost_miss=0.0))

    def test_single_class_is_nan(self) -> None:
        value, threshold = min_detection_cost(
            np.array([1.0, 2.0]), np.array([SPOOF, SPOOF]), BALANCED
        )
        assert np.isnan(value) and np.isnan(threshold)


class TestSummarise:
    def test_reports_eer_and_every_cost_model_together(self) -> None:
        """AGENTS.md: never an EER without its cost-weighted companion."""
        text = summarise(*separated(gap=3.0))
        assert "EER" in text
        for name in PRESETS:
            assert name in text
        assert "min-DCF" in text
        assert "bonafide" in text and "spoof" in text
