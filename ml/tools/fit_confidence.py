"""Fit the confidence reference from in-domain ASVspoof audio.

    .venv\\Scripts\\python.exe -m ml.tools.fit_confidence
    .venv\\Scripts\\python.exe -m ml.tools.fit_confidence --clips 120 --evaluate

Writes `confidence_reference.npz` beside the weights, outside the repo, because it
is derived from a licensed corpus.

`--evaluate` scores the fitted reference against every labelled clip we have and
reports the AUC for predicting a wrong answer. Run it after any change: a confidence
signal that nobody has measured is worse than none, because it invites trust.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from ml.eval import confidence as confidence_module
from ml.eval.activity import select_windows
from ml.eval.canonical import load
from ml.paths import model_root
from ml.tools.baseline import IFD_SUBJECTS, SOURCES
from ml.tools.sweep import WINDOW_SAMPLES, build_check

#: Held-out ASVspoof eval clips used to fit the reference. Balanced across classes,
#: because the reference describes the *domain*, not one class within it.
DEFAULT_CLIPS = 120


def embed_and_score(scorer: object, samples: np.ndarray) -> tuple[np.ndarray, float]:
    """Mean embedding and mean score over the speech-active windows of one clip."""
    embeddings, scores = [], []
    for window in select_windows(samples, WINDOW_SAMPLES).windows:
        pcm = (np.clip(window, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        embeddings.append(scorer.embed(pcm, 16000))  # type: ignore[attr-defined]
        scores.append(scorer.score(pcm, 16000))  # type: ignore[attr-defined]
    if not embeddings:
        raise ValueError("no speech-active window to embed")
    return np.mean(embeddings, axis=0), float(np.mean(scores))


def auc(distances: np.ndarray, wrong: np.ndarray) -> float:
    """Probability that a wrong clip ranks further out than a correct one."""
    order = np.argsort(distances)
    ranked = wrong[order]
    positives, negatives = int(ranked.sum()), int((~ranked).sum())
    if positives == 0 or negatives == 0:
        return float("nan")
    seen, total = 0, 0
    for is_wrong in ranked:
        if is_wrong:
            total += seen
        else:
            seen += 1
    return total / (positives * negatives)


def main(argv: list[str] | None = None) -> int:
    from ml.train.dataset import BONAFIDE, load_flac, read_protocol

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clips", type=int, default=DEFAULT_CLIPS)
    parser.add_argument("--k", type=int, default=confidence_module.DEFAULT_K)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="also measure how well the fitted reference predicts a wrong answer",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("data/results/canonical"))
    args = parser.parse_args(argv)

    out = args.out or confidence_module.reference_path()
    check = build_check("xlsr-aasist", args.device)
    scorer = check._scorer

    corpus = model_root().parent / "data" / "LA"
    utterances = sorted(read_protocol(corpus, "eval"), key=lambda u: u.path.name)
    per_class = args.clips // 2
    bonafide = [u for u in utterances if u.label == BONAFIDE][:per_class]
    spoof = [u for u in utterances if u.label != BONAFIDE][:per_class]

    # Half fit the reference, half are held out for the evaluation. Fitting and
    # measuring on the same clips would report how well it memorised them.
    fit_set, held_set = [], []
    print(f"embedding {len(bonafide) + len(spoof)} ASVspoof eval clips", file=sys.stderr)
    for index, utterance in enumerate(bonafide + spoof):
        embedding, score = embed_and_score(scorer, load_flac(utterance.path))
        truth = 0.0 if utterance.label == BONAFIDE else 1.0
        (fit_set if index % 2 == 0 else held_set).append((embedding, score, truth))

    reference = confidence_module.fit(
        np.stack([e for e, _, _ in fit_set]), k=args.k
    )
    reference.save(out)
    print(f"\nfitted on {reference.size} in-domain clips, k={reference.k}")
    print(f"wrote {out}")
    print(
        f"reference self-distance: median "
        f"{np.median(reference.self_distances):.3f}, "
        f"range {reference.self_distances.min():.3f} to "
        f"{reference.self_distances.max():.3f}"
    )

    if not args.evaluate:
        return 0

    labelled: list[tuple[str, np.ndarray, float, float]] = [
        ("asvspoof", e, s, t) for e, s, t in held_set
    ]
    for subject in IFD_SUBJECTS:
        for kind in ("bonafide", "deepfake"):
            truth = 0.0 if kind == "bonafide" else 1.0
            source = Path.home() / "Downloads" / f"{subject}_{kind}.wav"
            if source.exists():
                labelled.append(
                    ("ifd", *embed_and_score(scorer, load(source, args.cache_dir)), truth)
                )
            for device in ("iphone", "samsung"):
                replay = Path(f"data/replay/{device}/{subject}_{kind}_phone.wav")
                if replay.exists():
                    labelled.append(
                        (
                            f"replay_{device}",
                            *embed_and_score(scorer, load(replay, args.cache_dir)),
                            truth,
                        )
                    )
    for relative, _, label in SOURCES.values():
        source = Path.home() / relative
        if source.exists():
            labelled.append(
                (
                    "internal",
                    *embed_and_score(scorer, load(source, args.cache_dir)),
                    0.0 if label == "genuine" else 1.0,
                )
            )

    distances = np.array([reference.distance(e) for _, e, _, _ in labelled])
    confidences = np.array([reference.confidence(e) for _, e, _, _ in labelled])
    errors = np.array([abs(s - t) for _, _, s, t in labelled])
    wrong = errors > 0.5

    print(f"\nevaluated on {len(labelled)} clips with a known label")
    print(f"{'group':<16} {'n':>3} {'wrong':>6} {'confidence mean':>16} {'range':>16}")
    for group in sorted({g for g, _, _, _ in labelled}):
        mask = np.array([g == group for g, _, _, _ in labelled])
        c = confidences[mask]
        print(
            f"{group:<16} {mask.sum():>3} {wrong[mask].sum():>6} "
            f"{c.mean():>16.3f} {f'{c.min():.3f} to {c.max():.3f}':>16}"
        )

    out_of_domain = np.array([g != "asvspoof" for g, _, _, _ in labelled])
    print(
        f"\nAUC, distance separating out-of-domain from in-domain: "
        f"{auc(distances, out_of_domain):.3f}   (what it measures)"
    )
    print(
        f"AUC, distance predicting a wrong answer:                "
        f"{auc(distances, wrong):.3f}   (what you might want)"
    )
    print("  The second is lower because an out-of-domain clip the model")
    print("  happens to get right also earns low confidence. That is correct")
    print("  behaviour, not a miss: the audio is still outside what the")
    print("  checkpoint has seen.")
    print(
        f"correlation of distance with |score - truth|: "
        f"r = {np.corrcoef(distances, errors)[0, 1]:+.3f}"
    )
    print(
        f"confidence when the model is wrong:   mean {confidences[wrong].mean():.3f}\n"
        f"confidence when the model is correct: mean {confidences[~wrong].mean():.3f}"
    )
    print(
        "\nA graded hint for the risk engine, never a gate. It misses more than half "
        "the errors\nat any threshold that keeps the false-flag rate tolerable."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
