"""The factory the runner calls, and the confidence path through the check.

Two things are worth failing loudly about and are tested for it: building a check
that cannot meet the runner's deadline, and letting confidence reach the risk engine
only as text a caller has to parse.

No checkpoint is loaded. The device decision is monkeypatched and the scorer is fake.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from contracts.checks import CheckStatus, ReasonCode
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioBatch
from ml.checks.machine_fingerprint import (
    DEFAULT_LOW_CONFIDENCE,
    MachineFingerprintCheck,
    build_default_check,
    factory,
)


class _PlainScorer:
    model_name = "plain"
    model_version = "0"

    def __init__(self, score: float = 0.9) -> None:
        self._score = score

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        return self._score


class _ConfidentScorer(_PlainScorer):
    model_name = "confident"

    def __init__(self, score: float = 0.9, confidence: float = 0.8) -> None:
        super().__init__(score)
        self._confidence = confidence
        self.score_calls = 0

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        self.score_calls += 1
        return self._score

    def score_with_confidence(
        self, pcm_s16le: bytes, sample_rate: int
    ) -> tuple[float, float]:
        return self._score, self._confidence


def batch(seconds: float = 4.0375) -> CanonicalAudioBatch:
    samples = int(seconds * 16000)
    pcm = np.zeros(samples, dtype="<i2").tobytes()
    started = datetime.now(UTC)
    return CanonicalAudioBatch(
        stream_id="s",
        call_id="c",
        start_sequence=0,
        end_sequence=0,
        pcm_s16le=pcm,
        sample_count=samples,
        capture_started_at=started,
        capture_ended_at=started + timedelta(seconds=seconds),
        window_ms=int(seconds * 1000),
    )


def context() -> CallContext:
    return CallContext(stream_id="s", call_id="c", started_at=datetime.now(UTC))


class TestConfidenceReachesTheEvidence:
    def test_a_scorer_without_confidence_still_works(self) -> None:
        # The optional protocol must not break the scorers that predate it.
        result = MachineFingerprintCheck(_PlainScorer()).run(batch(), context())
        assert result.status == CheckStatus.OK
        assert "confidence" not in (result.evidence[0].detail or "")

    def test_confidence_appears_in_the_detail(self) -> None:
        result = MachineFingerprintCheck(_ConfidentScorer(0.9, 0.8)).run(
            batch(), context()
        )
        assert "confidence 0.800" in (result.evidence[0].detail or "")

    def test_low_confidence_degrades_the_status(self) -> None:
        result = MachineFingerprintCheck(_ConfidentScorer(0.99, 0.02)).run(
            batch(), context()
        )
        assert result.status == CheckStatus.DEGRADED

    def test_low_confidence_emits_a_reason_code_not_only_text(self) -> None:
        # The risk engine must be able to branch on this without a regex over a
        # free-text field.
        result = MachineFingerprintCheck(_ConfidentScorer(0.99, 0.02)).run(
            batch(), context()
        )
        codes = [item.reason_code for item in result.evidence]
        assert ReasonCode.DEGRADED_CHECK in codes

    def test_the_signal_still_carries_the_score_when_degraded(self) -> None:
        # DEGRADED is a caveat, not a suppression. The risk engine still gets a
        # number and decides what to do with it.
        result = MachineFingerprintCheck(_ConfidentScorer(0.99, 0.02)).run(
            batch(), context()
        )
        assert result.signal is not None
        assert result.signal.synthetic_probability == pytest.approx(0.99)

    def test_high_confidence_stays_ok(self) -> None:
        result = MachineFingerprintCheck(_ConfidentScorer(0.99, 0.95)).run(
            batch(), context()
        )
        assert result.status == CheckStatus.OK

    def test_the_threshold_is_configurable(self) -> None:
        check = MachineFingerprintCheck(_ConfidentScorer(0.9, 0.5), low_confidence=0.9)
        assert check.run(batch(), context()).status == CheckStatus.DEGRADED

    def test_a_confident_scorer_that_raises_is_still_a_failure_not_a_verdict(
        self,
    ) -> None:
        class _Raiser(_PlainScorer):
            def score_with_confidence(self, pcm_s16le: bytes, sample_rate: int):
                raise RuntimeError("checkpoint gone")

        result = MachineFingerprintCheck(_Raiser()).run(batch(), context())
        assert result.status == CheckStatus.FAILED
        assert result.signal is None


class TestFactoryRefusesToMissTheDeadline:
    def test_a_cpu_only_machine_raises_with_the_numbers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory, "cuda_available", lambda: False)
        with pytest.raises(RuntimeError) as excinfo:
            build_default_check()
        message = str(excinfo.value)
        assert "523" in message or "522" in message
        assert "180" in message
        assert "allow_cpu_fallback" in message

    def test_the_error_warns_that_the_fallback_is_inverted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A fallback that is faster and scores bonafide above deepfake is not a
        # graceful degradation, and nobody should reach for it uninformed.
        monkeypatch.setattr(factory, "cuda_available", lambda: False)
        with pytest.raises(RuntimeError, match="INVERTED"):
            build_default_check()

    def test_an_explicit_cpu_device_is_still_refused_without_the_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory, "cuda_available", lambda: True)
        with pytest.raises(RuntimeError):
            build_default_check(device="cpu")

    def test_the_measured_numbers_are_the_ones_in_the_csv(self) -> None:
        assert factory.MEASURED_MS[("xlsr-aasist", "cuda")] < factory.DEADLINE_MS
        assert factory.MEASURED_MS[("xlsr-aasist", "cpu")] > factory.DEADLINE_MS
        assert factory.MEASURED_MS[("AASIST-L", "cpu")] < factory.DEADLINE_MS

    def test_the_deadline_matches_the_runner(self) -> None:
        assert factory.DEADLINE_MS == 180.0


class TestThresholdIsHonest:
    def test_the_default_sits_below_the_in_domain_mean(self) -> None:
        # In-domain confidence is roughly uniform by construction, mean 0.508, so a
        # threshold of 0.3 marks about 28% of in-domain windows DEGRADED. That is a
        # property of percentile calibration, not a defect, and it is why the
        # constant is documented as configuration rather than a measured boundary.
        assert DEFAULT_LOW_CONFIDENCE == 0.3
        assert DEFAULT_LOW_CONFIDENCE < 0.508
