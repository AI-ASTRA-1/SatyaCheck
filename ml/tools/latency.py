"""Measure per-window latency against the 180 ms stage 04 budget.

    .venv\\Scripts\\python.exe -m ml.tools.latency
    .venv\\Scripts\\python.exe -m ml.tools.latency --device cpu --repeats 20

`AGENTS.md` budgets stage 04 at **under 180 ms** for all four checks in parallel, and
the whole spoken-word-to-warning path at **under 400 ms p90**. Only GPU numbers
existed before this: a 300M-parameter transformer on a CPU is a real risk if the demo
machine has no GPU, so both are measured here and written to a CSV.

Reports the **median and the full range**, never a bare mean. One slow call caused by
another process is not a property of the model, and a mean hides it while a range
shows it.
"""

from __future__ import annotations

import argparse
import csv
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.checks.machine_fingerprint.ssl_aasist import SSL_INPUT_SAMPLES

#: The stage 04 budget from AGENTS.md, for all four checks in parallel.
STAGE_04_BUDGET_MS = 180.0

#: The end-to-end figure the deck quotes, spoken word to warning on screen.
END_TO_END_BUDGET_MS = 400.0

FIELDS = [
    "run_id",
    "device",
    "model",
    "operation",
    "repeats",
    "median_ms",
    "min_ms",
    "max_ms",
    "budget_ms",
    "within_budget",
    "threads",
    "notes",
]


@dataclass(frozen=True)
class Timing:
    device: str
    model: str
    operation: str
    samples: list[float]

    @property
    def median(self) -> float:
        return float(np.median(self.samples))

    @property
    def low(self) -> float:
        return float(np.min(self.samples))

    @property
    def high(self) -> float:
        return float(np.max(self.samples))

    @property
    def within(self) -> bool:
        return self.median <= STAGE_04_BUDGET_MS


def time_calls(fn, repeats: int, device: str) -> list[float]:
    """Run `fn` and return per-call milliseconds, discarding the first.

    The first call after warmup still pays for allocator and kernel caching, so it is
    measured and thrown away rather than folded into the median.
    """
    import torch

    samples: list[float] = []
    for index in range(repeats + 1):
        started = time.perf_counter()
        fn()
        if device == "cuda":
            torch.cuda.synchronize()
        elapsed = (time.perf_counter() - started) * 1000.0
        if index > 0:
            samples.append(elapsed)
    return samples


def _ssl_timings(device: str, repeats: int, pcm: bytes) -> list[Timing]:
    """XLS-R + AASIST. Scoped so the checkpoint is freed before the next model."""
    from ml.checks.machine_fingerprint.ssl_aasist import SslAasistScorer

    scorer = SslAasistScorer(device=device)
    scorer.warmup()
    return [
        Timing(
            device,
            "xlsr-aasist",
            "score",
            time_calls(lambda: scorer.score(pcm, 16000), repeats, device),
        ),
        Timing(
            device,
            "xlsr-aasist",
            "score_and_embed",
            time_calls(lambda: scorer.score_and_embed(pcm, 16000), repeats, device),
        ),
        Timing(
            device,
            "xlsr-aasist",
            "score_then_embed",
            time_calls(
                lambda: (scorer.score(pcm, 16000), scorer.embed(pcm, 16000)),
                repeats,
                device,
            ),
        ),
    ]


def _aasist_timing(
    variant: str, device: str, repeats: int, pcm: bytes
) -> Timing | None:
    """AASIST alone, the lightweight comparison AGENTS.md names as the CPU path."""
    from ml.checks.machine_fingerprint.aasist_scorer import AasistScorer

    try:
        scorer = AasistScorer(variant, device=device)
        scorer.warmup()
    except Exception as error:  # noqa: BLE001 - a missing checkpoint is not fatal here
        print(f"  {variant} unavailable: {type(error).__name__}", file=sys.stderr)
        return None
    return Timing(
        device,
        variant,
        "score",
        time_calls(lambda: scorer.score(pcm, 16000), repeats, device),
    )


def measure(device: str, repeats: int) -> list[Timing]:
    window = np.random.default_rng(0).normal(0.0, 0.1, SSL_INPUT_SAMPLES)
    pcm = (np.clip(window, -1, 1) * 32767).astype("<i2").tobytes()

    timings = _ssl_timings(device, repeats, pcm)
    for variant in ("AASIST", "AASIST-L"):
        timing = _aasist_timing(variant, device, repeats, pcm)
        if timing is not None:
            timings.append(timing)
    return timings


def write(timings: list[Timing], path: Path, threads: int, note: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for timing in sorted(timings, key=lambda t: (t.device, t.model, t.operation)):
            writer.writerow(
                {
                    "run_id": "latency",
                    "device": timing.device,
                    "model": timing.model,
                    "operation": timing.operation,
                    "repeats": len(timing.samples),
                    "median_ms": f"{timing.median:.3f}",
                    "min_ms": f"{timing.low:.3f}",
                    "max_ms": f"{timing.high:.3f}",
                    "budget_ms": f"{STAGE_04_BUDGET_MS:.1f}",
                    "within_budget": "yes" if timing.within else "NO",
                    "threads": threads,
                    "notes": note,
                }
            )
    return path


def main(argv: list[str] | None = None) -> int:
    import torch

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", action="append", default=None, choices=["cpu", "cuda"])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("data/results/latency.csv"))
    args = parser.parse_args(argv)

    devices = args.device or (["cuda", "cpu"] if torch.cuda.is_available() else ["cpu"])
    threads = torch.get_num_threads()
    note = f"{platform.processor() or platform.machine()}, torch {torch.__version__}"
    if "cuda" in devices:
        note += f", {torch.cuda.get_device_name(0)}"

    print(f"budget   {STAGE_04_BUDGET_MS:.0f} ms per window, stage 04, AGENTS.md")
    print(f"threads  {threads}")
    print(f"machine  {note}\n")

    timings: list[Timing] = []
    for device in devices:
        print(f"measuring on {device}", file=sys.stderr)
        timings += measure(device, args.repeats)

    header = (
        f"{'device':<6} {'model':<12} {'operation':<18} {'median':>9} "
        f"{'min':>8} {'max':>8}  verdict"
    )
    print(header)
    print("-" * len(header))
    for timing in timings:
        verdict = (
            "within 180 ms"
            if timing.within
            else f"OVER by {timing.median / STAGE_04_BUDGET_MS:.1f}x"
        )
        print(
            f"{timing.device:<6} {timing.model:<12} {timing.operation:<18} "
            f"{timing.median:>7.1f}ms {timing.low:>7.1f} {timing.high:>7.1f}  {verdict}"
        )

    write(timings, args.out, threads, note)
    print(f"\nwrote {args.out}")
    print(
        "\nMedian and range, never a bare mean: one slow call caused by another\n"
        "process is not a property of the model, and a mean hides it."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
