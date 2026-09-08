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
from backend.app.response.dispatcher import ResponseDispatcher
from contracts.checks import ReasonCode
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioChunk
from contracts.risk import CallEnded, RiskLevel, RiskUpdate, RiskVerdict, SessionStart
from ml.checks.machine_fingerprint import build_default_check
from ml.runner.runner import DefaultCheckRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("satyacheck.session")

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
    ) -> None:
        self.runner = runner if runner is not None else DefaultCheckRunner()
        self.fusion = fusion if fusion is not None else RiskFusionEngine()
        self.dispatcher = dispatcher if dispatcher is not None else ResponseDispatcher()
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
        update = self.fusion.update(results, context)
        self._last_update[stream_id] = update
        logger.info(
            "processed by backend: stream_id=%s score=%d risk_level=%s verdict=%s",
            stream_id,
            update.score,
            update.risk_level.value,
            update.verdict.value,
        )
        await self.dispatcher.send(stream_id, update)


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


orchestrator = CallSessionOrchestrator(runner=_build_runner())


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
