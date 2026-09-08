"""Fine-tune AASIST on ASVspoof 2019 LA through the phone channel.

    .venv\\Scripts\\python.exe -m ml.train.finetune_aasist --epochs 3

Starts from the clovaai pretrained weights rather than from scratch, because the
architecture already knows what synthetic speech looks like in clean studio audio.
What it does not know is that a phone changes the signal, and that is what the
augmentation teaches it.

Why AASIST rather than XLS-R + AASIST: 85K parameters against 300M. It trains in
hours on one laptop GPU instead of days, and `AGENTS.md` records that AASIST-L runs
on CPU. The XLS-R path stays available for comparison.

Reports EER on dev after every epoch. EER alone is not a sufficient metric per
`AGENTS.md`, and `ml/eval/` adds the cost-weighted companion; this loop reports EER
because that is what selects a checkpoint during training.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from ml.checks.machine_fingerprint.aasist_scorer import _load_architecture
from ml.eval.eer import compute_eer
from ml.paths import model_root, require
from ml.train.dataset import (
    AsvspoofLaDataset,
    PhoneChannelAugmenter,
    class_counts,
)


def build_model(device, variant: str = "AASIST"):
    import torch

    aasist_dir = require("aasist")
    config = json.loads(
        (aasist_dir / "config" / f"{variant}.conf").read_text(encoding="utf-8")
    )["model_config"]
    architecture = _load_architecture(aasist_dir)
    model = architecture(config)

    weights = aasist_dir / "models" / "weights" / f"{variant}.pth"
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    return model.to(device)


def evaluate(model, loader, device) -> tuple[float, float]:
    import torch

    model.eval()
    scores: list[float] = []
    labels: list[int] = []
    with torch.no_grad():
        for batch, target in loader:
            batch = batch.to(device, non_blocking=True)
            _, logits = model(batch)
            # Column 1 is the bonafide score, per the published evaluation code.
            scores.extend(logits[:, 1].detach().cpu().numpy().tolist())
            labels.extend(target.numpy().tolist())
    return compute_eer(np.asarray(scores), np.asarray(labels))


def main(argv: list[str] | None = None) -> int:
    import torch
    from torch.utils.data import DataLoader

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epochs", type=int, default=3)
    # Batch 8, and this is measured, not a guess. On an 8 GB card AASIST peaks at
    # 3.57 GB at batch 8, 7.11 GB at 16 and 14.20 GB at 32. Past batch 8 it is
    # already spilling, and throughput collapses rather than degrading gracefully:
    # 24.3 utterances/s at batch 8, 8.8 at 16, 1.0 at 32. Raise it only on a card
    # with more memory, and re-measure when you do.
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--variant", default="AASIST", choices=["AASIST", "AASIST-L"])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--train-limit", type=int, default=None, help="subsample train, for a smoke run"
    )
    parser.add_argument(
        "--dev-limit", type=int, default=4000, help="subsample dev for per-epoch EER"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--init-weights",
        type=Path,
        default=None,
        help="warm start from a previous fine-tune instead of the released weights",
    )
    parser.add_argument(
        "--no-amp",
        action="store_true",
        help="disable mixed precision (slower, more memory, occasionally more stable)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="checkpoint directory (default: <model root>/finetuned)",
    )
    args = parser.parse_args(argv)

    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    corpus = model_root().parent / "data" / "LA"
    out_dir = args.out or (model_root() / "finetuned")
    out_dir.mkdir(parents=True, exist_ok=True)

    augmenter = PhoneChannelAugmenter(seed=args.seed)
    train_set = AsvspoofLaDataset(
        corpus, "train", augmenter=augmenter, seed=args.seed, limit=args.train_limit
    )
    # Dev is scored through the same channel, otherwise the number says how well the
    # model does on studio audio, which is not the question.
    dev_set = AsvspoofLaDataset(
        corpus,
        "dev",
        augmenter=PhoneChannelAugmenter(seed=args.seed + 1),
        seed=args.seed,
        limit=args.dev_limit,
    )

    print(f"device: {device}", flush=True)
    print(f"train: {len(train_set)} {class_counts(train_set.utterances)}", flush=True)
    print(f"dev:   {len(dev_set)} {class_counts(dev_set.utterances)}", flush=True)

    train_loader = DataLoader(
        train_set,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.workers,
        drop_last=True,
        persistent_workers=args.workers > 0,
    )
    dev_loader = DataLoader(
        dev_set, batch_size=args.batch_size, shuffle=False, num_workers=args.workers
    )

    model = build_model(device, args.variant)
    if args.init_weights is not None:
        if not args.init_weights.exists():
            raise SystemExit(f"missing init weights: {args.init_weights}")
        model.load_state_dict(
            torch.load(args.init_weights, map_location=device, weights_only=True)
        )
        print(f"warm start from {args.init_weights.name}", flush=True)

    # ASVspoof LA is roughly 1:9 bonafide to spoof. Without the weighting the model
    # can score well by calling everything spoof, which is exactly the failure mode
    # already observed in the pretrained checkpoints.
    counts = class_counts(train_set.utterances)
    weight = torch.tensor(
        [1.0, counts["spoof"] / max(counts["bonafide"], 1)], dtype=torch.float32
    ).to(device)
    criterion = torch.nn.CrossEntropyLoss(weight=weight)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)

    use_amp = (not args.no_amp) and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    print(f"mixed precision: {use_amp}", flush=True)

    baseline_eer, _ = evaluate(model, dev_loader, device)
    print(f"before training: dev EER {baseline_eer * 100:.2f}%")

    best = baseline_eer
    for epoch in range(1, args.epochs + 1):
        model.train()
        started = time.perf_counter()
        running = 0.0
        seen = 0
        for step, (batch, target) in enumerate(train_loader, start=1):
            batch = batch.to(device, non_blocking=True)
            target = target.to(device, non_blocking=True)

            optimiser.zero_grad(set_to_none=True)
            with torch.autocast("cuda", dtype=torch.float16, enabled=use_amp):
                _, logits = model(batch)
                loss = criterion(logits, target)

            if use_amp:
                scaler.scale(loss).backward()
                scaler.step(optimiser)
                scaler.update()
            else:
                loss.backward()
                optimiser.step()

            running += float(loss.item()) * batch.size(0)
            seen += batch.size(0)
            if step % 50 == 0:
                rate = seen / (time.perf_counter() - started)
                print(
                    f"  epoch {epoch} step {step}/{len(train_loader)} "
                    f"loss {running / seen:.4f}  {rate:.1f} utt/s",
                    flush=True,
                )

        eer, threshold = evaluate(model, dev_loader, device)
        elapsed = time.perf_counter() - started
        print(
            f"epoch {epoch}: loss {running / max(seen, 1):.4f}  "
            f"dev EER {eer * 100:.2f}%  threshold {threshold:.3f}  {elapsed / 60:.1f} min"
        )

        torch.save(model.state_dict(), out_dir / f"{args.variant}_phone_epoch{epoch}.pth")
        if eer < best:
            best = eer
            torch.save(model.state_dict(), out_dir / f"{args.variant}_phone_best.pth")
            print(f"  new best, saved {args.variant}_phone_best.pth")

    print(f"\nbest dev EER {best * 100:.2f}% (baseline {baseline_eer * 100:.2f}%)")
    print(f"checkpoints in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
