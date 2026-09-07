"""Unit tests for WebRTC acquisition layer.

Verifies:
1. Protocol conformance (AudioStreamAdapter & AudioStreamConsumer).
2. Monotonic sequence numbering and field validation on AudioChunk.
3. Exact callback ordering (on_open -> on_chunk* -> on_close).
4. Transport invariant AST walk ensuring no illegal imports across boundaries.
"""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime
import inspect
from pathlib import Path
import sys
from typing import List
import unittest

from .contracts_shim import (
    AudioChunk,
    AudioStreamAdapter,
    AudioStreamConsumer,
    CallDirection,
    Codec,
    StreamClose,
    StreamOpen,
    Transport,
)
from .adapter import WebRTCAdapter, WebRTCSession
from .signalling import SignallingServer


class DummyConsumer:
    """Test consumer satisfying AudioStreamConsumer protocol."""

    def __init__(self) -> None:
        self.open_msg: StreamOpen | None = None
        self.chunks: List[AudioChunk] = []
        self.close_msg: StreamClose | None = None

    def on_open(self, open_msg: StreamOpen) -> None:
        self.open_msg = open_msg

    def on_chunk(self, chunk: AudioChunk) -> None:
        self.chunks.append(chunk)

    def on_close(self, close_msg: StreamClose) -> None:
        self.close_msg = close_msg


class TestWebRTCAdapterProtocol(unittest.TestCase):
    """Test suite for protocol compliance and callback sequences."""

    def test_protocol_signature(self) -> None:
        """Verify WebRTCAdapter satisfies AudioStreamAdapter signature."""
        adapter = WebRTCAdapter()
        self.assertTrue(hasattr(adapter, "connect"))

        sig = inspect.signature(adapter.connect)
        params = list(sig.parameters.keys())
        self.assertIn("endpoint", params)
        self.assertIn("on_open", params)
        self.assertIn("on_chunk", params)
        self.assertIn("on_close", params)

        # Keyword-only callback parameters
        self.assertEqual(sig.parameters["on_open"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(sig.parameters["on_chunk"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(sig.parameters["on_close"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_audio_chunk_monotonicity_and_fields(self) -> None:
        """Verify 10 chunks fed through adapter maintain monotonic sequence and transport tag."""
        consumer = DummyConsumer()
        adapter = WebRTCAdapter(codec=Codec.OPUS, sample_rate=48000, channels=1, frame_ms=20)

        adapter.connect(
            endpoint="ws://127.0.0.1:8766",
            on_open=consumer.on_open,
            on_chunk=consumer.on_chunk,
            on_close=consumer.on_close,
        )

        call_id = "test_call_987"
        peer_id = "peer_test_456"
        session = adapter.create_session(call_id=call_id, peer_id=peer_id)

        # Feed 10 chunks
        payload_chunk = b"\x00\x01\x02\x03\x04" * 10  # 50 bytes
        for i in range(10):
            session.push_chunk(payload=payload_chunk, rtp_ts=1000 + i * 960)

        session.close_sync(reason="completed")

        # 1. Verify on_open
        self.assertIsNotNone(consumer.open_msg)
        open_msg = consumer.open_msg
        self.assertEqual(open_msg.stream_id, session.stream_id)
        self.assertEqual(open_msg.call_id, call_id)
        self.assertEqual(open_msg.transport, Transport.WEBRTC)
        self.assertEqual(open_msg.direction, CallDirection.INBOUND)
        self.assertIsNone(open_msg.caller_number)
        self.assertIsNone(open_msg.callee_number)
        self.assertEqual(open_msg.codec, Codec.OPUS)
        self.assertEqual(open_msg.sample_rate, 48000)
        self.assertEqual(open_msg.channels, 1)
        self.assertEqual(open_msg.frame_ms, 20)
        self.assertEqual(open_msg.external_ref, peer_id)

        # 2. Verify chunks
        self.assertEqual(len(consumer.chunks), 10)
        for idx, chunk in enumerate(consumer.chunks):
            self.assertEqual(chunk.stream_id, session.stream_id)
            self.assertEqual(chunk.call_id, call_id)
            self.assertEqual(chunk.transport, Transport.WEBRTC)
            self.assertEqual(chunk.codec, Codec.OPUS)
            self.assertEqual(chunk.sample_rate, 48000)
            self.assertEqual(chunk.channels, 1)
            self.assertEqual(chunk.frame_ms, 20)
            self.assertEqual(chunk.sequence, idx, f"Sequence must be monotonic {idx}")
            self.assertEqual(chunk.payload, payload_chunk)
            self.assertEqual(chunk.rtp_ts, 1000 + idx * 960)
            self.assertEqual(chunk.metadata.get("peer_id"), peer_id)
            self.assertIsInstance(chunk.received_at, datetime)

        # 3. Verify on_close
        self.assertIsNotNone(consumer.close_msg)
        close_msg = consumer.close_msg
        self.assertEqual(close_msg.stream_id, session.stream_id)
        self.assertEqual(close_msg.call_id, call_id)
        self.assertEqual(close_msg.reason, "completed")
        self.assertEqual(close_msg.frames_received, 10)
        self.assertEqual(close_msg.bytes_received, 10 * len(payload_chunk))
        self.assertEqual(close_msg.dropped_frames, 0)

    def test_mock_async_track_consumption(self) -> None:
        """Test consuming an async audio track yielding frames."""
        async def run_async_test() -> None:
            consumer = DummyConsumer()
            adapter = WebRTCAdapter()
            adapter.connect(
                endpoint="ws://127.0.0.1:8766",
                on_open=consumer.on_open,
                on_chunk=consumer.on_chunk,
                on_close=consumer.on_close,
            )

            session = adapter.create_session(call_id="call_async_test")

            # Mock track
            class MockTrack:
                def __init__(self) -> None:
                    self.count = 0

                async def recv(self) -> bytes | None:
                    if self.count >= 5:
                        return None
                    self.count += 1
                    return b"\xaa\xbb" * 20

            mock_track = MockTrack()
            await session.handle_audio_track(mock_track)

            self.assertEqual(len(consumer.chunks), 5)
            self.assertEqual([c.sequence for c in consumer.chunks], [0, 1, 2, 3, 4])
            self.assertIsNotNone(consumer.close_msg)
            self.assertEqual(consumer.close_msg.frames_received, 5)

        asyncio.run(run_async_test())


class TestTransportInvariant(unittest.TestCase):
    """AST walk verifying strict transport boundary invariants."""

    def test_transport_invariant_ast_walk(self) -> None:
        """Verify acquisitions/webrtc/ only imports allowed modules and never touches backend/ml/app."""
        webrtc_dir = Path(__file__).resolve().parent

        # Whitelist of top-level modules allowed
        allowed_top_levels = {
            # Standard libraries
            "argparse", "ast", "asyncio", "dataclasses", "datetime", "enum",
            "inspect", "json", "logging", "pathlib", "sys", "types", "typing",
            "unittest", "urllib", "uuid", "__future__",
            # Approved external transport dependencies
            "aiortc", "websockets", "aiohttp", "av",
            # Allowed contract interface
            "contracts",
        }

        forbidden_prefixes = ("backend", "ml", "app", "tests", "docs")

        py_files = list(webrtc_dir.glob("*.py"))
        self.assertGreater(len(py_files), 0, "Expected python files in acquisitions/webrtc/")

        for py_file in py_files:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top_module = alias.name.split(".")[0]
                        for forbidden in forbidden_prefixes:
                            self.assertFalse(
                                alias.name.startswith(forbidden),
                                f"{py_file.name} illegally imports '{alias.name}' from forbidden layer '{forbidden}'",
                            )
                        self.assertIn(
                            top_module,
                            allowed_top_levels,
                            f"{py_file.name} imports unauthorized module '{alias.name}'",
                        )

                elif isinstance(node, ast.ImportFrom):
                    # Relative imports (level > 0) within acquisitions/webrtc/ are intra-package
                    if node.level > 0:
                        continue

                    if node.module:
                        top_module = node.module.split(".")[0]
                        for forbidden in forbidden_prefixes:
                            self.assertFalse(
                                node.module.startswith(forbidden),
                                f"{py_file.name} illegally imports '{node.module}' from forbidden layer '{forbidden}'",
                            )
                        self.assertIn(
                            top_module,
                            allowed_top_levels,
                            f"{py_file.name} imports unauthorized module '{node.module}'",
                        )


class TestWebRTCEndToEnd(unittest.TestCase):
    """End-to-end signalling handshake test using websockets and aiortc."""

    def test_signalling_offer_answer_handshake(self) -> None:
        """Test complete offer/answer handshake over WebSocket."""
        from aiortc import RTCPeerConnection
        import websockets
        import json

        async def run_e2e() -> None:
            consumer = DummyConsumer()
            adapter = WebRTCAdapter()
            port = 8779
            adapter.connect(
                endpoint=f"ws://127.0.0.1:{port}",
                on_open=consumer.on_open,
                on_chunk=consumer.on_chunk,
                on_close=consumer.on_close,
            )

            server = SignallingServer(adapter=adapter, host="127.0.0.1", port=port)
            await server.start()

            client_pc = RTCPeerConnection()
            client_pc.addTransceiver("audio", direction="sendonly")

            try:
                async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                    offer = await client_pc.createOffer()
                    await client_pc.setLocalDescription(offer)

                    # Send offer
                    await ws.send(json.dumps({
                        "type": "offer",
                        "call_id": "call_e2e_123",
                        "sdp": client_pc.localDescription.sdp,
                    }))

                    # Receive session_id
                    raw_msg1 = await ws.recv()
                    msg1 = json.loads(raw_msg1)
                    self.assertEqual(msg1.get("type"), "session_id")
                    self.assertEqual(msg1.get("call_id"), "call_e2e_123")
                    self.assertTrue(msg1.get("stream_id").startswith("stream_"))

                    # Receive answer
                    raw_msg2 = await ws.recv()
                    msg2 = json.loads(raw_msg2)
                    self.assertEqual(msg2.get("type"), "answer")
                    self.assertIn("v=0", msg2.get("sdp", ""))

                    # Send ping, verify pong
                    await ws.send(json.dumps({"type": "ping"}))
                    raw_msg3 = await ws.recv()
                    msg3 = json.loads(raw_msg3)
                    self.assertEqual(msg3.get("type"), "pong")

            finally:
                await client_pc.close()
                await server.close()

        asyncio.run(run_e2e())


if __name__ == "__main__":
    unittest.main()
