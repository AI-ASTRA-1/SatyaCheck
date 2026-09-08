"""Transcribe a wav file through the real stt_llm check, window by window.

Developer tool. Goes through SttLlmCheck and CanonicalAudioBatch so what you see
is what the pipeline sees: the transcript is produced inside the check, scored,
and discarded on return. With --show-transcript this tool transcribes once more
itself, outside the check, and prints the text for debugging the ASR path. That
text is never written to disk; in the pipeline it never leaves the check.

    .venv\\Scripts\\python.exe -m ml.tools.transcribe_file call.16k.wav
    .venv\\Scripts\\python.exe -m ml.tools.transcribe_file call.16k.wav --show-transcript
    .venv\\Scripts\\python.exe -m ml.tools.transcribe_file call.16k.wav --window-ms 45000

The file must be 16 kHz mono 16-bit PCM. If it is not, the error prints the
ffmpeg line that converts it. The script_risk printed is evidence, not a verdict.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contracts.checks import SttLlmSignal
from contracts.context import CallContext
from contracts.pipeline import CANONICAL_SAMPLE_RATE, CanonicalAudioBatch
from ml.checks.stt_llm import FasterWhisperTranscriber, SttLlmCheck
from ml.tools.score_file import BYTES_PER_SAMPLE, read_canonical_wav, windows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", type=Path, help="16 kHz mono s16le wav file")
    parser.add_argument(
        "--window-ms",
        type=int,
        default=30000,
        help="analysis window; script analysis wants tens of seconds (default: 30000)",
    )
    parser.add_argument("--device", default=None, help="cuda, cpu (default: auto)")
    parser.add_argument(
        "--show-transcript",
        action="store_true",
        help="print the transcript per window (debug only; not persisted)",
    )
    args = parser.parse_args(argv)

    pcm = read_canonical_wav(args.audio)
    duration_ms = len(pcm) // BYTES_PER_SAMPLE * 1000 // CANONICAL_SAMPLE_RATE

    transcriber = FasterWhisperTranscriber(device=args.device)
    transcriber.warmup()
    check = SttLlmCheck(transcriber)

    started_at = datetime.now(UTC)
    context = CallContext(
        stream_id="transcribe-file", call_id=args.audio.name, started_at=started_at
    )

    print(
        f"{args.audio.name}: {duration_ms} ms, window {args.window_ms} ms, "
        f"model {transcriber.model_name}"
    )
    header = f"{'window':>10}  {'status':>9}  {'script_risk':>11}  {'top tactic':>18}"
    if args.show_transcript:
        header += f"  {'words':>5}"
    header += f"  {'ms':>7}"
    print(header)

    offset_ms = 0
    for chunk in windows(pcm, args.window_ms):
        chunk_ms = len(chunk) // BYTES_PER_SAMPLE * 1000 // CANONICAL_SAMPLE_RATE
        batch = CanonicalAudioBatch(
            stream_id="transcribe-file",
            call_id=args.audio.name,
            start_sequence=0,
            end_sequence=0,
            pcm_s16le=chunk,
            sample_count=len(chunk) // BYTES_PER_SAMPLE,
            capture_started_at=started_at + timedelta(milliseconds=offset_ms),
            capture_ended_at=started_at + timedelta(milliseconds=offset_ms + chunk_ms),
            window_ms=chunk_ms,
        )

        transcript = (
            transcriber.transcribe(chunk, CANONICAL_SAMPLE_RATE)
            if args.show_transcript
            else None
        )
        result = check.run(batch, context)

        signal = result.signal
        has_signal = isinstance(signal, SttLlmSignal)
        risk = (
            f"{signal.script_risk:.3f}"
            if has_signal and signal.script_risk is not None
            else "-"
        )
        category = signal.script_category if has_signal and signal.script_category else "-"
        latency = result.evidence[0].latency_ms if result.evidence else 0.0

        row = (
            f"{offset_ms:>8}ms  {result.status.value:>9}  {risk:>11}  {category:>18}"
        )
        if args.show_transcript:
            row += f"  {len((transcript or '').split()):>5}"
        row += f"  {latency:>7.1f}"
        print(row)
        if transcript is not None:
            print(f"    {transcript!r}")
        offset_ms += chunk_ms

    print("\nEvidence, not a verdict. The transcript is not persisted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
