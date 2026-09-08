"""Tests for CallSessionOrchestrator: stage 02 callbacks through stage 06 dispatch.

No real sockets: a fake dispatcher records every AppMessage sent, and the
orchestrator's own async callbacks are driven directly.
"""

from __future__ import annotations

import asyncio
import struct
from datetime import UTC, datetime

from backend.app.main import CallSessionOrchestrator
from backend.app.pipeline.buffer import FRAMES_PER_WINDOW
from contracts.pipeline import CANONICAL_FRAME_BYTES, CanonicalAudioChunk
from contracts.risk import AppMessage, CallEnded, RiskUpdate, RiskVerdict, SessionStart

N_SAMPLES = CANONICAL_FRAME_BYTES // 2


class RecordingDispatcher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, AppMessage]] = []

    async def send(self, stream_id: str, message: AppMessage) -> None:
        self.sent.append((stream_id, message))


def _tone_chunk(sequence: int) -> CanonicalAudioChunk:
    now = datetime.now(UTC)
    samples = [16000 if i % 2 == 0 else -16000 for i in range(N_SAMPLES)]
    pcm = struct.pack(f"<{N_SAMPLES}h", *samples)
    return CanonicalAudioChunk(
        stream_id="s1",
        call_id="c1",
        sequence=sequence,
        pcm_s16le=pcm,
        capture_timestamp=now,
        ingest_timestamp=now,
    )


def test_full_session_emits_session_start_then_risk_updates() -> None:
    dispatcher = RecordingDispatcher()
    orchestrator = CallSessionOrchestrator(dispatcher=dispatcher)  # type: ignore[arg-type]

    async def run() -> None:
        started_at = datetime.now(UTC)
        await orchestrator.on_stream_start("s1", "c1", started_at)
        for i in range(FRAMES_PER_WINDOW):
            await orchestrator.on_canonical_chunk(_tone_chunk(i))
        await orchestrator.on_stream_end("s1", "c1")

    asyncio.run(run())

    assert len(dispatcher.sent) >= 2
    first_stream_id, first_message = dispatcher.sent[0]
    assert first_stream_id == "s1"
    assert isinstance(first_message, SessionStart)

    risk_updates = [msg for _, msg in dispatcher.sent if isinstance(msg, RiskUpdate)]
    assert len(risk_updates) >= 1
    update = risk_updates[0]
    assert update.stream_id == "s1"
    assert update.call_id == "c1"
    assert 0 <= update.score <= 100

    call_ended = [msg for _, msg in dispatcher.sent if isinstance(msg, CallEnded)]
    assert len(call_ended) == 1
    assert call_ended[0].stream_id == "s1"
    assert call_ended[0].call_id == "c1"
    assert call_ended[0].final_score == risk_updates[-1].score
    assert call_ended[0].final_verdict == risk_updates[-1].verdict
    assert call_ended[0].duration_seconds >= 0.0


def test_stream_end_still_scores_the_final_short_window() -> None:
    """A trailing partial window (fewer than FRAMES_PER_WINDOW chunks) must still
    be scored on stream end, not silently dropped because the context was popped
    before the flushed tick was processed."""
    dispatcher = RecordingDispatcher()
    orchestrator = CallSessionOrchestrator(dispatcher=dispatcher)  # type: ignore[arg-type]

    async def run() -> None:
        # _tone_chunk hardcodes stream_id="s1"/call_id="c1" (matching the test
        # above); reuse those ids here too since each test has its own
        # orchestrator instance.
        await orchestrator.on_stream_start("s1", "c1", datetime.now(UTC))
        # Fewer than a full window -- add_chunk alone would never emit a tick.
        for i in range(FRAMES_PER_WINDOW - 1):
            await orchestrator.on_canonical_chunk(_tone_chunk(i))
        await orchestrator.on_stream_end("s1", "c1")

    asyncio.run(run())

    risk_updates = [msg for _, msg in dispatcher.sent if isinstance(msg, RiskUpdate)]
    assert len(risk_updates) == 1  # the flush-on-close tick, and only that one

    call_ended = [msg for _, msg in dispatcher.sent if isinstance(msg, CallEnded)]
    assert len(call_ended) == 1
    assert call_ended[0].final_score == risk_updates[0].score
    assert call_ended[0].final_verdict == risk_updates[0].verdict


def test_silent_stream_produces_no_risk_updates() -> None:
    dispatcher = RecordingDispatcher()
    orchestrator = CallSessionOrchestrator(dispatcher=dispatcher)  # type: ignore[arg-type]

    async def silence_chunk(sequence: int) -> CanonicalAudioChunk:
        now = datetime.now(UTC)
        return CanonicalAudioChunk(
            stream_id="s2",
            call_id="c2",
            sequence=sequence,
            pcm_s16le=b"\x00\x00" * N_SAMPLES,
            capture_timestamp=now,
            ingest_timestamp=now,
        )

    async def run() -> None:
        await orchestrator.on_stream_start("s2", "c2", datetime.now(UTC))
        for i in range(FRAMES_PER_WINDOW):
            await orchestrator.on_canonical_chunk(await silence_chunk(i))
        await orchestrator.on_stream_end("s2", "c2")

    asyncio.run(run())

    risk_updates = [msg for _, msg in dispatcher.sent if isinstance(msg, RiskUpdate)]
    assert risk_updates == []

    call_ended = [msg for _, msg in dispatcher.sent if isinstance(msg, CallEnded)]
    assert len(call_ended) == 1
    # No voiced window ever occurred, so CallEnded falls back to UNKNOWN/0
    # rather than fabricating a score from nothing.
    assert call_ended[0].final_score == 0
    assert call_ended[0].final_verdict == RiskVerdict.UNKNOWN
