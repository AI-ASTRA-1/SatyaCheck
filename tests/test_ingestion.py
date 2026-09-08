"""Tests for stage 02's IngestionConsumer."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from backend.app.ingestion.consumer import (
    IngestionConsumer,
    UnsupportedAudioFormatError,
)
from contracts.acquisition import (
    AudioChunk,
    CallDirection,
    Codec,
    StreamClose,
    StreamOpen,
    Transport,
)
from contracts.pipeline import CANONICAL_FRAME_BYTES, CanonicalAudioChunk

FRAME = b"\x00\x00" * (CANONICAL_FRAME_BYTES // 2)


def _make_consumer() -> tuple[IngestionConsumer, list, list[CanonicalAudioChunk], list]:
    starts: list = []
    chunks: list[CanonicalAudioChunk] = []
    ends: list = []

    async def on_stream_start(stream_id: str, call_id: str, started_at: datetime) -> None:
        starts.append((stream_id, call_id, started_at))

    async def on_canonical_chunk(chunk: CanonicalAudioChunk) -> None:
        chunks.append(chunk)

    async def on_stream_end(stream_id: str, call_id: str) -> None:
        ends.append((stream_id, call_id))

    consumer = IngestionConsumer(
        on_stream_start=on_stream_start,
        on_canonical_chunk=on_canonical_chunk,
        on_stream_end=on_stream_end,
    )
    return consumer, starts, chunks, ends


def _chunk(
    sequence: int,
    *,
    codec: Codec = Codec.PCM_S16LE,
    sample_rate: int = 16000,
    payload: bytes = FRAME,
    is_final: bool = False,
) -> AudioChunk:
    now = datetime.now(UTC)
    return AudioChunk(
        stream_id="s1",
        call_id="c1",
        transport=Transport.WEBRTC,
        codec=codec,
        sample_rate=sample_rate,
        sequence=sequence,
        payload=payload,
        capture_timestamp=now,
        received_at=now,
        is_final=is_final,
    )


def test_on_open_forwards_only_primitives() -> None:
    consumer, starts, _, _ = _make_consumer()
    started_at = datetime.now(UTC)

    async def run() -> None:
        await consumer.on_open(
            StreamOpen(
                stream_id="s1",
                call_id="c1",
                transport=Transport.WEBRTC,
                direction=CallDirection.INBOUND,
                started_at=started_at,
                codec=Codec.PCM_S16LE,
                sample_rate=16000,
            )
        )

    asyncio.run(run())
    assert starts == [("s1", "c1", started_at)]


def test_on_chunk_renumbers_sequence_from_zero_even_with_gaps() -> None:
    consumer, _, chunks, _ = _make_consumer()

    async def run() -> None:
        await consumer.on_chunk(_chunk(sequence=7))
        await consumer.on_chunk(_chunk(sequence=42))

    asyncio.run(run())
    assert [c.sequence for c in chunks] == [0, 1]
    assert all(isinstance(c, CanonicalAudioChunk) for c in chunks)


def test_on_chunk_propagates_is_final() -> None:
    consumer, _, chunks, _ = _make_consumer()
    short_payload = b"\x00\x00" * 3  # shorter than CANONICAL_FRAME_BYTES

    async def run() -> None:
        await consumer.on_chunk(_chunk(sequence=0, is_final=True, payload=short_payload))

    asyncio.run(run())
    assert chunks[0].is_final is True
    assert chunks[0].pcm_s16le == short_payload


def test_on_chunk_rejects_unsupported_codec() -> None:
    consumer, _, _, _ = _make_consumer()

    async def run() -> None:
        await consumer.on_chunk(_chunk(sequence=0, codec=Codec.OPUS))

    with pytest.raises(UnsupportedAudioFormatError):
        asyncio.run(run())


def test_on_chunk_rejects_unsupported_sample_rate() -> None:
    consumer, _, _, _ = _make_consumer()

    async def run() -> None:
        await consumer.on_chunk(_chunk(sequence=0, sample_rate=48000))

    with pytest.raises(UnsupportedAudioFormatError):
        asyncio.run(run())


def test_on_close_forwards_ids() -> None:
    consumer, _, _, ends = _make_consumer()

    async def run() -> None:
        await consumer.on_close(
            StreamClose(
                stream_id="s1",
                call_id="c1",
                ended_at=datetime.now(UTC),
                reason="completed",
            )
        )

    asyncio.run(run())
    assert ends == [("s1", "c1")]
