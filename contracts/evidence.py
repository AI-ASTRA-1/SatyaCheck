"""Stage 07 evidence shapes. No audio, no transcript, no voice data, no numbers.

Each alert event is fingerprinted (a hash over the canonical alert event JSON:
score, verdict, reasons, model versions, call metadata, timestamps), the
fingerprints are folded into a Merkle tree, and the root is published where it
cannot be quietly rewritten. That proves a single alert existed and predates the
transfer without exposing any other person's call. Handed to NCRP / 1930 on
request.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .checks import CheckName, ReasonCode
from .risk import RiskLevel, RiskVerdict


class ChainAnchor(BaseModel):
    """Where the Merkle root was published. Off the ledger."""

    network: str
    root: str
    published_at: datetime


class SealedRecord(BaseModel):
    """The artifact handed to NCRP / 1930 on request. Restricted, off-ledger."""

    sealed_record_id: str
    alert_fingerprint: str
    created_at: datetime


class AlertRecord(BaseModel):
    """One alert. The ledger carries roots only, never audio or personal data."""

    alert_id: str
    stream_id: str
    call_id: str
    raised_at: datetime
    final_score: int = Field(ge=0, le=100)
    verdict: RiskVerdict
    risk_level: RiskLevel
    reasons: list[ReasonCode] = Field(default_factory=list)
    contributing_checks: list[CheckName] = Field(default_factory=list)
    degraded_checks: list[CheckName] = Field(default_factory=list)
    fingerprint: str  # sha256 over the canonical alert event; no audio, no transcript
    merkle_leaf: str
    merkle_root: str
    root_published_at: datetime
    chain_anchor: ChainAnchor | None = None
    sealed_record_ref: str | None = None