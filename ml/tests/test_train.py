"""Tests for the fine-tuning pipeline.

The EER tests use synthetic score arrays with answers that can be worked out by
hand, because an EER function that is quietly wrong produces plausible numbers
rather than an error, and every claim in the report would then rest on it.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.augment.noise import active_speech_rms
from ml.train.dataset import (
    BONAFIDE,
    SPOOF,
    PhoneChannelAugmenter,
    fixed_length,
)
from ml.train.finetune_aasist import compute_eer


class TestComputeEer:
    def test_perfect_separation_is_zero(self) -> None:
        scores = np.array([0.1, 0.2, 0.3, 0.8, 0.9, 1.0])
        labels = np.array([SPOOF, SPOOF, SPOOF, BONAFIDE, BONAFIDE, BONAFIDE])
        eer, _ = compute_eer(scores, labels)
        assert eer == pytest.approx(0.0, abs=1e-9)

    def test_perfectly_inverted_is_one(self) -> None:
        """A detector that is exactly backwards should score 1.0, not 0.0."""
        scores = np.array([0.1, 0.2, 0.3, 0.8, 0.9, 1.0])
        labels = np.array([BONAFIDE, BONAFIDE, BONAFIDE, SPOOF, SPOOF, SPOOF])
        eer, _ = compute_eer(scores, labels)
        assert eer > 0.9

    def test_identical_distributions_are_about_half(self) -> None:
        rng = np.random.default_rng(0)
        scores = rng.normal(0.0, 1.0, 4000)
        labels = np.array([BONAFIDE, SPOOF] * 2000)
        eer, _ = compute_eer(scores, labels)
        assert eer == pytest.approx(0.5, abs=0.05)

    def test_partial_overlap_lands_between(self) -> None:
        rng = np.random.default_rng(1)
        bonafide = rng.normal(1.0, 1.0, 2000)
        spoof = rng.normal(-1.0, 1.0, 2000)
        scores = np.concatenate([bonafide, spoof])
        labels = np.concatenate([np.full(2000, BONAFIDE), np.full(2000, SPOOF)])
        eer, _ = compute_eer(scores, labels)
        assert 0.10 < eer < 0.25

    def test_single_class_returns_nan_rather_than_a_wrong_number(self) -> None:
        scores = np.array([0.1, 0.2, 0.3])
        labels = np.array([BONAFIDE, BONAFIDE, BONAFIDE])
        eer, _ = compute_eer(scores, labels)
        assert np.isnan(eer)


class TestFixedLength:
    def test_long_input_is_cropped_to_target(self) -> None:
        import random

        out = fixed_length(np.arange(1000, dtype=np.float32), 400, random.Random(0))
        assert out.shape == (400,)

    def test_short_input_is_tiled_not_zero_padded(self) -> None:
        import random

        out = fixed_length(np.array([0.5, -0.5], dtype=np.float32), 6, random.Random(0))
        assert out.shape == (6,)
        assert not np.any(out == 0.0)

    def test_empty_input_returns_silence_of_target_length(self) -> None:
        import random

        out = fixed_length(np.array([], dtype=np.float32), 100, random.Random(0))
        assert out.shape == (100,)

    def test_crop_position_varies_with_the_rng(self) -> None:
        import random

        source = np.arange(10000, dtype=np.float32)
        starts = {float(fixed_length(source, 100, random.Random(s))[0]) for s in range(8)}
        assert len(starts) > 1


class TestPhoneChannelAugmenter:
    def test_output_is_finite_and_in_range(self) -> None:
        rng = np.random.default_rng(0)
        x = rng.normal(0, 0.2, 16000).astype(np.float32)
        augmenter = PhoneChannelAugmenter(seed=0)
        for _ in range(10):
            out = augmenter(x)
            assert np.all(np.isfinite(out))
            assert np.abs(out).max() <= 1.0
            assert out.dtype == np.float32

    def test_same_seed_gives_the_same_sequence(self) -> None:
        rng = np.random.default_rng(0)
        x = rng.normal(0, 0.2, 16000).astype(np.float32)
        first = [PhoneChannelAugmenter(seed=7)(x) for _ in range(3)]
        second = [PhoneChannelAugmenter(seed=7)(x) for _ in range(3)]
        for a, b in zip(first, second, strict=True):
            assert np.allclose(a, b)

    def test_level_actually_varies_across_draws(self) -> None:
        """The whole reason this pipeline exists. If level stops varying, the
        model goes back to reading loudness as evidence of synthesis."""
        rng = np.random.default_rng(0)
        x = rng.normal(0, 0.2, 16000).astype(np.float32)
        augmenter = PhoneChannelAugmenter(seed=0)
        levels = [active_speech_rms(augmenter(x)) for _ in range(15)]
        assert max(levels) / min(levels) > 2.0

    def test_disabling_everything_is_a_passthrough(self) -> None:
        rng = np.random.default_rng(0)
        x = rng.normal(0, 0.2, 16000).astype(np.float32)
        augmenter = PhoneChannelAugmenter(
            seed=0,
            gain_probability=0.0,
            compress_probability=0.0,
            reverb_probability=0.0,
            codec_probability=0.0,
            noise_probability=0.0,
        )
        assert np.allclose(augmenter(x), x)

    def test_input_is_not_mutated(self) -> None:
        rng = np.random.default_rng(0)
        x = rng.normal(0, 0.2, 16000).astype(np.float32)
        before = x.copy()
        PhoneChannelAugmenter(seed=0)(x)
        assert np.array_equal(x, before)


class TestDeterministicAugmentation:
    """The evaluation metric must not depend on how many DataLoader workers ran.

    Each worker gets a *copy* of the augmenter, so per-instance RNG state made the
    channel applied to a given utterance a function of call order. The same
    checkpoint on the same dev subsample measured 16.29% at 4 workers and 17.50% at
    6. `for_index` makes it a function of the item instead.
    """

    def _signal(self) -> np.ndarray:
        rng = np.random.default_rng(0)
        return rng.normal(0, 0.2, 16000).astype(np.float32)

    def test_for_index_is_independent_of_call_order(self) -> None:
        x = self._signal()
        forward = [PhoneChannelAugmenter(seed=1).for_index(i)(x) for i in range(5)]
        backward = [
            PhoneChannelAugmenter(seed=1).for_index(i)(x) for i in reversed(range(5))
        ][::-1]
        for a, b in zip(forward, backward, strict=True):
            assert np.allclose(a, b)

    def test_for_index_survives_a_shared_parent_being_used(self) -> None:
        """A worker copy that has already augmented other items must still agree."""
        x = self._signal()
        clean = PhoneChannelAugmenter(seed=1)
        expected = clean.for_index(3)(x)

        used = PhoneChannelAugmenter(seed=1)
        for _ in range(7):
            used(x)  # advance the parent's own RNG, as a worker would
        assert np.allclose(used.for_index(3)(x), expected)

    def test_different_items_still_get_different_channels(self) -> None:
        """Determinism must not collapse into applying one fixed channel."""
        x = self._signal()
        parent = PhoneChannelAugmenter(seed=1)
        levels = {round(float(np.abs(parent.for_index(i)(x)).max()), 6) for i in range(12)}
        assert len(levels) > 1

    def test_stateful_call_really_is_order_dependent(self) -> None:
        """Guards the premise: without for_index the problem is real, not imagined."""
        x = self._signal()
        first = PhoneChannelAugmenter(seed=1)
        a = [first(x) for _ in range(3)]

        offset = PhoneChannelAugmenter(seed=1)
        offset(x)
        b = [offset(x) for _ in range(3)]
        assert not all(np.allclose(p, q) for p, q in zip(a, b, strict=True))

    def test_seed_still_changes_the_channel(self) -> None:
        x = self._signal()
        a = PhoneChannelAugmenter(seed=1).for_index(0)(x)
        b = PhoneChannelAugmenter(seed=2).for_index(0)(x)
        assert not np.allclose(a, b)
