"""Stage 03: in-process buffering and silence filtering.

AGENTS.md documents stage 03's buffer as Redis Streams. This prototype runs a
single process, so InProcessStreamBuffer holds the window in memory instead,
behind the same two-method shape (add_chunk / flush) a Redis-backed buffer would
need, so swapping one in later doesn't change stage 04's caller.

Silence filtering is a whole-window gate, not a byte-level filter: a window is
always built and RMS-checked; the caller skips stage 04/06 for unvoiced ticks
rather than this class dropping bytes mid-window (CanonicalAudioBatch is
documented as "a contiguous window").
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

from contracts.pipeline import (
    CANONICAL_FRAME_MS,
    CanonicalAudioBatch,
    CanonicalAudioChunk,
)

WINDOW_MS = 1000
FRAMES_PER_WINDOW = WINDOW_MS // CANONICAL_FRAME_MS
SILENCE_RMS_THRESHOLD = 150.0


def _rms_int16(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm)
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return math.sqrt(mean_square)


@dataclass
class BufferTick:
    batch: CanonicalAudioBatch
    is_voiced: bool
    rms: float


class InProcessStreamBuffer:
    """Accumulates CanonicalAudioChunks into fixed windows for one stream."""

    def __init__(self, stream_id: str, call_id: str) -> None:
        self._stream_id = stream_id
        self._call_id = call_id
        self._chunks: list[CanonicalAudioChunk] = []

    def add_chunk(self, chunk: CanonicalAudioChunk) -> BufferTick | None:
        self._chunks.append(chunk)
        if len(self._chunks) >= FRAMES_PER_WINDOW:
            return self._build_tick()
        return None

    def flush(self) -> BufferTick | None:
        if not self._chunks:
            return None
        return self._build_tick()

    def _build_tick(self) -> BufferTick:
        window, self._chunks = self._chunks, []
        pcm = b"".join(c.pcm_s16le for c in window)
        rms = _rms_int16(pcm)
        batch = CanonicalAudioBatch(
            stream_id=self._stream_id,
            call_id=self._call_id,
            start_sequence=window[0].sequence,
            end_sequence=window[-1].sequence,
            pcm_s16le=pcm,
            sample_count=len(pcm) // 2,
            capture_started_at=window[0].capture_timestamp,
            capture_ended_at=window[-1].capture_timestamp,
            window_ms=len(window) * CANONICAL_FRAME_MS,
        )
        return BufferTick(batch=batch, is_voiced=rms >= SILENCE_RMS_THRESHOLD, rms=rms)
