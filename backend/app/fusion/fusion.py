"""Stage 05: risk fusion.

Reads the machine_fingerprint result only (the sole implemented check) plus
CallContext, and produces one RiskUpdate per tick. Per R2.md, fusion must not
trigger on a single instantaneous score: an EMA smooths the score across
consecutive ticks for a stream, with a same-tick override when the raw reading
alone is high-severity enough to warrant immediate escalation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from contracts.checks import (
    CheckName,
    ChecksBatchResult,
    CheckStatus,
    MachineFingerprintSignal,
    ReasonCode,
)
from contracts.context import CallContext
from contracts.risk import DEFAULT_BAND_MAPPING, RiskLevel, RiskUpdate, RiskVerdict

EMA_ALPHA = 0.4
HIGH_SEVERITY_OVERRIDE = 90


def _raw_score(results: ChecksBatchResult) -> tuple[int, RiskVerdict, list[ReasonCode], list[CheckName]]:
    fingerprint = next(
        (r for r in results.results if r.check == CheckName.MACHINE_FINGERPRINT), None
    )
    if fingerprint is None or fingerprint.status not in (CheckStatus.OK, CheckStatus.DEGRADED):
        reason = (
            ReasonCode.INSUFFICIENT_AUDIO
            if fingerprint is None or fingerprint.status == CheckStatus.SKIPPED
            else ReasonCode.DEGRADED_CHECK
        )
        return 0, RiskVerdict.UNKNOWN, [reason], []

    signal = fingerprint.signal
    if not isinstance(signal, MachineFingerprintSignal):
        return 0, RiskVerdict.UNKNOWN, [ReasonCode.DEGRADED_CHECK], []

    score = round(signal.synthetic_probability * 100)
    verdict = RiskVerdict.SYNTHETIC if signal.synthetic_probability >= 0.5 else RiskVerdict.GENUINE
    reasons = [item.reason_code for item in fingerprint.evidence] or [
        ReasonCode.FINGERPRINT_SYNTHETIC if verdict == RiskVerdict.SYNTHETIC else ReasonCode.FINGERPRINT_GENUINE
    ]
    return score, verdict, reasons, [CheckName.MACHINE_FINGERPRINT]


def _context_adjustment(raw_score: int, context: CallContext) -> tuple[int, ReasonCode | None]:
    """The concrete place CallContext enters fusion, alongside the check signals."""
    reputation = context.number_reputation
    if reputation is not None and (reputation.blocklisted or reputation.reported_before):
        return min(100, raw_score + 15), ReasonCode.CONTEXT_HIGH_RISK
    return raw_score, None


def _band_for(score: int, mapping: dict[int, RiskLevel]) -> RiskLevel:
    level = RiskLevel.LOW
    for threshold in sorted(mapping):
        if score >= threshold:
            level = mapping[threshold]
    return level


@dataclass
class _StreamFusionState:
    ema_score: float = 0.0
    ticks_seen: int = 0


class RiskFusionEngine:
    """Implements stage 05: ChecksBatchResult + CallContext -> RiskUpdate."""

    def __init__(
        self,
        ema_alpha: float = EMA_ALPHA,
        high_severity_override: int = HIGH_SEVERITY_OVERRIDE,
        band_mapping: dict[int, RiskLevel] | None = None,
    ) -> None:
        self._ema_alpha = ema_alpha
        self._high_severity_override = high_severity_override
        self._band_mapping = band_mapping if band_mapping is not None else DEFAULT_BAND_MAPPING
        self._state: dict[str, _StreamFusionState] = {}

    def update(self, results: ChecksBatchResult, context: CallContext) -> RiskUpdate:
        raw_score, verdict, reasons, contributing = _raw_score(results)
        adjusted_score, context_reason = _context_adjustment(raw_score, context)
        if context_reason is not None:
            reasons = [*reasons, context_reason]

        state = self._state.setdefault(results.stream_id, _StreamFusionState())
        state.ticks_seen += 1
        if adjusted_score >= self._high_severity_override:
            state.ema_score = float(adjusted_score)
        else:
            state.ema_score = self._ema_alpha * adjusted_score + (1 - self._ema_alpha) * state.ema_score

        final_score = round(min(100.0, max(0.0, state.ema_score)))
        risk_level = _band_for(final_score, self._band_mapping)

        return RiskUpdate(
            stream_id=results.stream_id,
            call_id=results.call_id,
            sequence=state.ticks_seen,
            timestamp=datetime.now(UTC),
            score=final_score,
            verdict=verdict,
            risk_level=risk_level,
            confidence=len(contributing) / len(CheckName),
            reasons=reasons,
            contributing_checks=contributing,
            degraded_checks=list(results.degraded),
        )
