"""Smoke suite for the machine fingerprint check. Fake scorers only, no model.

What these tests pin down is the contract behaviour: a model error is FAILED and
never a verdict, too little audio is SKIPPED, the batch is never mutated, and no
PII from CallContext reaches the evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from contracts.checks import Check, CheckName, CheckStatus, ReasonCode
from contracts.context import CallContext
from contracts.pipeline import (
    CANONICAL_FRAME_MS,
    CANONICAL_SAMPLE_RATE,
    CanonicalAudioBatch,
)
from ml.checks.machine_fingerprint import MachineFingerprintCheck

CALLER_NUMBER = "+919876543210"
CALLEE_NUMBER = "+919812345678"
STARTED_AT = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def _batch(window_ms: int) -> CanonicalAudioBatch:
    sample_count = CANONICAL_SAMPLE_RATE * window_ms // 1000
    return CanonicalAudioBatch(
        stream_id="stream-1",
        call_id="call-1",
        start_sequence=0,
        end_sequence=max(window_ms // CANONICAL_FRAME_MS - 1, 0),
        pcm_s16le=b"\x11\x22" * sample_count,
        sample_count=sample_count,
        capture_started_at=STARTED_AT,
        capture_ended_at=STARTED_AT + timedelta(milliseconds=window_ms),
        window_ms=window_ms,
    )


def _context() -> CallContext:
    return CallContext(
        stream_id="stream-1",
        call_id="call-1",
        caller_number=CALLER_NUMBER,
        callee_number=CALLEE_NUMBER,
        started_at=STARTED_AT,
    )


class _FixedScorer:
    model_name = "fixed-test-scorer"
    model_version = "0"

    def __init__(self, value: float) -> None:
        self.value = value
        self.seen_sample_rate: int | None = None
        self.warmed = False

    def warmup(self) -> None:
        self.warmed = True

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        self.seen_sample_rate = sample_rate
        return self.value


class _RaisingScorer:
    model_name = "raising-test-scorer"
    model_version = "0"

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        raise RuntimeError(f"checkpoint missing for {CALLER_NUMBER}")


def _reasons(result) -> list[ReasonCode]:
    return [item.reason_code for item in result.evidence]


def test_satisfies_the_check_protocol() -> None:
    check: Check = MachineFingerprintCheck()
    assert check.name is CheckName.MACHINE_FINGERPRINT


def test_short_window_is_skipped_not_a_verdict() -> None:
    result = MachineFingerprintCheck(_FixedScorer(0.99)).run(_batch(200), _context())
    assert result.status is CheckStatus.SKIPPED
    assert result.signal is None
    assert _reasons(result) == [ReasonCode.INSUFFICIENT_AUDIO]


def test_no_scorer_configured_is_failed_never_ok() -> None:
    result = MachineFingerprintCheck().run(_batch(4000), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None
    assert _reasons(result) == [ReasonCode.DEGRADED_CHECK]


def test_scorer_error_is_failed_and_leaks_no_message() -> None:
    result = MachineFingerprintCheck(_RaisingScorer()).run(_batch(4000), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None
    detail = result.evidence[0].detail or ""
    assert "RuntimeError" in detail
    assert CALLER_NUMBER not in detail
    assert "checkpoint missing" not in detail


@pytest.mark.parametrize("value", [1.5, -0.1, float("nan"), float("inf")])
def test_out_of_range_score_is_failed(value: float) -> None:
    result = MachineFingerprintCheck(_FixedScorer(value)).run(_batch(4000), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None


def test_high_probability_is_ok_with_synthetic_evidence() -> None:
    result = MachineFingerprintCheck(_FixedScorer(0.92)).run(_batch(4000), _context())
    assert result.status is CheckStatus.OK
    assert result.signal is not None
    assert result.signal.kind == "machine_fingerprint"
    assert result.signal.synthetic_probability == pytest.approx(0.92)
    assert _reasons(result) == [ReasonCode.FINGERPRINT_SYNTHETIC]


def test_low_probability_is_ok_with_genuine_evidence() -> None:
    result = MachineFingerprintCheck(_FixedScorer(0.03)).run(_batch(4000), _context())
    assert result.status is CheckStatus.OK
    assert _reasons(result) == [ReasonCode.FINGERPRINT_GENUINE]


def test_medium_window_is_degraded_but_still_signals() -> None:
    result = MachineFingerprintCheck(_FixedScorer(0.7)).run(_batch(1500), _context())
    assert result.status is CheckStatus.DEGRADED
    assert result.signal is not None
    assert ReasonCode.DEGRADED_CHECK in _reasons(result)


def test_scorer_is_told_the_canonical_sample_rate() -> None:
    scorer = _FixedScorer(0.5)
    MachineFingerprintCheck(scorer).run(_batch(4000), _context())
    assert scorer.seen_sample_rate == CANONICAL_SAMPLE_RATE


def test_batch_is_not_mutated() -> None:
    batch = _batch(4000)
    before = bytes(batch.pcm_s16le)
    snapshot = batch.model_dump()
    MachineFingerprintCheck(_FixedScorer(0.4)).run(batch, _context())
    assert batch.pcm_s16le == before
    assert batch.model_dump() == snapshot


def test_evidence_records_model_window_and_latency() -> None:
    result = MachineFingerprintCheck(_FixedScorer(0.4)).run(_batch(4000), _context())
    item = result.evidence[0]
    assert item.model == "fixed-test-scorer"
    assert item.model_version == "0"
    assert item.window_started_at == STARTED_AT
    assert item.latency_ms is not None and item.latency_ms >= 0.0
    assert result.window_ms == 4000


def test_serialized_result_round_trips_and_carries_no_pii() -> None:
    result = MachineFingerprintCheck(_FixedScorer(0.81)).run(_batch(4000), _context())
    payload = result.model_dump_json()
    assert CALLER_NUMBER not in payload
    assert CALLEE_NUMBER not in payload
    from contracts.checks import CheckResult

    assert CheckResult.model_validate_json(payload) == result
