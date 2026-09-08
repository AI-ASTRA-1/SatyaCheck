"""WebRTC audio stream adapter implementing contracts.acquisition.AudioStreamAdapter.

Receives audio frames via a WebSocket ingest connection (port 8767) from the
receiver app (Phone B), which taps its incoming WebRTC remote audio track and
forwards raw Opus frames to this adapter.

Lifecycle per call:
1. on_open(StreamOpen)  -- once, on JSON handshake receipt
2. on_chunk(AudioChunk) -- once per binary frame (20 ms Opus)
3. on_close(StreamClose) -- once, on WebSocket disconnect or hangup
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import json
import logging
from typing import Any, Callable, Dict, Optional, Union
import uuid

# Invariant: only standard library, websockets, and contracts.acquisition
try:
    import websockets
except ImportError:
    websockets = None  # type: ignore[assignment]

try:
    from contracts.acquisition import (
        AudioChunk,
        AudioStreamAdapter,
        AudioStreamConsumer,
        CallDirection,
        Codec,
        StreamClose,
        StreamOpen,
        Transport,
    )
except ImportError:
    from .contracts_shim import (
        AudioChunk,
        AudioStreamAdapter,
        AudioStreamConsumer,
        CallDirection,
        Codec,
        StreamClose,
        StreamOpen,
        Transport,
    )

logger = logging.getLogger(__name__)

# Maps handshake codec strings to Codec enum values
_CODEC_MAP: Dict[str, Codec] = {
    "opus": Codec.OPUS,
    "pcm_s16le": Codec.PCM_S16LE,
}


def _invoke_callback(callback: Optional[Callable[[Any], None]], arg: Any) -> None:
    """Safely invoke synchronous or asynchronous callback."""
    if callback is None:
        return
    try:
        res = callback(arg)
        if inspect.isawaitable(res):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(res)
            except RuntimeError:
                asyncio.run(res)
    except Exception as exc:
        logger.error("Error in acquisition callback %s: %s", callback, exc, exc_info=True)


class WebRTCSession:
    """Encapsulates a single WebRTC audio session / stream leg.

    Each session maps to one call's audio flowing through the ingest
    WebSocket. Sequence numbers are monotonic starting at 0 and
    callbacks follow the strict open -> chunk* -> close order.
    """

    def __init__(
        self,
        stream_id: str,
        call_id: str,
        peer_id: Optional[str] = None,
        codec: Codec = Codec.OPUS,
        sample_rate: int = 48000,
        channels: int = 1,
        frame_ms: int = 20,
        on_open: Optional[Callable[[StreamOpen], None]] = None,
        on_chunk: Optional[Callable[[AudioChunk], None]] = None,
        on_close: Optional[Callable[[StreamClose], None]] = None,
    ) -> None:
        self.stream_id = stream_id
        self.call_id = call_id
        self.peer_id = peer_id
        self.codec = codec
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_ms = frame_ms

        self._on_open = on_open
        self._on_chunk = on_chunk
        self._on_close = on_close

        self.sequence = 0
        self.frames_received = 0
        self.bytes_received = 0
        self.dropped_frames = 0

        self._opened = False
        self._closed = False

    def start(self) -> None:
        """Trigger on_open once before any audio chunk is emitted."""
        if self._opened or self._closed:
            return
        self._opened = True

        open_msg = StreamOpen(
            stream_id=self.stream_id,
            call_id=self.call_id,
            transport=Transport.WEBRTC,
            direction=CallDirection.INBOUND,
            caller_number=None,
            callee_number=None,
            started_at=datetime.now(timezone.utc),
            codec=self.codec,
            sample_rate=self.sample_rate,
            channels=self.channels,
            frame_ms=self.frame_ms,
            external_ref=self.peer_id,
        )
        _invoke_callback(self._on_open, open_msg)

    def push_chunk(
        self,
        payload: bytes,
        capture_timestamp: Optional[Union[datetime, float]] = None,
        rtp_ts: Optional[int] = None,
    ) -> AudioChunk:
        """Emit an individual AudioChunk ensuring monotonic sequencing."""
        if self._closed:
            raise RuntimeError(f"Cannot push chunk to closed session {self.stream_id}")

        if not self._opened:
            self.start()

        if capture_timestamp is None:
            capture_timestamp = datetime.now(timezone.utc).timestamp()

        metadata: Dict[str, Any] = {}
        if self.peer_id:
            metadata["peer_id"] = self.peer_id

        chunk = AudioChunk(
            stream_id=self.stream_id,
            call_id=self.call_id,
            transport=Transport.WEBRTC,
            codec=self.codec,
            sample_rate=self.sample_rate,
            channels=self.channels,
            frame_ms=self.frame_ms,
            sequence=self.sequence,
            payload=payload,
            capture_timestamp=capture_timestamp,
            received_at=datetime.now(timezone.utc),
            rtp_ts=rtp_ts,
            metadata=metadata,
        )

        self.sequence += 1
        self.frames_received += 1
        self.bytes_received += len(payload)

        _invoke_callback(self._on_chunk, chunk)
        return chunk

    def close_sync(self, reason: str = "completed") -> None:
        """Close the session and emit StreamClose exactly once."""
        if self._closed:
            return
        self._closed = True

        if not self._opened:
            self.start()

        close_msg = StreamClose(
            stream_id=self.stream_id,
            call_id=self.call_id,
            ended_at=datetime.now(timezone.utc),
            reason=reason,
            frames_received=self.frames_received,
            bytes_received=self.bytes_received,
            dropped_frames=self.dropped_frames,
        )
        _invoke_callback(self._on_close, close_msg)


class WebRTCAdapter:
    """WebRTC AudioStreamAdapter receiving audio via WebSocket binary frames.

    The receiver app (Phone B) taps the incoming WebRTC remote audio track
    and forwards raw Opus frames to this adapter over a WebSocket connection
    on the audio ingest port (default 8767).

    Protocol on the ingest WebSocket:
    1. First message (text): JSON handshake
       ``{"call_id": "...", "codec": "opus", "sample_rate": 48000, "channels": 1}``
    2. Subsequent messages (binary): raw Opus audio frames, 20 ms each
    3. On disconnect: session is closed, StreamClose emitted
    """

    def __init__(
        self,
        codec: Codec = Codec.OPUS,
        sample_rate: int = 48000,
        channels: int = 1,
        frame_ms: int = 20,
    ) -> None:
        self.codec = codec
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_ms = frame_ms

        self._on_open: Optional[Callable[[StreamOpen], None]] = None
        self._on_chunk: Optional[Callable[[AudioChunk], None]] = None
        self._on_close: Optional[Callable[[StreamClose], None]] = None

        self._endpoint: Optional[str] = None
        self._is_connected: bool = False
        self._sessions: Dict[str, WebRTCSession] = {}
        self._ingest_server: Optional[Any] = None

    @property
    def is_connected(self) -> bool:
        """Return connection state."""
        return self._is_connected

    def connect(
        self,
        endpoint: str,
        *,
        on_open: Callable[[StreamOpen], None],
        on_chunk: Callable[[AudioChunk], None],
        on_close: Callable[[StreamClose], None],
    ) -> None:
        """Connect to the acquisition endpoint and bind downstream consumer callbacks.

        Parameters
        ----------
        endpoint : str
            Target audio ingest endpoint URI (e.g. ``ws://0.0.0.0:8767``).
        on_open : Callable[[StreamOpen], None]
            Stage 02 consumer callback for stream start.
        on_chunk : Callable[[AudioChunk], None]
            Stage 02 consumer callback for individual audio frames.
        on_close : Callable[[StreamClose], None]
            Stage 02 consumer callback for stream termination.
        """
        self._endpoint = endpoint
        self._on_open = on_open
        self._on_chunk = on_chunk
        self._on_close = on_close
        self._is_connected = True

        logger.info("WebRTCAdapter connected to endpoint: %s", endpoint)

    def create_session(
        self,
        call_id: str,
        peer_id: Optional[str] = None,
        codec: Optional[Codec] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
    ) -> WebRTCSession:
        """Create and track a new WebRTCSession with unique stream_id."""
        stream_id = f"stream_{uuid.uuid4().hex}"
        session = WebRTCSession(
            stream_id=stream_id,
            call_id=call_id,
            peer_id=peer_id,
            codec=codec or self.codec,
            sample_rate=sample_rate or self.sample_rate,
            channels=channels or self.channels,
            frame_ms=self.frame_ms,
            on_open=self._on_open,
            on_chunk=self._on_chunk,
            on_close=self._on_close,
        )
        self._sessions[stream_id] = session
        return session

    def get_session(self, stream_id: str) -> Optional[WebRTCSession]:
        """Retrieve active session by stream ID."""
        return self._sessions.get(stream_id)

    # -- audio ingest WebSocket server ---------------------------------------

    async def _handle_audio_ws(self, websocket: Any) -> None:
        """Handle a single audio ingest WebSocket connection.

        Protocol:
        1. First message must be a JSON handshake with at least ``call_id``.
        2. All subsequent binary messages are treated as Opus audio frames.
        3. A text message with ``{"type": "hangup"}`` ends the session early.
        4. On WebSocket close the session is finalized with StreamClose.
        """
        session: Optional[WebRTCSession] = None

        try:
            # -- step 1: JSON handshake --------------------------------------
            raw_handshake = await websocket.recv()

            if isinstance(raw_handshake, bytes):
                logger.warning("Audio ingest: first message must be JSON, got binary")
                return

            try:
                handshake = json.loads(raw_handshake)
            except json.JSONDecodeError as exc:
                logger.warning("Audio ingest: invalid JSON handshake: %s", exc)
                return

            call_id = handshake.get("call_id")
            if not call_id:
                logger.warning("Audio ingest: handshake missing call_id")
                return

            codec_str = handshake.get("codec", "opus")
            codec = _CODEC_MAP.get(codec_str, self.codec)
            sample_rate = handshake.get("sample_rate", self.sample_rate)
            channels = handshake.get("channels", self.channels)

            session = self.create_session(
                call_id=call_id,
                codec=codec,
                sample_rate=sample_rate,
                channels=channels,
            )
            session.start()
            logger.info(
                "Audio ingest session started: stream=%s call=%s codec=%s rate=%d",
                session.stream_id, call_id, codec_str, sample_rate,
            )

            # -- step 2: receive audio frames --------------------------------
            async for message in websocket:
                if isinstance(message, bytes):
                    session.push_chunk(payload=message)
                elif isinstance(message, str):
                    # Text message during streaming: check for control commands
                    try:
                        ctrl = json.loads(message)
                        if ctrl.get("type") == "hangup":
                            logger.info(
                                "Audio ingest: hangup received for stream %s",
                                session.stream_id,
                            )
                            break
                    except json.JSONDecodeError:
                        pass

        except websockets.exceptions.ConnectionClosed:
            logger.info("Audio ingest: client disconnected")
        except Exception as exc:
            logger.error("Audio ingest error: %s", exc, exc_info=True)
        finally:
            if session is not None:
                session.close_sync(reason="completed")
                logger.info(
                    "Audio ingest session closed: stream=%s frames=%d bytes=%d",
                    session.stream_id, session.frames_received, session.bytes_received,
                )

    async def serve_audio_ingest(
        self, host: str = "0.0.0.0", port: int = 8767,
    ) -> None:
        """Start the audio ingest WebSocket server.

        The server listens for connections from the receiver app (Phone B)
        which forwards tapped WebRTC audio frames as binary WebSocket messages.
        """
        if websockets is None:
            raise RuntimeError(
                "websockets library is required. Install via: pip install websockets",
            )
        logger.info("Starting audio ingest server on ws://%s:%d", host, port)
        self._ingest_server = await websockets.serve(
            self._handle_audio_ws, host, port,
        )

    async def close_ingest(self) -> None:
        """Stop the audio ingest server and close all sessions."""
        if self._ingest_server:
            self._ingest_server.close()
            await self._ingest_server.wait_closed()
        for session in list(self._sessions.values()):
            session.close_sync(reason="completed")
        self._sessions.clear()
        self._is_connected = False
        logger.info("Audio ingest server stopped.")

    def close(self) -> None:
        """Terminate all active sessions and mark adapter disconnected."""
        for session in list(self._sessions.values()):
            session.close_sync(reason="completed")
        self._sessions.clear()
        self._is_connected = False
        logger.info("WebRTCAdapter closed.")


def main() -> None:
    """Entrypoint for running the audio ingest server standalone."""
    import argparse

    parser = argparse.ArgumentParser(
        description="WebRTC Audio Ingest WebSocket Server",
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=8767, help="Bind port (default: 8767)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO", help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    adapter = WebRTCAdapter()

    async def run() -> None:
        await adapter.serve_audio_ingest(host=args.host, port=args.port)
        try:
            await asyncio.Future()
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await adapter.close_ingest()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Audio ingest server stopped by user.")


if __name__ == "__main__":
    main()

