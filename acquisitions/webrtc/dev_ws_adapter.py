"""Dev WebSocket stand-in for the WebRTC acquisition path.

Exists only until a real WebRTC/RTP or Exotel adapter lands. A test client sends
raw 16 kHz mono s16le frames as WebSocket binary messages; this adapter wraps each
one as an AudioChunk (transport=WEBRTC, codec=PCM_S16LE) and drives the same
StreamOpen -> AudioChunk* -> StreamClose lifecycle any acquisition adapter must.

AudioStreamAdapter.connect() models an outbound dial-out adapter (endpoint to
call). This harness is inbound: FastAPI has already accepted the socket before any
adapter code runs, so run_forever() is the real entry point. connect() stays only
to keep the class Protocol-shaped and raises NotImplementedError.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from starlette.websockets import WebSocketDisconnect

from contracts.acquisition import (
    AudioChunk,
    CallDirection,
    Codec,
    StreamClose,
    StreamOpen,
    Transport,
)

FRAME_MS = 20
SAMPLE_RATE = 16000
CHANNELS = 1


class WebSocketLike(Protocol):
    async def receive_bytes(self) -> bytes: ...


OnOpen = Callable[[StreamOpen], Awaitable[None]]
OnChunk = Callable[[AudioChunk], Awaitable[None]]
OnClose = Callable[[StreamClose], Awaitable[None]]


class DevWebSocketAdapter:
    """Stands in for acquisitions/webrtc's real adapter during prototyping."""

    def connect(
        self,
        endpoint: str,
        *,
        on_open: OnOpen,
        on_chunk: OnChunk,
        on_close: OnClose,
    ) -> None:
        raise NotImplementedError(
            "DevWebSocketAdapter is inbound-only; use run_forever with an "
            "already-accepted websocket instead of dialing an endpoint."
        )

    async def run_forever(
        self,
        websocket: WebSocketLike,
        stream_id: str,
        call_id: str,
        *,
        on_open: OnOpen,
        on_chunk: OnChunk,
        on_close: OnClose,
    ) -> None:
        started_at = datetime.now(UTC)
        await on_open(
            StreamOpen(
                stream_id=stream_id,
                call_id=call_id,
                transport=Transport.WEBRTC,
                direction=CallDirection.INBOUND,
                started_at=started_at,
                codec=Codec.PCM_S16LE,
                sample_rate=SAMPLE_RATE,
                channels=CHANNELS,
                frame_ms=FRAME_MS,
            )
        )

        sequence = 0
        frames_received = 0
        bytes_received = 0
        reason: Literal["completed", "error"] = "completed"
        try:
            while True:
                payload = await websocket.receive_bytes()
                now = datetime.now(UTC)
                await on_chunk(
                    AudioChunk(
                        stream_id=stream_id,
                        call_id=call_id,
                        transport=Transport.WEBRTC,
                        codec=Codec.PCM_S16LE,
                        sample_rate=SAMPLE_RATE,
                        channels=CHANNELS,
                        frame_ms=FRAME_MS,
                        sequence=sequence,
                        payload=payload,
                        capture_timestamp=now,
                        received_at=now,
                    )
                )
                sequence += 1
                frames_received += 1
                bytes_received += len(payload)
        except WebSocketDisconnect:
            reason = "completed"
        except Exception:
            reason = "error"
            raise
        finally:
            await on_close(
                StreamClose(
                    stream_id=stream_id,
                    call_id=call_id,
                    ended_at=datetime.now(UTC),
                    reason=reason,
                    frames_received=frames_received,
                    bytes_received=bytes_received,
                )
            )
