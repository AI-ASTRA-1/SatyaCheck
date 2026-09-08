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
    SttLlmSignal,
)
from contracts.context import CallContext, NumberReputation
from contracts.risk import RiskLevel, RiskVerdict


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


# These three are about the EMA and the high-severity override, not about check 4.
# They predate it and drive a fingerprint-only batch, which now spends its first
# ticks in warm-up suppression, so the grace is turned off to isolate what they
# actually test. Warm-up has its own tests at the end of this file.


def test_single_high_severity_tick_escalates_immediately() -> None:
    engine = RiskFusionEngine(warmup_grace_ticks=0)
    update = engine.update(_results("s1", 0.95), _context())
    assert update.risk_level == RiskLevel.CRITICAL


def test_single_moderate_tick_does_not_alone_reach_high() -> None:
    engine = RiskFusionEngine(warmup_grace_ticks=0)
    update = engine.update(_results("s1", 0.70), _context())
    assert update.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def test_sustained_moderate_high_ticks_eventually_reach_high() -> None:
    engine = RiskFusionEngine(warmup_grace_ticks=0)
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


# --- Check 4 weighting (script 0.85 / fingerprint 0.15), added 2026-09-09 ---


def _results_with_script(
    stream_id: str,
    probability: float | None,
    script_risk: float | None,
    *,
    script_status: CheckStatus = CheckStatus.OK,
    call_id: str = "c1",
) -> ChecksBatchResult:
    """A batch carrying both implemented checks.

    `probability=None` or `script_risk=None` leaves that check absent the way the
    pipeline leaves it absent: SKIPPED with no signal.
    """
    now = datetime.now(UTC)
    results: list[CheckResult] = []

    if probability is None:
        results.append(
            CheckResult(
                check=CheckName.MACHINE_FINGERPRINT,
                status=CheckStatus.SKIPPED,
                processed_at=now,
                window_ms=0,
            )
        )
    else:
        results.append(
            CheckResult(
                check=CheckName.MACHINE_FINGERPRINT,
                status=CheckStatus.OK,
                signal=MachineFingerprintSignal(synthetic_probability=probability),
                processed_at=now,
                window_ms=1000,
            )
        )

    if script_risk is None:
        results.append(
            CheckResult(
                check=CheckName.STT_LLM, status=CheckStatus.SKIPPED, processed_at=now, window_ms=0
            )
        )
    else:
        results.append(
            CheckResult(
                check=CheckName.STT_LLM,
                status=script_status,
                signal=SttLlmSignal(script_risk=script_risk, script_category="payment_instruction"),
                processed_at=now,
                window_ms=10000,
            )
        )

    results.extend(
        CheckResult(check=name, status=CheckStatus.SKIPPED, processed_at=now, window_ms=0)
        for name in (CheckName.SPEAKER_IDENTITY, CheckName.PROSODY)
    )
    return ChecksBatchResult(
        stream_id=stream_id,
        call_id=call_id,
        started_at=now,
        batch_sequence=0,
        results=results,
        audio_window_ms=1000,
    )


def _settle(engine: RiskFusionEngine, results: ChecksBatchResult, ticks: int = 20):
    """Drive the same reading until the EMA converges, and return the last update.

    Fusion deliberately smooths across ticks, so a single call returns a fraction
    of the weighted score. These tests are about the weighting, so they let the
    EMA settle rather than reaching past it.
    """
    update = None
    for _ in range(ticks):
        update = engine.update(results, _context())
    assert update is not None
    return update


def test_script_dominates_the_score_over_the_fingerprint() -> None:
    # script 0.0 with a fingerprint screaming 1.0 settles near 0.15 * 100 = 15,
    # which is the false positive from the 2026-09-09 live call being contained.
    engine = RiskFusionEngine()
    update = _settle(engine, _results_with_script("s-quiet", 1.0, 0.0))
    assert 13 <= update.score <= 17
    assert update.risk_level is RiskLevel.LOW


def test_high_script_risk_drives_the_score_up_on_a_clean_fingerprint() -> None:
    engine = RiskFusionEngine()
    update = _settle(engine, _results_with_script("s-script", 0.0, 1.0))
    assert 83 <= update.score <= 87


def test_verdict_follows_the_audio_not_the_transcript() -> None:
    """A human reading a scam script is high risk AND a genuine voice."""
    engine = RiskFusionEngine()
    update = _settle(engine, _results_with_script("s-human", 0.05, 1.0))
    assert update.score >= 80
    assert update.verdict is RiskVerdict.GENUINE
    assert ReasonCode.SCRIPT_RISK_HIGH in update.reasons


def test_a_clone_saying_nothing_suspicious_is_still_flagged_synthetic() -> None:
    engine = RiskFusionEngine()
    update = engine.update(_results_with_script("s-clone", 0.99, 0.0), _context())
    assert update.verdict is RiskVerdict.SYNTHETIC


def test_absent_script_renormalises_onto_the_fingerprint_and_marks_degraded() -> None:
    """A missing check must not read as a safe call.

    Without renormalising, a fingerprint of 1.0 with no script signal would score
    0.15 * 100 = 15 and look low risk precisely when a check has failed.
    """
    engine = RiskFusionEngine()
    # Report once so the stream is past warm-up: this is about losing a working
    # check, not about one that has not started yet.
    engine.update(_results_with_script("s-nostt", 1.0, 0.0), _context())
    for _ in range(20):
        update = engine.update(_results_with_script("s-nostt", 1.0, None), _context())
    assert update.score == 100
    assert CheckName.STT_LLM in update.degraded_checks
    assert ReasonCode.SCRIPT_RISK_ABSENT in update.reasons


def test_failed_script_check_is_treated_as_absent_not_as_zero_risk() -> None:
    engine = RiskFusionEngine()
    engine.update(_results_with_script("s-failstt", 1.0, 0.0), _context())  # past warm-up
    for _ in range(20):
        update = engine.update(
            _results_with_script("s-failstt", 1.0, 0.0, script_status=CheckStatus.FAILED),
            _context(),
        )
    assert update.score == 100
    assert CheckName.STT_LLM in update.degraded_checks


def test_neither_check_reporting_is_unknown_and_zero() -> None:
    engine = RiskFusionEngine()
    update = engine.update(_results_with_script("s-none", None, None), _context())
    assert update.score == 0
    assert update.verdict is RiskVerdict.UNKNOWN


def test_both_checks_contributing_raises_confidence() -> None:
    engine = RiskFusionEngine()
    one = engine.update(_results_with_script("s-c1", 0.4, None), _context())
    two = engine.update(_results_with_script("s-c2", 0.4, 0.4), _context())
    assert two.confidence > one.confidence
    assert set(two.contributing_checks) == {CheckName.MACHINE_FINGERPRINT, CheckName.STT_LLM}


# --- warm-up suppression, added 2026-09-09 ---


def test_no_warning_before_check_four_has_ever_reported() -> None:
    """A call nothing has judged yet must not raise a warning.

    The fingerprint pins at 1.0 on real phone audio, so without this the first
    seconds of every genuine call would render as CRITICAL while the transcript
    worker is still filling its buffer.
    """
    engine = RiskFusionEngine()
    for _ in range(20):
        update = engine.update(_results_with_script("s-warm", 1.0, None), _context())
    assert update.risk_level is RiskLevel.LOW
    assert update.score <= 15
    assert CheckName.STT_LLM in update.degraded_checks


def test_absence_after_a_successful_report_is_a_failure_not_a_warm_up() -> None:
    """Once check 4 has worked, losing it must not read as a safe call."""
    engine = RiskFusionEngine()
    # It reports once, so the stream is past warm-up.
    engine.update(_results_with_script("s-lost", 1.0, 0.0), _context())
    # Then it goes away: stale cache, dead worker, API down.
    for _ in range(20):
        update = engine.update(_results_with_script("s-lost", 1.0, None), _context())
    assert update.score == 100
    assert update.risk_level is not RiskLevel.LOW
    assert CheckName.STT_LLM in update.degraded_checks


def test_warm_up_state_is_per_stream() -> None:
    engine = RiskFusionEngine()
    engine.update(_results_with_script("s-a", 1.0, 0.0), _context())
    # A different stream has its own warm-up, so it is still suppressed.
    for _ in range(20):
        update = engine.update(_results_with_script("s-b", 1.0, None), _context())
    assert update.risk_level is RiskLevel.LOW


def test_a_real_scam_script_still_escalates_during_the_same_call() -> None:
    """Warm-up suppression must not swallow the signal it is waiting for."""
    engine = RiskFusionEngine()
    engine.update(_results_with_script("s-esc", 1.0, None), _context())  # warming up
    for _ in range(20):
        update = engine.update(_results_with_script("s-esc", 1.0, 0.95), _context())
    assert update.score >= 80
    assert update.risk_level is not RiskLevel.LOW


def test_suppression_is_bounded_when_check_four_never_reports() -> None:
    """A permanently broken check 4 must not silence warnings for the whole call.

    Suppressing until check 4 speaks is right while it is starting up and wrong
    if it never speaks: without a bound, a stream whose transcript worker failed
    to build would score every window LOW no matter what the audio was.
    """
    engine = RiskFusionEngine(warmup_grace_ticks=5)
    update = None
    for _ in range(30):
        update = engine.update(_results_with_script("s-never", 1.0, None), _context())
    assert update.score == 100
    assert update.risk_level is RiskLevel.CRITICAL
    assert CheckName.STT_LLM in update.degraded_checks


def test_within_the_grace_window_it_is_still_suppressed() -> None:
    engine = RiskFusionEngine(warmup_grace_ticks=50)
    update = None
    for _ in range(20):
        update = engine.update(_results_with_script("s-grace", 1.0, None), _context())
    assert update.risk_level is RiskLevel.LOW
