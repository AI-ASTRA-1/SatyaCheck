"""Stage 05: risk fusion.

Combines the two implemented checks plus CallContext into one RiskUpdate per
tick. Per R2.md, fusion must not trigger on a single instantaneous score: an EMA
smooths the score across consecutive ticks for a stream, with a same-tick
override when the raw reading alone is high-severity enough to warrant immediate
escalation.

Two rules decide how the checks combine, both set by the team on 2026-09-09:

**1. The transcript dominates the score, 85 to 15.** A scam script is the
stronger evidence that a call is dangerous. It is also the signal we can
currently trust more: the fingerprint model is out of domain on real phone audio
and converges toward 1.0 on genuine speech, so giving it the majority of the
weight produced a critical verdict on every real call.

**2. The transcript never touches the verdict.** `RiskVerdict` answers "is this
voice synthetic", and words cannot establish that. A human running a scam script
is a real voice and a high risk, which comes out here as a high score with
verdict GENUINE. Letting a transcript declare a voice synthetic would make the
field mean nothing.

**3. A missing script signal is scored two different ways, on purpose.** Before
check 4 has ever answered for a stream, the call is not scoreable yet: the plain
weighted sum applies, the fingerprint contributes at most its own 0.15, and the
score stays inside the LOW band, so no warning is raised on a call that nothing
has judged. Once check 4 has answered at least once, a later absence is a real
failure, and the score renormalises onto the fingerprint alone rather than
multiplying it by 0.15, because a broken check must not make a call look safe.

Both cases mark the update degraded, so neither is silent.
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
    SttLlmSignal,
)
from contracts.context import CallContext
from contracts.risk import DEFAULT_BAND_MAPPING, RiskLevel, RiskUpdate, RiskVerdict

EMA_ALPHA = 0.4
HIGH_SEVERITY_OVERRIDE = 90

#: Relative weight of each check in the 0-100 score. Named, not inlined, because
#: AGENTS.md makes policy per deployment: a bank and a family want different
#: balances, and these are the knob.
SCRIPT_WEIGHT = 0.85
FINGERPRINT_WEIGHT = 0.15

#: The fingerprint probability at or above which the voice is called synthetic.
VERDICT_THRESHOLD = 0.5

#: How many scoring ticks a stream waits for check 4's first answer before
#: giving up on it. Ticks are roughly one per second, and the transcript worker
#: needs a few seconds of buffer plus a pass, so this is generous.
#:
#: It is bounded on purpose. Suppressing warnings until check 4 reports is
#: correct while it is starting up, and catastrophic if it never reports at all:
#: a stream whose check 4 is broken or absent would never warn about anything.
#: After the grace period the stream is treated as having lost the check, which
#: renormalises onto the fingerprint and can warn again.
WARMUP_GRACE_TICKS = 20


@dataclass(frozen=True)
class _Reading:
    """One check's contribution: a 0-1 value plus the reasons behind it."""

    value: float | None
    reasons: list[ReasonCode]
    contributed: bool


def _fingerprint_reading(results: ChecksBatchResult) -> _Reading:
    result = next(
        (r for r in results.results if r.check == CheckName.MACHINE_FINGERPRINT), None
    )
    if result is None or result.status not in (CheckStatus.OK, CheckStatus.DEGRADED):
        reason = (
            ReasonCode.INSUFFICIENT_AUDIO
            if result is None or result.status == CheckStatus.SKIPPED
            else ReasonCode.DEGRADED_CHECK
        )
        return _Reading(None, [reason], False)

    signal = result.signal
    if not isinstance(signal, MachineFingerprintSignal):
        return _Reading(None, [ReasonCode.DEGRADED_CHECK], False)

    reasons = [item.reason_code for item in result.evidence] or [
        ReasonCode.FINGERPRINT_SYNTHETIC
        if signal.synthetic_probability >= VERDICT_THRESHOLD
        else ReasonCode.FINGERPRINT_GENUINE
    ]
    return _Reading(signal.synthetic_probability, reasons, True)


def _script_reading(results: ChecksBatchResult) -> _Reading:
    """Check 4's contribution. Absent is normal early in a call, not an error.

    The result is put here by the caller from the out-of-band transcript worker
    cache, and only when it is fresh. A stale one never reaches this function,
    so "not present" already means "no recent answer".
    """
    result = next((r for r in results.results if r.check == CheckName.STT_LLM), None)
    if result is None or result.status not in (CheckStatus.OK, CheckStatus.DEGRADED):
        return _Reading(None, [ReasonCode.SCRIPT_RISK_ABSENT], False)

    signal = result.signal
    if not isinstance(signal, SttLlmSignal) or signal.script_risk is None:
        return _Reading(None, [ReasonCode.SCRIPT_RISK_ABSENT], False)

    reasons = [item.reason_code for item in result.evidence] or [
        ReasonCode.SCRIPT_RISK_HIGH
        if signal.script_risk >= 0.5
        else ReasonCode.SCRIPT_RISK_ABSENT
    ]
    return _Reading(signal.script_risk, reasons, True)


def _verdict_for(fingerprint: _Reading) -> RiskVerdict:
    """Audio only. See rule 2 in the module docstring."""
    if fingerprint.value is None:
        return RiskVerdict.UNKNOWN
    return (
        RiskVerdict.SYNTHETIC
        if fingerprint.value >= VERDICT_THRESHOLD
        else RiskVerdict.GENUINE
    )


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
    #: Has check 4 ever produced a signal for this stream? Distinguishes "not
    #: ready yet", early in a call, from "was working and has now failed". The
    #: two must not score the same way. See `update`.
    script_has_reported: bool = False


class RiskFusionEngine:
    """Implements stage 05: ChecksBatchResult + CallContext -> RiskUpdate."""

    def __init__(
        self,
        ema_alpha: float = EMA_ALPHA,
        high_severity_override: int = HIGH_SEVERITY_OVERRIDE,
        band_mapping: dict[int, RiskLevel] | None = None,
        script_weight: float = SCRIPT_WEIGHT,
        fingerprint_weight: float = FINGERPRINT_WEIGHT,
        warmup_grace_ticks: int = WARMUP_GRACE_TICKS,
    ) -> None:
        self._warmup_grace_ticks = warmup_grace_ticks
        self._ema_alpha = ema_alpha
        self._high_severity_override = high_severity_override
        self._band_mapping = band_mapping if band_mapping is not None else DEFAULT_BAND_MAPPING
        self._script_weight = script_weight
        self._fingerprint_weight = fingerprint_weight
        self._state: dict[str, _StreamFusionState] = {}

    def update(self, results: ChecksBatchResult, context: CallContext) -> RiskUpdate:
        script = _script_reading(results)
        fingerprint = _fingerprint_reading(results)

        state = self._state.setdefault(results.stream_id, _StreamFusionState())
        if script.contributed:
            state.script_has_reported = True

        # How a missing script signal is scored depends on whether check 4 has
        # ever answered for this stream, and the difference is the whole point:
        #
        # - Never answered (the first seconds of a call, while the transcript
        #   worker fills its buffer): the call is not scoreable yet. Keep the
        #   plain weighted sum, so the fingerprint contributes at most its own
        #   0.15 and the score stays inside the LOW band. No warning is raised
        #   on a call nothing has actually judged.
        # - Answered before and now missing (stale, failed, API down): a real
        #   failure. Renormalise onto the fingerprint alone, because a broken
        #   check must not make a call look safe.
        #
        # Both are marked degraded, so neither is silent.
        #
        # The wait is bounded by WARMUP_GRACE_TICKS. A check 4 that never
        # answers, because it failed to build or crashes on every pass, would
        # otherwise suppress every warning for the whole call.
        warming_up = (
            not state.script_has_reported
            and script.value is None
            and state.ticks_seen < self._warmup_grace_ticks
        )

        parts: list[tuple[float, float]] = []
        if script.value is not None:
            parts.append((self._script_weight, script.value))
        if fingerprint.value is not None:
            parts.append((self._fingerprint_weight, fingerprint.value))

        if not parts:
            raw_score = 0
        elif warming_up:
            raw_score = round(sum(w * v for w, v in parts) * 100)
        else:
            total_weight = sum(w for w, _ in parts)
            raw_score = round(sum(w * v for w, v in parts) / total_weight * 100)

        verdict = _verdict_for(fingerprint)
        reasons = [*script.reasons, *fingerprint.reasons]
        contributing = [
            name
            for name, reading in (
                (CheckName.STT_LLM, script),
                (CheckName.MACHINE_FINGERPRINT, fingerprint),
            )
            if reading.contributed
        ]

        adjusted_score, context_reason = _context_adjustment(raw_score, context)
        if context_reason is not None:
            reasons = [*reasons, context_reason]

        state.ticks_seen += 1
        if adjusted_score >= self._high_severity_override:
            state.ema_score = float(adjusted_score)
        else:
            state.ema_score = self._ema_alpha * adjusted_score + (1 - self._ema_alpha) * state.ema_score

        final_score = round(min(100.0, max(0.0, state.ema_score)))
        risk_level = _band_for(final_score, self._band_mapping)

        degraded = list(results.degraded)
        if not script.contributed and CheckName.STT_LLM not in degraded:
            # The script check carries most of the weight, so its absence changes
            # what the number means. Say so rather than leaving it inferred.
            degraded.append(CheckName.STT_LLM)

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
            degraded_checks=degraded,
        )
