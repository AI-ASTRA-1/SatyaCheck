"""Pure WebSocket signalling broker for WebRTC P2P calls.

Routes SDP offers/answers and ICE candidates between two phone peers.
Handles one call at a time (demo mode). No aiortc, no server-side
PeerConnection, no audio processing. Audio flows peer-to-peer between
the two phones; this server never sees it.

Message protocol (contract A from the split-ownership plan):

    App -> Server:  { "type": "dial",          "call_id": "...", "sdp": "<offer>" }
    Server -> App:  { "type": "ringing",       "call_id": "..." }
    Server -> App:  { "type": "incoming_call", "call_id": "...", "sdp": "<offer>" }
    App -> Server:  { "type": "accept",        "call_id": "...", "sdp": "<answer>" }
    App <-> Server: { "type": "ice",           "call_id": "...", "candidate": {...} }
    App -> Server:  { "type": "hangup",        "call_id": "..." }
    Server -> App:  { "type": "call_ended",    "call_id": "..." }
    Server -> App:  { "type": "error",         "reason": "..." }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any, Optional, Set
import uuid

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore[assignment]

logger = logging.getLogger("webrtc.signalling")


class CallState:
    """Tracks a single active call between two peers."""

    def __init__(self, call_id: str, caller_ws: Any, offer_sdp: str) -> None:
        self.call_id = call_id
        self.caller_ws = caller_ws
        self.callee_ws: Optional[Any] = None
        self.offer_sdp = offer_sdp
        self.answered = False
        self.pending_ice_for_callee: list[dict] = []
        self.pending_ice_for_caller: list[dict] = []


class SignallingServer:
    """Async WebSocket signalling broker for P2P WebRTC calls.

    Handles one call at a time. First client to send ``dial`` is the caller.
    Any other connected client receives ``incoming_call`` with the offer SDP.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8766) -> None:
        self.host = host
        self.port = port
        self._server: Optional[Any] = None
        self._clients: Set[Any] = set()
        self._active_call: Optional[CallState] = None
        self._is_running = False

    # -- helpers -------------------------------------------------------------

    async def _send_json(self, ws: Any, data: dict) -> None:
        """Send a JSON message to a client, swallowing send errors."""
        try:
            await ws.send(json.dumps(data))
        except Exception as exc:
            logger.warning("Failed to send to client: %s", exc)

    def _get_peer(self, ws: Any) -> Optional[Any]:
        """Return the other peer in the active call, or None."""
        call = self._active_call
        if call is None:
            return None
        if ws is call.caller_ws:
            return call.callee_ws
        if ws is call.callee_ws:
            return call.caller_ws
        return None

    def _is_in_call(self, ws: Any) -> bool:
        """Return True if this websocket is part of the active call."""
        call = self._active_call
        if call is None:
            return False
        return ws is call.caller_ws or ws is call.callee_ws

    async def _try_deliver_incoming_call(self) -> None:
        """If a pending call exists and a callee is available, send incoming_call."""
        call = self._active_call
        if call is None or call.callee_ws is not None:
            return
        for client in self._clients:
            if client is not call.caller_ws:
                call.callee_ws = client
                await self._send_json(client, {
                    "type": "incoming_call",
                    "call_id": call.call_id,
                    "sdp": call.offer_sdp,
                })
                logger.info(
                    "Call %s: sent incoming_call to callee", call.call_id,
                )
                for cand in call.pending_ice_for_callee:
                    await self._send_json(client, cand)
                    logger.info("Call %s: flushed buffered ICE candidate to callee", call.call_id)
                call.pending_ice_for_callee.clear()
                break

    # -- message handlers ----------------------------------------------------

    async def _handle_dial(self, ws: Any, data: dict) -> None:
        if self._active_call is not None:
            await self._send_json(ws, {
                "type": "error",
                "reason": "A call is already in progress",
            })
            return

        call_id = data.get("call_id") or f"call_{uuid.uuid4().hex[:8]}"
        sdp = data.get("sdp")

        if not sdp:
            await self._send_json(ws, {
                "type": "error",
                "reason": "Missing 'sdp' in dial message",
            })
            return

        self._active_call = CallState(
            call_id=call_id, caller_ws=ws, offer_sdp=sdp,
        )

        await self._send_json(ws, {
            "type": "ringing",
            "call_id": call_id,
        })
        logger.info("Call %s: dial received, ringing sent to caller", call_id)

        # If the callee is already connected, deliver immediately
        await self._try_deliver_incoming_call()

    async def _handle_accept(self, ws: Any, data: dict) -> None:
        call = self._active_call
        if call is None:
            await self._send_json(ws, {
                "type": "error",
                "reason": "No active call to accept",
            })
            return

        sdp = data.get("sdp")
        if not sdp:
            await self._send_json(ws, {
                "type": "error",
                "reason": "Missing 'sdp' in accept message",
            })
            return

        call.answered = True

        # Forward answer SDP to caller
        await self._send_json(call.caller_ws, {
            "type": "answer",
            "sdp": sdp,
        })
        logger.info("Call %s: accepted, answer forwarded to caller", call.call_id)

        # Flush any pending ICE candidates from callee to caller
        for cand in call.pending_ice_for_caller:
            await self._send_json(call.caller_ws, cand)
            logger.info("Call %s: flushed buffered ICE candidate to caller", call.call_id)
        call.pending_ice_for_caller.clear()

    async def _handle_ice(self, ws: Any, data: dict) -> None:
        call = self._active_call
        if call is None:
            return
        peer = self._get_peer(ws)
        if peer is None:
            if ws is call.caller_ws:
                call.pending_ice_for_callee.append(data)
                logger.info("Call %s: buffered ICE candidate for callee", call.call_id)
            elif ws is call.callee_ws:
                call.pending_ice_for_caller.append(data)
                logger.info("Call %s: buffered ICE candidate for caller", call.call_id)
            return

        await self._send_json(peer, {
            "type": "ice",
            "call_id": data.get("call_id", ""),
            "candidate": data.get("candidate"),
        })
        logger.info("Call %s: forwarded ICE candidate to peer", call.call_id)

    async def _handle_hangup(self, ws: Any, data: dict) -> None:
        call = self._active_call
        if call is None:
            return

        call_id = call.call_id
        ended_msg = {"type": "call_ended", "call_id": call_id}

        for peer_ws in (call.caller_ws, call.callee_ws):
            if peer_ws is not None:
                await self._send_json(peer_ws, ended_msg)

        logger.info("Call %s: hangup, call_ended sent to both", call_id)
        self._active_call = None

    # -- connection lifecycle ------------------------------------------------

    async def handle_client(self, websocket: Any) -> None:
        """Handle a single WebSocket client connection."""
        self._clients.add(websocket)
        logger.info("Client connected (%d total)", len(self._clients))

        # If there is a pending call waiting for a callee, deliver it
        await self._try_deliver_incoming_call()

        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError as exc:
                    logger.warning("Malformed JSON: %s", exc)
                    await self._send_json(websocket, {
                        "type": "error",
                        "reason": "Invalid JSON payload",
                    })
                    continue

                msg_type = data.get("type")

                if msg_type == "dial":
                    await self._handle_dial(websocket, data)
                elif msg_type == "accept":
                    await self._handle_accept(websocket, data)
                elif msg_type == "ice":
                    await self._handle_ice(websocket, data)
                elif msg_type == "hangup":
                    await self._handle_hangup(websocket, data)
                elif msg_type == "ping":
                    await self._send_json(websocket, {"type": "pong"})
                else:
                    logger.warning("Unknown message type: %s", msg_type)
                    await self._send_json(websocket, {
                        "type": "error",
                        "reason": f"Unsupported message type: '{msg_type}'",
                    })

        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected")
        except Exception as exc:
            logger.error("WebSocket error: %s", exc, exc_info=True)
        finally:
            self._clients.discard(websocket)

            # If this client was part of an active call, notify the peer and clean up
            if self._active_call is not None and self._is_in_call(websocket):
                peer = self._get_peer(websocket)
                if peer is not None:
                    await self._send_json(peer, {
                        "type": "call_ended",
                        "call_id": self._active_call.call_id,
                    })
                self._active_call = None

            logger.info("Client cleaned up (%d remaining)", len(self._clients))

    # -- server lifecycle ----------------------------------------------------

    async def start(self) -> None:
        """Start the signalling broker."""
        if websockets is None:
            raise RuntimeError(
                "websockets library is required. Install via: pip install websockets",
            )
        logger.info(
            "Starting signalling broker on ws://%s:%d", self.host, self.port,
        )
        self._is_running = True
        self._server = await websockets.serve(
            self.handle_client, self.host, self.port,
        )

    async def close(self) -> None:
        """Stop the signalling broker and clean up."""
        self._is_running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._clients.clear()
        self._active_call = None
        logger.info("Signalling broker stopped.")

    async def serve(self) -> None:
        """Run the broker until interrupted."""
        await self.start()
        try:
            await asyncio.Future()  # run forever
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await self.close()


def main() -> None:
    """Entrypoint for running the signalling broker standalone."""
    parser = argparse.ArgumentParser(
        description="WebRTC WebSocket Signalling Broker",
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=8766, help="Bind port (default: 8766)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO", help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server = SignallingServer(host=args.host, port=args.port)
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        logger.info("Signalling broker stopped by user.")


if __name__ == "__main__":
    main()
