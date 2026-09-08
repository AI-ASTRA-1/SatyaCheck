"""Out-of-band runner for check 4 (stt_llm).

Stage 04 is a 180 ms budget and `DefaultCheckRunner` enforces it. Transcription
plus a language model takes seconds, so check 4 cannot run there: it would be
marked FAILED on every window and contribute nothing. Instead this worker keeps
a rolling window of recent audio per stream, runs the check on its own cadence
in a background task, and publishes the newest result into a cache that fusion
reads.

The consequences, stated rather than hidden:

- **The script signal lags.** Fusion sees a judgement of the last ~10 seconds,
  refreshed every few seconds, not of the window it is scoring right now. That
  is the right shape for a scam script, which unfolds across a call, and the
  wrong shape for anything needing per-window precision.
- **Its age is part of the reading.** `get_fresh` refuses a result older than
  `max_age_s` rather than letting a stale judgement look current, so fusion can
  tell "no script risk" apart from "no recent answer".
- **A slow or failed transcript never blocks audio.** The worker owns its own
  task; the ingestion path never waits on it.

Transport-blind, like everything below stage 02: this sees `CanonicalAudioChunk`
and nothing about how the audio arrived.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass

from contracts.checks import CheckResult
from contracts.context import CallContext
from contracts.pipeline import (
    CANONICAL_FRAME_MS,
    CanonicalAudioBatch,
    CanonicalAudioChunk,
)

logger = logging.getLogger("satyacheck.transcript")

#: How much recent audio the scam-script judgement is made from.
BUFFER_SECONDS = 10.0

#: How often the worker re-transcribes. Faster costs GPU and API calls for very
#: little: a scam script does not change meaningfully inside three seconds.
INTERVAL_SECONDS = 3.0

#: Fusion ignores a script signal older than this. Chosen so a single slow or
#: failed pass still leaves a usable answer, while a dead worker stops
#: contributing rather than pinning the score to its last reading.
DEFAULT_MAX_SIGNAL_AGE_S = 15.0

_MAX_CHUNKS = int(BUFFER_SECONDS * 1000 / CANONICAL_FRAME_MS)


@dataclass
class CachedSignal:
    """A check 4 result plus when it was produced."""

    result: CheckResult
    produced_at: float  # time.monotonic()

    def age_s(self, now: float | None = None) -> float:
        return (now if now is not None else time.monotonic()) - self.produced_at


class _StreamState:
    def __init__(self, call_id: str, context: CallContext) -> None:
        self.call_id = call_id
        self.context = context
        self.chunks: deque[CanonicalAudioChunk] = deque(maxlen=_MAX_CHUNKS)
        self.cached: CachedSignal | None = None
        self.task: asyncio.Task[None] | None = None


class TranscriptWorker:
    """Runs check 4 out of band and caches the newest result per stream."""

    def __init__(
        self,
        check: object | None = None,
        *,
        interval_s: float = INTERVAL_SECONDS,
        min_seconds_before_first_run: float = 4.0,
    ) -> None:
        # `check` is anything implementing contracts.checks.Check. Optional so
        # the backend still runs with check 4 absent, in which case fusion sees
        # no script signal and says so.
        self._check = check
        self._interval_s = interval_s
        self._min_chunks = int(min_seconds_before_first_run * 1000 / CANONICAL_FRAME_MS)
        self._streams: dict[str, _StreamState] = {}

    @property
    def enabled(self) -> bool:
        return self._check is not None

    def start_stream(self, stream_id: str, call_id: str, context: CallContext) -> None:
        state = _StreamState(call_id, context)
        self._streams[stream_id] = state
        if self._check is None:
            return
        state.task = asyncio.create_task(self._run_loop(stream_id))

    async def stop_stream(self, stream_id: str) -> None:
        state = self._streams.pop(stream_id, None)
        if state is None or state.task is None:
            return
        state.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await state.task

    def add_chunk(self, chunk: CanonicalAudioChunk) -> None:
        state = self._streams.get(chunk.stream_id)
        if state is not None:
            state.chunks.append(chunk)

    def get_fresh(
        self, stream_id: str, max_age_s: float = DEFAULT_MAX_SIGNAL_AGE_S
    ) -> CachedSignal | None:
        """The newest result for this stream, or None if there is none or it is stale."""
        state = self._streams.get(stream_id)
        if state is None or state.cached is None:
            return None
        if state.cached.age_s() > max_age_s:
            return None
        return state.cached

    async def _run_loop(self, stream_id: str) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            state = self._streams.get(stream_id)
            if state is None:
                return
            if len(state.chunks) < self._min_chunks:
                continue
            try:
                await self._run_once(stream_id, state)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("transcript pass failed for stream_id=%s", stream_id)

    async def _run_once(self, stream_id: str, state: _StreamState) -> None:
        batch = self._snapshot(stream_id, state)
        assert self._check is not None
        started = time.monotonic()
        result = await asyncio.to_thread(self._check.run, batch, state.context)  # type: ignore[attr-defined]
        state.cached = CachedSignal(result=result, produced_at=time.monotonic())
        signal = result.signal
        logger.info(
            "transcript pass: stream_id=%s status=%s script_risk=%s took=%.2fs window=%dms",
            stream_id,
            result.status.value,
            getattr(signal, "script_risk", None),
            time.monotonic() - started,
            batch.window_ms,
        )

    @staticmethod
    def _snapshot(stream_id: str, state: _StreamState) -> CanonicalAudioBatch:
        chunks = list(state.chunks)
        pcm = b"".join(c.pcm_s16le for c in chunks)
        return CanonicalAudioBatch(
            stream_id=stream_id,
            call_id=state.call_id,
            start_sequence=chunks[0].sequence,
            end_sequence=chunks[-1].sequence,
            pcm_s16le=pcm,
            sample_count=len(pcm) // 2,
            capture_started_at=chunks[0].capture_timestamp,
            capture_ended_at=chunks[-1].capture_timestamp,
            window_ms=len(chunks) * CANONICAL_FRAME_MS,
        )
