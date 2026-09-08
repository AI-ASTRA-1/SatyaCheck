"""Check 1 of 4: machine fingerprints. Is the waveform synthetic.

Implements contracts.checks.Check. Emits a MachineFingerprintSignal plus the
evidence that justifies it, never a final security verdict. A model error is
CheckStatus.FAILED with no signal, so a failure degrades to "no warning". Too
little audio is CheckStatus.SKIPPED, which is the normal state at the start of a
call.

The check does not enforce the 180 ms stage 04 budget. It records its own
latency_ms against it; the runner owns the deadline.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime

from contracts.checks import (
    CheckName,
    CheckResult,
    CheckStatus,
    EvidenceItem,
    MachineFingerprintSignal,
    ReasonCode,
)
from contracts.context import CallContext
from contracts.pipeline import CANONICAL_SAMPLE_RATE, CanonicalAudioBatch

from .scorer import SyntheticScorer

#: Below this the window cannot support a score at all.
DEFAULT_MIN_WINDOW_MS = 1000

#: Between MIN and this, a score is emitted with caveats (CheckStatus.DEGRADED).
DEFAULT_DEGRADED_WINDOW_MS = 3000

#: Which reason code labels the evidence. This is an EVIDENCE LABELLING cut point,
#: not a policy threshold and not a decision. synthetic_probability is the output
#: the risk engine consumes; the reason code is a human-readable label attached to
#: it, and what a score triggers is per deployment.
DEFAULT_EVIDENCE_THRESHOLD = 0.5

# All three numbers above are provisional. They are configuration, not measured
# results, and none of them has been calibrated yet. Calibration on unseen data
# revisits them; until then 0.5 on an uncalibrated score means very little.


class MachineFingerprintCheck:
    """XLS-R + AASIST check. Model-agnostic: the model plugs in as a SyntheticScorer."""

    name = CheckName.MACHINE_FINGERPRINT

    def __init__(
        self,
        scorer: SyntheticScorer | None = None,
        *,
        min_window_ms: int = DEFAULT_MIN_WINDOW_MS,
        degraded_window_ms: int = DEFAULT_DEGRADED_WINDOW_MS,
        evidence_threshold: float = DEFAULT_EVIDENCE_THRESHOLD,
    ) -> None:
        self._scorer = scorer
        self._min_window_ms = min_window_ms
        self._degraded_window_ms = degraded_window_ms
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

        if self._scorer is None:
            return self._failed(batch, "no scorer configured", started)

        try:
            probability = float(self._scorer.score(batch.pcm_s16le, CANONICAL_SAMPLE_RATE))
        except Exception as exc:  # noqa: BLE001 - deliberate: a model failure is never a verdict
            return self._failed(batch, f"scorer raised {type(exc).__name__}", started)

        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            return self._failed(batch, "scorer returned a value outside [0, 1]", started)

        reason = (
            ReasonCode.FINGERPRINT_SYNTHETIC
            if probability >= self._evidence_threshold
            else ReasonCode.FINGERPRINT_GENUINE
        )
        evidence = [
            self._evidence(batch, reason, f"synthetic_probability {probability:.3f}", started)
        ]

        status = CheckStatus.OK
        if window_ms < self._degraded_window_ms:
            status = CheckStatus.DEGRADED
            evidence.append(
                self._evidence(
                    batch,
                    ReasonCode.DEGRADED_CHECK,
                    f"short window {window_ms} ms below {self._degraded_window_ms} ms",
                    started,
                )
            )

        return self._result(
            batch,
            status,
            MachineFingerprintSignal(synthetic_probability=probability),
            evidence,
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
        # detail is built only from this check's own numbers. Nothing from
        # CallContext reaches it; caller and callee numbers are PII and
        # EvidenceItem.detail is specified non-PII.
        return EvidenceItem(
            reason_code=reason_code,
            detail=detail,
            model=self._scorer.model_name if self._scorer is not None else None,
            model_version=self._scorer.model_version if self._scorer is not None else None,
            window_started_at=batch.capture_started_at,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _result(
        self,
        batch: CanonicalAudioBatch,
        status: CheckStatus,
        signal: MachineFingerprintSignal | None,
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
