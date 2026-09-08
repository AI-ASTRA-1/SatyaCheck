"""Wiring: the FastAPI app hosting both WebSocket endpoints.

CallSessionOrchestrator ties stages 02 (ingestion callbacks) -> 03 (buffer) ->
04 (runner) -> 05 (fusion) -> 06 (dispatcher) together per call. It takes zero
FastAPI/WebSocket imports so it is testable standalone (tests/test_session_wiring.py).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import FastAPI, WebSocket

from backend.app.fusion.fusion import RiskFusionEngine
from backend.app.ingestion.websocket_endpoint import run_audio_ingestion
from backend.app.pipeline.buffer import BufferTick, InProcessStreamBuffer
from backend.app.pipeline.transcript_worker import (
    DEFAULT_MAX_SIGNAL_AGE_S,
    TranscriptWorker,
)
from backend.app.response.dispatcher import ResponseDispatcher
from contracts.checks import CheckName, ReasonCode
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioChunk
from contracts.risk import CallEnded, RiskLevel, RiskUpdate, RiskVerdict, SessionStart
from ml.checks.machine_fingerprint import build_default_check
from ml.runner.runner import DefaultCheckRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("satyacheck.session")


def _load_dotenv() -> None:
    """Read .env into the environment before anything reads a key out of it.

    Must run before `_build_transcript_worker()` below, because check 4's scorer
    is chosen at startup on whether GROQ_API_KEY is set. Loading it later would
    leave the backend on the keyword scorer for the whole run with a valid key
    sitting in the file.

    `python-dotenv` arrives with uvicorn[standard]. Missing .env is normal and
    silent: the keyword scorer needs no key.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # override=False so a real environment variable always beats the file.
    if load_dotenv(override=False):
        logger.info("loaded .env")


_load_dotenv()

# Log every Nth received chunk instead of every one, to keep the console readable
# at 50 chunks/window while still proving frames are arriving.
_CHUNK_LOG_STRIDE = 10


class CallSessionOrchestrator:
    """Per-process, per-stream state: one buffer and one CallContext per call."""

    def __init__(
        self,
        runner: DefaultCheckRunner | None = None,
        fusion: RiskFusionEngine | None = None,
        dispatcher: ResponseDispatcher | None = None,
        transcripts: TranscriptWorker | None = None,
        max_script_age_s: float = DEFAULT_MAX_SIGNAL_AGE_S,
    ) -> None:
        self.runner = runner if runner is not None else DefaultCheckRunner()
        self.fusion = fusion if fusion is not None else RiskFusionEngine()
        self.dispatcher = dispatcher if dispatcher is not None else ResponseDispatcher()
        # Check 4 runs out of band, so it is not in `runner`. None means the
        # backend runs without it and fusion reports the script signal absent.
        self.transcripts = transcripts if transcripts is not None else TranscriptWorker()
        self._max_script_age_s = max_script_age_s
        self._buffers: dict[str, InProcessStreamBuffer] = {}
        self._contexts: dict[str, CallContext] = {}
        self._chunk_counts: dict[str, int] = {}
        self._last_update: dict[str, RiskUpdate] = {}

    async def on_stream_start(self, stream_id: str, call_id: str, started_at: datetime) -> None:
        logger.info("stream started: stream_id=%s call_id=%s", stream_id, call_id)
        self._buffers[stream_id] = InProcessStreamBuffer(stream_id, call_id)
        self._contexts[stream_id] = CallContext(
            stream_id=stream_id, call_id=call_id, started_at=started_at
        )
        self._chunk_counts[stream_id] = 0
        self.transcripts.start_stream(stream_id, call_id, self._contexts[stream_id])
        await self.dispatcher.send(
            stream_id,
            SessionStart(stream_id=stream_id, call_id=call_id, started_at=started_at),
        )

    async def on_canonical_chunk(self, chunk: CanonicalAudioChunk) -> None:
        buffer = self._buffers.get(chunk.stream_id)
        if buffer is None:
            return
        count = self._chunk_counts.get(chunk.stream_id, 0) + 1
        self._chunk_counts[chunk.stream_id] = count
        # Feed the out-of-band transcript buffer. Never awaits work: it appends
        # to a bounded deque, so ingestion is not slowed by check 4.
        self.transcripts.add_chunk(chunk)
        if count % _CHUNK_LOG_STRIDE == 0:
            logger.info(
                "audio received: stream_id=%s frames_so_far=%d last_sequence=%d bytes=%d",
                chunk.stream_id,
                count,
                chunk.sequence,
                len(chunk.pcm_s16le),
            )
        tick = buffer.add_chunk(chunk)
        if tick is not None:
            await self._process_tick(chunk.stream_id, tick)

    async def on_stream_end(self, stream_id: str, call_id: str) -> None:
        logger.info(
            "stream ended: stream_id=%s call_id=%s total_frames=%d",
            stream_id,
            call_id,
            self._chunk_counts.get(stream_id, 0),
        )
        buffer = self._buffers.pop(stream_id, None)
        if buffer is not None:
            # Process the final (possibly short) flushed window BEFORE popping
            # the context below -- _process_tick looks the context up by
            # stream_id, so popping first silently drops the last score.
            tick = buffer.flush()
            if tick is not None:
                await self._process_tick(stream_id, tick)

        # After the final flush, for the same reason the buffer is flushed before
        # the context is popped: stopping the worker first would drop the script
        # signal from the last window.
        await self.transcripts.stop_stream(stream_id)

        context = self._contexts.pop(stream_id, None)
        self._chunk_counts.pop(stream_id, None)
        last_update = self._last_update.pop(stream_id, None)

        ended_at = datetime.now(UTC)
        duration_seconds = (
            (ended_at - context.started_at).total_seconds() if context is not None else 0.0
        )
        if last_update is not None:
            final_score = last_update.score
            final_verdict = last_update.verdict
            final_level = last_update.risk_level
            reasons = last_update.reasons
        else:
            final_score = 0
            final_verdict = RiskVerdict.UNKNOWN
            final_level = RiskLevel.LOW
            reasons = [ReasonCode.INSUFFICIENT_AUDIO]

        await self.dispatcher.send(
            stream_id,
            CallEnded(
                stream_id=stream_id,
                call_id=call_id,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
                final_score=final_score,
                final_verdict=final_verdict,
                final_level=final_level,
                reasons=reasons,
            ),
        )

    async def _process_tick(self, stream_id: str, tick: BufferTick) -> None:
        logger.info(
            "window buffered: stream_id=%s sequence=%d-%d rms=%.1f voiced=%s",
            stream_id,
            tick.batch.start_sequence,
            tick.batch.end_sequence,
            tick.rms,
            tick.is_voiced,
        )
        if not tick.is_voiced:
            return
        context = self._contexts.get(stream_id)
        if context is None:
            return
        results = await self.runner.run_checks(tick.batch, context)
        script_age = self._overlay_script_result(stream_id, results)
        update = self.fusion.update(results, context)
        self._last_update[stream_id] = update
        logger.info(
            "processed by backend: stream_id=%s score=%d risk_level=%s verdict=%s "
            "script_age=%s degraded=%s",
            stream_id,
            update.score,
            update.risk_level.value,
            update.verdict.value,
            "none" if script_age is None else f"{script_age:.1f}s",
            [c.value for c in update.degraded_checks],
        )
        await self.dispatcher.send(stream_id, update)

    def _overlay_script_result(self, stream_id: str, results) -> float | None:
        """Put the newest fresh check 4 result into this tick's batch result.

        Check 4 does not run in stage 04, so `run_checks` returns it SKIPPED.
        Replacing that entry with the cached one is what lets fusion read both
        checks through the same `ChecksBatchResult` it already takes, with no
        extra parameter and no special case in the scoring path.

        A cached result older than `max_script_age_s` is not overlaid at all, so
        fusion sees the check as absent and renormalises rather than scoring on
        a stale judgement.
        """
        cached = self.transcripts.get_fresh(stream_id, self._max_script_age_s)
        if cached is None:
            return None
        results.results = [r for r in results.results if r.check != CheckName.STT_LLM]
        results.results.append(cached.result)
        return cached.age_s()


app = FastAPI(title="SATYACHECK backend prototype")


def _build_runner() -> DefaultCheckRunner:
    """Stage 04 runner, real machine-fingerprint check when the ML stack is present.

    `build_default_check()` is the R1 factory: it selects the device, loads the
    checkpoint and the confidence reference, and refuses to build the flagship
    model on a CPU-only box (RuntimeError with the measured numbers attached) so a
    check that would miss the 180 ms deadline on every window fails here at
    startup rather than backing the call buffer up per call. That refusal is
    deliberate and is never caught.

    The one graceful path is a missing torch, which `cuda_available()` would
    swallow and misreport as the CPU-only case. Probe it up front: without the ML
    extra there is no model at all, so fall back to the unconfigured default
    runner, which keeps the pipeline testable and degrades each window to FAILED
    "no scorer configured" rather than exploding at import time.
    """
    try:
        import torch  # noqa: F401
    except ImportError:
        logger.warning(
            "torch is not importable; the machine-fingerprint check runs "
            "unconfigured. Install the ML extra (`uv sync --extra ml`) to score "
            "real audio through the pipeline."
        )
        return DefaultCheckRunner()
    return DefaultCheckRunner(checks=[build_default_check()])


def _build_transcript_worker() -> TranscriptWorker:
    """Check 4's out-of-band worker, with the real check when it can be built.

    Unlike the fingerprint factory this never refuses: check 4 runs outside the
    180 ms budget, so a slow build is late rather than fatal. Any failure here
    (no torch, no Whisper weights, no network for the first download) leaves the
    worker disabled, and fusion then reports the script signal absent and marks
    the update degraded rather than pretending the call was judged.
    """
    try:
        from ml.checks.stt_llm import build_default_check as build_stt_check

        return TranscriptWorker(build_stt_check())
    except Exception as exc:  # noqa: BLE001 - check 4 is never worth failing startup for
        logger.warning(
            "check 4 (stt_llm) is disabled: %s: %s. Risk scores will come from "
            "the fingerprint alone and every update will be marked degraded.",
            type(exc).__name__,
            exc,
        )
        return TranscriptWorker()


orchestrator = CallSessionOrchestrator(
    runner=_build_runner(), transcripts=_build_transcript_worker()
)


@app.websocket("/ws/audio/{stream_id}/{call_id}")
async def audio_ingestion_endpoint(websocket: WebSocket, stream_id: str, call_id: str) -> None:
    await websocket.accept()
    await run_audio_ingestion(
        websocket,
        stream_id,
        call_id,
        on_stream_start=orchestrator.on_stream_start,
        on_canonical_chunk=orchestrator.on_canonical_chunk,
        on_stream_end=orchestrator.on_stream_end,
    )


@app.websocket("/ws/risk/{stream_id}")
async def risk_update_endpoint(websocket: WebSocket, stream_id: str) -> None:
    await orchestrator.dispatcher.listen_forever(stream_id, websocket)
