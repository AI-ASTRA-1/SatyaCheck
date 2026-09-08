"""Exotel Voice Streaming WebSocket adapter.

Handles Exotel's JSON-over-WebSocket audio streaming protocol:
1. start event: extracts call_sid, stream_sid, caller/callee numbers, media_format.
   Emits StreamOpen.
2. media event: base64-encoded linear PCM (typically 8000 Hz, 16-bit mono).
   Decodes, upsamples 8 kHz to canonical 16 kHz if needed, slices into 20 ms
   frames, and emits AudioChunk per frame.
3. stop event / disconnect: extracts reason, emits StreamClose.

Also accepts raw binary frames on the same connection: already-16kHz-mono-s16le PCM
of any size, buffered and sliced into canonical frames the same way as the JSON
media path. This is both the dev/test harness path and the join point for a custom
WebRTC adapter (see docs/interfaces.md section 2.1) -- a WebRTC sender must decode
Opus and resample to 16kHz itself before sending here; this adapter does not do it.
"""

from __future__ import annotations

import array
import base64
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from starlette.websockets import WebSocketDisconnect

from contracts.acquisition import (
    AudioChunk,
    CallDirection,
    Codec,
    StreamClose,
    StreamOpen,
    Transport,
)

logger = logging.getLogger("satyacheck.exotel")

CANONICAL_FRAME_MS = 20
CANONICAL_SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
CANONICAL_FRAME_BYTES = (CANONICAL_SAMPLE_RATE * CANONICAL_FRAME_MS // 1000) * BYTES_PER_SAMPLE * CHANNELS  # 640 bytes


class WebSocketLike(Protocol):
    async def receive(self) -> dict[str, Any]: ...


OnOpen = Callable[[StreamOpen], Awaitable[None]]
OnChunk = Callable[[AudioChunk], Awaitable[None]]
OnClose = Callable[[StreamClose], Awaitable[None]]


def _resample_8k_to_16k(pcm_8k: bytes, pending: int | None) -> tuple[bytes, int | None]:
    """Linearly upsample 8000 Hz 16-bit mono PCM to 16000 Hz.

    `pending` is the last raw 8kHz sample carried over from the previous media
    event; it is used to interpolate the first output sample of this chunk so
    consecutive ~100ms media events don't produce a discontinuity at the seam.
    Returns the resampled bytes plus this chunk's last raw sample, to be passed
    as `pending` on the next call.
    """
    samples_in = array.array("h")
    samples_in.frombytes(pcm_8k)
    n = len(samples_in)
    if n == 0:
        return b"", pending

    samples = ([pending] if pending is not None else []) + list(samples_in)
    m = len(samples)
    samples_out = array.array("h", [0] * (2 * (m - 1)))
    for i in range(m - 1):
        samples_out[2 * i] = samples[i]
        samples_out[2 * i + 1] = (samples[i] + samples[i + 1]) // 2
    return samples_out.tobytes(), samples_in[-1]


class ExotelWebSocketAdapter:
    """Acquisition adapter for Exotel Voice Streaming."""

    def connect(
        self,
        endpoint: str,
        *,
        on_open: OnOpen,
        on_chunk: OnChunk,
        on_close: OnClose,
    ) -> None:
        raise NotImplementedError(
            "ExotelWebSocketAdapter is inbound-only; use run_forever with an "
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
        opened = False
        frame_sequence = 0
        frames_received = 0
        bytes_received = 0
        dropped_frames = 0
        reason: Literal["completed", "dropped", "timeout", "error"] = "completed"
        audio_buffer = bytearray()
        source_sample_rate = 8000
        resample_pending: int | None = None

        async def ensure_open(
            caller: str | None = None,
            callee: str | None = None,
            ext_ref: str | None = None,
            transport: Transport = Transport.EXOTEL,
        ) -> None:
            nonlocal opened
            if not opened:
                opened = True
                await on_open(
                    StreamOpen(
                        stream_id=stream_id,
                        call_id=call_id,
                        transport=transport,
                        direction=CallDirection.INBOUND,
                        caller_number=caller,
                        callee_number=callee,
                        started_at=started_at,
                        codec=Codec.PCM_S16LE,
                        sample_rate=CANONICAL_SAMPLE_RATE,
                        channels=CHANNELS,
                        frame_ms=CANONICAL_FRAME_MS,
                        external_ref=ext_ref,
                    )
                )

        try:
            while True:
                message = await websocket.receive()
                msg_type = message.get("type")

                if msg_type == "websocket.disconnect":
                    reason = "dropped"
                    break

                if msg_type != "websocket.receive":
                    continue

                text_data = message.get("text")
                bytes_data = message.get("bytes")

                if text_data is not None:
                    try:
                        data = json.loads(text_data)
                    except json.JSONDecodeError:
                        logger.warning("invalid json received on stream %s", stream_id)
                        continue

                    event = data.get("event")

                    if event == "connected":
                        logger.info("Exotel stream connected: %s", data)
                        continue

                    elif event == "start":
                        start_info = data.get("start", {})
                        stream_sid = start_info.get("stream_sid") or data.get("stream_sid")
                        call_sid = start_info.get("call_sid")
                        caller_num = start_info.get("from")
                        callee_num = start_info.get("to")
                        media_fmt = start_info.get("media_format", {})
                        try:
                            source_sample_rate = int(media_fmt.get("sample_rate", 8000))
                        except (TypeError, ValueError):
                            source_sample_rate = 8000
                        resample_pending = None

                        logger.info(
                            "Exotel start event: stream_sid=%s call_sid=%s from=%s to=%s sample_rate=%d",
                            stream_sid,
                            call_sid,
                            caller_num,
                            callee_num,
                            source_sample_rate,
                        )

                        if source_sample_rate not in (8000, CANONICAL_SAMPLE_RATE):
                            logger.error(
                                "unsupported Exotel media_format.sample_rate=%d on stream %s; "
                                "closing stream",
                                source_sample_rate,
                                stream_id,
                            )
                            reason = "error"
                            break

                        await ensure_open(
                            caller=caller_num,
                            callee=callee_num,
                            ext_ref=call_sid or stream_sid,
                            transport=Transport.EXOTEL,
                        )

                    elif event == "media":
                        await ensure_open()
                        media_info = data.get("media", {})
                        payload_b64 = media_info.get("payload")
                        if not payload_b64:
                            logger.warning("empty/missing media payload on stream %s", stream_id)
                            dropped_frames += 1
                            continue

                        try:
                            raw_pcm = base64.b64decode(payload_b64)
                        except Exception as decode_err:
                            logger.warning("failed to base64 decode media payload: %s", decode_err)
                            dropped_frames += 1
                            continue

                        if len(raw_pcm) % 2 != 0:
                            logger.warning(
                                "odd-length audio payload (%d bytes) on stream %s; "
                                "trimming trailing byte",
                                len(raw_pcm),
                                stream_id,
                            )
                            raw_pcm = raw_pcm[:-1]
                        if not raw_pcm:
                            continue

                        # Resample to canonical 16000 Hz if arriving at 8000 Hz
                        if source_sample_rate == 8000:
                            pcm_16k, resample_pending = _resample_8k_to_16k(raw_pcm, resample_pending)
                        else:
                            pcm_16k = raw_pcm

                        audio_buffer.extend(pcm_16k)
                        now = datetime.now(UTC)

                        # Slice into 20ms canonical frames (640 bytes)
                        while len(audio_buffer) >= CANONICAL_FRAME_BYTES:
                            frame = bytes(audio_buffer[:CANONICAL_FRAME_BYTES])
                            del audio_buffer[:CANONICAL_FRAME_BYTES]

                            chunk = AudioChunk(
                                stream_id=stream_id,
                                call_id=call_id,
                                transport=Transport.EXOTEL,
                                codec=Codec.PCM_S16LE,
                                sample_rate=CANONICAL_SAMPLE_RATE,
                                channels=CHANNELS,
                                frame_ms=CANONICAL_FRAME_MS,
                                sequence=frame_sequence,
                                payload=frame,
                                capture_timestamp=now,
                                received_at=now,
                            )
                            frame_sequence += 1
                            frames_received += 1
                            bytes_received += len(frame)
                            await on_chunk(chunk)

                    elif event == "stop":
                        stop_info = data.get("stop", {})
                        stop_reason = stop_info.get("reason", "callended")
                        logger.info("Exotel stop event: reason=%s", stop_reason)
                        reason = "completed" if stop_reason in ("callended", "stopped") else "dropped"
                        break

                    else:
                        logger.debug("unrecognized Exotel event=%r on stream %s", event, stream_id)

                elif bytes_data is not None:
                    # Binary path: raw 16kHz PCM from test clients or a WebRTC adapter.
                    await ensure_open(transport=Transport.WEBRTC)
                    if len(bytes_data) % 2 != 0:
                        logger.warning(
                            "odd-length binary audio payload (%d bytes) on stream %s; "
                            "trimming trailing byte",
                            len(bytes_data),
                            stream_id,
                        )
                        bytes_data = bytes_data[:-1]
                    audio_buffer.extend(bytes_data)
                    now = datetime.now(UTC)

                    while len(audio_buffer) >= CANONICAL_FRAME_BYTES:
                        frame = bytes(audio_buffer[:CANONICAL_FRAME_BYTES])
                        del audio_buffer[:CANONICAL_FRAME_BYTES]

                        chunk = AudioChunk(
                            stream_id=stream_id,
                            call_id=call_id,
                            transport=Transport.WEBRTC,
                            codec=Codec.PCM_S16LE,
                            sample_rate=CANONICAL_SAMPLE_RATE,
                            channels=CHANNELS,
                            frame_ms=CANONICAL_FRAME_MS,
                            sequence=frame_sequence,
                            payload=frame,
                            capture_timestamp=now,
                            received_at=now,
                        )
                        frame_sequence += 1
                        frames_received += 1
                        bytes_received += len(frame)
                        await on_chunk(chunk)

        except WebSocketDisconnect:
            reason = "dropped"
        except Exception as exc:
            logger.exception("exception in Exotel audio stream: %s", exc)
            reason = "error"
            raise
        finally:
            # Emit the trailing partial frame (<20ms) as a final, unpadded chunk
            # so downstream sees the real tail instead of fabricated silence.
            # CanonicalAudioChunk.is_final tells stage 03/04 to tolerate the
            # short length instead of requiring exactly CANONICAL_FRAME_BYTES.
            if len(audio_buffer) > 0 and opened:
                now = datetime.now(UTC)
                chunk = AudioChunk(
                    stream_id=stream_id,
                    call_id=call_id,
                    transport=Transport.EXOTEL,
                    codec=Codec.PCM_S16LE,
                    sample_rate=CANONICAL_SAMPLE_RATE,
                    channels=CHANNELS,
                    frame_ms=CANONICAL_FRAME_MS,
                    sequence=frame_sequence,
                    payload=bytes(audio_buffer),
                    capture_timestamp=now,
                    received_at=now,
                    is_final=True,
                )
                frame_sequence += 1
                frames_received += 1
                bytes_received += len(audio_buffer)
                await on_chunk(chunk)

            await ensure_open()
            await on_close(
                StreamClose(
                    stream_id=stream_id,
                    call_id=call_id,
                    ended_at=datetime.now(UTC),
                    reason=reason,
                    frames_received=frames_received,
                    bytes_received=bytes_received,
                    dropped_frames=dropped_frames,
                )
            )
