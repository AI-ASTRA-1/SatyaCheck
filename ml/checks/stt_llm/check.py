"""Check 4 of 4: what is being said. Is this a scam script.

Implements `contracts.checks.Check`, the same protocol as the other three, so
the out-of-band worker in `backend/app/pipeline/` can call it exactly the way
`DefaultCheckRunner` calls the fingerprint check.

It does NOT run inside the 180 ms stage 04 budget, and it is not meant to.
Transcription plus a language model takes seconds, so a worker runs this on a
rolling buffer on its own cadence and fusion reads the most recent result. That
decision is recorded in `docs/interfaces.md`.

Status transitions:

| Condition | CheckStatus |
|---|---|
| window below min_window_ms | skipped, no signal, insufficient_audio |
| no transcriber or no scorer configured | failed, no signal |
| transcriber or scorer raised | failed, no signal |
| no speech found in the window | ok, signal with script_risk 0.0 |
| otherwise | ok, signal present |

**The transcript never leaves this method.** It is produced, scored, and
discarded when `run` returns. Evidence carries the number, the category and
which scorer produced it, never the words. `contracts/checks.py` requires this.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from contracts.checks import (
    CheckName,
    CheckResult,
    CheckStatus,
    EvidenceItem,
    ReasonCode,
    SttLlmSignal,
)
from contracts.context import CallContext
from contracts.pipeline import CANONICAL_SAMPLE_RATE, CanonicalAudioBatch

from .scorer import CATEGORY_NONE, ScriptScorer
from .transcriber import Transcriber

#: Below this a window carries too few words to judge a script.
DEFAULT_MIN_WINDOW_MS = 3000

#: At or above this, evidence is labelled SCRIPT_RISK_HIGH. An evidence
#: labelling cut point, not a policy threshold: the risk engine owns what a
#: score triggers, and this number is provisional and uncalibrated.
DEFAULT_SCRIPT_RISK_THRESHOLD = 0.5


class SttLlmCheck:
    """Speech to text, then a scam-script score. Model-agnostic on both halves."""

    name = CheckName.STT_LLM

    def __init__(
        self,
        transcriber: Transcriber | None = None,
        scorer: ScriptScorer | None = None,
        *,
        min_window_ms: int = DEFAULT_MIN_WINDOW_MS,
        script_risk_threshold: float = DEFAULT_SCRIPT_RISK_THRESHOLD,
    ) -> None:
        self._transcriber = transcriber
        self._scorer = scorer
        self._min_window_ms = min_window_ms
        self._threshold = script_risk_threshold

    def run(self, batch: CanonicalAudioBatch, context: CallContext) -> CheckResult:
        started = time.perf_counter()

        if batch.window_ms < self._min_window_ms:
            return self._result(
                batch,
                CheckStatus.SKIPPED,
                None,
                [
                    self._evidence(
                        batch,
                        ReasonCode.INSUFFICIENT_AUDIO,
                        f"window {batch.window_ms} ms below minimum {self._min_window_ms} ms",
                        started,
                    )
                ],
            )

        if self._transcriber is None or self._scorer is None:
            return self._failed(batch, "no transcriber or scorer configured", started)

        try:
            transcript = self._transcriber.transcribe(batch.pcm_s16le, CANONICAL_SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001 - a model failure is never a verdict
            return self._failed(batch, f"transcriber raised {type(exc).__name__}", started)

        try:
            assessment = self._scorer.score(transcript)
        except Exception as exc:  # noqa: BLE001 - see above
            return self._failed(batch, f"scorer raised {type(exc).__name__}", started)
        finally:
            # Explicit, so the intent survives any later edit: the words are a
            # working artifact of this call and go no further.
            del transcript

        if not 0.0 <= assessment.script_risk <= 1.0:
            return self._failed(batch, "scorer returned script_risk outside [0, 1]", started)

        reason = (
            ReasonCode.SCRIPT_RISK_HIGH
            if assessment.script_risk >= self._threshold
            else ReasonCode.SCRIPT_RISK_ABSENT
        )
        detail = (
            f"script_risk {assessment.script_risk:.3f}; "
            f"category {assessment.category or CATEGORY_NONE}; "
            f"scorer {assessment.scorer}"
        )
        return self._result(
            batch,
            CheckStatus.OK,
            SttLlmSignal(
                script_risk=assessment.script_risk,
                script_category=assessment.category,
            ),
            [self._evidence(batch, reason, detail, started)],
        )

    def _failed(self, batch: CanonicalAudioBatch, detail: str, started: float) -> CheckResult:
        return self._result(
            batch,
            CheckStatus.FAILED,
            None,
            [self._evidence(batch, ReasonCode.DEGRADED_CHECK, detail, started)],
        )

    def _evidence(
        self,
        batch: CanonicalAudioBatch,
        reason_code: ReasonCode,
        detail: str,
        started: float,
    ) -> EvidenceItem:
        # detail is built from this check's own numbers and labels only. No
        # transcript text, and nothing from CallContext, which carries PII.
        return EvidenceItem(
            reason_code=reason_code,
            detail=detail,
            model=self._transcriber.model_name if self._transcriber is not None else None,
            model_version=self._scorer.name if self._scorer is not None else None,
            window_started_at=batch.capture_started_at,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _result(
        self,
        batch: CanonicalAudioBatch,
        status: CheckStatus,
        signal: SttLlmSignal | None,
        evidence: list[EvidenceItem],
    ) -> CheckResult:
        return CheckResult(
            check=self.name,
            status=status,
            signal=signal,
            evidence=evidence,
            processed_at=datetime.now(UTC),
            window_ms=batch.window_ms,
        )
