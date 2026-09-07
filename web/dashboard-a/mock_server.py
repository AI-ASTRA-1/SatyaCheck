"""Fake local WebSocket server for Web Dashboard A.

Emits AppMessage JSON matching contracts/risk.py exactly.
Runs on ws://127.0.0.1:8765 and optionally serves HTTP on http://127.0.0.1:8080.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import http.server
import json
import os
from pathlib import Path
import sys
import threading
from typing import AsyncGenerator

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import websockets

from contracts.checks import CheckName, ReasonCode
from contracts.risk import (
    CallEnded,
    RiskLevel,
    RiskUpdate,
    RiskVerdict,
    SessionStart,
)

WS_HOST = "127.0.0.1"
WS_PORT = 8765
HTTP_PORT = 8080
STATIC_DIR = Path(__file__).parent.resolve()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def scenario_genuine_call(stream_id: str, call_id: str) -> AsyncGenerator[str, None]:
    """Scenario 1: Genuine Indian-accented call. Score stays low."""
    # 1. Session start
    start = SessionStart(
        stream_id=stream_id,
        call_id=call_id,
        started_at=_utc_now(),
        protected_number="+919876543210",
    )
    yield start.model_dump_json()
    await asyncio.sleep(1.0)

    # 2. Sequential ticks (approx 1 tick/sec)
    scores = [
        (1, 8, RiskVerdict.UNKNOWN, RiskLevel.LOW, 0.40, [ReasonCode.INSUFFICIENT_AUDIO], [], [CheckName.SPEAKER_IDENTITY]),
        (2, 12, RiskVerdict.GENUINE, RiskLevel.LOW, 0.72, [ReasonCode.FINGERPRINT_GENUINE, ReasonCode.PROSODY_NORMAL], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY], []),
        (3, 15, RiskVerdict.GENUINE, RiskLevel.LOW, 0.85, [ReasonCode.FINGERPRINT_GENUINE, ReasonCode.PROSODY_NORMAL, ReasonCode.VOICEPRINT_NO_ENROLMENT], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY], []),
        (4, 10, RiskVerdict.GENUINE, RiskLevel.LOW, 0.91, [ReasonCode.FINGERPRINT_GENUINE, ReasonCode.PROSODY_NORMAL, ReasonCode.SCRIPT_RISK_ABSENT], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY, CheckName.STT_LLM], []),
        (5, 14, RiskVerdict.GENUINE, RiskLevel.LOW, 0.88, [ReasonCode.FINGERPRINT_GENUINE, ReasonCode.PROSODY_NORMAL], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY], []),
    ]

    for seq, score, verdict, level, conf, reasons, cont_checks, deg_checks in scores:
        update = RiskUpdate(
            stream_id=stream_id,
            call_id=call_id,
            sequence=seq,
            timestamp=_utc_now(),
            score=score,
            verdict=verdict,
            risk_level=level,
            confidence=conf,
            reasons=reasons,
            contributing_checks=cont_checks,
            degraded_checks=deg_checks,
            evidence_refs=[f"ev_{stream_id}_{seq:03d}"],
        )
        yield update.model_dump_json()
        await asyncio.sleep(1.0)

    # 3. Call Ended
    end = CallEnded(
        stream_id=stream_id,
        call_id=call_id,
        ended_at=_utc_now(),
        duration_seconds=6.0,
        final_score=14,
        final_verdict=RiskVerdict.GENUINE,
        final_level=RiskLevel.LOW,
        reasons=[ReasonCode.FINGERPRINT_GENUINE, ReasonCode.PROSODY_NORMAL],
        alert_fingerprint=None,
        merkle_root=None,
        sealed_record_id=None,
    )
    yield end.model_dump_json()


async def scenario_clone_attack(stream_id: str, call_id: str) -> AsyncGenerator[str, None]:
    """Scenario 2: AI-cloned voice impersonation attack. Score spikes to High/Critical."""
    start = SessionStart(
        stream_id=stream_id,
        call_id=call_id,
        started_at=_utc_now(),
        protected_number="+919876543210",
    )
    yield start.model_dump_json()
    await asyncio.sleep(1.0)

    scores = [
        (1, 15, RiskVerdict.UNKNOWN, RiskLevel.LOW, 0.45, [ReasonCode.INSUFFICIENT_AUDIO], [CheckName.PROSODY], [CheckName.MACHINE_FINGERPRINT]),
        (2, 48, RiskVerdict.UNKNOWN, RiskLevel.MEDIUM, 0.68, [ReasonCode.PROSODY_ANOMALY, ReasonCode.CONTEXT_HIGH_RISK], [CheckName.PROSODY], []),
        (3, 76, RiskVerdict.SYNTHETIC, RiskLevel.HIGH, 0.86, [ReasonCode.FINGERPRINT_SYNTHETIC, ReasonCode.PROSODY_ANOMALY], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY], []),
        (4, 93, RiskVerdict.SYNTHETIC, RiskLevel.CRITICAL, 0.95, [ReasonCode.FINGERPRINT_SYNTHETIC, ReasonCode.PROSODY_ANOMALY, ReasonCode.SCRIPT_RISK_HIGH], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY, CheckName.STT_LLM], []),
        (5, 96, RiskVerdict.SYNTHETIC, RiskLevel.CRITICAL, 0.98, [ReasonCode.FINGERPRINT_SYNTHETIC, ReasonCode.PROSODY_ANOMALY, ReasonCode.SCRIPT_RISK_HIGH, ReasonCode.CONTEXT_HIGH_RISK], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY, CheckName.STT_LLM], []),
    ]

    for seq, score, verdict, level, conf, reasons, cont_checks, deg_checks in scores:
        update = RiskUpdate(
            stream_id=stream_id,
            call_id=call_id,
            sequence=seq,
            timestamp=_utc_now(),
            score=score,
            verdict=verdict,
            risk_level=level,
            confidence=conf,
            reasons=reasons,
            contributing_checks=cont_checks,
            degraded_checks=deg_checks,
            evidence_refs=[f"ev_{stream_id}_{seq:03d}"],
        )
        yield update.model_dump_json()
        await asyncio.sleep(1.0)

    end = CallEnded(
        stream_id=stream_id,
        call_id=call_id,
        ended_at=_utc_now(),
        duration_seconds=6.0,
        final_score=96,
        final_verdict=RiskVerdict.SYNTHETIC,
        final_level=RiskLevel.CRITICAL,
        reasons=[ReasonCode.FINGERPRINT_SYNTHETIC, ReasonCode.PROSODY_ANOMALY, ReasonCode.SCRIPT_RISK_HIGH],
        alert_fingerprint="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        merkle_root="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        sealed_record_id="seal_rec_98273491",
        root_published_at=_utc_now(),
    )
    yield end.model_dump_json()


async def scenario_degraded_clone(stream_id: str, call_id: str) -> AsyncGenerator[str, None]:
    """Scenario 3: Badly degraded clone with noisy channel and degraded checks."""
    start = SessionStart(
        stream_id=stream_id,
        call_id=call_id,
        started_at=_utc_now(),
        protected_number="+919876543210",
    )
    yield start.model_dump_json()
    await asyncio.sleep(1.0)

    scores = [
        (1, 10, RiskVerdict.UNKNOWN, RiskLevel.LOW, 0.35, [ReasonCode.INSUFFICIENT_AUDIO, ReasonCode.DEGRADED_CHECK], [], [CheckName.PROSODY, CheckName.MACHINE_FINGERPRINT]),
        (2, 45, RiskVerdict.UNKNOWN, RiskLevel.MEDIUM, 0.52, [ReasonCode.DEGRADED_CHECK, ReasonCode.PROSODY_ANOMALY], [CheckName.PROSODY], [CheckName.MACHINE_FINGERPRINT]),
        (3, 58, RiskVerdict.SYNTHETIC, RiskLevel.MEDIUM, 0.65, [ReasonCode.FINGERPRINT_SYNTHETIC, ReasonCode.DEGRADED_CHECK], [CheckName.MACHINE_FINGERPRINT], [CheckName.PROSODY]),
        (4, 72, RiskVerdict.SYNTHETIC, RiskLevel.HIGH, 0.74, [ReasonCode.FINGERPRINT_SYNTHETIC, ReasonCode.PROSODY_ANOMALY], [CheckName.MACHINE_FINGERPRINT, CheckName.PROSODY], [CheckName.SPEAKER_IDENTITY]),
    ]

    for seq, score, verdict, level, conf, reasons, cont_checks, deg_checks in scores:
        update = RiskUpdate(
            stream_id=stream_id,
            call_id=call_id,
            sequence=seq,
            timestamp=_utc_now(),
            score=score,
            verdict=verdict,
            risk_level=level,
            confidence=conf,
            reasons=reasons,
            contributing_checks=cont_checks,
            degraded_checks=deg_checks,
            evidence_refs=[f"ev_{stream_id}_{seq:03d}"],
        )
        yield update.model_dump_json()
        await asyncio.sleep(1.0)

    end = CallEnded(
        stream_id=stream_id,
        call_id=call_id,
        ended_at=_utc_now(),
        duration_seconds=5.0,
        final_score=72,
        final_verdict=RiskVerdict.SYNTHETIC,
        final_level=RiskLevel.HIGH,
        reasons=[ReasonCode.FINGERPRINT_SYNTHETIC, ReasonCode.DEGRADED_CHECK],
        alert_fingerprint="a8f5f167f44f4964e6c998dee827110c",
        merkle_root="3a7bd3e2360a3d29eea436fcfb7e44c735d117e38d",
        sealed_record_id="seal_rec_45199201",
        root_published_at=_utc_now(),
    )
    yield end.model_dump_json()


async def run_scenario(websocket, scenario_name: str, call_id_num: int) -> None:
    """Runs a single chosen scenario."""
    if scenario_name == "genuine":
        stream_id = f"st_gen_{call_id_num}"
        call_id = f"call_gen_{call_id_num}"
        async for msg in scenario_genuine_call(stream_id, call_id):
            await websocket.send(msg)
    elif scenario_name == "attack":
        stream_id = f"st_atk_{call_id_num}"
        call_id = f"call_atk_{call_id_num}"
        async for msg in scenario_clone_attack(stream_id, call_id):
            await websocket.send(msg)
    elif scenario_name == "degraded":
        stream_id = f"st_deg_{call_id_num}"
        call_id = f"call_deg_{call_id_num}"
        async for msg in scenario_degraded_clone(stream_id, call_id):
            await websocket.send(msg)
    elif scenario_name == "all":
        # Run all 3 in sequence once
        async for msg in scenario_genuine_call(f"st_gen_{call_id_num}", f"call_gen_{call_id_num}"):
            await websocket.send(msg)
        await asyncio.sleep(2.0)
        async for msg in scenario_clone_attack(f"st_atk_{call_id_num}", f"call_atk_{call_id_num}"):
            await websocket.send(msg)
        await asyncio.sleep(2.0)
        async for msg in scenario_degraded_clone(f"st_deg_{call_id_num}", f"call_deg_{call_id_num}"):
            await websocket.send(msg)


async def handler(websocket) -> None:
    """Client connection handler with interactive scenario triggering."""
    print(f"[WS] Client connected: {websocket.remote_address}")
    call_counter = 1
    current_task: asyncio.Task | None = None
    loop_mode = False

    async def scenario_worker(scenario_type: str) -> None:
        nonlocal call_counter
        try:
            while True:
                await run_scenario(websocket, scenario_type, call_counter)
                call_counter += 1
                if not loop_mode:
                    break
                await asyncio.sleep(3.0)
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed:
            pass

    # Start genuine call scenario once on first connect
    current_task = asyncio.create_task(scenario_worker("genuine"))

    try:
        async for message_str in websocket:
            try:
                data = json.loads(message_str)
                action = data.get("action")
                if action == "play":
                    scenario = data.get("scenario", "genuine")
                    if current_task and not current_task.done():
                        current_task.cancel()
                    current_task = asyncio.create_task(scenario_worker(scenario))
                elif action == "stop":
                    if current_task and not current_task.done():
                        current_task.cancel()
                elif action == "set_loop":
                    loop_mode = bool(data.get("loop", False))
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        print(f"[WS] Client disconnected: {websocket.remote_address}")
    finally:
        if current_task and not current_task.done():
            current_task.cancel()


def start_http_server() -> None:
    """Serves the static web dashboard files."""
    os.chdir(STATIC_DIR)
    handler_class = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(("", HTTP_PORT), handler_class)
    print(f"[HTTP] Serving Dashboard A at http://127.0.0.1:{HTTP_PORT}")
    httpd.serve_forever()


async def main() -> None:
    print(f"[WS] Starting Fake Risk Server on ws://{WS_HOST}:{WS_PORT}")
    async with websockets.serve(handler, WS_HOST, WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Server] Stopped.")
