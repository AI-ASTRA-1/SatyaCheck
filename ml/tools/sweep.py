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
from ml.eval.activity import (
    ACTIVITY_FLOOR,
    STATUS_OK,
    VAD_FAIL,
    select_windows,
)

WINDOW_SAMPLES = 64600

#: Re-exported so the existing name keeps working for anything importing it.
__all__ = [
    "ACTIVITY_FLOOR",
    "conditions",
    "mean_score",
    "read_wav",
    "speech_windows",
]


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
    """Speech-active windows. Silence scores differently and would skew the mean.

    Thin wrapper over `ml.eval.activity.select_windows`, kept because the windowing
    is now shared with `ml/tools/baseline.py` and the fallback behaviour needed
    tests of its own. The ordinary path is unchanged, so every figure already in
    `ml/README.md` still reproduces.
    """
    return select_windows(x, WINDOW_SAMPLES).windows


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


def mean_score(
    check: MachineFingerprintCheck, x: np.ndarray
) -> dict[str, object]:
    """Mean P(synthetic) over speech-active windows, and how it was arrived at.

    Returns `score: None` with `vad_status: "FAIL"` when no window could be scored,
    never `nan`. A missing score and a high score are different facts, and a caller
    that formats `nan` into a table has silently turned the first into the second.
    Anything consuming `score` must branch on `None` rather than coercing it.

    The status matters separately: a figure from the `sparse` fallback rests on one
    salvaged window and should not be read as equal to one averaged over sixteen.
    """
    selection = select_windows(x, WINDOW_SAMPLES)
    windows, status = selection.windows, selection.status
    result: dict[str, object] = {
        "score": None,
        "vad_status": selection.vad_status,
        "status": status,
        "reason": selection.reason,
        "speech_s": selection.speech_seconds,
        "duration_s": x.size / CANONICAL_SAMPLE_RATE,
        "windows": 0,
    }
    if not windows:
        return result
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
        outcome = check.run(batch, context)
        if isinstance(outcome.signal, MachineFingerprintSignal):
            scores.append(outcome.signal.synthetic_probability)
    if not scores:
        # Windows were selected but the scorer refused every one of them. That is a
        # model failure rather than a silence failure, so it reports FAIL with its
        # own reason instead of borrowing the selection's.
        result["vad_status"] = VAD_FAIL
        result["reason"] = f"scorer returned no signal for {len(windows)} windows"
        return result
    result["score"] = float(np.mean(scores))
    result["windows"] = len(scores)
    return result


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


def _cell(score: float | None) -> str:
    """A cell in the table. `FAIL` where there is no score, never a number."""
    return f"{score:>7.3f}" if score is not None else f"{VAD_FAIL:>7}"


def _delta_cell(score: float | None, reference: float | None) -> str:
    """A delta cell. Absent on either side means no delta exists, not zero."""
    if score is None or reference is None:
        return f"{'-':>7}"
    return f"{score - reference:>+7.3f}"


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

    rows: dict[str, dict[str, float | None]] = {}
    names: list[str] = []
    for path in args.audio:
        x = read_wav(path)
        built = conditions(x, rng)
        if not names:
            names = list(built)
        row: dict[str, float | None] = {}
        windows = 0
        status = STATUS_OK
        for name in names:
            outcome = mean_score(check, built[name])
            row[name] = outcome["score"]  # type: ignore[assignment]
            windows = int(outcome["windows"])  # type: ignore[arg-type]
            status = str(outcome["status"])
            if outcome["vad_status"] == VAD_FAIL:
                print(
                    f"  {path.stem}/{name}: no score, {outcome['reason']}",
                    file=sys.stderr,
                )
        # The status rides on the label, so a salvaged figure is never read as a
        # clean one further down the page.
        marker = "" if status == STATUS_OK else f" {status}"
        rows[f"{path.stem} [{windows}w{marker}]"] = row
        print(f"scored {path.name}", file=sys.stderr)

    print(f"\nmean P(synthetic), model={args.model}, speech-active windows only\n")
    header = f"{'clip':>26} " + " ".join(f"{n:>7}" for n in names)
    print(header)
    print("-" * len(header))
    for label, row in rows.items():
        print(f"{label:>26} " + " ".join(_cell(row[n]) for n in names))

    print("\ndelta from source\n")
    print(f"{'clip':>26} " + " ".join(f"{n:>7}" for n in names[1:]))
    for label, row in rows.items():
        print(
            f"{label:>26} "
            + " ".join(_delta_cell(row[n], row["source"]) for n in names[1:])
        )

    print("\nEvidence, not a verdict. n is small; report the clip count with any figure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
