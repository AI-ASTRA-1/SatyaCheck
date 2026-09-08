"""Tests for the AASIST scorer and the model-path helper.

Everything that does not need the checkpoint runs everywhere. The one test that
loads the real model is skipped when the weights are not on the machine, and says
so; it is an environment-conditional integration test, not a disabled test.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml import paths
from ml.checks.machine_fingerprint.aasist_scorer import (
    AASIST_INPUT_SAMPLES,
    AasistScorer,
    _tile_pad,
)
from ml.tools.score_file import windows


def _weights_present() -> bool:
    return (
        paths.model_root() / "aasist" / "models" / "weights" / "AASIST.pth"
    ).exists()


needs_weights = pytest.mark.skipif(
    not _weights_present(),
    reason="AASIST weights not downloaded on this machine",
)


class TestModelPaths:
    def test_env_var_overrides_the_default(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(paths.ENV_VAR, str(tmp_path))
        assert paths.model_root() == tmp_path

    def test_require_returns_an_existing_path(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(paths.ENV_VAR, str(tmp_path))
        (tmp_path / "thing.pth").write_bytes(b"x")
        assert paths.require("thing.pth") == tmp_path / "thing.pth"

    def test_require_names_the_missing_path_and_the_override(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv(paths.ENV_VAR, str(tmp_path))
        with pytest.raises(FileNotFoundError) as excinfo:
            paths.require("absent.pth")
        message = str(excinfo.value)
        assert "absent.pth" in message
        assert paths.ENV_VAR in message


class TestTilePad:
    def test_short_input_is_repeated_not_zero_filled(self) -> None:
        samples = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        padded = _tile_pad(samples, 8)
        assert padded.shape == (8,)
        assert np.allclose(padded, [0.1, 0.2, 0.3, 0.1, 0.2, 0.3, 0.1, 0.2])
        assert not np.any(padded == 0.0)

    def test_long_input_is_truncated(self) -> None:
        samples = np.arange(20, dtype=np.float32)
        assert _tile_pad(samples, 8).shape == (8,)

    def test_exact_length_is_unchanged(self) -> None:
        samples = np.arange(8, dtype=np.float32)
        assert np.array_equal(_tile_pad(samples, 8), samples)

    def test_empty_input_raises(self) -> None:
        with pytest.raises(ValueError):
            _tile_pad(np.array([], dtype=np.float32), 8)


class TestScorerContract:
    def test_unknown_variant_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            AasistScorer("AASIST-XL")

    def test_wrong_sample_rate_raises_before_loading_anything(self) -> None:
        # No checkpoint is touched, so this passes with no weights on the machine.
        scorer = AasistScorer()
        with pytest.raises(ValueError, match="16000"):
            scorer.score(b"\x00\x00" * 1000, 8000)

    def test_version_string_identifies_the_weights(self) -> None:
        assert AasistScorer("AASIST-L").model_version == (
            "clovaai-AASIST-L-asvspoof2019la"
        )
        assert AasistScorer("AASIST-L").model_name == "aasist-l"


class TestWindowing:
    def test_splits_into_equal_windows_dropping_the_partial_tail(self) -> None:
        # 16000 Hz * 2 bytes = 32000 bytes per second.
        pcm = b"\x00\x01" * 16000 * 5  # 5 seconds
        chunks = windows(pcm, 2000)
        assert len(chunks) == 2
        assert all(len(chunk) == 64000 for chunk in chunks)

    def test_audio_shorter_than_one_window_is_kept_whole(self) -> None:
        pcm = b"\x00\x01" * 8000  # 0.5 s
        assert windows(pcm, 4000) == [pcm]


@needs_weights
class TestAgainstTheRealModel:
    def test_scores_are_probabilities_and_deterministic(self) -> None:
        rng = np.random.default_rng(0)
        pcm = rng.normal(0, 2000, AASIST_INPUT_SAMPLES).astype("<i2").tobytes()
        scorer = AasistScorer("AASIST", device="cpu")
        first = scorer.score(pcm, 16000)
        second = scorer.score(pcm, 16000)
        assert 0.0 <= first <= 1.0
        assert first == pytest.approx(second, abs=1e-6)

    def test_short_window_is_padded_rather_than_rejected(self) -> None:
        rng = np.random.default_rng(1)
        pcm = rng.normal(0, 2000, 16000).astype("<i2").tobytes()  # 1 second
        assert 0.0 <= AasistScorer("AASIST", device="cpu").score(pcm, 16000) <= 1.0

    def test_input_bytes_are_not_mutated(self) -> None:
        rng = np.random.default_rng(2)
        pcm = rng.normal(0, 2000, AASIST_INPUT_SAMPLES).astype("<i2").tobytes()
        before = bytes(pcm)
        AasistScorer("AASIST", device="cpu").score(pcm, 16000)
        assert pcm == before
