"""Score a wav file through the real machine fingerprint check.

Deliberately goes through MachineFingerprintCheck and CanonicalAudioBatch rather
than calling the model directly, so what you see here is what the pipeline sees.

The file must be 16 kHz mono 16-bit PCM, the canonical format below stage 02. If it
is not, the error prints the ffmpeg command that converts it.

    .venv\\Scripts\\python.exe -m ml.tools.score_file sample.wav
    .venv\\Scripts\\python.exe -m ml.tools.score_file sample.wav --window-ms 4000

This is a developer tool. It is not part of the runtime pipeline, and the score it
prints is evidence, not a verdict.
"""

from __future__ import annotations

import argparse
import sys
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contracts.checks import MachineFingerprintSignal
from contracts.context import CallContext
from contracts.pipeline import CANONICAL_SAMPLE_RATE, CanonicalAudioBatch
from ml.checks.machine_fingerprint import MachineFingerprintCheck
from ml.checks.machine_fingerprint.aasist_scorer import AasistScorer
from ml.checks.machine_fingerprint.ssl_aasist import SslAasistScorer

BYTES_PER_SAMPLE = 2


def read_canonical_wav(path: Path) -> bytes:
    """Read a 16 kHz mono s16le wav file, or explain how to convert it."""
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if (channels, width, rate) != (1, 2, CANONICAL_SAMPLE_RATE):
        raise SystemExit(
            f"{path} is {rate} Hz, {channels} channel(s), {width * 8}-bit. "
            f"The pipeline is {CANONICAL_SAMPLE_RATE} Hz mono 16-bit. Convert it:\n"
            f'  ffmpeg -i "{path}" -ac 1 -ar {CANONICAL_SAMPLE_RATE} '
            f'-sample_fmt s16 "{path.with_suffix(".16k.wav")}"'
        )
    return frames


def windows(pcm: bytes, window_ms: int) -> list[bytes]:
    """Split into consecutive windows, dropping a trailing partial window."""
    size = CANONICAL_SAMPLE_RATE * window_ms // 1000 * BYTES_PER_SAMPLE
    if size <= 0:
        raise SystemExit("--window-ms must be positive")
    count = len(pcm) // size
    if count == 0:
        return [pcm]
    return [pcm[i * size : (i + 1) * size] for i in range(count)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", type=Path, help="16 kHz mono s16le wav file")
    parser.add_argument(
        "--window-ms",
        type=int,
        default=4000,
        help="analysis window; AASIST's native input is 4038 ms (default: 4000)",
    )
    parser.add_argument(
        "--model",
        default="xlsr-aasist",
        choices=["xlsr-aasist", "AASIST", "AASIST-L"],
        help=(
            "xlsr-aasist is the architecture the deck describes and the default. "
            "AASIST variants are the lightweight CPU comparison, and their score "
            "tracks input loudness on out-of-domain audio (default: xlsr-aasist)"
        ),
    )
    parser.add_argument("--device", default=None, help="cuda, cpu (default: auto)")
    args = parser.parse_args(argv)

    pcm = read_canonical_wav(args.audio)
    duration_ms = len(pcm) // BYTES_PER_SAMPLE * 1000 // CANONICAL_SAMPLE_RATE

    if args.model == "xlsr-aasist":
        scorer: object = SslAasistScorer(device=args.device)
    else:
        scorer = AasistScorer(args.model, device=args.device)
    scorer.warmup()  # type: ignore[attr-defined]
    check = MachineFingerprintCheck(scorer)  # type: ignore[arg-type]

    started_at = datetime.now(UTC)
    context = CallContext(
        stream_id="score-file", call_id=args.audio.name, started_at=started_at
    )

    print(f"{args.audio.name}: {duration_ms} ms, {args.model}")
    print(f"{'window':>10}  {'status':>9}  {'P(synthetic)':>12}  {'ms':>7}  reasons")

    offset_ms = 0
    for chunk in windows(pcm, args.window_ms):
        chunk_ms = len(chunk) // BYTES_PER_SAMPLE * 1000 // CANONICAL_SAMPLE_RATE
        batch = CanonicalAudioBatch(
            stream_id="score-file",
            call_id=args.audio.name,
            start_sequence=0,
            end_sequence=0,
            pcm_s16le=chunk,
            sample_count=len(chunk) // BYTES_PER_SAMPLE,
            capture_started_at=started_at + timedelta(milliseconds=offset_ms),
            capture_ended_at=started_at + timedelta(milliseconds=offset_ms + chunk_ms),
            window_ms=chunk_ms,
        )
        result = check.run(batch, context)
        signal = result.signal
        probability = (
            f"{signal.synthetic_probability:.4f}"
            if isinstance(signal, MachineFingerprintSignal)
            else "-"
        )
        latency = result.evidence[0].latency_ms if result.evidence else 0.0
        reasons = ",".join(item.reason_code.value for item in result.evidence)
        print(
            f"{offset_ms:>8}ms  {result.status.value:>9}  {probability:>12}  "
            f"{latency:>7.1f}  {reasons}"
        )
        offset_ms += chunk_ms

    print("\nEvidence, not a verdict. The risk engine fuses this with call context.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
