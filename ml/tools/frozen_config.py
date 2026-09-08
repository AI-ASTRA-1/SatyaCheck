"""Read the frozen diagnosis config out of the running code.

    .venv\\Scripts\\python.exe -m ml.tools.frozen_config
    .venv\\Scripts\\python.exe -m ml.tools.frozen_config --hash

This exists so `FROZEN.md` is transcribed from the code rather than from memory, and
so every later run can confirm the config has not moved underneath it. The values it
prints are the ones `ml/tests/test_frozen_config.py` asserts against `FROZEN.md`.

`--hash` adds the checkpoint SHA256. It is off by default because the checkpoint is
1.2 GB and hashing it takes several seconds, which is not worth paying on every call.

Deliberately does not load the model. Every value here is a constant or a path, so
reading them must not need a GPU, a warm checkpoint, or 20 seconds.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from ml.checks.machine_fingerprint import check as check_module
from ml.checks.machine_fingerprint import ssl_aasist
from ml.eval import activity
from ml.paths import require

#: The checkpoint this config is frozen on. Not the fine-tuned AASIST ones under
#: `finetuned/` and `finetuned_room/`; see FROZEN.md for why.
CHECKPOINT = "Best_LA_model_for_DF.pth"

SAMPLE_RATE = 16000

#: The ffmpeg invocation every audio file goes through before the model sees it.
#: Written out rather than assembled, because a changed flag here silently changes
#: every number downstream.
FFMPEG_ARGS = ("-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16")


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def collect(*, with_hash: bool = False) -> dict[str, str]:
    """Every frozen field, read from the modules that define it."""
    window = ssl_aasist.SSL_INPUT_SAMPLES
    checkpoint = require(CHECKPOINT)
    fields = {
        "checkpoint_path": str(checkpoint),
        "checkpoint_bytes": str(checkpoint.stat().st_size),
        "model_id": "xlsr-aasist",
        "model_version": ssl_aasist.SslAasistScorer().model_version,
        "input_sample_rate": str(SAMPLE_RATE),
        "resample_method": "ffmpeg " + " ".join(FFMPEG_ARGS),
        "vad_implementation": "ml/eval/activity.py",
        "vad_frame_ms": str(activity.FRAME_SAMPLES / SAMPLE_RATE * 1000),
        "vad_gate_fraction": str(activity.GATE_FRACTION),
        "vad_activity_floor": str(activity.ACTIVITY_FLOOR),
        "window_samples": str(window),
        "window_s": str(window / SAMPLE_RATE),
        "hop_s": str(window / SAMPLE_RATE),
        "sparse_hop_s": str(window // 4 / SAMPLE_RATE),
        "spoof_class_index": str(ssl_aasist.SPOOF_CLASS_INDEX),
        "normalize_input": "True",
        "min_window_ms": str(check_module.DEFAULT_MIN_WINDOW_MS),
        "degraded_window_ms": str(check_module.DEFAULT_DEGRADED_WINDOW_MS),
        "threshold": str(check_module.DEFAULT_EVIDENCE_THRESHOLD),
        "torch_version": _torch_version(),
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "frozen_commit": _git_head(),
    }
    if with_hash:
        fields["checkpoint_sha256"] = sha256(checkpoint)
    return fields


def _torch_version() -> str:
    import torch

    return str(torch.__version__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--hash",
        action="store_true",
        help="also hash the 1.2 GB checkpoint (several seconds)",
    )
    args = parser.parse_args(argv)

    fields = collect(with_hash=args.hash)
    width = max(len(k) for k in fields)
    for key, value in fields.items():
        print(f"{key:<{width}} : {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
