"""Hold the speech constant, vary only the acquisition channel.

    .venv\\Scripts\\python.exe -m ml.tools.transplant
    .venv\\Scripts\\python.exe -m ml.tools.transplant --subject pc --subject alia

The decisive experiment of the diagnosis. Speaker, accent, words and generator are
identical down each column; the only thing that changes is how the audio was
acquired. Six cells:

                     A: original file    B: speaker to phone   C: B through Exotel
    IFD bonafide     have it             record                record
    IFD deepfake     have it             record                record

**Both classes, never just the genuine one.** Replaying only bonafide cannot tell
"the channel makes genuine audio look fake" apart from "the channel raises every
score", and those two findings lead to different branches of the H+4 gate.

Paths B and C need a person, a speaker and a phone, so this tool runs with whatever
cells exist and says plainly which are missing. It does not invent a delta it could
not measure. See `ml/TRANSPLANT_CAPTURE.md` for the capture procedure and the
controls that must be held constant.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ml.checks.machine_fingerprint import MachineFingerprintCheck
from ml.eval import runlog
from ml.eval.canonical import SAMPLE_RATE, load
from ml.eval.transplant import describe
from ml.tools.frozen_config import CHECKPOINT, collect
from ml.tools.sweep import build_check, mean_score

#: The three acquisition paths, by the suffix their file carries and the `channel`
#: value the row records.
PATHS: dict[str, tuple[str, str]] = {
    # path -> (filename suffix, channel)
    "A": ("", "broadcast"),
    "B": ("_phone", "phone"),
    "C": ("_exotel", "phone_exotel"),
}

#: The two classes, by filename suffix and run-log label.
CLASSES: dict[str, str] = {"bonafide": "genuine", "deepfake": "spoof"}

#: IFD `pc` by default: it has the cleanest separation this checkpoint shows on
#: independent audio (0.029 against 0.847), so a collapse is unambiguous.
DEFAULT_SUBJECTS = ("pc",)

#: Controls that must be identical across all four captures. A capture without
#: these recorded is confounded and cannot be read, so the file is required as soon
#: as any B or C recording exists.
REQUIRED_CONDITIONS = (
    "speaker_volume",
    "phone_model",
    "distance_cm",
    "room",
    "background_noise",
)

CONDITIONS_FILE = "capture_conditions.json"


def load_conditions(capture_dir: Path) -> dict[str, str]:
    """Read and validate the capture controls, or explain what is missing."""
    path = capture_dir / CONDITIONS_FILE
    if not path.exists():
        raise SystemExit(
            f"missing {path}. Every replayed capture must record the controls "
            f"({', '.join(REQUIRED_CONDITIONS)}) or the experiment is confounded and "
            "its deltas cannot be read. See ml/TRANSPLANT_CAPTURE.md."
        )
    conditions = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_CONDITIONS if not str(conditions.get(key, "")).strip()]
    if missing:
        raise SystemExit(f"{path} is missing: {', '.join(missing)}")
    return {key: str(conditions[key]) for key in REQUIRED_CONDITIONS}


def conditions_note(conditions: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in conditions.items())


def score_cells(
    check: MachineFingerprintCheck,
    subjects: tuple[str, ...],
    source_dir: Path,
    capture_dir: Path,
    cache: Path,
    commit: str,
    conditions: dict[str, str] | None,
) -> tuple[list[runlog.Row], dict[tuple[str, str, str], float], list[str]]:
    """Score every cell that exists. Returns rows, a lookup, and what was missing."""
    rows: list[runlog.Row] = []
    scores: dict[tuple[str, str, str], float] = {}
    missing: list[str] = []

    for subject in subjects:
        for klass, label in CLASSES.items():
            for path_id, (suffix, channel) in PATHS.items():
                name = f"{subject}_{klass}{suffix}"
                directory = source_dir if path_id == "A" else capture_dir
                source = directory / f"{name}.wav"
                if not source.exists():
                    missing.append(f"{path_id}/{subject}/{klass} at {source}")
                    print(f"  {name:<26} MISSING", file=sys.stderr)
                    continue

                outcome = mean_score(check, load(source, cache))
                note = f"path {path_id}, {subject} {klass}"
                if path_id != "A":
                    note += f"; {conditions_note(conditions or {})}"
                rows.append(
                    runlog.Row(
                        run_id="transplant",
                        filename=name,
                        speaker=f"ifd_{subject}",
                        label=label,
                        dataset="ifd",
                        channel=channel,
                        duration_s=float(outcome["duration_s"]),  # type: ignore[arg-type]
                        sample_rate=SAMPLE_RATE,
                        vad_status=str(outcome["vad_status"]),
                        speech_s=float(outcome["speech_s"]),  # type: ignore[arg-type]
                        score=outcome["score"],  # type: ignore[arg-type]
                        checkpoint=CHECKPOINT,
                        frozen_commit=commit,
                        notes=note,
                    )
                )
                shown = (
                    "FAIL"
                    if outcome["score"] is None
                    else f"{float(outcome['score']):.4f}"  # type: ignore[arg-type]
                )
                print(
                    f"  {name:<26} {shown:>8}  {outcome['status']:<9} "
                    f"{outcome['windows']:>3}w",
                    file=sys.stderr,
                )
                if outcome["score"] is not None:
                    scores[(path_id, subject, klass)] = float(outcome["score"])  # type: ignore[arg-type]

    return rows, scores, missing


def deltas(
    scores: dict[tuple[str, str, str], float], subjects: tuple[str, ...]
) -> dict[str, float | None]:
    """The four deltas the H+4 gate reads. `None` where a cell is missing."""
    out: dict[str, float | None] = {}
    for path_id, path_name in (("B", "phone"), ("C", "exotel")):
        for klass, class_name in (("bonafide", "genuine"), ("deepfake", "spoof")):
            pairs = [
                scores[(path_id, s, klass)] - scores[("A", s, klass)]
                for s in subjects
                if (path_id, s, klass) in scores and ("A", s, klass) in scores
            ]
            out[f"delta_{class_name}_{path_name}"] = (
                sum(pairs) / len(pairs) if pairs else None
            )
    return out


def class_scores(
    scores: dict[tuple[str, str, str], float], path_id: str
) -> tuple[list[float], list[float]]:
    genuine = [v for (p, _, k), v in scores.items() if p == path_id and k == "bonafide"]
    spoof = [v for (p, _, k), v in scores.items() if p == path_id and k == "deepfake"]
    return genuine, spoof


def report(
    scores: dict[tuple[str, str, str], float],
    subjects: tuple[str, ...],
    missing: list[str],
) -> dict[str, float | None]:
    print("\nscores by path")
    header = f"{'subject':<10} {'class':<10} {'A original':>11} {'B phone':>9} {'C exotel':>9}"
    print(header)
    print("-" * len(header))
    for subject in subjects:
        for klass in CLASSES:
            cells = [
                f"{scores[(p, subject, klass)]:>{w}.4f}"
                if (p, subject, klass) in scores
                else f"{'-':>{w}}"
                for p, w in (("A", 11), ("B", 9), ("C", 9))
            ]
            print(f"{subject:<10} {klass:<10} " + " ".join(cells))

    computed = deltas(scores, subjects)
    print("\ndeltas, path minus original")
    for name, value in computed.items():
        shown = "not measured" if value is None else f"{value:+.4f}"
        print(f"  {name:<24} {shown}")

    print("\nseparation")
    for path_id, title in (
        ("A", "before, original files"),
        ("B", "after, speaker to phone"),
        ("C", "after, through Exotel"),
    ):
        genuine, spoof = class_scores(scores, path_id)
        print(f"\n{title}")
        if not genuine or not spoof:
            print("  not measurable, a class is missing on this path")
            continue
        for line in describe(genuine, spoof).splitlines():
            print(f"  {line}")

    if missing:
        print(f"\n{len(missing)} of 6 cells are missing:")
        for item in missing:
            print(f"  {item}")
        print(
            "\nThe H+4 gate cannot be evaluated. Rules 3, 4 and 5 all read "
            "delta_genuine_phone, which needs path B for both classes. "
            "See ml/TRANSPLANT_CAPTURE.md."
        )
    return computed


def main(argv: list[str] | None = None) -> int:
    downloads = Path.home() / "Downloads"
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--subject",
        dest="subjects",
        action="append",
        default=None,
        help=f"IFD subject to transplant (default: {' '.join(DEFAULT_SUBJECTS)})",
    )
    parser.add_argument("--source-dir", type=Path, default=downloads)
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=Path("data/replay"),
        help="where the replayed path B and C recordings live",
    )
    parser.add_argument("--out", type=Path, default=Path("data/results/transplant.csv"))
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    subjects = tuple(args.subjects or DEFAULT_SUBJECTS)
    cache = args.cache_dir or args.out.parent / "canonical"
    fields = collect()
    commit = fields["frozen_commit"]

    has_captures = any(args.capture_dir.glob("*_phone.wav")) or any(
        args.capture_dir.glob("*_exotel.wav")
    )
    conditions = load_conditions(args.capture_dir) if has_captures else None

    print(f"model    {fields['model_id']}  {Path(fields['checkpoint_path']).name}")
    print(f"commit   {commit}")
    print(f"subjects {' '.join(subjects)}")
    print(f"captures {args.capture_dir}" + ("" if has_captures else "  (none yet)"))
    if conditions:
        print(f"controls {conditions_note(conditions)}")
    print()

    check = build_check("xlsr-aasist", args.device)
    rows, scores, missing = score_cells(
        check, subjects, args.source_dir, args.capture_dir, cache, commit, conditions
    )

    runlog.write(rows, args.out)
    print(f"\nwrote {len(rows)} rows to {args.out}")
    report(scores, subjects, missing)
    print(
        "\nEvidence, not a verdict. One subject per column unless --subject is "
        "repeated, and overlap needs more than one clip per class to mean anything."
    )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
