"""The confidence estimator and the handoff API.

`api.score_window` is the entire surface the product team sees, so its contract is
tested harder than its internals: `p_synthetic` is a float or None and never NaN,
`None` always arrives with `vad_status FAIL`, and `confidence` is always a float in
[0, 1] even when nothing could be scored.

The scorer is faked. These tests need no checkpoint, no GPU and no reference file.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ml.checks.machine_fingerprint import api
from ml.eval import confidence as confidence_module
from ml.eval.activity import VAD_FAIL, VAD_PASS

WINDOW = 64600


def cloud(n: int, spread: float, seed: int = 0, dims: int = 8) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, spread, (n, dims)).astype(np.float32)


class TestFit:
    def test_a_reference_keeps_its_embeddings_and_self_distances(self) -> None:
        reference = confidence_module.fit(cloud(20, 1.0))
        assert reference.size == 20
        assert reference.self_distances.shape == (20,)

    def test_a_clip_is_not_its_own_neighbour(self) -> None:
        # Including itself makes every self-distance smaller and the whole
        # calibration too generous.
        reference = confidence_module.fit(cloud(20, 1.0))
        assert reference.self_distances.min() > 0.0

    def test_too_few_clips_for_k_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot support"):
            confidence_module.fit(cloud(5, 1.0), k=5)

    def test_a_one_dimensional_array_is_refused(self) -> None:
        with pytest.raises(ValueError, match="2-D array"):
            confidence_module.fit(np.zeros(10, dtype=np.float32))


class TestDistanceAndConfidence:
    @staticmethod
    def reference() -> confidence_module.Reference:
        return confidence_module.fit(cloud(40, 1.0, seed=1))

    def test_a_point_at_the_centre_is_closer_than_one_far_out(self) -> None:
        reference = self.reference()
        near = reference.distance(np.zeros(8, dtype=np.float32))
        far = reference.distance(np.full(8, 50.0, dtype=np.float32))
        assert far > near

    def test_confidence_falls_as_distance_grows(self) -> None:
        reference = self.reference()
        assert reference.confidence(np.zeros(8, dtype=np.float32)) > reference.confidence(
            np.full(8, 50.0, dtype=np.float32)
        )

    def test_far_out_is_zero_not_negative(self) -> None:
        reference = self.reference()
        assert reference.confidence(np.full(8, 1e6, dtype=np.float32)) == 0.0

    @pytest.mark.parametrize("scale", [0.0, 0.5, 2.0, 10.0, 1e5])
    def test_confidence_always_lands_inside_zero_and_one(self, scale: float) -> None:
        reference = self.reference()
        value = reference.confidence(np.full(8, scale, dtype=np.float32))
        assert 0.0 <= value <= 1.0

    def test_an_empty_calibration_set_is_refused(self) -> None:
        with pytest.raises(ValueError, match="empty reference"):
            confidence_module.distance_to_confidence(1.0, np.zeros(0))

    def test_it_round_trips_through_a_file(self, tmp_path: Path) -> None:
        reference = self.reference()
        loaded = confidence_module.Reference.load(
            reference.save(tmp_path / "ref.npz")
        )
        probe = np.full(8, 0.3, dtype=np.float32)
        assert loaded.k == reference.k
        assert loaded.size == reference.size
        assert loaded.confidence(probe) == pytest.approx(reference.confidence(probe))


class _FakeScorer:
    """Answers with a fixed score and a fixed embedding. No checkpoint needed."""

    model_name = "fake"
    model_version = "0"

    def __init__(self, score: float = 0.42, embedding: float = 0.0) -> None:
        self._score = score
        self._embedding = embedding
        self.calls = 0

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        self.calls += 1
        return self._score

    def embed(self, pcm_s16le: bytes, sample_rate: int) -> np.ndarray:
        return np.full(8, self._embedding, dtype=np.float32)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> _FakeScorer:
    scorer = _FakeScorer()
    reference = confidence_module.fit(cloud(40, 1.0, seed=2))
    monkeypatch.setattr(api, "_scorer", scorer)
    monkeypatch.setattr(api, "_reference", reference)
    return scorer


def speech(seconds: float = 4.1, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, 0.2, int(seconds * 16000)).astype(
        np.float32
    )


class TestScoreWindowContract:
    def test_speech_returns_all_three_fields(self, wired: _FakeScorer) -> None:
        result = api.score_window(speech())
        assert set(result) == {"p_synthetic", "confidence", "vad_status"}
        assert result["p_synthetic"] == pytest.approx(0.42)
        assert result["vad_status"] == VAD_PASS

    def test_silence_returns_none_with_a_fail_status(self, wired: _FakeScorer) -> None:
        result = api.score_window(np.zeros(WINDOW, dtype=np.float32))
        assert result["p_synthetic"] is None
        assert result["vad_status"] == VAD_FAIL

    def test_empty_input_does_not_raise(self, wired: _FakeScorer) -> None:
        result = api.score_window(np.zeros(0, dtype=np.float32))
        assert result["p_synthetic"] is None
        assert result["vad_status"] == VAD_FAIL

    def test_confidence_is_a_float_even_when_nothing_was_scored(
        self, wired: _FakeScorer
    ) -> None:
        # A None here would make every caller handle two optional fields instead of
        # one, and a NaN would defeat the whole point of the contract.
        result = api.score_window(np.zeros(WINDOW, dtype=np.float32))
        assert isinstance(result["confidence"], float)
        assert result["confidence"] == 0.0

    @pytest.mark.parametrize(
        "audio",
        [
            np.zeros(0, dtype=np.float32),
            np.zeros(WINDOW, dtype=np.float32),
            speech(4.1),
            speech(0.5),
            np.full(WINDOW, 1e-9, dtype=np.float32),
        ],
    )
    def test_no_input_produces_a_nan(self, wired: _FakeScorer, audio: np.ndarray) -> None:
        result = api.score_window(audio)
        assert result["p_synthetic"] is None or np.isfinite(result["p_synthetic"])
        assert np.isfinite(result["confidence"])

    def test_none_always_travels_with_fail(self, wired: _FakeScorer) -> None:
        for audio in (np.zeros(0, dtype=np.float32), np.zeros(WINDOW, dtype=np.float32)):
            result = api.score_window(audio)
            assert (result["p_synthetic"] is None) == (result["vad_status"] == VAD_FAIL)

    def test_confidence_stays_in_range_on_real_input(self, wired: _FakeScorer) -> None:
        assert 0.0 <= api.score_window(speech())["confidence"] <= 1.0

    def test_a_wrong_sample_rate_is_refused_not_resampled(
        self, wired: _FakeScorer
    ) -> None:
        # Resampling here would be a second decode path, and every score would then
        # depend on which one the caller happened to use.
        with pytest.raises(ValueError, match="expected 16000 Hz"):
            api.score_window(speech(), sample_rate=8000)

    def test_a_list_is_accepted_like_an_array(self, wired: _FakeScorer) -> None:
        assert api.score_window(speech().tolist())["vad_status"] == VAD_PASS

    def test_far_out_of_domain_audio_gets_low_confidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api, "_scorer", _FakeScorer(score=0.99, embedding=99.0))
        monkeypatch.setattr(api, "_reference", confidence_module.fit(cloud(40, 1.0, 3)))
        result = api.score_window(speech())
        assert result["p_synthetic"] == pytest.approx(0.99)
        assert result["confidence"] == 0.0, "a confident score on unfamiliar audio"


class TestModelIdentity:
    def test_it_names_the_model_and_the_reference(self, wired: _FakeScorer) -> None:
        identity = api.model_identity()
        assert identity["model_name"] == "fake"
        assert identity["window_samples"] == WINDOW
        assert identity["sample_rate"] == 16000
        assert identity["confidence_reference_size"] == 40
