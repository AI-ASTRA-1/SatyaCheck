"""Stage 06: response dispatch of AppMessage over WebSocket.

A separate WebSocket surface from audio-in (backend/app/ingestion). A listener
here never touches acquisitions/ or ingestion; it only ever sees AppMessage JSON.
"""

from __future__ import annotations

from typing import Protocol

from starlette.websockets import WebSocketDisconnect

from contracts.risk import AppMessage


class WebSocketLike(Protocol):
    async def accept(self) -> None: ...
    async def send_text(self, data: str) -> None: ...
    async def receive_text(self) -> str: ...


class ResponseDispatcher:
    """Fans RiskUpdate/SessionStart/CallEnded out to every listener of a stream."""

    def __init__(self) -> None:
        self._listeners: dict[str, set[WebSocketLike]] = {}

    async def register(self, stream_id: str, websocket: WebSocketLike) -> None:
        await websocket.accept()
        self._listeners.setdefault(stream_id, set()).add(websocket)

    def unregister(self, stream_id: str, websocket: WebSocketLike) -> None:
        listeners = self._listeners.get(stream_id)
        if listeners is None:
            return
        listeners.discard(websocket)
        if not listeners:
            del self._listeners[stream_id]

    async def send(self, stream_id: str, message: AppMessage) -> None:
        listeners = self._listeners.get(stream_id)
        if not listeners:
            return
        payload = message.model_dump_json()
        dead: list[WebSocketLike] = []
        for websocket in list(listeners):
            try:
                await websocket.send_text(payload)
            except Exception:  # noqa: BLE001 - one dead listener must not block the rest
                dead.append(websocket)
        for websocket in dead:
            self.unregister(stream_id, websocket)

    async def listen_forever(self, stream_id: str, websocket: WebSocketLike) -> None:
        await self.register(stream_id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            self.unregister(stream_id, websocket)
