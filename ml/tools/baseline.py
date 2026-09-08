"""Score everything we have, once, into one reproducible table.

    .venv\\Scripts\\python.exe -m ml.tools.baseline
    .venv\\Scripts\\python.exe -m ml.tools.baseline --out data/results/baseline.csv

The anchor for the whole H+0 to H+4 diagnosis. Every later experiment is read as a
change from these rows, so if these are wrong nothing downstream can be trusted.
Runs against the config in `FROZEN.md`.

Four sets, all through one pipeline in one process:

  asvspoof   20 eval clips, 10 bonafide and 10 spoof, the in-domain anchor
  ifd        all 10 IndieFake clips, 5 bonafide and 5 deepfake
  internal   our own 5 genuine recordings
  internal   nik_clone, a real commercial voice clone of one of those speakers

The last two are regenerated from their source media rather than read from working
copies, because the working copies are gitignored and are no longer on disk. See
`SOURCES` for the mapping and `ml/README.md` for what each recording is.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from ml.checks.machine_fingerprint import MachineFingerprintCheck
from ml.eval import runlog
from ml.eval.canonical import SAMPLE_RATE, load
from ml.paths import model_root
from ml.tools.frozen_config import CHECKPOINT, collect
from ml.tools.sweep import build_check, mean_score

#: The five genuine recordings and the clone, by the source each was made from. The
#: working copies named in `ml/README.md` are gitignored and are not on disk any
#: more, so each is regenerated from its source through the frozen decode. Two of
#: them originally passed through an intermediate lossless stereo wav; that step is
#: lossless, but it is the first thing to suspect if an anchor misses.
SOURCES: dict[str, tuple[str, str, str]] = {
    # working copy name -> (source, relative to --source-root; speaker; label)
    "spk_01_source.wav": ("Downloads/Bharath.mpeg", "speaker_a", "genuine"),
    "spk_02_source.wav": ("Downloads/Goutham.mp4", "speaker_b", "genuine"),
    "spk_03_source.wav": ("Downloads/Nikhil.mp4", "speaker_c", "genuine"),
    "spk_03b_source.wav": ("Downloads/Nikhil_2.mp4", "speaker_c", "genuine"),
    "nik_clean.wav": (
        "OneDrive/Documents/Sound Recordings/nikhil_clean.m4a",
        "speaker_c",
        "genuine",
    ),
    "nik_clone.wav": ("Downloads/nikhil_clone.wav", "speaker_c", "spoof"),
}

#: The five IFD public figures, bonafide and deepfake of each.
IFD_SUBJECTS = ("alia", "cb", "madhavan", "pc", "sadhguru")

#: How many ASVspoof eval clips per class. Selected by sorted file id rather than by
#: a seeded sample, so the selection reproduces with no seed to record.
ASVSPOOF_PER_CLASS = 10

#: Anchors from `ml/README.md` for this checkpoint, with the tolerance a re-run must
#: land inside. These are the point of the file: if the environment has moved, every
#: later number in the diagnosis inherits the difference without saying so.
ANCHORS: dict[str, tuple[float, float]] = {
    # filename      -> (expected, tolerance)
    "pc_bonafide": (0.029, 0.01),
    "pc_deepfake": (0.847, 0.05),
}

#: ASVspoof bonafide scores 0.000 on this checkpoint. Checked as a ceiling on the
#: median rather than per clip, because a single clip is one draw.
ASVSPOOF_BONAFIDE_CEILING = 0.01


def _row(
    filename: str,
    outcome: dict[str, object],
    *,
    label: str,
    dataset: str,
    channel: str,
    speaker: str,
    notes: str,
    frozen_commit: str,
) -> runlog.Row:
    return runlog.Row(
        run_id="baseline",
        filename=filename,
        speaker=speaker,
        label=label,
        dataset=dataset,
        channel=channel,
        duration_s=float(outcome["duration_s"]),  # type: ignore[arg-type]
        sample_rate=SAMPLE_RATE,
        vad_status=str(outcome["vad_status"]),
        speech_s=float(outcome["speech_s"]),  # type: ignore[arg-type]
        score=outcome["score"],  # type: ignore[arg-type]
        checkpoint=CHECKPOINT,
        frozen_commit=frozen_commit,
        notes=notes,
    )


def _cell(outcome: dict[str, object]) -> str:
    score = outcome["score"]
    shown = "FAIL" if score is None else f"{float(score):.4f}"  # type: ignore[arg-type]
    return f"{shown:>8}  {outcome['status']:<9} {outcome['windows']:>3}w"


def asvspoof_rows(
    check: MachineFingerprintCheck, commit: str, per_class: int
) -> list[runlog.Row]:
    from ml.train.dataset import BONAFIDE, load_flac, read_protocol

    corpus = model_root().parent / "data" / "LA"
    utterances = sorted(read_protocol(corpus, "eval"), key=lambda u: u.path.name)
    bonafide = [u for u in utterances if u.label == BONAFIDE][:per_class]
    spoof = [u for u in utterances if u.label != BONAFIDE][:per_class]

    rows = []
    for utterance in bonafide + spoof:
        genuine = utterance.label == BONAFIDE
        outcome = mean_score(check, load_flac(utterance.path))
        rows.append(
            _row(
                utterance.path.stem,
                outcome,
                label="genuine" if genuine else "spoof",
                dataset="asvspoof",
                channel="studio",
                speaker="n/a",
                notes=f"2019 LA eval, attack={utterance.attack_id}",
                frozen_commit=commit,
            )
        )
        print(f"  {utterance.path.stem:<20} {_cell(outcome)}", file=sys.stderr)
    return rows


def ifd_rows(
    check: MachineFingerprintCheck, ifd_dir: Path, cache: Path, commit: str
) -> list[runlog.Row]:
    rows = []
    for subject in IFD_SUBJECTS:
        for kind, label, channel in (
            ("bonafide", "genuine", "broadcast"),
            ("deepfake", "spoof", "generated"),
        ):
            name = f"{subject}_{kind}"
            source = ifd_dir / f"{name}.wav"
            if not source.exists():
                print(f"  {name:<20} MISSING at {source}", file=sys.stderr)
                continue
            outcome = mean_score(check, load(source, cache))
            rows.append(
                _row(
                    name,
                    outcome,
                    label=label,
                    dataset="ifd",
                    channel=channel,
                    speaker=f"ifd_{subject}",
                    notes="IndieFake sample, 5 to 6 s, window choice matters",
                    frozen_commit=commit,
                )
            )
            print(f"  {name:<20} {_cell(outcome)}", file=sys.stderr)
    return rows


def internal_rows(
    check: MachineFingerprintCheck, source_root: Path, cache: Path, commit: str
) -> list[runlog.Row]:
    rows = []
    for working_name, (relative, speaker, label) in SOURCES.items():
        source = source_root / relative
        if not source.exists():
            print(f"  {working_name:<20} MISSING at {source}", file=sys.stderr)
            continue
        outcome = mean_score(check, load(source, cache))
        rows.append(
            _row(
                Path(working_name).stem,
                outcome,
                label=label,
                dataset="internal",
                channel="generated" if label == "spoof" else "phone",
                speaker=speaker,
                notes=f"regenerated from {Path(relative).name}",
                frozen_commit=commit,
            )
        )
        print(f"  {working_name:<20} {_cell(outcome)}", file=sys.stderr)
    return rows


def summarise(rows: list[runlog.Row]) -> None:
    print("\nby dataset and label, over scored rows")
    header = (
        f"{'dataset':<10} {'label':<9} {'n':>3} {'fail':>5} "
        f"{'mean':>7} {'min':>7} {'max':>7}"
    )
    print(header)
    print("-" * len(header))
    groups: dict[tuple[str, str], list[runlog.Row]] = {}
    for row in rows:
        groups.setdefault((row.dataset, row.label), []).append(row)
    for (dataset, label), group in sorted(groups.items()):
        scored = [r.score for r in group if r.score is not None]
        failed = len(group) - len(scored)
        if not scored:
            print(f"{dataset:<10} {label:<9} {len(group):>3} {failed:>5} {'-':>7}")
            continue
        array = np.asarray(scored)
        print(
            f"{dataset:<10} {label:<9} {len(group):>3} {failed:>5} "
            f"{array.mean():>7.3f} {array.min():>7.3f} {array.max():>7.3f}"
        )


def check_anchors(rows: list[runlog.Row]) -> list[str]:
    """Compare against the recorded values. Prints every check, returns failures.

    A drifted anchor is not cosmetic. It means this environment differs from the one
    that produced `ml/README.md`, and every later number would inherit that
    difference silently.
    """
    by_name = {row.filename: row for row in rows}
    failures: list[str] = []

    print("\nanchor check, against ml/README.md for this checkpoint")
    for name, (expected, tolerance) in ANCHORS.items():
        row = by_name.get(name)
        if row is None or row.score is None:
            failures.append(f"{name}: no score to compare")
            print(f"  {name:<16} {'MISSING':>8}   expected {expected:.3f}")
            continue
        delta = row.score - expected
        drifted = abs(delta) > tolerance
        failures += (
            [f"{name}: {row.score:.4f}, expected {expected:.3f} +/- {tolerance}"]
            if drifted
            else []
        )
        print(
            f"  {name:<16} {row.score:>8.4f}   expected {expected:.3f} "
            f"+/- {tolerance}   delta {delta:+.4f}   "
            f"{'DRIFTED' if drifted else 'ok'}"
        )

    bonafide = [
        r.score
        for r in rows
        if r.dataset == "asvspoof" and r.label == "genuine" and r.score is not None
    ]
    if not bonafide:
        failures.append("no ASVspoof bonafide rows to check")
        return failures

    median = float(np.median(bonafide))
    drifted = median > ASVSPOOF_BONAFIDE_CEILING
    if drifted:
        failures.append(
            f"asvspoof bonafide median {median:.4f} above {ASVSPOOF_BONAFIDE_CEILING}"
        )
    print(
        f"  {'asvspoof bona':<16} {median:>8.4f}   expected <= "
        f"{ASVSPOOF_BONAFIDE_CEILING}   median of {len(bonafide)}   "
        f"{'DRIFTED' if drifted else 'ok'}"
    )
    return failures


def main(argv: list[str] | None = None) -> int:
    downloads = Path.home() / "Downloads"
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path.home(),
        help="root the SOURCES paths are relative to (default: the home directory)",
    )
    parser.add_argument("--ifd-dir", type=Path, default=downloads)
    parser.add_argument("--out", type=Path, default=Path("data/results/baseline.csv"))
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="where canonical 16 kHz decodes are kept (default: beside --out)",
    )
    parser.add_argument("--device", default=None)
    parser.add_argument("--asvspoof-per-class", type=int, default=ASVSPOOF_PER_CLASS)
    args = parser.parse_args(argv)

    cache = args.cache_dir or args.out.parent / "canonical"
    fields = collect()
    commit = fields["frozen_commit"]
    print(f"model    {fields['model_id']}  {Path(fields['checkpoint_path']).name}")
    print(f"commit   {commit}")
    print(f"window   {fields['window_s']} s, activity floor {fields['vad_activity_floor']}")
    print(f"cache    {cache}\n")

    check = build_check("xlsr-aasist", args.device)

    print("asvspoof", file=sys.stderr)
    rows = asvspoof_rows(check, commit, args.asvspoof_per_class)
    print("ifd", file=sys.stderr)
    rows += ifd_rows(check, args.ifd_dir, cache, commit)
    print("internal", file=sys.stderr)
    rows += internal_rows(check, args.source_root, cache, commit)

    runlog.write(rows, args.out)
    print(f"\nwrote {len(rows)} rows to {args.out}")

    summarise(rows)
    failures = check_anchors(rows)

    if failures:
        print("\nANCHORS DRIFTED. Do not run further experiments against this build.")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nEvery later number would inherit the difference without saying so. "
            "Find what changed in the environment first."
        )
        return 1

    print("\nanchors hold. This environment matches the one in ml/README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
