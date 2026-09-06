"""SATYACHECK interface contracts.

Schema-only: types, enums, defaults and validators. No IO, no orchestration, no
torch or fastapi imports. Everything below stage 02 imports from this package;
nothing below stage 02 may import the acquisition boundary types
(contracts.acquisition). See docs/interfaces.md and tests/test_transport_invariant.py.
"""

from .acquisition import (
    AudioChunk,
    AudioStreamAdapter,
    AudioStreamConsumer,
    CallDirection,
    Codec,
    StreamClose,
    StreamOpen,
    Transport,
)
from .checks import (
    Check,
    CheckName,
    CheckResult,
    CheckRunner,
    CheckStatus,
    ChecksBatchResult,
    EvidenceItem,
    MachineFingerprintSignal,
    ProsodySignal,
    ReasonCode,
    Signal,
    SpeakerIdentitySignal,
    SttLlmSignal,
)
from .context import CallContext, CallHistoryEntry, NumberReputation, PolicyRef
from .evidence import AlertRecord, ChainAnchor, SealedRecord
from .pipeline import (
    CANONICAL_FRAME_BYTES,
    CANONICAL_FRAME_MS,
    CANONICAL_SAMPLE_RATE,
    CanonicalAudioBatch,
    CanonicalAudioChunk,
)
from .risk import (
    DEFAULT_BAND_MAPPING,
    AppMessage,
    CallEnded,
    RiskLevel,
    RiskUpdate,
    RiskVerdict,
    SCHEMA_VERSION,
    SessionStart,
)

__all__ = [
    "AudioChunk",
    "AudioStreamAdapter",
    "AudioStreamConsumer",
    "CallDirection",
    "Codec",
    "StreamClose",
    "StreamOpen",
    "Transport",
    "Check",
    "CheckName",
    "CheckResult",
    "CheckRunner",
    "CheckStatus",
    "ChecksBatchResult",
    "EvidenceItem",
    "MachineFingerprintSignal",
    "ProsodySignal",
    "ReasonCode",
    "Signal",
    "SpeakerIdentitySignal",
    "SttLlmSignal",
    "CallContext",
    "CallHistoryEntry",
    "NumberReputation",
    "PolicyRef",
    "AlertRecord",
    "ChainAnchor",
    "SealedRecord",
    "CANONICAL_FRAME_BYTES",
    "CANONICAL_FRAME_MS",
    "CANONICAL_SAMPLE_RATE",
    "CanonicalAudioBatch",
    "CanonicalAudioChunk",
    "DEFAULT_BAND_MAPPING",
    "AppMessage",
    "CallEnded",
    "RiskLevel",
    "RiskUpdate",
    "RiskVerdict",
    "SCHEMA_VERSION",
    "SessionStart",
]