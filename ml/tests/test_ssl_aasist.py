"""Tests for the ported XLS-R + AASIST scorer.

The port replaces a fairseq front end with a HuggingFace one, and the failure mode
that matters is silent: a partially loaded encoder produces confident nonsense rather
than an error. So the integration tests assert discrimination and level invariance,
not merely that a number comes back.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml import paths
from ml.checks.machine_fingerprint.ssl_aasist import (
    SSL_INPUT_SAMPLES,
    SslAasistScorer,
    _tile_pad,
)


def _assets_present() -> bool:
    root = paths.model_root()
    return (
        (root / "Best_LA_model_for_DF.pth").exists()
        and (root / "ssl_aasist" / "model.py").exists()
        and (root / "ssl_aasist" / "fairseq_to_hf.json").exists()
        and (root / "wav2vec2-xls-r-300m" / "config.json").exists()
    )


needs_assets = pytest.mark.skipif(
    not _assets_present(),
    reason="SSL-AASIST checkpoint, published model.py or key map not on this machine",
)


def _tone(seconds: float = 4.1, freq: float = 180.0, amplitude: float = 0.2) -> bytes:
    t = np.arange(int(16000 * seconds)) / 16000.0
    wave = amplitude * np.sin(2 * np.pi * freq * t)
    return (wave * 32767).astype("<i2").tobytes()


class TestContractWithoutTheModel:
    def test_wrong_sample_rate_raises_before_loading(self) -> None:
        with pytest.raises(ValueError, match="16000"):
            SslAasistScorer().score(b"\x00\x00" * 1000, 8000)

    def test_identity_strings_are_stable_and_name_the_port(self) -> None:
        scorer = SslAasistScorer()
        assert scorer.model_name == "xlsr-aasist"
        assert "hfport" in scorer.model_version

    def test_input_length_matches_the_published_model(self) -> None:
        assert SSL_INPUT_SAMPLES == 64600


class TestTilePad:
    def test_short_input_is_repeated_not_zero_filled(self) -> None:
        padded = _tile_pad(np.array([0.5, -0.5], dtype=np.float32), 5)
        assert padded.shape == (5,)
        assert not np.any(padded == 0.0)

    def test_long_input_is_truncated(self) -> None:
        assert _tile_pad(np.arange(50, dtype=np.float32), 8).shape == (8,)

    def test_empty_input_raises(self) -> None:
        with pytest.raises(ValueError):
            _tile_pad(np.array([], dtype=np.float32), 8)


@pytest.fixture(scope="module")
def scorer() -> SslAasistScorer:
    """Loads XLS-R 300m once for the whole module."""
    instance = SslAasistScorer()
    instance.warmup()
    return instance


@needs_assets
class TestAgainstTheRealModel:
    """Slow: shares one loaded scorer across the class."""

    def test_returns_a_probability(self, scorer: SslAasistScorer) -> None:
        value = scorer.score(_tone(), 16000)
        assert 0.0 <= value <= 1.0

    def test_is_deterministic(self, scorer: SslAasistScorer) -> None:
        pcm = _tone()
        assert scorer.score(pcm, 16000) == pytest.approx(scorer.score(pcm, 16000), abs=1e-6)

    def test_score_is_level_invariant(self, scorer: SslAasistScorer) -> None:
        """The defect that made the AASIST-only scorer unusable.

        Its score tracked input loudness rather than content, so the same speech at
        two gains scored 0.14 and 0.87. Input normalisation is what fixes it, and
        this test is what stops it regressing.
        """
        quiet = np.frombuffer(_tone(amplitude=0.02), dtype="<i2")
        loud = np.frombuffer(_tone(amplitude=0.40), dtype="<i2")
        a = scorer.score(quiet.tobytes(), 16000)
        b = scorer.score(loud.tobytes(), 16000)
        assert a == pytest.approx(b, abs=0.02)

    def test_warmup_is_idempotent(self, scorer: SslAasistScorer) -> None:
        scorer.warmup()
        assert 0.0 <= scorer.score(_tone(), 16000) <= 1.0

    def test_input_bytes_are_not_mutated(self, scorer: SslAasistScorer) -> None:
        pcm = _tone()
        before = bytes(pcm)
        scorer.score(pcm, 16000)
        assert pcm == before

    def test_short_window_is_padded_rather_than_rejected(self, scorer: SslAasistScorer) -> None:
        assert 0.0 <= scorer.score(_tone(seconds=1.0), 16000) <= 1.0
