"""Tests for the speaker-embedding probe.

No model is loaded here. These cover the two pieces that decide what the numbers
mean, both of which fail silently rather than raising:

  * `active_segments`, where a badly aligned window grid made one recording yield 2
    segments against 12 for comparable files, so its pooled embedding was far
    noisier than the ones it was compared against, and
  * `classify_pair`, where putting a pair in the wrong column changes the
    conclusion without producing any error.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ml.tools.speaker_probe import (
    CLONE_VS_TARGET,
    DIFFERENT_SPEAKER,
    SAME_SPEAKER,
    Recording,
    active_segments,
    classify_pair,
)

SAMPLE_RATE = 16000


def speech(seconds: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * seconds)
    t = np.arange(n) / SAMPLE_RATE
    tone = 0.4 * np.sin(2 * np.pi * 140 * t) + 0.15 * np.sin(2 * np.pi * 420 * t)
    return (tone + 0.01 * rng.normal(0, 1, n)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32)


class TestActiveSegments:
    def test_continuous_speech_yields_segments(self) -> None:
        assert len(active_segments(speech(12.0))) > 0

    def test_segments_have_the_requested_length(self) -> None:
        for segment in active_segments(speech(12.0), segment_s=4.0):
            assert segment.shape == (int(4.0 * SAMPLE_RATE),)

    def test_pure_silence_yields_nothing(self) -> None:
        assert active_segments(silence(12.0)) == []

    def test_empty_input_yields_nothing(self) -> None:
        assert active_segments(np.array([], dtype=np.float32)) == []

    def test_shorter_than_one_segment_yields_nothing(self) -> None:
        assert active_segments(speech(1.0), segment_s=4.0) == []

    def test_speech_split_by_pauses_still_yields_segments(self) -> None:
        """The regression that motivated the overlapping hop.

        A recording made with gaps between takes has most non-overlapping windows
        straddling a gap. Here every speech run is 5 s, longer than the 4 s segment,
        so well-aligned windows exist and the grid must be able to find them.
        """
        blocks = []
        for take in range(4):
            blocks.append(speech(5.0, seed=take))
            blocks.append(silence(3.0))
        assert len(active_segments(np.concatenate(blocks), segment_s=4.0)) >= 4

    def test_overlapping_hop_finds_more_than_a_non_overlapping_grid_would(self) -> None:
        """Guards the premise: the hop is doing something, not just costing time."""
        signal = np.concatenate([speech(5.0), silence(3.0), speech(5.0), silence(3.0)])
        found = len(active_segments(signal, segment_s=4.0))
        non_overlapping = signal.size // int(4.0 * SAMPLE_RATE)
        assert found > non_overlapping // 2

    def test_a_loud_burst_does_not_gate_out_the_speech(self) -> None:
        """The gate is relative to the 95th percentile, so one click must not
        raise the threshold above ordinary speech and silence the whole file."""
        signal = speech(12.0).copy()
        signal[1000:1100] = 1.0
        assert len(active_segments(signal)) > 0


class TestClassifyPair:
    def _rec(self, label: str, speaker: str, synthetic: bool = False) -> Recording:
        return Recording(label, Path(f"{label}.wav"), speaker, synthetic=synthetic)

    def test_same_speaker_two_sessions(self) -> None:
        a = self._rec("s1", "speaker_a")
        b = self._rec("s2", "speaker_a")
        assert classify_pair(a, b) == SAME_SPEAKER

    def test_two_different_people(self) -> None:
        a = self._rec("s1", "speaker_a")
        b = self._rec("s2", "speaker_b")
        assert classify_pair(a, b) == DIFFERENT_SPEAKER

    def test_clone_against_its_own_target(self) -> None:
        a = self._rec("s1", "speaker_a")
        b = self._rec("clone", "speaker_a", synthetic=True)
        assert classify_pair(a, b) == CLONE_VS_TARGET

    def test_clone_against_someone_else_is_an_impostor_pair(self) -> None:
        """Counting this as the case under test would dilute the clone group with
        easy pairs and flatter the result."""
        a = self._rec("s2", "speaker_b")
        b = self._rec("clone", "speaker_a", synthetic=True)
        assert classify_pair(a, b) == DIFFERENT_SPEAKER

    def test_argument_order_does_not_matter(self) -> None:
        a = self._rec("s1", "speaker_a")
        b = self._rec("clone", "speaker_a", synthetic=True)
        assert classify_pair(a, b) == classify_pair(b, a)

    def test_the_three_groups_are_distinct(self) -> None:
        assert len({SAME_SPEAKER, DIFFERENT_SPEAKER, CLONE_VS_TARGET}) == 3
