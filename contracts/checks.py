"""The four AI checks. Models emit evidence; the risk engine owns the decision.

No module here returns a final security verdict. Each check returns CheckResult:
structured signals plus the evidence that justifies them. The runner (ml/runner)
handles stage 04 orchestration: a parallel fan-out on a COPY of the audio with a
shared 180 ms deadline.

Round 1 shape: speaker_identity carries a no_enrolment state because the Family
Vault is Round 2. That state contributes neutral evidence, never a verdict. Check 4
(STT then LLM) is Round 1 as an evidence channel producing script_risk; a
product-level transcript warning feature is Round 2 and is not part of the app
contract.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Protocol, Union

from pydantic import BaseModel, Field

from .context import CallContext
from .pipeline import CanonicalAudioBatch


class CheckName(str, Enum):
    MACHINE_FINGERPRINT = "machine_fingerprint"  # XLS-R + AASIST
    SPEAKER_IDENTITY = "speaker_identity"  # ECAPA-TDNN
    PROSODY = "prosody"  # openSMILE
    STT_LLM = "stt_llm"  # speech-to-text then language model


class CheckStatus(str, Enum):
    OK = "ok"  # produced a signal
    DEGRADED = "degraded"  # ran with caveats (very short window)
    FAILED = "failed"  # model error -> treated as no signal, NEVER a verdict
    SKIPPED = "skipped"  # not enough audio yet; scores start UNKNOWN / LOW


class ReasonCode(str, Enum):
    """Stable, non-PII reason strings the risk engine folds into the score."""

    FINGERPRINT_SYNTHETIC = "fingerprint_synthetic"
    FINGERPRINT_GENUINE = "fingerprint_genuine"
    VOICEPRINT_NO_ENROLMENT = "voiceprint_no_enrolment"
    VOICEPRINT_NO_MATCH = "voiceprint_no_match"
    VOICEPRINT_MATCH = "voiceprint_match"
    VOICEPRINT_MATCH_SYNTHETIC = "voiceprint_match_synthetic"
    PROSODY_ANOMALY = "prosody_anomaly"
    PROSODY_NORMAL = "prosody_normal"
    SCRIPT_RISK_HIGH = "script_risk_high"
    SCRIPT_RISK_ABSENT = "script_risk_absent"
    CONTEXT_HIGH_RISK = "context_high_risk"
    CONTEXT_LOW_RISK = "context_low_risk"
    INSUFFICIENT_AUDIO = "insufficient_audio"
    DEGRADED_CHECK = "degraded_check"


class EvidenceItem(BaseModel):
    """One piece of evidence justifying a signal. Short and non-PII."""

    reason_code: ReasonCode
    detail: str | None = None
    model: str | None = None
    model_version: str | None = None
    window_started_at: datetime | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)


class MachineFingerprintSignal(BaseModel):
    kind: Literal["machine_fingerprint"] = "machine_fingerprint"
    synthetic_probability: float = Field(ge=0.0, le=1.0)


class SpeakerIdentitySignal(BaseModel):
    kind: Literal["speaker_identity"] = "speaker_identity"

    # Round 1 has no enrolment store, so no_enrolment is the expected state and is
    # neutral. match_synthetic is the dangerous case: a clone of an enrolled person.
    match_status: Literal["no_enrolment", "no_match", "match_synthetic", "match_human"]
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class ProsodySignal(BaseModel):
    kind: Literal["prosody"] = "prosody"
    anomaly_score: float = Field(ge=0.0, le=1.0)


class SttLlmSignal(BaseModel):
    kind: Literal["stt_llm"] = "stt_llm"
    script_risk: float | None = Field(default=None, ge=0.0, le=1.0)
    script_category: str | None = None

    # The transcript itself is an in-memory working artifact of THIS check only.
    # It MUST NOT appear in EvidenceItem, CheckResult, RiskUpdate or AlertRecord,
    # and is discarded when the check returns. No transcript at rest.


Signal = Annotated[
    Union[
        MachineFingerprintSignal,
        SpeakerIdentitySignal,
        ProsodySignal,
        SttLlmSignal,
    ],
    Field(discriminator="kind"),
]


class CheckResult(BaseModel):
    """A check's output. Models emit evidence; the risk engine owns the decision."""

    check: CheckName
    status: CheckStatus
    signal: Signal | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    processed_at: datetime
    window_ms: int = 0


class Check(Protocol):
    """Implemented by each of the four checks in ml/checks."""

    name: CheckName

    def run(self, batch: CanonicalAudioBatch, context: CallContext) -> CheckResult: ...


class CheckRunner(Protocol):
    """Stage 04. Fans out to all four checks in parallel on a COPY of the batch,
    enforces the shared 180 ms deadline, marks stragglers FAILED or SKIPPED,
    returns one ChecksBatchResult. Implemented in ml/runner."""

    def run_checks(
        self, batch: CanonicalAudioBatch, context: CallContext
    ) -> ChecksBatchResult: ...


class ChecksBatchResult(BaseModel):
    """One stage 04 run across all four checks on one window."""

    stream_id: str
    call_id: str
    started_at: datetime
    batch_sequence: int
    results: list[CheckResult] = Field(default_factory=list)
    audio_window_ms: int = 0
    degraded: list[CheckName] = Field(default_factory=list)