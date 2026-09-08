"""Tests for the dev WebSocket stand-in acquisition adapter."""

from __future__ import annotations

import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from acquisitions.webrtc.dev_ws_adapter import DevWebSocketAdapter
from contracts.acquisition import AudioChunk, StreamClose, StreamOpen, Transport

FRAME = b"\x00\x00" * 320  # frame content is irrelevant to the adapter itself


class FakeWebSocket:
    def __init__(self, frames: list[bytes]) -> None:
        self._frames = list(frames)

    async def receive_bytes(self) -> bytes:
        if not self._frames:
            raise WebSocketDisconnect()
        return self._frames.pop(0)


class ExplodingWebSocket:
    async def receive_bytes(self) -> bytes:
        raise RuntimeError("boom")


def test_connect_is_not_implemented() -> None:
    adapter = DevWebSocketAdapter()
    with pytest.raises(NotImplementedError):
        adapter.connect("endpoint", on_open=None, on_chunk=None, on_close=None)  # type: ignore[arg-type]


def test_stream_lifecycle_and_sequence() -> None:
    opens: list[StreamOpen] = []
    chunks: list[AudioChunk] = []
    closes: list[StreamClose] = []

    async def on_open(msg: StreamOpen) -> None:
        opens.append(msg)

    async def on_chunk(msg: AudioChunk) -> None:
        chunks.append(msg)

    async def on_close(msg: StreamClose) -> None:
        closes.append(msg)

    async def run() -> None:
        adapter = DevWebSocketAdapter()
        websocket = FakeWebSocket([FRAME, FRAME, FRAME])
        await adapter.run_forever(
            websocket,
            "s1",
            "c1",
            on_open=on_open,
            on_chunk=on_chunk,
            on_close=on_close,
        )

    asyncio.run(run())

    assert len(opens) == 1
    assert opens[0].transport == Transport.WEBRTC
    assert [c.sequence for c in chunks] == [0, 1, 2]
    assert all(c.transport == Transport.WEBRTC for c in chunks)
    assert len(closes) == 1
    assert closes[0].reason == "completed"
    assert closes[0].frames_received == 3


def test_unexpected_error_still_emits_close_and_reraises() -> None:
    closes: list[StreamClose] = []

    async def on_open(msg: StreamOpen) -> None:
        pass

    async def on_chunk(msg: AudioChunk) -> None:
        pass

    async def on_close(msg: StreamClose) -> None:
        closes.append(msg)

    async def run() -> None:
        adapter = DevWebSocketAdapter()
        with pytest.raises(RuntimeError):
            await adapter.run_forever(
                ExplodingWebSocket(),
                "s1",
                "c1",
                on_open=on_open,
                on_chunk=on_chunk,
                on_close=on_close,
            )

    asyncio.run(run())

    assert len(closes) == 1
    assert closes[0].reason == "error"
