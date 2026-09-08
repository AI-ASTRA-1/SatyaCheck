"""Tests for the Exotel Voice Streaming WebSocket adapter."""

from __future__ import annotations

import array
import asyncio
import base64
import json
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from acquisitions.exotel.ws_adapter import ExotelWebSocketAdapter, _resample_8k_to_16k
from contracts.acquisition import AudioChunk, StreamClose, StreamOpen, Transport


class FakeExotelWebSocket:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = list(messages)

    async def receive(self) -> dict[str, Any]:
        if not self._messages:
            raise WebSocketDisconnect()
        return self._messages.pop(0)


class ExplodingWebSocket:
    async def receive(self) -> dict[str, Any]:
        raise RuntimeError("network failure")


def test_connect_is_not_implemented() -> None:
    adapter = ExotelWebSocketAdapter()
    with pytest.raises(NotImplementedError):
        adapter.connect("endpoint", on_open=None, on_chunk=None, on_close=None)  # type: ignore[arg-type]


def test_exotel_json_stream_lifecycle() -> None:
    opens: list[StreamOpen] = []
    chunks: list[AudioChunk] = []
    closes: list[StreamClose] = []

    async def on_open(msg: StreamOpen) -> None:
        opens.append(msg)

    async def on_chunk(msg: AudioChunk) -> None:
        chunks.append(msg)

    async def on_close(msg: StreamClose) -> None:
        closes.append(msg)

    # 100 ms of 8000 Hz 16-bit mono PCM = 800 samples = 1600 bytes
    sample_8k_pcm = b"\x10\x00" * 800
    sample_8k_b64 = base64.b64encode(sample_8k_pcm).decode("ascii")

    messages = [
        {"type": "websocket.receive", "text": json.dumps({"event": "connected", "protocol": "Call"})},
        {
            "type": "websocket.receive",
            "text": json.dumps(
                {
                    "event": "start",
                    "sequence_number": "1",
                    "stream_sid": "MZ123",
                    "start": {
                        "stream_sid": "MZ123",
                        "call_sid": "CA456",
                        "account_sid": "AC789",
                        "from": "+919876543210",
                        "to": "+918047491899",
                        "media_format": {"sample_rate": "8000", "encoding": "audio/x-raw"},
                    },
                }
            ),
        },
        {
            "type": "websocket.receive",
            "text": json.dumps(
                {
                    "event": "media",
                    "sequence_number": "2",
                    "stream_sid": "MZ123",
                    "media": {"chunk": "1", "timestamp": "100", "payload": sample_8k_b64},
                }
            ),
        },
        {
            "type": "websocket.receive",
            "text": json.dumps(
                {
                    "event": "stop",
                    "sequence_number": "3",
                    "stream_sid": "MZ123",
                    "stop": {"call_sid": "CA456", "reason": "callended"},
                }
            ),
        },
    ]

    async def run() -> None:
        adapter = ExotelWebSocketAdapter()
        ws = FakeExotelWebSocket(messages)
        await adapter.run_forever(
            ws,
            "exotel-stream",
            "exotel-call",
            on_open=on_open,
            on_chunk=on_chunk,
            on_close=on_close,
        )

    asyncio.run(run())

    assert len(opens) == 1
    assert opens[0].transport == Transport.EXOTEL
    assert opens[0].caller_number == "+919876543210"
    assert opens[0].callee_number == "+918047491899"
    assert opens[0].sample_rate == 16000

    # 100 ms at 8 kHz (1600 B = 800 samples) upsamples to 1598 samples (3196 B):
    # the very first chunk of a stream has no prior sample to interpolate
    # against, so it's 2 samples short of a naive 2x (see _resample_8k_to_16k).
    # 3196 B slices into 4 full 20ms frames (2560 B); the 636 B remainder is
    # emitted as a final, unpadded, is_final=True chunk at stream close.
    assert len(chunks) == 5
    assert [c.sequence for c in chunks] == [0, 1, 2, 3, 4]
    assert all(c.transport == Transport.EXOTEL for c in chunks)
    assert all(c.sample_rate == 16000 for c in chunks)
    assert [len(c.payload) for c in chunks] == [640, 640, 640, 640, 636]
    assert [c.is_final for c in chunks] == [False, False, False, False, True]

    assert len(closes) == 1
    assert closes[0].reason == "completed"
    assert closes[0].frames_received == 5
    assert closes[0].bytes_received == 3196
    assert closes[0].dropped_frames == 0


def test_unexpected_error_emits_close_and_reraises() -> None:
    closes: list[StreamClose] = []

    async def on_open(msg: StreamOpen) -> None:
        pass

    async def on_chunk(msg: AudioChunk) -> None:
        pass

    async def on_close(msg: StreamClose) -> None:
        closes.append(msg)

    async def run() -> None:
        adapter = ExotelWebSocketAdapter()
        with pytest.raises(RuntimeError):
            await adapter.run_forever(
                ExplodingWebSocket(),
                "err-stream",
                "err-call",
                on_open=on_open,
                on_chunk=on_chunk,
                on_close=on_close,
            )

    asyncio.run(run())

    assert len(closes) == 1
    assert closes[0].reason == "error"


def test_resample_bridges_chunk_boundary() -> None:
    """Consecutive media events must interpolate across the chunk seam, not
    duplicate/copy verbatim at the boundary (see _resample_8k_to_16k)."""
    chunk1 = array.array("h", [0, 100, 200]).tobytes()
    chunk2 = array.array("h", [300, 400]).tobytes()

    out1, pending1 = _resample_8k_to_16k(chunk1, None)
    assert pending1 == 200
    samples1 = array.array("h")
    samples1.frombytes(out1)
    assert list(samples1) == [0, 50, 100, 150]

    out2, pending2 = _resample_8k_to_16k(chunk2, pending1)
    assert pending2 == 400
    samples2 = array.array("h")
    samples2.frombytes(out2)
    # First output sample of chunk 2 is the carried-over last sample of chunk 1
    # (200), and the next is the true midpoint toward chunk 2's first sample
    # (300) -- no flat/duplicated seam.
    assert list(samples2) == [200, 250, 300, 350]


async def _run_json_lifecycle(messages: list[dict[str, Any]]) -> tuple[list[StreamOpen], list[AudioChunk], list[StreamClose]]:
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
        ws,
        "exotel-stream",
        "exotel-call",
        on_open=on_open,
        on_chunk=on_chunk,
        on_close=on_close,
    )
    return opens, chunks, closes


def _start_message(sample_rate: str | int = "8000") -> dict[str, Any]:
    return {
        "type": "websocket.receive",
        "text": json.dumps(
            {
                "event": "start",
                "stream_sid": "MZ123",
                "start": {
                    "stream_sid": "MZ123",
                    "call_sid": "CA456",
                    "from": "+919876543210",
                    "to": "+918047491899",
                    "media_format": {"sample_rate": sample_rate, "encoding": "audio/x-raw"},
                },
            }
        ),
    }


def _media_message(payload_b64: str | None) -> dict[str, Any]:
    return {
        "type": "websocket.receive",
        "text": json.dumps({"event": "media", "media": {"chunk": "1", "payload": payload_b64}}),
    }


_STOP_MESSAGE = {
    "type": "websocket.receive",
    "text": json.dumps({"event": "stop", "stop": {"call_sid": "CA456", "reason": "callended"}}),
}


def test_odd_length_payload_is_trimmed_not_crashed() -> None:
    odd_pcm = b"\x10\x00" * 10 + b"\x01"  # 21 bytes, odd
    payload_b64 = base64.b64encode(odd_pcm).decode("ascii")
    messages = [_start_message(), _media_message(payload_b64), _STOP_MESSAGE]

    opens, _chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(opens) == 1
    assert len(closes) == 1
    assert closes[0].reason == "completed"  # did not crash/error


def test_unsupported_sample_rate_is_rejected() -> None:
    messages = [_start_message(sample_rate="44100"), _STOP_MESSAGE]

    _opens, chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(chunks) == 0
    assert len(closes) == 1
    assert closes[0].reason == "error"


def test_missing_media_payload_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    messages = [_start_message(), _media_message(None), _STOP_MESSAGE]

    with caplog.at_level("WARNING"):
        _opens, chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(chunks) == 0
    assert closes[0].reason == "completed"
    assert closes[0].frames_received == 0
    assert closes[0].dropped_frames == 1
    assert any("media payload" in record.message for record in caplog.records)


def test_invalid_base64_payload_counts_as_dropped_frame() -> None:
    messages = [_start_message(), _media_message("not-valid-base64!!!"), _STOP_MESSAGE]

    _opens, chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(chunks) == 0
    assert closes[0].reason == "completed"
    assert closes[0].dropped_frames == 1


def test_unrecognized_event_is_ignored() -> None:
    messages = [
        _start_message(),
        {"type": "websocket.receive", "text": json.dumps({"event": "mark", "mark": {"name": "x"}})},
        _STOP_MESSAGE,
    ]

    _opens, _chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(closes) == 1
    assert closes[0].reason == "completed"


def test_media_after_stop_is_not_processed() -> None:
    sample_8k_pcm = b"\x10\x00" * 800
    sample_8k_b64 = base64.b64encode(sample_8k_pcm).decode("ascii")
    messages = [_start_message(), _STOP_MESSAGE, _media_message(sample_8k_b64)]

    _opens, chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(chunks) == 0
    assert closes[0].reason == "completed"


def test_abrupt_websocket_disconnect_marks_dropped() -> None:
    # No stop event; FakeExotelWebSocket raises WebSocketDisconnect once exhausted.
    messages = [_start_message()]

    _opens, _chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(closes) == 1
    assert closes[0].reason == "dropped"


def test_asgi_disconnect_message_marks_dropped() -> None:
    messages = [_start_message(), {"type": "websocket.disconnect"}]

    _opens, _chunks, closes = asyncio.run(_run_json_lifecycle(messages))

    assert len(closes) == 1
    assert closes[0].reason == "dropped"
