"""Score an ASVspoof 2019 LA split and report EER with its cost-weighted companion.

    .venv\\Scripts\\python.exe -m ml.tools.evaluate --split eval --weights <ckpt>
    .venv\\Scripts\\python.exe -m ml.tools.evaluate --split eval --channel clean

Why this exists separately from the training loop: the loop reports **dev** EER,
because dev is what selects a checkpoint. A figure chosen on the data it was selected
against is not a result. The eval split is held out, and its attacks A07 to A19 are
mostly generators absent from training, which is the whole point of `AGENTS.md`
"train across corpora, score only unseen data".

Reports EER and normalised min-DCF together, never EER alone.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from ml.eval.cost import summarise
from ml.eval.eer import compute_eer, false_accept_at_false_reject
from ml.paths import model_root
from ml.train.dataset import AsvspoofLaDataset, PhoneChannelAugmenter, class_counts


def main(argv: list[str] | None = None) -> int:
    import torch
    from torch.utils.data import DataLoader

    from ml.train.finetune_aasist import build_model

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", default="eval", choices=["train", "dev", "eval"])
    parser.add_argument("--variant", default="AASIST", choices=["AASIST", "AASIST-L"])
    parser.add_argument(
        "--weights", type=Path, default=None, help="fine-tuned checkpoint (default: released)"
    )
    parser.add_argument(
        "--channel",
        default="phone",
        choices=["phone", "clean"],
        help="score through the phone channel, or on the corpus as recorded",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=6)
    # Inference only, so no activations are retained for backward and this can be
    # larger than the training batch. Still modest: the card may be busy training.
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    corpus = model_root().parent / "data" / "LA"

    augmenter = (
        PhoneChannelAugmenter(seed=args.seed + 1) if args.channel == "phone" else None
    )
    dataset = AsvspoofLaDataset(
        corpus,
        args.split,
        augmenter=augmenter,
        seed=args.seed,
        limit=args.limit,
        # The channel becomes a property of the utterance rather than of call
        # order, so the figure does not move with --workers.
        deterministic_augmentation=True,
    )
    counts = class_counts(dataset.utterances)
    print(f"split={args.split} channel={args.channel} n={len(dataset)} {counts}", flush=True)

    model = build_model(device, args.variant)
    if args.weights is not None:
        if not args.weights.exists():
            raise SystemExit(f"missing checkpoint: {args.weights}")
        model.load_state_dict(torch.load(args.weights, map_location=device, weights_only=True))
        print(f"weights: {args.weights.name}", flush=True)
    else:
        print(f"weights: released {args.variant}", flush=True)
    model.eval()

    loader = DataLoader(
        dataset, batch_size=args.batch_size, shuffle=False, num_workers=args.workers
    )

    scores: list[float] = []
    labels: list[int] = []
    started = time.perf_counter()
    with torch.no_grad():
        for index, (batch, target) in enumerate(loader, start=1):
            batch = batch.to(device, non_blocking=True)
            _, logits = model(batch)
            # Column 1 is the bonafide score, per the published evaluation code.
            scores.extend(logits[:, 1].cpu().numpy().tolist())
            labels.extend(target.numpy().tolist())
            if index % 100 == 0:
                done = len(scores)
                rate = done / (time.perf_counter() - started)
                print(f"  {done}/{len(dataset)}  {rate:.1f} utt/s", flush=True)

    score_array = np.asarray(scores)
    label_array = np.asarray(labels)

    print(f"\n{'=' * 62}")
    print(f"split={args.split}  channel={args.channel}  workers={args.workers}")
    print(f"weights={args.weights.name if args.weights else 'released ' + args.variant}")
    print("=" * 62)
    print(summarise(score_array, label_array))

    for target_far in (0.01, 0.05, 0.10):
        missed, threshold = false_accept_at_false_reject(score_array, label_array, target_far)
        print(
            f"at {target_far * 100:4.1f}% of genuine callers flagged, "
            f"{missed * 100:5.1f}% of spoofs get through  (threshold {threshold:.4f})"
        )

    eer, _ = compute_eer(score_array, label_array)
    if args.channel == "phone":
        print(
            "\nPhone channel is seeded per utterance index, so this figure is "
            "reproducible across worker counts."
        )
    print(f"\nheadline: EER {eer * 100:.2f}% on {args.split}, n={len(dataset)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
