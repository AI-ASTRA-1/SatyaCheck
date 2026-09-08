"""Stage 02 ingestion consumer.

Implements contracts.acquisition.AudioStreamConsumer. The only module below stage
02 allowed to see AudioChunk/StreamOpen/StreamClose; everything downstream only
ever sees CanonicalAudioChunk (contracts.pipeline). This prototype's dev WebSocket
harness always sends already-canonical audio (16 kHz mono PCM s16le), so no codec
decoding is implemented here yet -- real codec transcoding (Opus/G.711/AMR-NB) is
future work for whichever adapter needs it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from contracts.acquisition import AudioChunk, Codec, StreamClose, StreamOpen
from contracts.pipeline import CANONICAL_SAMPLE_RATE, CanonicalAudioChunk

OnStreamStart = Callable[[str, str, datetime], Awaitable[None]]
OnCanonicalChunk = Callable[[CanonicalAudioChunk], Awaitable[None]]
OnStreamEnd = Callable[[str, str], Awaitable[None]]


class UnsupportedAudioFormatError(ValueError):
    """Raised when an AudioChunk arrives in a format stage 02 cannot normalize yet."""


class IngestionConsumer:
    """What stage 02 implements: the seam every acquisition adapter terminates at."""

    def __init__(
        self,
        *,
        on_stream_start: OnStreamStart,
        on_canonical_chunk: OnCanonicalChunk,
        on_stream_end: OnStreamEnd,
    ) -> None:
        self._on_stream_start = on_stream_start
        self._on_canonical_chunk = on_canonical_chunk
        self._on_stream_end = on_stream_end
        self._sequence = 0

    async def on_open(self, open_msg: StreamOpen) -> None:
        self._sequence = 0
        await self._on_stream_start(open_msg.stream_id, open_msg.call_id, open_msg.started_at)

    async def on_chunk(self, chunk: AudioChunk) -> None:
        if (
            chunk.codec != Codec.PCM_S16LE
            or chunk.sample_rate != CANONICAL_SAMPLE_RATE
            or chunk.channels != 1
        ):
            raise UnsupportedAudioFormatError(
                f"stage 02 prototype only accepts {Codec.PCM_S16LE.value} at "
                f"{CANONICAL_SAMPLE_RATE} Hz mono; got {chunk.codec.value} at "
                f"{chunk.sample_rate} Hz, {chunk.channels} channel(s)"
            )
        canonical = CanonicalAudioChunk(
            stream_id=chunk.stream_id,
            call_id=chunk.call_id,
            sequence=self._sequence,
            pcm_s16le=chunk.payload,
            capture_timestamp=chunk.capture_timestamp,
            ingest_timestamp=chunk.received_at,
            is_final=chunk.is_final,
        )
        self._sequence += 1
        await self._on_canonical_chunk(canonical)

    async def on_close(self, close_msg: StreamClose) -> None:
        await self._on_stream_end(close_msg.stream_id, close_msg.call_id)
