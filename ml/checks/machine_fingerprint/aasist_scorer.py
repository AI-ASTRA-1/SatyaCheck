"""AASIST as a SyntheticScorer. Pure PyTorch, no fairseq, runs on Python 3.13.

The architecture and the weights both come from the clovaai/aasist release in the
model directory, so nothing about the published model is copied into this repo. The
model definition is loaded from that directory by path.

What these weights are: AASIST trained on ASVspoof 2019 LA. They are a starting
point that makes the check runnable today, not the detector we ship. Round 1's own
training runs this architecture through G.711 and AMR-NB compression and noise
first, because a model trained on clean 16 kHz studio audio has not seen the
conditions a phone call arrives in.

Convention taken from the release's own evaluation code: the model returns
(last_hidden, logits) over two classes where index 1 is bonafide and index 0 is
spoof, and it expects 64600 raw samples at 16 kHz, tiled-repeat padded when the
input is shorter.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path
from typing import Any

import numpy as np

from ml.paths import require

#: 64600 samples at 16 kHz is 4.0375 s. Fixed by the architecture, not by us.
AASIST_INPUT_SAMPLES = 64600

#: Index of the spoof class in the model's two-class output.
SPOOF_CLASS_INDEX = 0


def _load_architecture(aasist_dir: Path) -> Any:
    """Import the release's AASIST.py by path and return its Model class."""
    source = aasist_dir / "models" / "AASIST.py"
    if not source.exists():
        raise FileNotFoundError(f"missing AASIST model definition: {source}")
    module_name = "satyacheck_external_aasist"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached.Model
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load a module spec from {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.Model


def _tile_pad(samples: np.ndarray, target: int) -> np.ndarray:
    """Repeat the waveform up to `target` samples, or truncate it.

    Matches the release's own `pad`. Repetition rather than zero padding, because
    zeros are not silence to a model that is looking at spectral detail.
    """
    length = samples.shape[0]
    if length == 0:
        raise ValueError("empty audio window")
    if length >= target:
        return samples[:target]
    repeats = target // length + 1
    return np.tile(samples, repeats)[:target]


class AasistScorer:
    """SyntheticScorer backed by AASIST. Loads lazily, on the first score."""

    def __init__(
        self,
        variant: str = "AASIST",
        *,
        device: str | None = None,
        weights_override: Path | str | None = None,
    ) -> None:
        if variant not in ("AASIST", "AASIST-L"):
            raise ValueError(f"unknown AASIST variant: {variant}")
        self._variant = variant
        self._requested_device = device
        # Points at a fine-tuned checkpoint instead of the released one. The
        # architecture is unchanged, so only the weights differ, and model_version
        # changes with it so a score is never ambiguous about which produced it.
        self._weights_override = Path(weights_override) if weights_override else None
        self._model: Any = None
        self._torch: Any = None
        self._device: Any = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._variant.lower()

    @property
    def model_version(self) -> str:
        # The released checkpoint, trained on ASVspoof 2019 LA. Fine-tuned weights
        # get a different version string, so a score can always be traced back to
        # the weights that produced it.
        if self._weights_override is not None:
            return f"finetuned-{self._weights_override.stem}"
        return f"clovaai-{self._variant}-asvspoof2019la"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch  # imported here so an absent torch is a scoring failure

            aasist_dir = require("aasist")
            config_path = require("aasist", "config", f"{self._variant}.conf")
            if self._weights_override is not None:
                weights_path = self._weights_override
                if not weights_path.exists():
                    raise FileNotFoundError(f"missing weights: {weights_path}")
            else:
                weights_path = require(
                    "aasist", "models", "weights", f"{self._variant}.pth"
                )

            model_config = json.loads(config_path.read_text(encoding="utf-8"))[
                "model_config"
            ]
            architecture = _load_architecture(aasist_dir)

            if self._requested_device is not None:
                device = torch.device(self._requested_device)
            else:
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            model = architecture(model_config)
            state = torch.load(weights_path, map_location=device, weights_only=True)
            model.load_state_dict(state)
            model.to(device)
            model.eval()

            self._torch = torch
            self._device = device
            self._model = model

    def warmup(self) -> None:
        """Load and run once, so the first real call does not pay for it.

        Loading is lazy and costs seconds; a scored window costs milliseconds. The
        stage 04 budget is 180 ms, so the first scoring tick of a call would blow it
        unless something calls this at startup.
        """
        self._ensure_loaded()
        self.score(b"\x00\x00" * AASIST_INPUT_SAMPLES, 16000)

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        """Probability in [0, 1] that this window is machine generated."""
        if sample_rate != 16000:
            raise ValueError(f"AASIST expects 16000 Hz, got {sample_rate}")

        self._ensure_loaded()
        torch = self._torch

        # frombuffer gives a read-only view over the caller's bytes. The batch is a
        # COPY that checks must not mutate, and nothing here writes to it.
        samples = np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
        padded = _tile_pad(samples, AASIST_INPUT_SAMPLES)

        tensor = torch.from_numpy(padded).unsqueeze(0).to(self._device)
        with torch.no_grad():
            _, logits = self._model(tensor)
            probabilities = torch.softmax(logits, dim=1)
        return float(probabilities[0, SPOOF_CLASS_INDEX].item())
