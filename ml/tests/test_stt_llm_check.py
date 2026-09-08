"""Smoke suite for the stt_llm check. Fake transcribers and fake LLM, no models.

What these pin down: a transcriber error is FAILED and never a verdict, too
little audio or a thin transcript is SKIPPED, a scam transcript yields an OK
signal, the batch is never mutated, and no transcript text or CallContext PII
reaches the evidence or the serialized result.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from contracts.checks import Check, CheckName, CheckResult, CheckStatus, ReasonCode
from contracts.context import CallContext
from contracts.pipeline import (
    CANONICAL_FRAME_MS,
    CANONICAL_SAMPLE_RATE,
    CanonicalAudioBatch,
)
from ml.checks.stt_llm.check import SttLlmCheck
from ml.checks.stt_llm.eval_transcripts import NORMAL_TRANSCRIPTS, SCAM_TRANSCRIPTS
from ml.checks.stt_llm.tactics import TACTICS

CALLER_NUMBER = "+919876543210"
CALLEE_NUMBER = "+919812345678"
STARTED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

SCAM = SCAM_TRANSCRIPTS[0]  # "...fraud department... forty thousand rupees..."
ORDINARY = NORMAL_TRANSCRIPTS[5]  # mutual fund courtesy call, no tactics


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


class _FixedTranscriber:
    model_name = "fake-transcriber"
    model_version = "0"

    def __init__(self, text: str) -> None:
        self.text = text
        self.seen_sample_rate: int | None = None

    def warmup(self) -> None:
        return None

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        self.seen_sample_rate = sample_rate
        return self.text


class _RaisingTranscriber:
    model_name = "raising-transcriber"
    model_version = "0"

    def warmup(self) -> None:
        return None

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        raise RuntimeError(f"cannot open {CALLER_NUMBER}.wav")


class _FixedLLM:
    model_name = "fake-llm"
    model_version = "0"

    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, system: str, transcript: str) -> str:
        return self.response


def _reasons(result: CheckResult) -> list[ReasonCode]:
    return [item.reason_code for item in result.evidence]


def test_satisfies_the_check_protocol() -> None:
    check: Check = SttLlmCheck()
    assert check.name is CheckName.STT_LLM


def test_short_window_is_skipped_not_a_verdict() -> None:
    result = SttLlmCheck(_FixedTranscriber(SCAM)).run(_batch(1000), _context())
    assert result.status is CheckStatus.SKIPPED
    assert result.signal is None
    assert _reasons(result) == [ReasonCode.INSUFFICIENT_AUDIO]


def test_no_transcriber_configured_is_failed_never_ok() -> None:
    result = SttLlmCheck().run(_batch(6000), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None
    assert _reasons(result) == [ReasonCode.DEGRADED_CHECK]


def test_transcriber_error_is_failed_and_leaks_no_message() -> None:
    result = SttLlmCheck(_RaisingTranscriber()).run(_batch(6000), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None
    detail = result.evidence[0].detail or ""
    assert "RuntimeError" in detail
    assert CALLER_NUMBER not in detail
    assert ".wav" not in detail


def test_scam_transcript_is_ok_with_high_script_evidence() -> None:
    result = SttLlmCheck(_FixedTranscriber(SCAM)).run(_batch(6000), _context())
    assert result.status is CheckStatus.OK
    assert result.signal is not None
    assert result.signal.kind == "stt_llm"
    assert result.signal.script_risk is not None and result.signal.script_risk >= 0.8
    assert result.signal.script_category in TACTICS
    assert _reasons(result) == [ReasonCode.SCRIPT_RISK_HIGH]


def test_ordinary_transcript_is_ok_with_absent_script_evidence() -> None:
    result = SttLlmCheck(_FixedTranscriber(ORDINARY)).run(_batch(6000), _context())
    assert result.status is CheckStatus.OK
    assert result.signal is not None
    assert result.signal.script_risk == 0.0
    assert result.signal.script_category is None
    assert _reasons(result) == [ReasonCode.SCRIPT_RISK_ABSENT]


def test_thin_transcript_is_skipped() -> None:
    result = SttLlmCheck(_FixedTranscriber("hello yes okay thanks")).run(
        _batch(6000), _context()
    )
    assert result.status is CheckStatus.SKIPPED
    assert result.signal is None


def test_empty_transcript_is_skipped() -> None:
    result = SttLlmCheck(_FixedTranscriber("")).run(_batch(6000), _context())
    assert result.status is CheckStatus.SKIPPED
    assert result.signal is None


def test_llm_path_is_used_when_provided() -> None:
    resp = json.dumps(
        {
            "tactics": {t: 0.1 for t in TACTICS},
            "intent": 0.95,
            "evidence": ["your account has been frozen"],
            "confidence": 0.9,
        }
    )
    result = SttLlmCheck(_FixedTranscriber(SCAM), _FixedLLM(resp)).run(
        _batch(6000), _context()
    )
    assert result.status is CheckStatus.OK
    assert result.signal is not None
    assert result.signal.script_risk == 0.95
    assert "source=llm" in (result.evidence[0].detail or "")


def test_transcriber_is_told_the_canonical_sample_rate() -> None:
    transcriber = _FixedTranscriber(ORDINARY)
    SttLlmCheck(transcriber).run(_batch(6000), _context())
    assert transcriber.seen_sample_rate == CANONICAL_SAMPLE_RATE


def test_batch_is_not_mutated() -> None:
    batch = _batch(6000)
    before = bytes(batch.pcm_s16le)
    snapshot = batch.model_dump()
    SttLlmCheck(_FixedTranscriber(SCAM)).run(batch, _context())
    assert batch.pcm_s16le == before
    assert batch.model_dump() == snapshot


def test_serialized_result_carries_no_transcript_text_or_pii() -> None:
    result = SttLlmCheck(_FixedTranscriber(SCAM)).run(_batch(6000), _context())
    payload = result.model_dump_json()
    assert "fraud department" not in payload
    assert "forty thousand" not in payload
    assert SCAM[:30] not in payload
    assert CALLER_NUMBER not in payload
    assert CALLEE_NUMBER not in payload
    assert CheckResult.model_validate_json(payload) == result


def test_evidence_records_model_window_and_latency() -> None:
    result = SttLlmCheck(_FixedTranscriber(SCAM)).run(_batch(6000), _context())
    item = result.evidence[0]
    assert item.model == "fake-transcriber"
    assert item.model_version == "0"
    assert item.window_started_at == STARTED_AT
    assert item.latency_ms is not None and item.latency_ms >= 0.0
    assert result.window_ms == 6000
