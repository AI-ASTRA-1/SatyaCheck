"""Tests for the stage 05 RiskFusionEngine."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.fusion.fusion import RiskFusionEngine
from contracts.checks import (
    CheckName,
    CheckResult,
    ChecksBatchResult,
    CheckStatus,
    MachineFingerprintSignal,
    ReasonCode,
)
from contracts.context import CallContext, NumberReputation
from contracts.risk import RiskLevel


def _results(stream_id: str, probability: float, *, call_id: str = "c1") -> ChecksBatchResult:
    now = datetime.now(UTC)
    fingerprint = CheckResult(
        check=CheckName.MACHINE_FINGERPRINT,
        status=CheckStatus.OK,
        signal=MachineFingerprintSignal(synthetic_probability=probability),
        processed_at=now,
        window_ms=1000,
    )
    others = [
        CheckResult(check=name, status=CheckStatus.SKIPPED, processed_at=now, window_ms=0)
        for name in (CheckName.SPEAKER_IDENTITY, CheckName.PROSODY, CheckName.STT_LLM)
    ]
    return ChecksBatchResult(
        stream_id=stream_id,
        call_id=call_id,
        started_at=now,
        batch_sequence=0,
        results=[fingerprint, *others],
        audio_window_ms=1000,
    )


def _context(*, blocklisted: bool = False) -> CallContext:
    reputation = NumberReputation(blocklisted=blocklisted) if blocklisted else None
    return CallContext(stream_id="s1", call_id="c1", started_at=datetime.now(UTC), number_reputation=reputation)


def test_score_is_int_in_range() -> None:
    engine = RiskFusionEngine()
    update = engine.update(_results("s1", 0.42), _context())
    assert isinstance(update.score, int)
    assert 0 <= update.score <= 100


def test_single_high_severity_tick_escalates_immediately() -> None:
    engine = RiskFusionEngine()
    update = engine.update(_results("s1", 0.95), _context())
    assert update.risk_level == RiskLevel.CRITICAL


def test_single_moderate_tick_does_not_alone_reach_high() -> None:
    engine = RiskFusionEngine()
    update = engine.update(_results("s1", 0.70), _context())
    assert update.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def test_sustained_moderate_high_ticks_eventually_reach_high() -> None:
    engine = RiskFusionEngine()
    update = None
    for _ in range(10):
        update = engine.update(_results("s1", 0.85), _context())
    assert update.risk_level == RiskLevel.HIGH


def test_blocklisted_context_raises_score_and_adds_reason() -> None:
    engine = RiskFusionEngine()
    plain = engine.update(_results("s1", 0.5), _context(blocklisted=False))

    engine2 = RiskFusionEngine()
    flagged = engine2.update(_results("s1", 0.5), _context(blocklisted=True))

    assert flagged.score >= plain.score
    assert ReasonCode.CONTEXT_HIGH_RISK in flagged.reasons


def test_independent_streams_keep_independent_state() -> None:
    engine = RiskFusionEngine()
    for _ in range(5):
        engine.update(_results("stream-a", 0.9), _context())
    fresh = engine.update(_results("stream-b", 0.1), _context())
    assert fresh.score < 50
