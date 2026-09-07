"""Fallback contracts shim matching contracts/acquisition.py specifications.

Used for standalone execution, isolated testing, and graceful degradation
when the contracts package is not yet on the python path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import sys
import types
from typing import Any, Callable, Dict, Optional, Protocol, Union


class Transport(str, Enum):
    """Transport protocol identifier."""
    WEBRTC = "webrtc"
    EXOTEL = "exotel"


class Codec(str, Enum):
    """Audio codec format."""
    OPUS = "opus"
    PCM_S16LE = "pcm_s16le"


class CallDirection(str, Enum):
    """Call direction."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class StreamOpen:
    """Event emitted once before audio streaming begins."""
    stream_id: str
    call_id: str
    transport: Transport = Transport.WEBRTC
    direction: CallDirection = CallDirection.INBOUND
    caller_number: Optional[str] = None
    callee_number: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    codec: Codec = Codec.OPUS
    sample_rate: int = 48000
    channels: int = 1
    frame_ms: int = 20
    external_ref: Optional[str] = None


@dataclass
class AudioChunk:
    """Individual audio packet emitted for each ~20ms frame."""
    stream_id: str
    call_id: str
    transport: Transport = Transport.WEBRTC
    codec: Codec = Codec.OPUS
    sample_rate: int = 48000
    channels: int = 1
    frame_ms: int = 20
    sequence: int = 0
    payload: bytes = b""
    capture_timestamp: Union[datetime, float] = 0.0
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rtp_ts: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamClose:
    """Event emitted once when the audio stream terminates."""
    stream_id: str
    call_id: str
    ended_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = "completed"
    frames_received: int = 0
    bytes_received: int = 0
    dropped_frames: int = 0


class AudioStreamAdapter(Protocol):
    """Acquisition adapter protocol to ingest audio streams."""
    def connect(
        self,
        endpoint: str,
        *,
        on_open: Callable[[StreamOpen], None],
        on_chunk: Callable[[AudioChunk], None],
        on_close: Callable[[StreamClose], None],
    ) -> None:
        ...


class AudioStreamConsumer(Protocol):
    """Ingestion stage 02 consumer protocol."""
    def on_open(self, open_msg: StreamOpen) -> None:
        ...

    def on_chunk(self, chunk: AudioChunk) -> None:
        ...

    def on_close(self, close_msg: StreamClose) -> None:
        ...


def register_shim() -> None:
    """Register fallback definitions into sys.modules as contracts.acquisition."""
    if "contracts.acquisition" not in sys.modules:
        contracts_mod = sys.modules.setdefault("contracts", types.ModuleType("contracts"))
        contracts_acq = types.ModuleType("contracts.acquisition")
        shim_exports = {
            "Transport": Transport,
            "Codec": Codec,
            "CallDirection": CallDirection,
            "StreamOpen": StreamOpen,
            "AudioChunk": AudioChunk,
            "StreamClose": StreamClose,
            "AudioStreamAdapter": AudioStreamAdapter,
            "AudioStreamConsumer": AudioStreamConsumer,
        }
        for k, v in shim_exports.items():
            setattr(contracts_acq, k, v)
        sys.modules["contracts.acquisition"] = contracts_acq
        setattr(contracts_mod, "acquisition", contracts_acq)


# Auto-register shim on import if root contracts module is absent
register_shim()
