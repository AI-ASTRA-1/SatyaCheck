"""The app contract: what the backend sends the SATYACHECK app.

The app renders states, never thresholds. It maps RiskLevel to overlay visuals and
never computes a band from score; DEFAULT_BAND_MAPPING is the agreed fallback and
deployments override it in backend policy config, not in app code.

Continuous scoring: RiskUpdate is sent roughly once a second for the life of the
call, never a single decision at the start.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .checks import CheckName, ReasonCode

SCHEMA_VERSION = "1.0"


class RiskVerdict(str, Enum):
    GENUINE = "genuine"
    SYNTHETIC = "synthetic"
    UNKNOWN = "unknown"  # insufficient audio, or a model degraded


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# score -> first RiskLevel at or above it. App renders RiskLevel only.
DEFAULT_BAND_MAPPING: dict[int, RiskLevel] = {
    0: RiskLevel.LOW,
    40: RiskLevel.MEDIUM,
    70: RiskLevel.HIGH,
    90: RiskLevel.CRITICAL,
}


class SessionStart(BaseModel):
    """Call started. App shows a subtle scanning indicator."""

    kind: Literal["session_start"] = "session_start"
    stream_id: str
    call_id: str
    started_at: datetime
    protected_number: str | None = None  # the enrolled user's own number
    schema_version: str = SCHEMA_VERSION


class RiskUpdate(BaseModel):
    """One scoring tick, roughly once per second while the call is live."""

    kind: Literal["risk_update"] = "risk_update"
    stream_id: str
    call_id: str
    sequence: int
    timestamp: datetime
    score: int = Field(ge=0, le=100)
    verdict: RiskVerdict
    risk_level: RiskLevel
    confidence: float = Field(ge=0.0, le=1.0)  # aggregate signal confidence, not a threshold
    reasons: list[ReasonCode] = Field(default_factory=list)
    contributing_checks: list[CheckName] = Field(default_factory=list)
    degraded_checks: list[CheckName] = Field(default_factory=list)
    # Opaque ids only. No audio, no transcript, no numbers.
    evidence_refs: list[str] = Field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


class CallEnded(BaseModel):
    """Terminal message. Carries the stage 07 evidence summary, nothing sensitive."""

    kind: Literal["call_ended"] = "call_ended"
    stream_id: str
    call_id: str
    ended_at: datetime
    duration_seconds: float = 0.0
    final_score: int = Field(ge=0, le=100)
    final_verdict: RiskVerdict
    final_level: RiskLevel
    reasons: list[ReasonCode] = Field(default_factory=list)
    alert_fingerprint: str | None = None  # present iff an alert was raised
    merkle_root: str | None = None  # published off-ledger anchor
    sealed_record_id: str | None = None
    root_published_at: datetime | None = None
    schema_version: str = SCHEMA_VERSION


AppMessage = Annotated[
    Union[SessionStart, RiskUpdate, CallEnded],
    Field(discriminator="kind"),
]