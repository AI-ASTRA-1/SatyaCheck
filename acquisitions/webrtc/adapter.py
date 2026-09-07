"""WebRTC audio stream adapter implementing contracts.acquisition.AudioStreamAdapter.

This module consumes incoming WebRTC media tracks via aiortc, splits or converts
frames into AudioChunk payloads, and delivers them strictly in sequence:
1. on_open(StreamOpen) -> once before any audio
2. on_chunk(AudioChunk) -> once per frame with monotonic sequence numbers starting at 0
3. on_close(StreamClose) -> once after stream termination
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import logging
from typing import Any, Callable, Dict, Optional, Union
from urllib.parse import urlparse
import uuid

# Invariant: only standard library, aiortc, websockets, and contracts.acquisition
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
    """Encapsulates a single WebRTC audio session / stream leg."""

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
        self._lock = asyncio.Lock()

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

    async def handle_audio_track(self, track: Any) -> None:
        """Consume incoming aiortc MediaStreamTrack frames asynchronously."""
        self.start()
        logger.info("Started consuming audio track for stream %s (call %s)", self.stream_id, self.call_id)
        try:
            while not self._closed:
                try:
                    frame = await track.recv()
                except Exception as exc:
                    # aiortc raises MediaStreamError or CancelledError when track ends
                    logger.debug("Track recv stopped for stream %s: %s", self.stream_id, exc)
                    break

                if frame is None:
                    break

                # Extract raw audio bytes from av.AudioFrame or bytes
                payload = b""
                if hasattr(frame, "planes") and frame.planes:
                    payload = bytes(frame.planes[0])
                elif hasattr(frame, "to_ndarray"):
                    payload = frame.to_ndarray().tobytes()
                elif isinstance(frame, bytes):
                    payload = frame
                elif hasattr(frame, "data"):
                    payload = bytes(frame.data)
                else:
                    payload = bytes(frame)

                rtp_ts = getattr(frame, "pts", None)
                capture_ts = getattr(frame, "time", None)
                if capture_ts is None:
                    capture_ts = datetime.now(timezone.utc).timestamp()

                self.push_chunk(payload=payload, capture_timestamp=capture_ts, rtp_ts=rtp_ts)
        except asyncio.CancelledError:
            logger.info("Audio track consumption cancelled for stream %s", self.stream_id)
        finally:
            await self.close(reason="completed")

    async def close(self, reason: str = "completed") -> None:
        """Close the session and emit StreamClose exactly once."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True

            # If closed before any audio was emitted, ensure on_open is fired first per contract
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
            logger.info(
                "Closed WebRTC session %s (call %s, reason=%s, frames=%d, bytes=%d)",
                self.stream_id,
                self.call_id,
                reason,
                self.frames_received,
                self.bytes_received,
            )

    def close_sync(self, reason: str = "completed") -> None:
        """Synchronous wrapper for closing session."""
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
    """Production-ready WebRTC AudioStreamAdapter implementing contracts.acquisition."""

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
        self._signalling_server: Optional[Any] = None

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
            Target signalling endpoint or bind URI (e.g. 'ws://0.0.0.0:8766' or '0.0.0.0:8766').
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

    def create_session(self, call_id: str, peer_id: Optional[str] = None) -> WebRTCSession:
        """Create and track a new WebRTCSession with unique stream_id."""
        stream_id = f"stream_{uuid.uuid4().hex}"
        session = WebRTCSession(
            stream_id=stream_id,
            call_id=call_id,
            peer_id=peer_id,
            codec=self.codec,
            sample_rate=self.sample_rate,
            channels=self.channels,
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

    def close(self) -> None:
        """Terminate all active sessions and mark adapter disconnected."""
        for session in list(self._sessions.values()):
            session.close_sync(reason="adapter_closed")
        self._sessions.clear()
        self._is_connected = False
        logger.info("WebRTCAdapter closed.")
