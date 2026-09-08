"""Locating a known clip inside a longer recording of it.

The replay takes are continuous, so every path B score depends on this cutting the
right seconds out. A mis-cut puts the wrong audio under the right filename and
nothing downstream can tell: the transplant would report a delta for a clip pair
that was never a pair. So the tests here are mostly about the ways a match can be
wrong while looking fine.

The recordings are synthesised, so no fixture audio and no checkpoint are needed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ml.eval.align import (
    HOP,
    SAMPLE_RATE,
    Match,
    envelope,
    find_clip,
    normalized_cross_correlation,
    overlaps,
)
from ml.tools import split_replay


def burst_clip(seconds: float, seed: int) -> np.ndarray:
    """Noise with a distinctive amplitude envelope, which is what alignment reads."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    noise = rng.normal(0.0, 0.2, n)
    # A slow random envelope, so different seeds have genuinely different shapes.
    frames = n // HOP + 1
    coarse = rng.random(frames) ** 2
    shape = np.repeat(coarse, HOP)[:n]
    return (noise * shape).astype(np.float32)


def place(clips: list[tuple[np.ndarray, float]], total_s: float) -> np.ndarray:
    """Lay clips into a silent take at given start times, with a little noise."""
    rng = np.random.default_rng(99)
    take = rng.normal(0.0, 0.002, int(total_s * SAMPLE_RATE)).astype(np.float32)
    for clip, start in clips:
        at = int(start * SAMPLE_RATE)
        take[at : at + clip.size] += clip
    return take


class TestEnvelope:
    def test_one_value_per_frame(self) -> None:
        assert envelope(np.zeros(HOP * 7, dtype=np.float32)).size == 7

    def test_a_partial_trailing_frame_is_dropped(self) -> None:
        assert envelope(np.zeros(HOP * 7 + 5, dtype=np.float32)).size == 7

    def test_empty_input_gives_an_empty_envelope(self) -> None:
        assert envelope(np.zeros(0, dtype=np.float32)).size == 0

    def test_silence_is_finite_not_negative_infinity(self) -> None:
        # A log of exact zero would poison every correlation it touched.
        assert np.isfinite(envelope(np.zeros(HOP * 10, dtype=np.float32))).all()

    def test_a_gain_becomes_a_constant_offset_above_the_floor(self) -> None:
        """Why alignment survives a level change: NCC removes the mean.

        Only holds above the energy floor, which exists to keep silence finite. Near
        it the mapping compresses, so quiet frames are excluded here rather than the
        floor being removed. That compression is harmless: it affects silence, and
        silence carries no alignment information.
        """
        x = burst_clip(1.0, seed=1)
        quiet, loud = envelope(x), envelope(x * 4.0)
        # The floor sits inside the sqrt, so frame RMS bottoms out at 1e-3. Frames
        # two orders of magnitude above that are unaffected by it.
        above_floor = quiet > np.log(1e-1)
        assert above_floor.sum() > 20, "the fixture must have loud frames to test"
        difference = (loud - quiet)[above_floor]
        assert np.allclose(difference, np.log(4.0), atol=1e-3)


class TestCorrelation:
    def test_a_clip_against_itself_peaks_at_one(self) -> None:
        x = envelope(burst_clip(2.0, seed=2))
        correlation = normalized_cross_correlation(x, x)
        assert correlation.size == 1
        assert correlation[0] == pytest.approx(1.0, abs=1e-6)

    def test_the_peak_lands_at_the_true_offset(self) -> None:
        clip = burst_clip(2.0, seed=3)
        take = place([(clip, 5.0)], 12.0)
        correlation = normalized_cross_correlation(envelope(take), envelope(clip))
        peak_s = int(np.argmax(correlation)) * HOP / SAMPLE_RATE
        assert peak_s == pytest.approx(5.0, abs=0.02)

    def test_values_stay_inside_minus_one_and_one(self) -> None:
        clip = burst_clip(1.5, seed=4)
        correlation = normalized_cross_correlation(envelope(place([(clip, 2.0)], 9.0)), envelope(clip))
        assert correlation.min() >= -1.0001
        assert correlation.max() <= 1.0001

    def test_a_shorter_recording_than_the_clip_gives_nothing(self) -> None:
        long, short = envelope(burst_clip(1.0, 5)), envelope(burst_clip(3.0, 5))
        assert normalized_cross_correlation(long, short).size == 0

    def test_a_constant_stretch_scores_zero_rather_than_dividing(self) -> None:
        clip = burst_clip(1.0, seed=6)
        flat = np.zeros(int(6.0 * SAMPLE_RATE), dtype=np.float32)
        correlation = normalized_cross_correlation(envelope(flat), envelope(clip))
        assert np.isfinite(correlation).all()


class TestFindClip:
    def test_it_finds_a_clip_played_into_a_take(self) -> None:
        clip = burst_clip(3.0, seed=7)
        match = find_clip(place([(clip, 8.0)], 20.0), clip)
        assert match is not None
        assert match.start_s == pytest.approx(8.0, abs=0.02)
        assert match.score > 0.9

    def test_it_survives_a_level_change(self) -> None:
        # The replay is quieter or louder than the original; that must not matter.
        clip = burst_clip(3.0, seed=8)
        match = find_clip(place([(clip * 0.15, 6.0)], 20.0), clip)
        assert match is not None
        assert match.start_s == pytest.approx(6.0, abs=0.05)

    def test_it_survives_added_noise(self) -> None:
        clip = burst_clip(3.0, seed=9)
        take = place([(clip, 4.0)], 15.0)
        take = take + np.random.default_rng(0).normal(0, 0.01, take.size).astype(np.float32)
        match = find_clip(take, clip)
        assert match is not None
        assert match.start_s == pytest.approx(4.0, abs=0.05)

    def test_playback_order_is_not_assumed(self) -> None:
        first, second = burst_clip(2.0, seed=10), burst_clip(2.0, seed=11)
        # `second` is played before `first`.
        take = place([(second, 2.0), (first, 9.0)], 16.0)
        match_first = find_clip(take, first)
        match_second = find_clip(take, second)
        assert match_first is not None and match_second is not None
        assert match_first.start_s > match_second.start_s

    def test_the_runner_up_ignores_the_peak_s_own_neighbourhood(self) -> None:
        # Offsets either side of the true match correlate almost as well. Counting
        # one of those as a rival would make every match look ambiguous.
        clip = burst_clip(3.0, seed=12)
        match = find_clip(place([(clip, 5.0)], 20.0), clip)
        assert match is not None
        assert match.margin > 0.2

    def test_a_take_shorter_than_the_clip_returns_none(self) -> None:
        assert find_clip(burst_clip(1.0, 13), burst_clip(4.0, 13)) is None

    def test_an_absent_clip_scores_low(self) -> None:
        present, absent = burst_clip(3.0, seed=14), burst_clip(3.0, seed=15)
        match = find_clip(place([(present, 5.0)], 20.0), absent)
        assert match is not None
        assert match.score < split_replay.MIN_SCORE


class TestMatchFields:
    def test_start_seconds_follows_the_offset(self) -> None:
        assert Match(offset=SAMPLE_RATE * 3, score=0.9, runner_up=0.2).start_s == 3.0

    def test_margin_is_the_lead_over_the_runner_up(self) -> None:
        assert Match(offset=0, score=0.9, runner_up=0.25).margin == pytest.approx(0.65)


class TestOverlaps:
    def test_touching_spans_do_not_overlap(self) -> None:
        assert not overlaps((0, 100), (100, 200))

    def test_one_sample_of_shared_audio_overlaps(self) -> None:
        assert overlaps((0, 101), (100, 200))

    def test_a_span_inside_another_overlaps(self) -> None:
        assert overlaps((0, 500), (100, 200))
        assert overlaps((100, 200), (0, 500))


class TestSplitWiring:
    def test_ten_clips_are_expected(self) -> None:
        names = split_replay.clip_names()
        assert len(names) == 10
        assert names.count("pc_bonafide") == 1
        assert all(n.endswith(("_bonafide", "_deepfake")) for n in names)

    def test_clipping_is_detected(self) -> None:
        clean = burst_clip(1.0, seed=16)
        assert split_replay.clipping_fraction(clean) == 0.0
        saturated = np.ones(1000, dtype=np.float32)
        assert split_replay.clipping_fraction(saturated) == 1.0

    def test_the_clipping_threshold_catches_a_rare_but_real_amount(self) -> None:
        # 0.001% of a 98 s take is roughly 15 samples. Clipping adds harmonics, so
        # even a small amount is a difference between devices worth stating.
        x = np.zeros(1_000_000, dtype=np.float32)
        x[:200] = 1.0
        assert split_replay.clipping_fraction(x) > split_replay.CLIP_FRACTION

    def test_written_clips_are_canonical(self, tmp_path: Path) -> None:
        import wave

        out = split_replay.write_wav(tmp_path / "x.wav", burst_clip(1.0, seed=17))
        with wave.open(str(out), "rb") as handle:
            assert handle.getframerate() == SAMPLE_RATE
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
