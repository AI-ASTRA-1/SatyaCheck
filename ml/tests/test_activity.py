"""Window selection returns a status, and never a NaN score.

The failure this file exists to stop: `sadhguru_deepfake` is a 6.03 s IFD clip, which
holds exactly one window on the non-overlapping 4.0375 s grid. That window straddles
a pause, so it was dropped and the file scored `nan`. A `nan` in a five-sample table
does not read as "no measurement", it reads as a broken tool, and the row gets
quietly excluded rather than counted. See `ml/README.md`, the IFD section.

The clip itself is not committed (`.gitignore` excludes audio), so the regression is
reproduced synthetically at the same duration and the same window arithmetic.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from ml.eval.activity import (
    ACTIVITY_FLOOR,
    STATUS_NO_SPEECH,
    STATUS_OK,
    STATUS_SHORT,
    STATUS_SPARSE,
    VAD_FAIL,
    VAD_PASS,
    select_windows,
    speech_seconds,
)

SAMPLE_RATE = 16000

#: 4.0375 s at 16 kHz, the window the published model takes. Same constant as
#: `ml.tools.sweep.WINDOW_SAMPLES`, repeated rather than imported so this file does
#: not need a scorer or a checkpoint to run.
WINDOW = 64600


def speech(seconds: float, seed: int = 0) -> np.ndarray:
    """Loud broadband audio. Not speech, but above the gate the same way."""
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 0.2, int(seconds * SAMPLE_RATE)).astype(np.float32)


def quiet(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


class TestStatuses:
    def test_full_speech_is_ok_and_passes(self) -> None:
        selection = select_windows(speech(12.0), WINDOW)
        assert selection.status == STATUS_OK
        assert selection.vad_status == VAD_PASS
        assert len(selection.windows) == 2
        assert str(ACTIVITY_FLOOR) in selection.reason

    def test_shorter_than_one_window_is_tiled_and_labelled(self) -> None:
        selection = select_windows(speech(2.0), WINDOW)
        assert selection.status == STATUS_SHORT
        assert selection.vad_status == VAD_PASS
        assert selection.windows[0].size == WINDOW
        assert "tiled" in selection.reason

    def test_silence_fails_with_a_reason(self) -> None:
        selection = select_windows(quiet(8.0), WINDOW)
        assert selection.status == STATUS_NO_SPEECH
        assert selection.vad_status == VAD_FAIL
        assert selection.windows == []
        assert selection.reason

    def test_empty_input_fails_rather_than_raising(self) -> None:
        selection = select_windows(np.zeros(0, dtype=np.float32), WINDOW)
        assert selection.vad_status == VAD_FAIL
        assert selection.reason


class TestSadhguruRegression:
    """The 6 s clip that returned nan: one window on the grid, straddling a pause."""

    @staticmethod
    def straddling_clip() -> np.ndarray:
        # 6.03 s, speech at both ends, a pause centred on the only grid window.
        return np.concatenate(
            [speech(1.2, seed=1), quiet(3.6), speech(1.23, seed=2)]
        )

    def test_the_single_grid_window_is_below_the_floor(self) -> None:
        x = self.straddling_clip()
        assert x.size // WINDOW == 1, "the regression needs exactly one grid window"
        selection = select_windows(x, WINDOW)
        assert selection.status != STATUS_OK

    def test_a_score_is_recoverable_and_labelled_sparse(self) -> None:
        selection = select_windows(self.straddling_clip(), WINDOW)
        assert selection.status == STATUS_SPARSE
        assert selection.vad_status == VAD_PASS
        assert selection.windows
        assert selection.reason

    def test_speech_seconds_is_reported_either_way(self) -> None:
        selection = select_windows(self.straddling_clip(), WINDOW)
        assert selection.speech_seconds == pytest.approx(
            speech_seconds(self.straddling_clip())
        )
        assert selection.speech_seconds > 2.0


class TestNoNaN:
    """No input produces a NaN. A missing score is None with a FAIL status."""

    @pytest.mark.parametrize(
        "x",
        [
            quiet(8.0),
            speech(12.0),
            speech(2.0),
            np.zeros(0, dtype=np.float32),
            np.concatenate([speech(1.2, seed=1), quiet(3.6), speech(1.23, seed=2)]),
            np.full(WINDOW * 2, 1e-9, dtype=np.float32),
        ],
    )
    def test_speech_seconds_is_finite(self, x: np.ndarray) -> None:
        assert math.isfinite(speech_seconds(x))

    @pytest.mark.parametrize(
        "x",
        [
            quiet(8.0),
            speech(12.0),
            np.zeros(0, dtype=np.float32),
            np.concatenate([speech(1.2, seed=1), quiet(3.6), speech(1.23, seed=2)]),
        ],
    )
    def test_selected_windows_are_finite_and_full_length(self, x: np.ndarray) -> None:
        selection = select_windows(x, WINDOW)
        assert selection.vad_status in {VAD_PASS, VAD_FAIL}
        for window in selection.windows:
            assert window.size == WINDOW
            assert np.isfinite(window).all()

    def test_failure_always_carries_a_reason(self) -> None:
        for x in (quiet(8.0), np.zeros(0, dtype=np.float32)):
            selection = select_windows(x, WINDOW)
            assert selection.vad_status == VAD_FAIL
            assert selection.reason != ""


class _FixedScorer:
    """A scorer that always answers, so these tests need no checkpoint."""

    model_name = "fixed-test-scorer"
    model_version = "0"

    def __init__(self, value: float) -> None:
        self.value = value
        self.calls = 0

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        self.calls += 1
        return self.value


class _RaisingScorer:
    """A scorer that fails. The check turns this into FAILED with no signal."""

    model_name = "raising-test-scorer"
    model_version = "0"

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        raise RuntimeError("checkpoint missing")


class TestMeanScore:
    """`sweep.mean_score` reports a status and never a NaN.

    This is the contract every downstream table depends on: `score` is a float or
    `None`, and `None` always arrives with `vad_status == "FAIL"` and a reason.
    """

    @staticmethod
    def run(x: np.ndarray, scorer: object) -> dict[str, object]:
        from ml.checks.machine_fingerprint import MachineFingerprintCheck
        from ml.tools.sweep import mean_score

        return mean_score(MachineFingerprintCheck(scorer), x)  # type: ignore[arg-type]

    def test_speech_returns_a_float_and_passes(self) -> None:
        result = self.run(speech(12.0), _FixedScorer(0.42))
        assert result["score"] == pytest.approx(0.42)
        assert result["vad_status"] == VAD_PASS
        assert result["windows"] == 2
        assert result["duration_s"] == pytest.approx(12.0)

    def test_silence_returns_none_not_nan(self) -> None:
        result = self.run(quiet(8.0), _FixedScorer(0.42))
        assert result["score"] is None
        assert result["vad_status"] == VAD_FAIL
        assert result["reason"]
        assert result["speech_s"] == 0.0

    def test_the_six_second_clip_never_returns_nan(self) -> None:
        clip = TestSadhguruRegression.straddling_clip()
        result = self.run(clip, _FixedScorer(0.9))
        assert result["score"] is None or math.isfinite(float(result["score"]))
        if result["score"] is None:
            assert result["vad_status"] == VAD_FAIL
            assert result["reason"]
        else:
            assert result["vad_status"] == VAD_PASS
            assert result["status"] == STATUS_SPARSE

    def test_a_scorer_failure_is_none_with_its_own_reason(self) -> None:
        result = self.run(speech(12.0), _RaisingScorer())
        assert result["score"] is None
        assert result["vad_status"] == VAD_FAIL
        assert "scorer" in str(result["reason"])
