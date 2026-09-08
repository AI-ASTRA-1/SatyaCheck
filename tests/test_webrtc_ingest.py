"""Tests for the WebRTC ingest join point: ExotelWebSocketAdapter's binary path.

Raw, already-16kHz-mono-s16le PCM sent as binary WebSocket frames is buffered and
sliced into canonical 640-byte frames regardless of chunk size -- see
docs/interfaces.md section 2.1. This is the join point a custom WebRTC adapter
connects to; ws_adapter.py's JSON/Exotel-protocol tests live in test_exotel_adapter.py.
"""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.websockets import WebSocketDisconnect

from acquisitions.exotel.ws_adapter import ExotelWebSocketAdapter
from contracts.acquisition import AudioChunk, StreamClose, StreamOpen, Transport


class FakeExotelWebSocket:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = list(messages)

    async def receive(self) -> dict[str, Any]:
        if not self._messages:
            raise WebSocketDisconnect()
        return self._messages.pop(0)


async def _run_binary_lifecycle(
    messages: list[dict[str, Any]],
) -> tuple[list[StreamOpen], list[AudioChunk], list[StreamClose]]:
    opens: list[StreamOpen] = []
    chunks: list[AudioChunk] = []
    closes: list[StreamClose] = []

    async def on_open(msg: StreamOpen) -> None:
        opens.append(msg)

    async def on_chunk(msg: AudioChunk) -> None:
        chunks.append(msg)

    async def on_close(msg: StreamClose) -> None:
        closes.append(msg)

    adapter = ExotelWebSocketAdapter()
    ws = FakeExotelWebSocket(messages)
    await adapter.run_forever(
        ws, "webrtc-stream", "webrtc-call", on_open=on_open, on_chunk=on_chunk, on_close=on_close
    )
    return opens, chunks, closes


def test_binary_frame_fallback() -> None:
    frame = b"\x00\x00" * 320  # 640 bytes
    messages = [
        {"type": "websocket.receive", "bytes": frame},
        {"type": "websocket.receive", "bytes": frame},
    ]

    opens, chunks, closes = asyncio.run(_run_binary_lifecycle(messages))

    assert len(opens) == 1
    assert opens[0].transport == Transport.WEBRTC
    assert len(chunks) == 2
    assert [c.sequence for c in chunks] == [0, 1]
    assert len(closes) == 1
    # No explicit stop event was sent; the fake socket just runs out of frames
    # and raises WebSocketDisconnect, which is an abrupt end, not a clean stop.
    assert closes[0].reason == "dropped"


def test_binary_frames_of_arbitrary_size_are_buffered_and_sliced() -> None:
    """A WebRTC sender forwards raw PCM in whatever chunk sizes it has on hand,
    not necessarily 640-byte aligned."""
    # Three irregular chunk sizes totalling 1250 bytes: one full 640-byte frame,
    # plus a 610-byte remainder that must survive as a final, unpadded chunk.
    chunk_sizes = [300, 500, 450]
    messages = [
        {"type": "websocket.receive", "bytes": b"\x01\x02" * (size // 2)} for size in chunk_sizes
    ]

    opens, chunks, closes = asyncio.run(_run_binary_lifecycle(messages))

    assert len(opens) == 1
    assert opens[0].transport == Transport.WEBRTC
    assert [len(c.payload) for c in chunks] == [640, 610]
    assert [c.is_final for c in chunks] == [False, True]
    assert closes[0].frames_received == 2
    assert closes[0].bytes_received == 1250


def test_binary_frame_odd_length_is_trimmed_not_crashed() -> None:
    odd_frame = (b"\x00\x00" * 320) + b"\x01"  # 641 bytes, odd
    messages = [{"type": "websocket.receive", "bytes": odd_frame}]

    opens, chunks, closes = asyncio.run(_run_binary_lifecycle(messages))

    assert len(opens) == 1
    assert [len(c.payload) for c in chunks] == [640]
    assert closes[0].reason == "dropped"  # no stop event sent; socket just runs out
