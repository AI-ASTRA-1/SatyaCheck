"""Manual demo: streams synthetic audio to the backend as a WebRTC sender would.

This exercises the WebRTC ingest join point (docs/interfaces.md section 2.1): the
same /ws/audio/{stream_id}/{call_id} endpoint Exotel uses, but sending raw binary
16kHz mono s16le PCM in irregular chunk sizes -- not the fixed 20ms/640-byte frames
tests/demo_audio_client.py sends -- to prove the backend's buffering/slicing handles
whatever chunk sizes a real WebRTC audio pipeline hands it. No JSON handshake.

Run the backend first:

    uv run --extra runtime uvicorn backend.app.main:app

Then, in another terminal:

    uv run python tests/demo_webrtc_audio_client.py <stream_id> <call_id> --seconds 5 --tone
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import struct

import websockets

SAMPLE_RATE = 16000
TONE_HZ = 440
TONE_AMPLITUDE = 12000
# Simulated WebRTC-style chunk sizes: irregular, not 20ms-frame-aligned.
MIN_CHUNK_BYTES = 320
MAX_CHUNK_BYTES = 4096


def _pcm(seconds: float, tone: bool) -> bytes:
    n_samples = int(seconds * SAMPLE_RATE)
    if not tone:
        return b"\x00\x00" * n_samples
    samples = [
        int(TONE_AMPLITUDE * math.sin(2 * math.pi * TONE_HZ * i / SAMPLE_RATE))
        for i in range(n_samples)
    ]
    return struct.pack(f"<{n_samples}h", *samples)


def _irregular_chunks(pcm: bytes) -> list[bytes]:
    chunks = []
    offset = 0
    while offset < len(pcm):
        size = random.randrange(MIN_CHUNK_BYTES, MAX_CHUNK_BYTES, 2)  # keep even
        chunks.append(pcm[offset : offset + size])
        offset += size
    return chunks


async def stream_audio(
    host: str, stream_id: str, call_id: str, seconds: float, tone: bool, realtime: bool
) -> None:
    uri = f"{host}/ws/audio/{stream_id}/{call_id}"
    pcm = _pcm(seconds, tone)
    chunks = _irregular_chunks(pcm)
    async with websockets.connect(uri) as websocket:
        for chunk in chunks:
            await websocket.send(chunk)
            if realtime:
                await asyncio.sleep(len(chunk) / 2 / SAMPLE_RATE)
    print(
        f"sent {len(chunks)} irregular chunks ({sum(len(c) for c in chunks)} bytes, "
        f"{'tone' if tone else 'silence'}) to {uri}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream synthetic audio to the SATYACHECK backend as a WebRTC "
        "sender would: raw binary PCM in irregular chunk sizes, no JSON handshake."
    )
    parser.add_argument("stream_id")
    parser.add_argument("call_id")
    parser.add_argument("--host", default="ws://127.0.0.1:8000")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--tone", action="store_true", help="send a synthetic tone instead of silence")
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="pace chunks to roughly real time instead of sending as fast as possible",
    )
    args = parser.parse_args()
    asyncio.run(
        stream_audio(args.host, args.stream_id, args.call_id, args.seconds, args.tone, args.realtime)
    )


if __name__ == "__main__":
    main()
