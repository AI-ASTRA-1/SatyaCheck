"""Unit tests for the rewritten WebRTC acquisition layer.

Verifies:
1. Protocol conformance (AudioStreamAdapter signature).
2. Audio ingest WebSocket: JSON handshake then binary Opus frames produce
   correct AudioChunk callbacks with monotonic sequences.
3. Signalling broker: full dial -> ringing -> incoming_call -> accept ->
   answer -> hangup -> call_ended flow.
4. Signalling broker: ICE candidate relay between caller and callee.
5. Transport invariant AST walk ensuring no illegal imports.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path
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

import websockets


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
    """Test suite for protocol compliance."""

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


class TestAudioIngest(unittest.TestCase):
    """Test audio ingest WebSocket: handshake + binary frames."""

    def test_audio_ingest_handshake_and_chunks(self) -> None:
        """JSON handshake on ingest port, then 10 binary frames produce
        10 AudioChunk callbacks with monotonic sequence and correct fields."""

        async def run() -> None:
            consumer = DummyConsumer()
            adapter = WebRTCAdapter(codec=Codec.OPUS, sample_rate=48000, channels=1)
            port = 18767  # test port, avoid clash with production

            adapter.connect(
                endpoint=f"ws://127.0.0.1:{port}",
                on_open=consumer.on_open,
                on_chunk=consumer.on_chunk,
                on_close=consumer.on_close,
            )

            await adapter.serve_audio_ingest(host="127.0.0.1", port=port)

            try:
                async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                    # Step 1: send JSON handshake
                    handshake = {
                        "call_id": "call_ingest_test",
                        "codec": "opus",
                        "sample_rate": 48000,
                        "channels": 1,
                    }
                    await ws.send(json.dumps(handshake))

                    # Small delay to let the server process the handshake
                    await asyncio.sleep(0.05)

                    # Step 2: send 10 binary Opus frames
                    payload = b"\xaa\xbb\xcc" * 20  # 60 bytes per frame
                    for _ in range(10):
                        await ws.send(payload)
                        await asyncio.sleep(0.01)

                # WebSocket closed; give the server a moment to finalize
                await asyncio.sleep(0.1)

                # -- verify on_open --
                self.assertIsNotNone(consumer.open_msg, "on_open was never called")
                open_msg = consumer.open_msg
                self.assertEqual(open_msg.call_id, "call_ingest_test")
                self.assertEqual(open_msg.transport, Transport.WEBRTC)
                self.assertEqual(open_msg.codec, Codec.OPUS)
                self.assertEqual(open_msg.sample_rate, 48000)
                self.assertEqual(open_msg.channels, 1)
                self.assertEqual(open_msg.frame_ms, 20)
                self.assertEqual(open_msg.direction, CallDirection.INBOUND)
                self.assertTrue(open_msg.stream_id.startswith("stream_"))

                # -- verify chunks --
                self.assertEqual(len(consumer.chunks), 10, "Expected 10 chunks")
                for idx, chunk in enumerate(consumer.chunks):
                    self.assertEqual(chunk.call_id, "call_ingest_test")
                    self.assertEqual(chunk.transport, Transport.WEBRTC)
                    self.assertEqual(chunk.codec, Codec.OPUS)
                    self.assertEqual(chunk.sequence, idx, f"Non-monotonic at {idx}")
                    self.assertEqual(chunk.payload, payload)
                    self.assertEqual(chunk.sample_rate, 48000)
                    self.assertEqual(chunk.channels, 1)
                    self.assertEqual(chunk.frame_ms, 20)

                # -- verify on_close --
                self.assertIsNotNone(consumer.close_msg, "on_close was never called")
                close_msg = consumer.close_msg
                self.assertEqual(close_msg.call_id, "call_ingest_test")
                self.assertEqual(close_msg.reason, "completed")
                self.assertEqual(close_msg.frames_received, 10)
                self.assertEqual(close_msg.bytes_received, 10 * len(payload))

            finally:
                await adapter.close_ingest()

        asyncio.run(run())


class TestSignallingBroker(unittest.TestCase):
    """Test the signalling broker message routing."""

    def test_signalling_dial_accept_flow(self) -> None:
        """Full flow: dial -> ringing, incoming_call -> accept -> answer,
        hangup -> call_ended to both peers."""

        async def run() -> None:
            port = 18766
            server = SignallingServer(host="127.0.0.1", port=port)
            await server.start()

            try:
                # Connect two clients: caller and callee
                async with websockets.connect(f"ws://127.0.0.1:{port}") as caller_ws:
                    async with websockets.connect(f"ws://127.0.0.1:{port}") as callee_ws:
                        # Small delay for both connections to register
                        await asyncio.sleep(0.05)

                        # Caller sends dial
                        await caller_ws.send(json.dumps({
                            "type": "dial",
                            "call_id": "call_test_123",
                            "sdp": "v=0\r\noffer_sdp_here",
                        }))

                        # Caller should receive ringing
                        raw = await asyncio.wait_for(caller_ws.recv(), timeout=2.0)
                        msg = json.loads(raw)
                        self.assertEqual(msg["type"], "ringing")
                        self.assertEqual(msg["call_id"], "call_test_123")

                        # Callee should receive incoming_call with the offer
                        raw = await asyncio.wait_for(callee_ws.recv(), timeout=2.0)
                        msg = json.loads(raw)
                        self.assertEqual(msg["type"], "incoming_call")
                        self.assertEqual(msg["call_id"], "call_test_123")
                        self.assertEqual(msg["sdp"], "v=0\r\noffer_sdp_here")

                        # Callee sends accept with answer SDP
                        await callee_ws.send(json.dumps({
                            "type": "accept",
                            "call_id": "call_test_123",
                            "sdp": "v=0\r\nanswer_sdp_here",
                        }))

                        # Caller should receive answer
                        raw = await asyncio.wait_for(caller_ws.recv(), timeout=2.0)
                        msg = json.loads(raw)
                        self.assertEqual(msg["type"], "answer")
                        self.assertEqual(msg["sdp"], "v=0\r\nanswer_sdp_here")

                        # Caller sends hangup
                        await caller_ws.send(json.dumps({
                            "type": "hangup",
                            "call_id": "call_test_123",
                        }))

                        # Both should receive call_ended
                        raw_caller = await asyncio.wait_for(caller_ws.recv(), timeout=2.0)
                        msg_caller = json.loads(raw_caller)
                        self.assertEqual(msg_caller["type"], "call_ended")
                        self.assertEqual(msg_caller["call_id"], "call_test_123")

                        raw_callee = await asyncio.wait_for(callee_ws.recv(), timeout=2.0)
                        msg_callee = json.loads(raw_callee)
                        self.assertEqual(msg_callee["type"], "call_ended")
                        self.assertEqual(msg_callee["call_id"], "call_test_123")

            finally:
                await server.close()

        asyncio.run(run())

    def test_signalling_ice_relay(self) -> None:
        """ICE candidates are relayed bidirectionally between caller and callee."""

        async def run() -> None:
            port = 18768
            server = SignallingServer(host="127.0.0.1", port=port)
            await server.start()

            try:
                async with websockets.connect(f"ws://127.0.0.1:{port}") as caller_ws:
                    async with websockets.connect(f"ws://127.0.0.1:{port}") as callee_ws:
                        await asyncio.sleep(0.05)

                        # Establish call first
                        await caller_ws.send(json.dumps({
                            "type": "dial",
                            "call_id": "call_ice_test",
                            "sdp": "v=0\r\noffer",
                        }))

                        # Drain ringing and incoming_call
                        await asyncio.wait_for(caller_ws.recv(), timeout=2.0)  # ringing
                        await asyncio.wait_for(callee_ws.recv(), timeout=2.0)  # incoming_call

                        # Accept
                        await callee_ws.send(json.dumps({
                            "type": "accept",
                            "call_id": "call_ice_test",
                            "sdp": "v=0\r\nanswer",
                        }))
                        await asyncio.wait_for(caller_ws.recv(), timeout=2.0)  # answer

                        # Caller sends ICE candidate
                        ice_from_caller = {
                            "candidate": "candidate:1 1 UDP 2130706431 192.168.1.1 5000 typ host",
                            "sdpMid": "0",
                            "sdpMLineIndex": 0,
                        }
                        await caller_ws.send(json.dumps({
                            "type": "ice",
                            "call_id": "call_ice_test",
                            "candidate": ice_from_caller,
                        }))

                        # Callee should receive the ICE candidate
                        raw = await asyncio.wait_for(callee_ws.recv(), timeout=2.0)
                        msg = json.loads(raw)
                        self.assertEqual(msg["type"], "ice")
                        self.assertEqual(msg["candidate"], ice_from_caller)

                        # Callee sends ICE candidate back
                        ice_from_callee = {
                            "candidate": "candidate:2 1 UDP 2130706431 192.168.1.2 5001 typ host",
                            "sdpMid": "0",
                            "sdpMLineIndex": 0,
                        }
                        await callee_ws.send(json.dumps({
                            "type": "ice",
                            "call_id": "call_ice_test",
                            "candidate": ice_from_callee,
                        }))

                        # Caller should receive it
                        raw = await asyncio.wait_for(caller_ws.recv(), timeout=2.0)
                        msg = json.loads(raw)
                        self.assertEqual(msg["type"], "ice")
                        self.assertEqual(msg["candidate"], ice_from_callee)

                        # Clean up
                        await caller_ws.send(json.dumps({
                            "type": "hangup",
                            "call_id": "call_ice_test",
                        }))
                        # Drain call_ended
                        await asyncio.wait_for(caller_ws.recv(), timeout=2.0)
                        await asyncio.wait_for(callee_ws.recv(), timeout=2.0)

            finally:
                await server.close()

        asyncio.run(run())


class TestTransportInvariant(unittest.TestCase):
    """AST walk verifying strict transport boundary invariants."""

    def test_transport_invariant_ast_walk(self) -> None:
        """Verify acquisitions/webrtc/ only imports allowed modules
        and never touches backend/ml/app."""
        webrtc_dir = Path(__file__).resolve().parent

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
                                f"{py_file.name} illegally imports '{alias.name}' "
                                f"from forbidden layer '{forbidden}'",
                            )
                        self.assertIn(
                            top_module,
                            allowed_top_levels,
                            f"{py_file.name} imports unauthorized module '{alias.name}'",
                        )

                elif isinstance(node, ast.ImportFrom):
                    # Relative imports within acquisitions/webrtc/ are fine
                    if node.level > 0:
                        continue

                    if node.module:
                        top_module = node.module.split(".")[0]
                        for forbidden in forbidden_prefixes:
                            self.assertFalse(
                                node.module.startswith(forbidden),
                                f"{py_file.name} illegally imports '{node.module}' "
                                f"from forbidden layer '{forbidden}'",
                            )
                        self.assertIn(
                            top_module,
                            allowed_top_levels,
                            f"{py_file.name} imports unauthorized module '{node.module}'",
                        )


if __name__ == "__main__":
    unittest.main()
