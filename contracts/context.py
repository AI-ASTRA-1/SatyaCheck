"""Call context that feeds risk fusion alongside the model signals.

Everything here is internal. Caller and callee numbers are PII; they never reach
the app contract (contracts.risk).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .acquisition import CallDirection


class NumberReputation(BaseModel):
    """Reputation of the calling number, from history / blocklists."""

    blocklisted: bool = False
    reported_before: bool = False
    spam_score: float | None = Field(default=None, ge=0.0, le=1.0)


class CallHistoryEntry(BaseModel):
    """One past call involving this caller or callee number."""

    other_number: str
    started_at: datetime
    duration_seconds: float | None = None
    outcome: str | None = None


class PolicyRef(BaseModel):
    """Which deployment policy governs this call. A bank is not a family.

    The 0 to 100 score is the output; what it triggers is configurable per
    deployment through this reference.
    """

    deployment_id: str
    policy_version: str


class CallContext(BaseModel):
    """Everything about the call except the audio itself.

    Flows into stage 05 fusion alongside the check signals. Call history, location
    and number reputation are whatever the deployment can legally supply.
    """

    stream_id: str
    call_id: str
    caller_number: str | None = None
    callee_number: str | None = None
    direction: CallDirection | None = None
    started_at: datetime
    location_hint: str | None = None
    call_history: list[CallHistoryEntry] = Field(default_factory=list)
    number_reputation: NumberReputation | None = None
    policy: PolicyRef | None = None