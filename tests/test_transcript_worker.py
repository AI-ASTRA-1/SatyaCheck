"""Tests for the out-of-band check 4 worker.

Fake checks only, so this runs without Whisper, torch or a network. What matters
here is the caching contract fusion depends on: a result is served while fresh,
refused once stale, and a slow or failing pass never blocks the audio path.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.pipeline.transcript_worker import CachedSignal, TranscriptWorker
from contracts.checks import (
    CheckName,
    CheckResult,
    CheckStatus,
    SttLlmSignal,
)
from contracts.context import CallContext
from contracts.pipeline import CANONICAL_FRAME_MS, CanonicalAudioChunk

FRAME_BYTES = 640  # 20 ms of 16 kHz mono s16le


def _context() -> CallContext:
    return CallContext(stream_id="s1", call_id="c1", started_at=datetime.now(UTC))


def _chunk(sequence: int, stream_id: str = "s1") -> CanonicalAudioChunk:
    now = datetime.now(UTC)
    return CanonicalAudioChunk(
        stream_id=stream_id,
        call_id="c1",
        sequence=sequence,
        pcm_s16le=b"\x00\x00" * (FRAME_BYTES // 2),
        capture_timestamp=now,
        ingest_timestamp=now,
    )


def _result(script_risk: float, status: CheckStatus = CheckStatus.OK) -> CheckResult:
    return CheckResult(
        check=CheckName.STT_LLM,
        status=status,
        signal=SttLlmSignal(script_risk=script_risk, script_category="payment_instruction"),
        processed_at=datetime.now(UTC),
        window_ms=10000,
    )


class _FakeCheck:
    name = CheckName.STT_LLM

    def __init__(self, script_risk: float = 0.7) -> None:
        self.calls = 0
        self.script_risk = script_risk
        self.last_window_ms = 0

    def run(self, batch, context):
        self.calls += 1
        self.last_window_ms = batch.window_ms
        return _result(self.script_risk)


def test_disabled_without_a_check() -> None:
    worker = TranscriptWorker()
    assert worker.enabled is False


def test_enabled_with_a_check() -> None:
    assert TranscriptWorker(_FakeCheck()).enabled is True


def test_get_fresh_is_none_before_any_pass_has_run() -> None:
    worker = TranscriptWorker(_FakeCheck())

    async def go() -> None:
        worker.start_stream("s1", "c1", _context())
        assert worker.get_fresh("s1") is None
        await worker.stop_stream("s1")

    asyncio.run(go())


def test_stale_result_is_refused_so_fusion_can_renormalise() -> None:
    """The whole point of the age check: a stale judgement must not look current."""
    worker = TranscriptWorker(_FakeCheck())

    async def go() -> None:
        worker.start_stream("s1", "c1", _context())
        state = worker._streams["s1"]
        # Produced 60 s ago on the monotonic clock the worker actually uses.
        import time

        state.cached = CachedSignal(result=_result(0.9), produced_at=time.monotonic() - 60.0)
        assert worker.get_fresh("s1", max_age_s=15.0) is None
        assert worker.get_fresh("s1", max_age_s=120.0) is not None
        await worker.stop_stream("s1")

    asyncio.run(go())


def test_a_pass_runs_and_caches_once_enough_audio_arrives() -> None:
    check = _FakeCheck(script_risk=0.8)
    worker = TranscriptWorker(check, interval_s=0.05, min_seconds_before_first_run=0.2)

    async def go() -> None:
        worker.start_stream("s1", "c1", _context())
        for sequence in range(20):  # 20 * 20 ms = 400 ms, over the 200 ms minimum
            worker.add_chunk(_chunk(sequence))
        await asyncio.sleep(0.25)
        cached = worker.get_fresh("s1")
        assert cached is not None
        assert cached.result.signal.script_risk == 0.8
        assert check.calls >= 1
        await worker.stop_stream("s1")

    asyncio.run(go())


def test_no_pass_runs_before_the_minimum_audio_is_buffered() -> None:
    check = _FakeCheck()
    worker = TranscriptWorker(check, interval_s=0.05, min_seconds_before_first_run=5.0)

    async def go() -> None:
        worker.start_stream("s1", "c1", _context())
        for sequence in range(5):  # 100 ms, far below the 5 s minimum
            worker.add_chunk(_chunk(sequence))
        await asyncio.sleep(0.2)
        assert check.calls == 0
        assert worker.get_fresh("s1") is None
        await worker.stop_stream("s1")

    asyncio.run(go())


def test_a_raising_check_does_not_kill_the_worker() -> None:
    class Boom:
        name = CheckName.STT_LLM

        def __init__(self) -> None:
            self.calls = 0

        def run(self, batch, context):
            self.calls += 1
            raise RuntimeError("whisper exploded")

    check = Boom()
    worker = TranscriptWorker(check, interval_s=0.05, min_seconds_before_first_run=0.1)

    async def go() -> None:
        worker.start_stream("s1", "c1", _context())
        for sequence in range(20):
            worker.add_chunk(_chunk(sequence))
        await asyncio.sleep(0.3)
        # It kept trying rather than dying on the first failure, and nothing
        # was cached, so fusion sees the check as absent.
        assert check.calls >= 2
        assert worker.get_fresh("s1") is None
        await worker.stop_stream("s1")

    asyncio.run(go())


def test_buffer_is_bounded_so_a_long_call_does_not_grow_without_limit() -> None:
    check = _FakeCheck()
    worker = TranscriptWorker(check)

    async def go() -> None:
        worker.start_stream("s1", "c1", _context())
        for sequence in range(5000):  # 100 s of audio into a 10 s buffer
            worker.add_chunk(_chunk(sequence))
        state = worker._streams["s1"]
        buffered_ms = len(state.chunks) * CANONICAL_FRAME_MS
        assert buffered_ms <= 10_000
        await worker.stop_stream("s1")

    asyncio.run(go())


def test_chunks_for_an_unknown_stream_are_ignored() -> None:
    worker = TranscriptWorker(_FakeCheck())
    worker.add_chunk(_chunk(0, stream_id="never-started"))
    assert worker.get_fresh("never-started") is None
