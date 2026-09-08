"""Manual demo: streams synthetic audio to the backend's audio-in WebSocket.

Not a pytest test (filename doesn't start with test_). Run the backend first:

    uv run --extra runtime uvicorn backend.app.main:app

Then, in another terminal:

    uv run python tests/demo_audio_client.py s1 c1 --seconds 5 --tone
"""

from __future__ import annotations

import argparse
import asyncio
import math
import struct

import websockets

SAMPLE_RATE = 16000
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
TONE_HZ = 440
TONE_AMPLITUDE = 12000


def _silence_frame() -> bytes:
    return b"\x00\x00" * SAMPLES_PER_FRAME


def _tone_frame(frame_index: int) -> bytes:
    base = frame_index * SAMPLES_PER_FRAME
    samples = [
        int(TONE_AMPLITUDE * math.sin(2 * math.pi * TONE_HZ * (base + i) / SAMPLE_RATE))
        for i in range(SAMPLES_PER_FRAME)
    ]
    return struct.pack(f"<{SAMPLES_PER_FRAME}h", *samples)


async def stream_audio(
    host: str, stream_id: str, call_id: str, seconds: float, tone: bool, realtime: bool
) -> None:
    uri = f"{host}/ws/audio/{stream_id}/{call_id}"
    frame_count = int(seconds * 1000 / FRAME_MS)
    async with websockets.connect(uri) as websocket:
        for i in range(frame_count):
            frame = _tone_frame(i) if tone else _silence_frame()
            await websocket.send(frame)
            if realtime:
                await asyncio.sleep(FRAME_MS / 1000)
    print(f"sent {frame_count} frames ({'tone' if tone else 'silence'}) to {uri}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream synthetic audio to the SATYACHECK backend prototype."
    )
    parser.add_argument("stream_id")
    parser.add_argument("call_id")
    parser.add_argument("--host", default="ws://127.0.0.1:8000")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--tone", action="store_true", help="send a synthetic tone instead of silence")
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="pace frames at 20ms each instead of sending as fast as possible",
    )
    args = parser.parse_args()
    asyncio.run(stream_audio(args.host, args.stream_id, args.call_id, args.seconds, args.tone, args.realtime))


if __name__ == "__main__":
    main()
