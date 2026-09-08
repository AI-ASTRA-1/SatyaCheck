"""Score wav files across the phone channel, with any scorer.

    .venv\\Scripts\\python.exe -m ml.tools.sweep clip.wav [more.wav ...]
    .venv\\Scripts\\python.exe -m ml.tools.sweep clip.wav --model finetuned

Prints one row per file and one column per condition, plus the delta from the
untouched baseline. This is the tool for demo item 3: the same voice, degraded, with
the score moving in front of the audience.

Scores are averaged over **speech-active windows only**. Quiet lead-ins score very
differently from speech and averaging them in produced a badly misleading result
once already; see `ml/README.md` Findings.
"""

from __future__ import annotations

import argparse
import sys
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from contracts.checks import MachineFingerprintSignal
from contracts.context import CallContext
from contracts.pipeline import CANONICAL_SAMPLE_RATE, CanonicalAudioBatch
from ml.augment.g711 import alaw_round_trip, mulaw_round_trip
from ml.augment.gain import PRESETS, compress
from ml.augment.noise import add_noise_at_snr
from ml.augment.phone_codecs import CodecName, ffmpeg_available, phone_codec_round_trip
from ml.checks.machine_fingerprint import MachineFingerprintCheck

WINDOW_SAMPLES = 64600

#: A window must be at least this fraction speech to be scored.
ACTIVITY_FLOOR = 0.4


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        channels, width, rate = (
            handle.getnchannels(),
            handle.getsampwidth(),
            handle.getframerate(),
        )
        frames = handle.readframes(handle.getnframes())
    if (channels, width, rate) != (1, 2, CANONICAL_SAMPLE_RATE):
        raise SystemExit(
            f"{path} is {rate} Hz, {channels}ch, {width * 8}-bit. Convert it:\n"
            f'  ffmpeg -i "{path}" -ac 1 -ar {CANONICAL_SAMPLE_RATE} '
            f'-sample_fmt s16 "{path.with_suffix(".16k.wav")}"'
        )
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def speech_windows(x: np.ndarray) -> list[np.ndarray]:
    """Windows that are mostly speech. Silence scores differently and would skew.

    The gate is **relative to this file's own speech level**, not an absolute
    amplitude. An absolute threshold discards nearly all of a quietly recorded clip
    and returns nan, which is worse than a wrong number because it looks like a
    tooling failure rather than a silent bias. A headset recording at active RMS
    0.018 lost all but 4 of its windows to a fixed 0.01 gate.
    """
    frames_all = x[: len(x) // 320 * 320].reshape(-1, 320)
    frame_rms = np.sqrt((frames_all**2).mean(axis=1) + 1e-12)
    if frame_rms.size == 0:
        return []
    # 15% of a robust "loud speech" level. Percentile rather than max so one click
    # or thump cannot raise the bar for the whole file.
    gate = max(float(np.percentile(frame_rms, 95)) * 0.15, 1e-4)

    out = []
    for i in range(len(x) // WINDOW_SAMPLES):
        chunk = x[i * WINDOW_SAMPLES : (i + 1) * WINDOW_SAMPLES]
        frames = chunk[: len(chunk) // 320 * 320].reshape(-1, 320)
        active = float((np.sqrt((frames**2).mean(axis=1)) > gate).mean())
        if active > ACTIVITY_FLOOR:
            out.append(chunk)
    return out


def conditions(x: np.ndarray, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """The phone channel, one condition at a time so each effect is separable."""
    built: dict[str, np.ndarray] = {"source": x}
    built["g711u"] = mulaw_round_trip(x)
    built["g711a"] = alaw_round_trip(x)
    if ffmpeg_available():
        try:
            built["amrnb"] = phone_codec_round_trip(x, CodecName.AMR_NB)
            built["opus"] = phone_codec_round_trip(x, CodecName.OPUS)
        except RuntimeError as error:
            print(f"  (codec unavailable: {error})", file=sys.stderr)
    built["agc"] = compress(x, PRESETS["aggressive_recorder"])
    for snr in (20.0, 10.0):
        built[f"snr{int(snr)}"] = add_noise_at_snr(x, snr, rng)
    return built


def mean_score(check: MachineFingerprintCheck, x: np.ndarray) -> tuple[float, int]:
    windows = speech_windows(x)
    if not windows:
        return float("nan"), 0
    started = datetime.now(UTC)
    context = CallContext(stream_id="sweep", call_id="sweep", started_at=started)
    scores = []
    for chunk in windows:
        pcm = (np.clip(chunk, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        batch = CanonicalAudioBatch(
            stream_id="sweep",
            call_id="sweep",
            start_sequence=0,
            end_sequence=0,
            pcm_s16le=pcm,
            sample_count=len(chunk),
            capture_started_at=started,
            capture_ended_at=started + timedelta(seconds=len(chunk) / 16000),
            window_ms=int(len(chunk) / 16000 * 1000),
        )
        result = check.run(batch, context)
        if isinstance(result.signal, MachineFingerprintSignal):
            scores.append(result.signal.synthetic_probability)
    return (float(np.mean(scores)) if scores else float("nan")), len(scores)


def build_check(
    model: str, device: str | None, weights: Path | None = None
) -> MachineFingerprintCheck:
    if model == "xlsr-aasist":
        from ml.checks.machine_fingerprint.ssl_aasist import SslAasistScorer

        if weights is not None:
            raise SystemExit("--weights applies to the AASIST variants, not xlsr-aasist")
        scorer: object = SslAasistScorer(device=device)
    else:
        from ml.checks.machine_fingerprint.aasist_scorer import AasistScorer

        scorer = AasistScorer(model, device=device, weights_override=weights)
    scorer.warmup()  # type: ignore[attr-defined]
    return MachineFingerprintCheck(scorer)  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", type=Path, nargs="+", help="16 kHz mono s16le wav")
    parser.add_argument(
        "--model", default="AASIST", choices=["AASIST", "AASIST-L", "xlsr-aasist"]
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=None,
        help="fine-tuned checkpoint to load instead of the released one",
    )
    parser.add_argument("--device", default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    check = build_check(args.model, args.device, args.weights)
    rng = np.random.default_rng(args.seed)

    rows: dict[str, dict[str, float]] = {}
    names: list[str] = []
    for path in args.audio:
        x = read_wav(path)
        built = conditions(x, rng)
        if not names:
            names = list(built)
        row = {}
        windows = 0
        for name in names:
            row[name], windows = mean_score(check, built[name])
        rows[f"{path.stem} [{windows}w]"] = row
        print(f"scored {path.name}", file=sys.stderr)

    print(f"\nmean P(synthetic), model={args.model}, speech-active windows only\n")
    header = f"{'clip':>26} " + " ".join(f"{n:>7}" for n in names)
    print(header)
    print("-" * len(header))
    for label, row in rows.items():
        print(f"{label:>26} " + " ".join(f"{row[n]:>7.3f}" for n in names))

    print("\ndelta from source\n")
    print(f"{'clip':>26} " + " ".join(f"{n:>7}" for n in names[1:]))
    for label, row in rows.items():
        print(
            f"{label:>26} "
            + " ".join(f"{row[n] - row['source']:>+7.3f}" for n in names[1:])
        )

    print("\nEvidence, not a verdict. n is small; report the clip count with any figure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
