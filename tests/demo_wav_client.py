"""Manual demo: streams a real 16 kHz mono wav to the backend's audio-in WebSocket.

Not a pytest test (filename doesn't start with test_). The other two demo clients
send a tone or silence, which transcribes to nothing, so check 4 always scores
0.0 against them. This one replays real speech, which is what demo step 1 needs:
a genuine Indian-accented call whose score stays low.

Run the backend first, then:

    uv run python tests/demo_wav_client.py path/to/16k-mono.wav s1 c1

Sends the Exotel JSON envelope by default; --raw sends bare binary frames the way
tests/demo_audio_client.py does. The same endpoint auto-detects both, so one file
exercises real speech through either transport shape.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import time
import wave

import websockets

SAMPLE_RATE = 16000
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = SAMPLES_PER_FRAME * 2


def _frames(path: str, loops: int) -> list[bytes]:
    """Whole 20 ms frames of s16le PCM, repeated `loops` times.

    Asserts the format rather than resampling: everything below stage 02 is
    canonical 16 kHz mono, and quietly converting here would hide a wav that the
    real pipeline would reject.
    """
    with wave.open(path, "rb") as handle:
        if handle.getnchannels() != 1:
            raise SystemExit(f"{path}: expected mono, got {handle.getnchannels()} channels")
        if handle.getframerate() != SAMPLE_RATE:
            raise SystemExit(f"{path}: expected {SAMPLE_RATE} Hz, got {handle.getframerate()}")
        if handle.getsampwidth() != 2:
            raise SystemExit(f"{path}: expected 16-bit samples")
        pcm = handle.readframes(handle.getnframes()) * loops

    usable = len(pcm) - (len(pcm) % FRAME_BYTES)
    return [pcm[i : i + FRAME_BYTES] for i in range(0, usable, FRAME_BYTES)]


async def stream_wav(
    host: str, stream_id: str, call_id: str, path: str, loops: int, raw: bool
) -> None:
    uri = f"{host}/ws/audio/{stream_id}/{call_id}"
    frames = _frames(path, loops)

    async with websockets.connect(uri, max_size=None) as websocket:
        if not raw:
            await websocket.send(
                json.dumps({"event": "start", "stream_sid": stream_id, "call_sid": call_id})
            )

        started = time.monotonic()
        for index, frame in enumerate(frames):
            if raw:
                await websocket.send(frame)
            else:
                await websocket.send(
                    json.dumps(
                        {
                            "event": "media",
                            "stream_sid": stream_id,
                            "media": {
                                "chunk": index,
                                "timestamp": str(index * FRAME_MS),
                                "payload": base64.b64encode(frame).decode("ascii"),
                            },
                        }
                    )
                )
            # Always real time, unlike the other demo clients where it is a flag.
            # Check 4 runs out of band every few seconds on a rolling buffer, so a
            # burst send finishes before the transcript worker has woken once and
            # the script signal never appears.
            target = started + (index + 1) * FRAME_MS / 1000
            delay = target - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)

        if not raw:
            await websocket.send(json.dumps({"event": "stop", "stream_sid": stream_id}))

    shape = "raw binary" if raw else "Exotel JSON"
    seconds = len(frames) * FRAME_MS / 1000
    print(f"sent {len(frames)} frames ({seconds:.1f}s, {shape}) from {path} to {uri}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream a real 16 kHz mono wav to the SATYACHECK backend prototype."
    )
    parser.add_argument("wav", help="16 kHz mono 16-bit wav file")
    parser.add_argument("stream_id")
    parser.add_argument("call_id")
    parser.add_argument("--host", default="ws://127.0.0.1:8000")
    parser.add_argument(
        "--loops", type=int, default=1, help="repeat the clip to make a longer call"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="send bare binary frames instead of the Exotel JSON envelope",
    )
    args = parser.parse_args()
    asyncio.run(
        stream_wav(args.host, args.stream_id, args.call_id, args.wav, args.loops, args.raw)
    )


if __name__ == "__main__":
    main()
