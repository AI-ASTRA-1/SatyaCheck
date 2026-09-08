"""Manual demo: prints every AppMessage received from the risk-update WebSocket.

Not a pytest test (filename doesn't start with test_).

    uv run python tests/demo_risk_listener.py s1
"""

from __future__ import annotations

import argparse
import asyncio

import websockets


async def listen(host: str, stream_id: str) -> None:
    uri = f"{host}/ws/risk/{stream_id}"
    async with websockets.connect(uri) as websocket:
        print(f"listening on {uri} ...")
        async for message in websocket:
            print(message)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print RiskUpdate/SessionStart/CallEnded messages as they arrive."
    )
    parser.add_argument("stream_id")
    parser.add_argument("--host", default="ws://127.0.0.1:8000")
    args = parser.parse_args()
    asyncio.run(listen(args.host, args.stream_id))


if __name__ == "__main__":
    main()
