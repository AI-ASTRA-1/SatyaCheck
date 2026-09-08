"""Check 4 of 4: what is being said. Is this a scam script.

Implements contracts.checks.Check. Round 1 evidence channel only: it emits an
SttLlmSignal (script_risk, script_category) plus the reason that labels it, never
a final security verdict. A product-level transcript warning is Round 2.

The transcript never leaves `run()`. It is transcribed from the batch, passed to
`analyze()`, and dropped when `run()` returns. It is not on the signal, the
evidence, the result, or any log. No transcript at rest.

A transcriber or model failure is CheckStatus.FAILED with no signal, so it
degrades to "no warning". Too little audio, or a transcript too thin to judge, is
CheckStatus.SKIPPED. The check records its own latency_ms; the runner owns the
180 ms stage 04 deadline.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
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

from .asr import Transcriber
from .llm import ScriptLLM, analyze

#: Below this the window is too short to hold a scam pitch worth transcribing.
DEFAULT_MIN_WINDOW_MS = 3000

#: script_risk at or above this labels the evidence SCRIPT_RISK_HIGH rather than
#: SCRIPT_RISK_ABSENT. An evidence-labelling cut point, not a policy threshold and
#: not a decision; script_risk is the output the risk engine consumes. Provisional
#: and uncalibrated.
DEFAULT_EVIDENCE_THRESHOLD = 0.5


class SttLlmCheck:
    """STT then tactic analysis. Model-agnostic: STT plugs in as a Transcriber,
    the optional language model as a ScriptLLM."""

    name = CheckName.STT_LLM

    def __init__(
        self,
        transcriber: Transcriber | None = None,
        llm: ScriptLLM | Sequence[ScriptLLM] | None = None,
        *,
        min_window_ms: int = DEFAULT_MIN_WINDOW_MS,
        evidence_threshold: float = DEFAULT_EVIDENCE_THRESHOLD,
    ) -> None:
        self._transcriber = transcriber
        self._llm = llm
        self._min_window_ms = min_window_ms
        self._evidence_threshold = evidence_threshold

    def run(self, batch: CanonicalAudioBatch, context: CallContext) -> CheckResult:
        started = time.perf_counter()
        window_ms = batch.window_ms

        if window_ms < self._min_window_ms:
            return self._result(
                batch,
                CheckStatus.SKIPPED,
                None,
                [
                    self._evidence(
                        batch,
                        ReasonCode.INSUFFICIENT_AUDIO,
                        f"window {window_ms} ms below minimum {self._min_window_ms} ms",
                        started,
                    )
                ],
            )

        if self._transcriber is None:
            return self._failed(batch, "no transcriber configured", started)

        try:
            transcript = self._transcriber.transcribe(
                batch.pcm_s16le, CANONICAL_SAMPLE_RATE
            )
        except Exception as exc:  # noqa: BLE001 - a model failure is never a verdict
            return self._failed(batch, f"transcriber raised {type(exc).__name__}", started)

        analysis = analyze(transcript, self._llm)
        # transcript is not referenced past this line and is not retained.

        if analysis.source == "none":
            return self._result(
                batch,
                CheckStatus.SKIPPED,
                None,
                [
                    self._evidence(
                        batch,
                        ReasonCode.INSUFFICIENT_AUDIO,
                        "transcript too thin to judge",
                        started,
                    )
                ],
            )

        reason = (
            ReasonCode.SCRIPT_RISK_HIGH
            if analysis.intent >= self._evidence_threshold
            else ReasonCode.SCRIPT_RISK_ABSENT
        )
        category = analysis.script_category()
        detail = f"script_risk {analysis.intent:.3f} source={analysis.source}"
        if category is not None:
            detail += f" top={category}"

        return self._result(
            batch,
            CheckStatus.OK,
            SttLlmSignal(script_risk=analysis.intent, script_category=category),
            [self._evidence(batch, reason, detail, started)],
        )

    def _failed(
        self, batch: CanonicalAudioBatch, detail: str, started: float
    ) -> CheckResult:
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
        # detail is built only from this check's own numbers and fixed labels.
        # Nothing from CallContext or the transcript reaches it.
        tr = self._transcriber
        return EvidenceItem(
            reason_code=reason_code,
            detail=detail,
            model=tr.model_name if tr is not None else None,
            model_version=tr.model_version if tr is not None else None,
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
