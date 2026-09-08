"""Tests for the stage 06 ResponseDispatcher."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.response.dispatcher import ResponseDispatcher
from contracts.risk import RiskLevel, RiskUpdate, RiskVerdict


class FakeWebSocket:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self._fail_send = fail_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        if self._fail_send:
            raise RuntimeError("connection reset")
        self.sent.append(data)

    async def receive_text(self) -> str:
        raise NotImplementedError


def _update(stream_id: str = "s1") -> RiskUpdate:
    return RiskUpdate(
        stream_id=stream_id,
        call_id="c1",
        sequence=1,
        timestamp=datetime.now(UTC),
        score=42,
        verdict=RiskVerdict.UNKNOWN,
        risk_level=RiskLevel.LOW,
        confidence=0.5,
    )


def test_send_delivers_to_registered_listeners_only() -> None:
    dispatcher = ResponseDispatcher()
    listener_a = FakeWebSocket()
    listener_b = FakeWebSocket()

    async def run() -> None:
        await dispatcher.register("s1", listener_a)
        await dispatcher.register("s2", listener_b)
        await dispatcher.send("s1", _update("s1"))

    asyncio.run(run())

    assert listener_a.accepted is True
    assert len(listener_a.sent) == 1
    assert listener_b.sent == []


def test_send_json_round_trips_to_a_risk_update() -> None:
    dispatcher = ResponseDispatcher()
    listener = FakeWebSocket()
    update = _update("s1")

    async def run() -> None:
        await dispatcher.register("s1", listener)
        await dispatcher.send("s1", update)

    asyncio.run(run())

    received = RiskUpdate.model_validate_json(listener.sent[0])
    assert received == update


def test_dead_listener_is_pruned_and_does_not_block_others() -> None:
    dispatcher = ResponseDispatcher()
    healthy = FakeWebSocket()
    broken = FakeWebSocket(fail_send=True)

    async def run() -> None:
        await dispatcher.register("s1", healthy)
        await dispatcher.register("s1", broken)
        await dispatcher.send("s1", _update("s1"))
        await dispatcher.send("s1", _update("s1"))

    asyncio.run(run())

    assert len(healthy.sent) == 2
