"""Tests for stage 03's in-process buffer."""

from __future__ import annotations

import struct
from datetime import UTC, datetime

from backend.app.pipeline.buffer import FRAMES_PER_WINDOW, InProcessStreamBuffer
from contracts.pipeline import CANONICAL_FRAME_BYTES, CanonicalAudioChunk

N_SAMPLES = CANONICAL_FRAME_BYTES // 2


def _silence_chunk(sequence: int) -> CanonicalAudioChunk:
    now = datetime.now(UTC)
    return CanonicalAudioChunk(
        stream_id="s1",
        call_id="c1",
        sequence=sequence,
        pcm_s16le=b"\x00\x00" * N_SAMPLES,
        capture_timestamp=now,
        ingest_timestamp=now,
    )


def _tone_chunk(sequence: int) -> CanonicalAudioChunk:
    now = datetime.now(UTC)
    samples = [10000 if i % 2 == 0 else -10000 for i in range(N_SAMPLES)]
    pcm = struct.pack(f"<{N_SAMPLES}h", *samples)
    return CanonicalAudioChunk(
        stream_id="s1",
        call_id="c1",
        sequence=sequence,
        pcm_s16le=pcm,
        capture_timestamp=now,
        ingest_timestamp=now,
    )


def test_full_window_of_silence_is_not_voiced() -> None:
    buf = InProcessStreamBuffer("s1", "c1")
    tick = None
    for i in range(FRAMES_PER_WINDOW):
        tick = buf.add_chunk(_silence_chunk(i))
    assert tick is not None
    assert tick.is_voiced is False
    assert tick.batch.start_sequence == 0
    assert tick.batch.end_sequence == FRAMES_PER_WINDOW - 1
    assert tick.batch.sample_count == FRAMES_PER_WINDOW * N_SAMPLES
    assert tick.batch.window_ms == 1000


def test_full_window_of_tone_is_voiced() -> None:
    buf = InProcessStreamBuffer("s1", "c1")
    tick = None
    for i in range(FRAMES_PER_WINDOW):
        tick = buf.add_chunk(_tone_chunk(i))
    assert tick is not None
    assert tick.is_voiced is True


def test_window_not_emitted_until_full() -> None:
    buf = InProcessStreamBuffer("s1", "c1")
    for i in range(FRAMES_PER_WINDOW - 1):
        assert buf.add_chunk(_silence_chunk(i)) is None


def test_flush_emits_short_tail_then_nothing() -> None:
    buf = InProcessStreamBuffer("s1", "c1")
    for i in range(FRAMES_PER_WINDOW - 1):
        buf.add_chunk(_silence_chunk(i))
    tick = buf.flush()
    assert tick is not None
    assert tick.batch.end_sequence == FRAMES_PER_WINDOW - 2
    assert buf.flush() is None
