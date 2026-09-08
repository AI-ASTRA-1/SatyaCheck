"""Stage the model files another machine needs, and verify they arrived intact.

    .venv\\Scripts\\python.exe -m ml.tools.handoff stage D:\\satyacheck_models
    .venv\\Scripts\\python.exe -m ml.tools.handoff verify D:\\satyacheck_models

**1.2 GB in five files, not 6.45 GB in six.** The model directory holds 6.45 GB, and
most of it is not needed to score audio:

  * `wav2vec2-xls-r-300m/pytorch_model.bin`, 1.2 GB, is **not** loaded. Only
    `config.json` is, to build an empty `Wav2Vec2Model`; every weight comes from the
    fine-tuned checkpoint. Verified by loading with the file absent.
  * `fairseq/xlsr2_300m.pt`, 3.6 GB, was used once to derive `fairseq_to_hf.json`.
    That mapping is checked in beside the weights and the source is never read again.
  * `faster-whisper-small/` and `spkrec-ecapa-voxceleb/` belong to checks that are
    still docstrings.

`--with-aasist` adds the 3.4 MB AASIST directory, which is the only model measured
inside the 180 ms stage 04 budget on a CPU. Worth taking if the target machine has no
GPU; see `data/results/latency.csv`.

The manifest records a SHA256 per file plus the score of a fixed synthetic window, so
`verify` proves both that the bytes arrived and that the two machines agree
numerically. Different scores on identical bytes means the environments differ, which
is a thing to fix before integration rather than during it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

from ml.paths import ENV_VAR, model_root

#: Everything needed to score audio with xlsr-aasist, relative to the model root.
REQUIRED = (
    "Best_LA_model_for_DF.pth",
    "confidence_reference.npz",
    "ssl_aasist/model.py",
    "ssl_aasist/fairseq_to_hf.json",
    "wav2vec2-xls-r-300m/config.json",
)

#: The CPU fallback. AASIST-L is the only model measured inside the 180 ms budget
#: without a GPU, and it discriminates worse; see ml/README.md before relying on it.
OPTIONAL_AASIST = ("aasist",)

MANIFEST = "MANIFEST.json"

#: The window `verify` scores on both machines. Generated from a seed rather than
#: shipped, so no audio travels with the bundle.
PROBE_SEED = 20260908
PROBE_SAMPLES = 64600


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_window() -> np.ndarray:
    return np.random.default_rng(PROBE_SEED).normal(0.0, 0.1, PROBE_SAMPLES).astype(
        np.float32
    )


def probe_score(model_dir: Path) -> float:
    """Score the fixed probe window with the model at `model_dir`.

    Runs in a subprocess with `SATYACHECK_MODEL_DIR` set, because the scorer caches
    its checkpoint at module level and staging then verifying in one process would
    measure the source directory twice.
    """
    import os
    import subprocess

    script = (
        "import numpy as np;"
        "from ml.tools.handoff import probe_window;"
        "from ml.checks.machine_fingerprint.api import score_window;"
        "print(score_window(probe_window())['p_synthetic'])"
    )
    environment = {**os.environ, ENV_VAR: str(model_dir)}
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        cwd=Path(__file__).resolve().parents[2],
    )
    if result.returncode != 0:
        raise RuntimeError(f"scoring failed under {model_dir}: {result.stderr[-500:]}")
    return float(result.stdout.strip().splitlines()[-1])


def files_for(with_aasist: bool, root: Path) -> list[str]:
    names = list(REQUIRED)
    if with_aasist:
        for directory in OPTIONAL_AASIST:
            base = root / directory
            names += [
                str(item.relative_to(root)).replace("\\", "/")
                for item in sorted(base.rglob("*"))
                if item.is_file()
                and ".git" not in item.parts
                and "__pycache__" not in item.parts
            ]
    return names


def stage(target: Path, with_aasist: bool) -> int:
    root = model_root()
    names = files_for(with_aasist, root)

    missing = [n for n in names if not (root / n).exists()]
    if missing:
        print(f"missing from {root}:")
        for name in missing:
            print(f"  {name}")
        if "confidence_reference.npz" in missing:
            print("\nBuild it with: python -m ml.tools.fit_confidence")
        return 1

    target.mkdir(parents=True, exist_ok=True)
    entries, total = {}, 0
    for name in names:
        source = root / name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        size = destination.stat().st_size
        total += size
        entries[name] = {"sha256": sha256(destination), "bytes": size}
        print(f"  {name:<44} {size / 1e6:>9.1f} MB")

    score = probe_score(target)
    (target / MANIFEST).write_text(
        json.dumps(
            {
                "files": entries,
                "probe": {
                    "seed": PROBE_SEED,
                    "samples": PROBE_SAMPLES,
                    "p_synthetic": f"{score:.6f}",
                },
                "env_var": ENV_VAR,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\nstaged {len(names)} files, {total / 1e9:.2f} GB, to {target}")
    print(f"probe p_synthetic {score:.6f}, recorded in {MANIFEST}")
    print("\nOn the receiving machine:")
    print(f"  set {ENV_VAR}=<where you put this>")
    print("  .venv\\Scripts\\python.exe -m ml.tools.handoff verify <where you put this>")
    return 0


def verify(target: Path) -> int:
    manifest_path = target / MANIFEST
    if not manifest_path.exists():
        print(f"no {MANIFEST} in {target}. Was this staged with `handoff stage`?")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    problems = []
    for name, entry in manifest["files"].items():
        path = target / name
        if not path.exists():
            problems.append(f"{name}: missing")
            print(f"  {name:<44} MISSING")
            continue
        digest = sha256(path)
        ok = digest == entry["sha256"]
        if not ok:
            problems.append(f"{name}: sha256 {digest[:12]} expected {entry['sha256'][:12]}")
        print(f"  {name:<44} {'ok' if ok else 'CORRUPT'}")

    if problems:
        print("\nthe transfer is not intact:")
        for problem in problems:
            print(f"  {problem}")
        print("\nCopy it again. Do not integrate against these files.")
        return 1

    expected = float(manifest["probe"]["p_synthetic"])
    actual = probe_score(target)
    agrees = abs(actual - expected) < 5e-5
    print(f"\nprobe p_synthetic  here {actual:.6f}  staged {expected:.6f}")
    if not agrees:
        print(
            "\nThe bytes match and the scores do not, so the two environments differ,\n"
            "not the model. Check torch, transformers and numpy versions before\n"
            "integrating; a difference here becomes an unexplainable difference later."
        )
        return 1
    print("agrees to four decimal places. Same bytes, same numbers.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["stage", "verify"])
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--with-aasist",
        action="store_true",
        help="add the 3.4 MB AASIST directory, the only CPU model inside the budget",
    )
    args = parser.parse_args(argv)

    if args.action == "stage":
        return stage(args.target, args.with_aasist)
    return verify(args.target)


if __name__ == "__main__":
    sys.exit(main())
