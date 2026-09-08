"""Which measured channel statistic does the score actually track?

    .venv\\Scripts\\python.exe -m ml.tools.correlate

Branch B, hours 4 to 6. Scores every clip we have, measures SNR, effective
bandwidth, noise floor, spectral centroid and crest factor on each, and reports the
correlation of each statistic with `synthetic_probability`.

**Pooled correlations across these datasets are confounded and the tool says so.**
ASVspoof clips are studio-clean and score near 0 or near 1 by class; ours are phone
captures and score high whatever the class. Any statistic that differs between the
two corpora will correlate with the score for that reason alone, without being a cue
the model uses. So the pooled figure is printed **and** the within-dataset figures
beside it. A statistic that only correlates pooled is describing the corpora; one
that correlates inside a dataset too is a candidate cue.

Domain distance is included as a comparison column. It is not a channel statistic; it
is there because the transplant already showed it dominates, and a channel statistic
that cannot beat it is not worth building an augmentation around.

Writes `data/results/correlation.csv`, one row per clip, and a dependency-free
`data/results/correlation.svg` scatter grid.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from ml.eval import acoustics
from ml.eval import confidence as confidence_module
from ml.eval.activity import select_windows
from ml.eval.canonical import load
from ml.paths import model_root
from ml.tools.baseline import IFD_SUBJECTS, SOURCES
from ml.tools.frozen_config import CHECKPOINT, collect
from ml.tools.sweep import WINDOW_SAMPLES, build_check

FIELDS = [
    "run_id",
    "filename",
    "dataset",
    "label",
    "channel",
    "score",
    "confidence",
    *acoustics.STATISTICS,
    "duration_s",
    "checkpoint",
    "frozen_commit",
]

#: Everything correlated against the score. Confidence is last and is not a channel
#: statistic; see the module docstring.
COLUMNS = [*acoustics.STATISTICS, "confidence"]


def analyse(scorer: object, samples: np.ndarray) -> tuple[float, float]:
    """Mean score and mean confidence over the speech-active windows."""
    scores, embeddings = [], []
    for window in select_windows(samples, WINDOW_SAMPLES).windows:
        pcm = (np.clip(window, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        score, embedding = scorer.score_and_embed(pcm, 16000)  # type: ignore[attr-defined]
        scores.append(score)
        embeddings.append(embedding)
    if not scores:
        raise ValueError("no speech-active window")
    reference = confidence_module.Reference.load(confidence_module.reference_path())
    return float(np.mean(scores)), reference.confidence(np.mean(embeddings, axis=0))


def collect_rows(scorer: object, cache: Path, commit: str) -> list[dict[str, object]]:
    from ml.train.dataset import BONAFIDE, load_flac, read_protocol

    rows: list[dict[str, object]] = []

    def add(name: str, dataset: str, label: str, channel: str, audio: np.ndarray) -> None:
        score, conf = analyse(scorer, audio)
        row: dict[str, object] = {
            "run_id": "correlation",
            "filename": name,
            "dataset": dataset,
            "label": label,
            "channel": channel,
            "score": score,
            "confidence": conf,
            "duration_s": audio.size / acoustics.SAMPLE_RATE,
            "checkpoint": CHECKPOINT,
            "frozen_commit": commit,
        }
        row.update(acoustics.describe(audio))
        rows.append(row)
        print(f"  {name:<26} score {score:.4f}  conf {conf:.3f}", file=sys.stderr)

    corpus = model_root().parent / "data" / "LA"
    utterances = sorted(read_protocol(corpus, "eval"), key=lambda u: u.path.name)
    for utterance in (
        [u for u in utterances if u.label == BONAFIDE][:20]
        + [u for u in utterances if u.label != BONAFIDE][:20]
    ):
        add(
            utterance.path.stem,
            "asvspoof",
            "genuine" if utterance.label == BONAFIDE else "spoof",
            "studio",
            load_flac(utterance.path),
        )

    for subject in IFD_SUBJECTS:
        for kind in ("bonafide", "deepfake"):
            label = "genuine" if kind == "bonafide" else "spoof"
            source = Path.home() / "Downloads" / f"{subject}_{kind}.wav"
            if source.exists():
                add(f"{subject}_{kind}", "ifd", label, "broadcast", load(source, cache))
            for device in ("iphone", "samsung"):
                replay = Path(f"data/replay/{device}/{subject}_{kind}_phone.wav")
                if replay.exists():
                    add(
                        f"{subject}_{kind}_{device}",
                        f"replay_{device}",
                        label,
                        "phone",
                        load(replay, cache),
                    )

    for working, (relative, _, label) in SOURCES.items():
        source = Path.home() / relative
        if source.exists():
            add(Path(working).stem, "internal", label, "phone", load(source, cache))

    return rows


def correlations(rows: list[dict[str, object]], column: str) -> tuple[float, float]:
    stat = np.array([float(r[column]) for r in rows])
    score = np.array([float(r["score"]) for r in rows])
    return acoustics.pearson(stat, score), acoustics.spearman(stat, score)


def report(rows: list[dict[str, object]]) -> None:
    datasets = sorted({str(r["dataset"]) for r in rows})
    usable = [d for d in datasets if sum(1 for r in rows if r["dataset"] == d) >= 4]

    header = (
        f"{'statistic':<24} {'pooled r':>9} {'pooled rho':>11}   "
        + " ".join(f"{d[:11]:>11}" for d in usable)
    )
    print("\ncorrelation with synthetic_probability, Pearson r and Spearman rho")
    print(header)
    print("-" * len(header))
    for column in COLUMNS:
        r, rho = correlations(rows, column)
        cells = []
        for dataset in usable:
            inside = [x for x in rows if x["dataset"] == dataset]
            within, _ = correlations(inside, column)
            cells.append("      -" if np.isnan(within) else f"{within:>11.2f}")
        marker = " <- not a channel statistic" if column == "confidence" else ""
        print(f"{column:<24} {r:>9.2f} {rho:>11.2f}   " + " ".join(cells) + marker)

    print("\nper-dataset columns are within-dataset correlations, n per column:")
    print(
        "  "
        + ", ".join(
            f"{d}={sum(1 for r in rows if r['dataset'] == d)}" for d in usable
        )
    )


def svg(rows: list[dict[str, object]], path: Path) -> Path:
    """A scatter grid, written by hand. No plotting dependency is installed."""
    colours = {
        "asvspoof": "#2c6fbb",
        "ifd": "#d1721f",
        "internal": "#b3303a",
        "replay_iphone": "#3f8f5a",
        "replay_samsung": "#6b4fa8",
    }
    cols, panel, pad = 3, 210, 46
    rows_n = (len(COLUMNS) + cols - 1) // cols
    width = cols * (panel + pad) + pad
    height = rows_n * (panel + pad) + pad + 46

    open_tag = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui,sans-serif">'
    )
    parts = [open_tag, f'<rect width="{width}" height="{height}" fill="#fdfdfc"/>']
    for index, column in enumerate(COLUMNS):
        cx = pad + (index % cols) * (panel + pad)
        cy = pad + (index // cols) * (panel + pad)
        values = np.array([float(r[column]) for r in rows])
        low, high = float(values.min()), float(values.max())
        span = (high - low) or 1.0
        parts.append(
            f'<rect x="{cx}" y="{cy}" width="{panel}" height="{panel}" fill="#fff" '
            f'stroke="#ccc"/>'
        )
        parts.append(
            f'<text x="{cx}" y="{cy - 8}" font-size="11" fill="#222">{column}</text>'
        )
        for row in rows:
            px = cx + (float(row[column]) - low) / span * panel
            py = cy + panel - float(row["score"]) * panel
            colour = colours.get(str(row["dataset"]), "#888")
            parts.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.6" fill="{colour}" '
                f'fill-opacity="0.72"/>'
            )
        r, _ = correlations(rows, column)
        parts.append(
            f'<text x="{cx + 4}" y="{cy + 13}" font-size="10" fill="#666">'
            f"r={r:+.2f}</text>"
        )
        parts.append(
            f'<text x="{cx - 6}" y="{cy + panel}" font-size="9" fill="#888" '
            f'text-anchor="end">0</text>'
        )
        parts.append(
            f'<text x="{cx - 6}" y="{cy + 8}" font-size="9" fill="#888" '
            f'text-anchor="end">1</text>'
        )

    legend_y = height - 18
    x = pad
    for dataset, colour in colours.items():
        parts.append(f'<circle cx="{x}" cy="{legend_y - 4}" r="4" fill="{colour}"/>')
        parts.append(
            f'<text x="{x + 9}" y="{legend_y}" font-size="11" fill="#333">{dataset}</text>'
        )
        x += 24 + len(dataset) * 6.6
    parts.append(
        f'<text x="{pad}" y="{legend_y - 20}" font-size="11" fill="#555">'
        "y axis is synthetic_probability, 0 at the bottom</text>"
    )
    parts.append("</svg>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/results/correlation.csv"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/results/canonical"))
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    fields = collect()
    check = build_check("xlsr-aasist", args.device)
    rows = collect_rows(check._scorer, args.cache_dir, fields["frozen_commit"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["dataset"], r["filename"])):
            writer.writerow(
                {
                    k: (f"{v:.6f}" if isinstance(v, float) else v)
                    for k, v in row.items()
                }
            )
    print(f"\nwrote {len(rows)} rows to {args.out}")

    report(rows)
    plot = svg(rows, args.out.with_suffix(".svg"))
    print(f"\nwrote {plot}")
    print(
        "\nA pooled correlation across these corpora is confounded: any statistic\n"
        "that differs between ASVspoof and phone audio correlates with the score for\n"
        "that reason alone. Read the within-dataset columns."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
