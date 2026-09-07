"""Standalone WebSocket signalling server for WebRTC acquisition.

Brokers offer/answer and ICE candidates between client audio sources (browsers,
test scripts) and server-side aiortc RTCPeerConnection instances.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set
import uuid

# Invariant: only standard library, aiortc, websockets, and contracts.acquisition
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    websockets = None
    WebSocketServerProtocol = Any  # type: ignore

try:
    from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
    from aiortc.sdp import candidate_from_sdp
except ImportError:
    RTCPeerConnection = None  # type: ignore
    RTCSessionDescription = None  # type: ignore
    RTCIceCandidate = None  # type: ignore
    candidate_from_sdp = None  # type: ignore

from .adapter import WebRTCAdapter, WebRTCSession

logger = logging.getLogger("webrtc.signalling")


class SignallingServer:
    """Async WebSocket signalling server handling WebRTC handshakes."""

    def __init__(
        self,
        adapter: Optional[WebRTCAdapter] = None,
        host: str = "0.0.0.0",
        port: int = 8766,
    ) -> None:
        self.adapter = adapter or WebRTCAdapter()
        self.host = host
        self.port = port
        self._server: Optional[Any] = None
        self._pcs: Set[Any] = set()
        self._is_running = False

    async def handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handle incoming WebSocket client session."""
        if RTCPeerConnection is None:
            err_msg = "aiortc is not installed. Please install aiortc to use WebRTC signalling."
            logger.error(err_msg)
            await websocket.send(json.dumps({"type": "error", "reason": err_msg}))
            return

        peer_id = f"peer_{uuid.uuid4().hex[:8]}"
        pc = RTCPeerConnection()
        self._pcs.add(pc)

        session: Optional[WebRTCSession] = None
        active_tasks: Set[asyncio.Task] = set()

        @pc.on("track")
        def on_track(track: Any) -> None:
            if track.kind == "audio":
                logger.info("[%s] Received audio track (id=%s)", peer_id, track.id)
                if session is not None:
                    task = asyncio.create_task(session.handle_audio_track(track))
                    active_tasks.add(task)
                    task.add_done_callback(active_tasks.discard)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            logger.info("[%s] PeerConnection state: %s", peer_id, pc.connectionState)
            if pc.connectionState in ("failed", "closed"):
                if session is not None:
                    reason = "dropped" if pc.connectionState == "failed" else "completed"
                    await session.close(reason=reason)
                await pc.close()

        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError as exc:
                    logger.warning("[%s] Malformed JSON received: %s", peer_id, exc)
                    await websocket.send(json.dumps({"type": "error", "reason": "Invalid JSON payload"}))
                    continue

                msg_type = data.get("type")

                if msg_type == "offer":
                    call_id = data.get("call_id") or f"call_{uuid.uuid4().hex[:8]}"
                    sdp = data.get("sdp")

                    if not sdp:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "reason": "Missing 'sdp' in offer message",
                        }))
                        continue

                    # Create or bind adapter session
                    session = self.adapter.create_session(call_id=call_id, peer_id=peer_id)
                    logger.info(
                        "[%s] Initialized session %s for call %s",
                        peer_id,
                        session.stream_id,
                        call_id,
                    )

                    # 1. Send session_id message to client
                    await websocket.send(json.dumps({
                        "type": "session_id",
                        "stream_id": session.stream_id,
                        "call_id": call_id,
                    }))

                    # 2. Configure remote offer
                    try:
                        offer_desc = RTCSessionDescription(sdp=sdp, type="offer")
                        await pc.setRemoteDescription(offer_desc)

                        # 3. Create and configure local answer
                        answer_desc = await pc.createAnswer()
                        await pc.setLocalDescription(answer_desc)

                        # 4. Send answer message to client
                        await websocket.send(json.dumps({
                            "type": "answer",
                            "sdp": pc.localDescription.sdp,
                        }))
                        logger.info("[%s] Sent answer for call %s", peer_id, call_id)
                    except Exception as exc:
                        logger.error("[%s] Failed processing offer: %s", peer_id, exc, exc_info=True)
                        await websocket.send(json.dumps({
                            "type": "error",
                            "reason": f"Offer processing error: {exc}",
                        }))

                elif msg_type == "ice":
                    cand_data = data.get("candidate")
                    if cand_data and candidate_from_sdp is not None:
                        try:
                            if isinstance(cand_data, dict):
                                cand_str = cand_data.get("candidate", "")
                                if cand_str and cand_str.strip():
                                    ice_cand = candidate_from_sdp(cand_str)
                                    ice_cand.sdpMid = cand_data.get("sdpMid")
                                    ice_cand.sdpMLineIndex = cand_data.get("sdpMLineIndex")
                                    await pc.addIceCandidate(ice_cand)
                            elif isinstance(cand_data, str) and cand_data.strip():
                                ice_cand = candidate_from_sdp(cand_data)
                                await pc.addIceCandidate(ice_cand)
                        except Exception as exc:
                            logger.warning("[%s] Failed to add ICE candidate: %s", peer_id, exc)

                elif msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))

                else:
                    logger.warning("[%s] Unknown message type: %s", peer_id, msg_type)
                    await websocket.send(json.dumps({
                        "type": "error",
                        "reason": f"Unsupported message type: '{msg_type}'",
                    }))

        except websockets.exceptions.ConnectionClosed:
            logger.info("[%s] WebSocket client disconnected", peer_id)
        except Exception as exc:
            logger.error("[%s] WebSocket unexpected error: %s", peer_id, exc, exc_info=True)
        finally:
            if session is not None:
                await session.close(reason="client_disconnected")
            for task in list(active_tasks):
                task.cancel()
            await pc.close()
            self._pcs.discard(pc)
            logger.info("[%s] Cleaned up peer connection", peer_id)

    async def start(self) -> None:
        """Start the WebSocket signalling server."""
        if websockets is None:
            raise RuntimeError("websockets library is required. Install via: pip install websockets")

        logger.info("Starting WebRTC Signalling Server on ws://%s:%d", self.host, self.port)
        self._is_running = True
        self._server = await websockets.serve(self.handle_client, self.host, self.port)

    async def close(self) -> None:
        """Stop the signalling server and close active peer connections."""
        self._is_running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for pc in list(self._pcs):
            await pc.close()
        self._pcs.clear()
        self.adapter.close()
        logger.info("WebRTC Signalling Server stopped.")

    async def serve(self) -> None:
        """Run the server until interrupted."""
        await self.start()
        try:
            await asyncio.Future()  # run forever
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await self.close()


def main() -> None:
    """Entrypoint for running the signalling server as a standalone script."""
    parser = argparse.ArgumentParser(description="WebRTC WebSocket Signalling Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8766, help="Binding port (default: 8766)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level (default: INFO)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Initialize adapter with dummy logging consumer for standalone demo
    adapter = WebRTCAdapter()
    adapter.connect(
        endpoint=f"ws://{args.host}:{args.port}",
        on_open=lambda msg: logger.info(">> [CONTRACT on_open] stream=%s call=%s codec=%s", msg.stream_id, msg.call_id, msg.codec),
        on_chunk=lambda chk: logger.debug(">> [CONTRACT on_chunk] stream=%s seq=%d bytes=%d", chk.stream_id, chk.sequence, len(chk.payload)),
        on_close=lambda cls: logger.info(">> [CONTRACT on_close] stream=%s frames=%d bytes=%d reason=%s", cls.stream_id, cls.frames_received, cls.bytes_received, cls.reason),
    )

    server = SignallingServer(adapter=adapter, host=args.host, port=args.port)
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        logger.info("Signalling server stopped by user.")


if __name__ == "__main__":
    main()
