"""Tests for room-acoustics augmentation.

This module exists because of a measurement: reverb alone moved known-bonafide
ASVspoof audio from P(synthetic) 0.005 to 0.651 under a checkpoint scoring 2.12% EER
on that same eval split, while spectral tilt moved it to 0.018. The model had learned
"no room implies genuine", which inverted it on real recordings.

So these tests check the property that matters, that a room is actually imposed and
that its amount is controllable, rather than only that arrays come back the right
shape.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.augment.room import (
    DEFAULT_RT60_RANGE,
    apply_reverb,
    synthetic_rir,
)

SAMPLE_RATE = 16000


def click(n: int = 16000, at: int = 2000) -> np.ndarray:
    """An impulse. Its response is literally the room, so decay is measurable."""
    x = np.zeros(n, dtype=np.float32)
    x[at] = 1.0
    return x


def speech_like(seconds: float = 1.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * seconds)
    t = np.arange(n) / SAMPLE_RATE
    tone = 0.5 * np.sin(2 * np.pi * 150 * t) + 0.2 * np.sin(2 * np.pi * 450 * t)
    return np.clip(tone + 0.02 * rng.normal(0, 1, n), -1, 1).astype(np.float32)


def tail_energy(x: np.ndarray, after: int) -> float:
    """Energy arriving after a given sample. Reflections live here."""
    return float((np.asarray(x, dtype=np.float64)[after:] ** 2).sum())


class TestSyntheticRir:
    def test_decays(self) -> None:
        rir = synthetic_rir(0.4, np.random.default_rng(0), SAMPLE_RATE)
        head = tail_energy(rir, 0) - tail_energy(rir, len(rir) // 2)
        tail = tail_energy(rir, len(rir) // 2)
        assert head > tail

    def test_longer_rt60_makes_a_longer_response(self) -> None:
        short = synthetic_rir(0.2, np.random.default_rng(0), SAMPLE_RATE)
        long = synthetic_rir(0.7, np.random.default_rng(0), SAMPLE_RATE)
        assert long.size > short.size

    def test_direct_path_is_the_loudest_point(self) -> None:
        """Reflections must never exceed the direct sound, or it is not a room."""
        rir = synthetic_rir(0.5, np.random.default_rng(1), SAMPLE_RATE)
        direct = int(SAMPLE_RATE * 0.002)
        assert np.argmax(np.abs(rir)) == direct

    def test_is_normalised_and_finite(self) -> None:
        rir = synthetic_rir(0.6, np.random.default_rng(2), SAMPLE_RATE)
        assert np.all(np.isfinite(rir))
        assert np.abs(rir).max() == pytest.approx(1.0, abs=1e-6)


class TestApplyReverb:
    def test_length_and_dtype_preserved(self) -> None:
        x = speech_like()
        out = apply_reverb(x, np.random.default_rng(0))
        assert out.shape == x.shape
        assert out.dtype == np.float32

    def test_a_room_is_actually_imposed(self) -> None:
        """The point of the module: energy must arrive after the direct sound."""
        x = click()
        dry = tail_energy(x, 2000 + 200)
        wet = tail_energy(apply_reverb(x, np.random.default_rng(0), rt60=0.5, wet=0.8), 2200)
        assert wet > dry * 100

    def test_more_reverb_time_means_more_late_energy(self) -> None:
        x = click()
        small = tail_energy(apply_reverb(x, np.random.default_rng(0), rt60=0.15, wet=0.8), 4000)
        big = tail_energy(apply_reverb(x, np.random.default_rng(0), rt60=0.7, wet=0.8), 4000)
        assert big > small

    def test_wet_zero_is_close_to_dry(self) -> None:
        x = speech_like()
        out = apply_reverb(x, np.random.default_rng(0), rt60=0.4, wet=0.0)
        assert np.allclose(out, x, atol=1e-5)

    def test_does_not_clip(self) -> None:
        x = speech_like() * 0.95
        for rt60 in (0.15, 0.4, 0.7):
            out = apply_reverb(x, np.random.default_rng(0), rt60=rt60, wet=0.9)
            assert np.abs(out).max() <= 1.0

    def test_loudness_is_roughly_preserved(self) -> None:
        """Reverb must not double as a gain change, or it confounds the level cue
        that random_gain already exists to neutralise."""
        x = speech_like()
        dry = float(np.sqrt(np.mean(x**2)))
        for wet in (0.2, 0.5, 0.8):
            out = apply_reverb(x, np.random.default_rng(0), rt60=0.4, wet=wet)
            assert float(np.sqrt(np.mean(out**2))) == pytest.approx(dry, rel=0.5)

    def test_randomised_calls_vary(self) -> None:
        x = speech_like()
        rng = np.random.default_rng(0)
        outs = [apply_reverb(x, rng) for _ in range(6)]
        assert len({round(float(np.abs(o).max()), 6) for o in outs}) > 1

    def test_rt60_stays_in_the_documented_range(self) -> None:
        low, high = DEFAULT_RT60_RANGE
        assert 0.0 < low < high < 2.0

    def test_empty_input_is_handled(self) -> None:
        assert apply_reverb(np.array([], dtype=np.float32), np.random.default_rng(0)).size == 0

    def test_input_is_not_mutated(self) -> None:
        x = speech_like()
        before = x.copy()
        apply_reverb(x, np.random.default_rng(0))
        assert np.array_equal(x, before)

    def test_output_is_finite(self) -> None:
        x = speech_like()
        for _ in range(10):
            assert np.all(np.isfinite(apply_reverb(x, np.random.default_rng(3))))
