"""Self-check tests for Web Dashboard A mock server and contracts."""

from __future__ import annotations

import asyncio
from pydantic import TypeAdapter

from contracts.risk import AppMessage, CallEnded, RiskLevel, RiskUpdate, SessionStart
from mock_server import scenario_clone_attack, scenario_degraded_clone, scenario_genuine_call


async def _run_test_all_scenarios() -> None:
    app_message_adapter = TypeAdapter(AppMessage)

    scenarios = [
        ("genuine", scenario_genuine_call("s_gen_01", "c_gen_01")),
        ("clone_attack", scenario_clone_attack("s_atk_01", "c_atk_01")),
        ("degraded", scenario_degraded_clone("s_deg_01", "c_deg_01")),
    ]

    for name, gen in scenarios:
        messages = []
        async for raw_json in gen:
            # 1. Must parse as valid AppMessage discriminated union
            msg = app_message_adapter.validate_json(raw_json)
            messages.append(msg)

            if isinstance(msg, SessionStart):
                assert msg.kind == "session_start"
                assert msg.stream_id.startswith("s_")
            elif isinstance(msg, RiskUpdate):
                assert msg.kind == "risk_update"
                assert 0 <= msg.score <= 100
                assert 0.0 <= msg.confidence <= 1.0
                assert isinstance(msg.risk_level, RiskLevel)
            elif isinstance(msg, CallEnded):
                assert msg.kind == "call_ended"
                assert 0 <= msg.final_score <= 100
                assert isinstance(msg.final_level, RiskLevel)

        # Ensure scenario started with SessionStart and ended with CallEnded
        assert isinstance(messages[0], SessionStart), f"{name} must start with SessionStart"
        assert isinstance(messages[-1], CallEnded), f"{name} must end with CallEnded"
        assert any(isinstance(m, RiskUpdate) for m in messages), f"{name} must have RiskUpdates"


async def _run_test_risk_levels() -> None:
    found_levels = set()
    for gen in [
        scenario_genuine_call("s1", "c1"),
        scenario_clone_attack("s2", "c2"),
        scenario_degraded_clone("s3", "c3"),
    ]:
        async for raw_json in gen:
            msg = TypeAdapter(AppMessage).validate_json(raw_json)
            if isinstance(msg, RiskUpdate):
                found_levels.add(msg.risk_level)
            elif isinstance(msg, CallEnded):
                found_levels.add(msg.final_level)

    assert RiskLevel.LOW in found_levels
    assert RiskLevel.MEDIUM in found_levels
    assert RiskLevel.HIGH in found_levels
    assert RiskLevel.CRITICAL in found_levels


def test_all_scenarios_emit_valid_app_messages() -> None:
    asyncio.run(_run_test_all_scenarios())


def test_all_four_risk_levels_rendered() -> None:
    asyncio.run(_run_test_risk_levels())


if __name__ == "__main__":
    test_all_scenarios_emit_valid_app_messages()
    test_all_four_risk_levels_rendered()
    print("All mock server tests passed successfully!")
