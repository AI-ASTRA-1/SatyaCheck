"""Acquisition boundary: what Exotel and WebRTC terminate at.

Transport-specific by design. These types carry transport, codec and sample-rate
fields because they describe what the telephony layer actually delivered. They must
never be imported below stage 02 (backend.app.ingestion); the pipeline, checks and
fusion see only CanonicalAudioChunk from contracts.pipeline.

The AudioStreamConsumer protocol is the single seam both transports terminate at.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Callable, Literal, Protocol

from pydantic import BaseModel, Field


class Transport(str, Enum):
    """The acquisition layer that delivered the audio. Allowed only at this boundary."""

    EXOTEL = "exotel"
    WEBRTC = "webrtc"


class Codec(str, Enum):
    """Codecs stage 02 must decode. Adds a transport that hands over raw PCM."""

    OPUS = "opus"
    G711_ULAW = "g711_ulaw"
    G711_ALAW = "g711_alaw"
    AMR_NB = "amr_nb"
    PCM_S16LE = "pcm_s16le"


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class AudioChunk(BaseModel):
    """One frame as the transport delivered it, 20 ms nominal.

    MUST NOT be imported below stage 02. The pipeline never sees this type. The
    transport, codec and sample-rate fields are documented per-stream properties
    of the acquisition layer, not decision inputs.
    """

    stream_id: str
    call_id: str
    transport: Transport
    codec: Codec
    sample_rate: int
    channels: int = 1
    frame_ms: int = 20
    sequence: int
    payload: bytes
    capture_timestamp: datetime
    received_at: datetime
    rtp_ts: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class StreamOpen(BaseModel):
    """Call start. Emitted once per stream before the first AudioChunk.

    Caller and callee numbers are PII. They are internal call context only and never
    reach the app contract.
    """

    kind: Literal["stream_open"] = "stream_open"
    stream_id: str
    call_id: str
    transport: Transport
    direction: CallDirection
    caller_number: str | None = None
    callee_number: str | None = None
    started_at: datetime
    codec: Codec
    sample_rate: int
    channels: int = 1
    frame_ms: int = 20
    external_ref: str | None = None


class StreamClose(BaseModel):
    """Call end. Emitted once after the last AudioChunk."""

    kind: Literal["stream_close"] = "stream_close"
    stream_id: str
    call_id: str
    ended_at: datetime
    reason: Literal["completed", "dropped", "timeout", "error"]
    frames_received: int = 0
    bytes_received: int = 0
    dropped_frames: int = 0


class AudioStreamAdapter(Protocol):
    """Implemented by acquisitions/exotel and acquisitions/webrtc.

    Yields exactly one StreamOpen, then AudioChunks, then one StreamClose. Raising
    here degrades to "no warning"; the call itself is untouched. Transport-specific
    handling stops where this adapter ends.
    """

    def connect(
        self,
        endpoint: str,
        *,
        on_open: Callable[[StreamOpen], None],
        on_chunk: Callable[[AudioChunk], None],
        on_close: Callable[[StreamClose], None],
    ) -> None: ...


class AudioStreamConsumer(Protocol):
    """What stage 02 implements. The single seam both transports terminate at."""

    def on_open(self, open_msg: StreamOpen) -> None: ...
    def on_chunk(self, chunk: AudioChunk) -> None: ...
    def on_close(self, close_msg: StreamClose) -> None: ...