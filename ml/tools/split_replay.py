"""Cut a continuous replay take back into the ten clips that were played into it.

    .venv\\Scripts\\python.exe -m ml.tools.split_replay data/replay/iphone_recordings.m4a --device iphone

The session is recorded as one take per device, which is how it should be done:
nothing is touched between clips, so the five controls hold by construction. This
puts the clips back.

Each original is located by normalised cross-correlation of log-energy envelopes,
so the playback order does not matter and a level difference cannot move a match.
Every match is reported with its correlation and its margin over the next-best
position, and the run refuses to write anything if any clip is weakly or ambiguously
matched, or if two matches overlap. A quietly mis-cut clip would put the wrong audio
under the right filename and there would be no later sign of it.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

from ml.eval.align import SAMPLE_RATE, find_clip, overlaps
from ml.eval.canonical import load
from ml.tools.baseline import IFD_SUBJECTS

#: Below this correlation a match is not trusted. Envelope correlation between a clip
#: and a room recording of itself runs high; anything near zero is a non-match.
MIN_SCORE = 0.45

#: The peak must beat the best rival position by this much on its own. Below this,
#: the match is only accepted if the rest of the take corroborates it: see
#: `corroborated_by_disjointness`.
MIN_MARGIN = 0.10

#: Fraction of samples at full scale above which the take is called clipped. Clipping
#: is a nonlinear distortion that adds harmonics the model may read, so it is a
#: confound between devices and must be reported rather than discovered later.
CLIP_FRACTION = 1e-4


def clip_names() -> list[str]:
    return [f"{s}_{k}" for s in IFD_SUBJECTS for k in ("bonafide", "deepfake")]


def write_wav(path: Path, samples: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return path


def clipping_fraction(x: np.ndarray) -> float:
    return float((np.abs(x) >= 0.999).mean())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("take", type=Path, help="the continuous recording")
    parser.add_argument(
        "--device", required=True, help="subdirectory to write into, e.g. iphone"
    )
    parser.add_argument("--source-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--out-root", type=Path, default=Path("data/replay"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/results/canonical"))
    parser.add_argument(
        "--force",
        action="store_true",
        help="write the clips even when a match is weak. Records the fact in the "
        "printed table; the numbers that follow are then not trustworthy",
    )
    args = parser.parse_args(argv)

    recording = load(args.take, args.cache_dir)
    clipped = clipping_fraction(recording)
    print(f"take     {args.take.name}")
    print(f"length   {recording.size / SAMPLE_RATE:.2f} s")
    print(f"peak     {np.abs(recording).max():.4f}")
    print(
        f"clipped  {clipped * 100:.3f}% of samples at full scale"
        + ("   <-- CONFOUND, see below" if clipped > CLIP_FRACTION else "")
    )
    print()

    header = f"{'clip':<22} {'start':>8} {'len':>7} {'corr':>6} {'margin':>7}  verdict"
    print(header)
    print("-" * len(header))

    matches = []
    problems: list[str] = []
    thin: list[str] = []
    for name in clip_names():
        source = args.source_dir / f"{name}.wav"
        if not source.exists():
            problems.append(f"{name}: original missing at {source}")
            print(f"{name:<22} {'-':>8} {'-':>7} {'-':>6} {'-':>7}  ORIGINAL MISSING")
            continue
        clip = load(source, args.cache_dir)
        match = find_clip(recording, clip)
        if match is None:
            problems.append(f"{name}: the take is shorter than the clip")
            print(f"{name:<22} {'-':>8} {'-':>7} {'-':>6} {'-':>7}  TAKE TOO SHORT")
            continue

        verdict = "ok"
        if match.score < MIN_SCORE:
            verdict = "NO MATCH"
            problems.append(f"{name}: correlation {match.score:.3f} below {MIN_SCORE}")
        elif match.margin < MIN_MARGIN:
            verdict = "thin"
            thin.append(f"{name}: margin {match.margin:.3f} below {MIN_MARGIN}")

        print(
            f"{name:<22} {match.start_s:>7.2f}s {clip.size / SAMPLE_RATE:>6.2f}s "
            f"{match.score:>6.3f} {match.margin:>7.3f}  {verdict}"
        )
        matches.append((name, match.offset, clip.size))

    spans = {name: (offset, offset + size) for name, offset, size in matches}
    collisions = []
    for i, (name_a, span_a) in enumerate(spans.items()):
        for name_b, span_b in list(spans.items())[i + 1 :]:
            if overlaps(span_a, span_b):
                collisions.append(f"{name_a} and {name_b} matched overlapping audio")
    problems += collisions

    complete = len(matches) == len(clip_names())
    if not complete:
        problems.append(f"only {len(matches)} of {len(clip_names())} clips matched")

    # A thin margin means some other position in the take correlated almost as well.
    # If every clip has its own non-overlapping slot, those rival positions are
    # already accounted for by other clips, and the thin match has nowhere else it
    # could belong. That is corroboration from the take as a whole rather than from
    # the clip alone, and it is recorded as such instead of being waved through.
    corroborated = complete and not collisions
    if thin and not corroborated:
        problems += thin

    if problems and not args.force:
        print("\nnot writing anything:")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nA mis-cut clip puts the wrong audio under the right filename and "
            "nothing downstream can tell. Fix the take, or pass --force and treat "
            "every number from it as provisional."
        )
        return 1

    out_dir = args.out_root / args.device
    for name, offset, size in matches:
        write_wav(out_dir / f"{name}_phone.wav", recording[offset : offset + size])
    print(f"\nwrote {len(matches)} clips to {out_dir}")

    if thin and corroborated:
        print(
            "\naccepted on disjointness, not on their own correlation:"
        )
        for item in thin:
            print(f"  {item}")
        print(
            "  All ten clips matched non-overlapping regions, so the rival positions "
            "these peaks competed with are occupied by other clips. Weaker evidence "
            "than a clean margin; it travels with any figure from these files."
        )

    if clipped > CLIP_FRACTION:
        print(
            f"\n{clipped * 100:.3f}% of this take is at full scale. Clipping is a "
            "nonlinear distortion that adds harmonics, so it is a difference between "
            "devices that is not the acquisition channel. Say so with any delta from "
            "this device, or re-record it quieter."
        )
    if problems:
        print("\nforced past:")
        for problem in problems:
            print(f"  {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
