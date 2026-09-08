"""Wiring for the audio-in WebSocket endpoint.

The only file in backend/ allowed to import acquisitions (see docs/interfaces.md
section 8's import rule matrix). Satisfies tests/test_transport_invariant.py
because this module lives inside backend/app/ingestion/.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from acquisitions.exotel.ws_adapter import ExotelWebSocketAdapter, WebSocketLike
from backend.app.ingestion.consumer import IngestionConsumer
from contracts.pipeline import CanonicalAudioChunk

logger = logging.getLogger("satyacheck.ingestion")

OnStreamStart = Callable[[str, str, datetime], Awaitable[None]]
OnCanonicalChunk = Callable[[CanonicalAudioChunk], Awaitable[None]]
OnStreamEnd = Callable[[str, str], Awaitable[None]]


async def run_audio_ingestion(
    websocket: WebSocketLike,
    stream_id: str,
    call_id: str,
    *,
    on_stream_start: OnStreamStart,
    on_canonical_chunk: OnCanonicalChunk,
    on_stream_end: OnStreamEnd,
) -> None:
    consumer = IngestionConsumer(
        on_stream_start=on_stream_start,
        on_canonical_chunk=on_canonical_chunk,
        on_stream_end=on_stream_end,
    )
    adapter = ExotelWebSocketAdapter()
    try:
        await adapter.run_forever(
            websocket,
            stream_id,
            call_id,
            on_open=consumer.on_open,
            on_chunk=consumer.on_chunk,
            on_close=consumer.on_close,
        )
    except Exception:
        # Per contracts.acquisition.AudioStreamAdapter: raising here degrades to
        # "no warning" for the rest of this call. The adapter's own `finally`
        # already emitted a best-effort StreamClose(reason="error"); this
        # boundary just stops the exception from reaching the ASGI route as an
        # unhandled error and killing the connection abruptly.
        logger.exception("audio ingestion failed for stream_id=%s call_id=%s", stream_id, call_id)
