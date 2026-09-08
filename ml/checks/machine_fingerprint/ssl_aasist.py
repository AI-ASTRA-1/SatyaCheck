"""XLS-R + AASIST as a SyntheticScorer, running on Python 3.13 without fairseq.

This is the architecture the deck and AGENTS.md describe for check 1, and the
published fine-tuned checkpoint behind the lab EER figure (Tak et al., Odyssey 2022,
arXiv:2202.12233). Its reference implementation loads XLS-R through fairseq, which
does not support Python 3.13, so the front end is swapped for an equivalent
HuggingFace Wav2Vec2Model carrying the same fine-tuned weights.

How the weights get across, and why this is not guesswork: the repository holds both
the original fairseq `xlsr2_300m.pt` and HuggingFace's converted
`facebook/wav2vec2-xls-r-300m`, which are the same weights under different names.
Matching them tensor by tensor yields an exact key mapping, checked in beside the
weights as `fairseq_to_hf.json` (429 of 429 mapped, none transposed). The mapping is
then replayed onto the fine-tuned checkpoint.

Status: behaviourally sound, not formally verified. Proving equivalence needs the
published pipeline run under Python 3.7 with fairseq to produce reference scores.
Until that comparison exists, describe this as "matches the published architecture",
never as "reproduces the published number".
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import types
from pathlib import Path
from typing import Any

import numpy as np

from ml.paths import require

#: 64600 samples at 16 kHz, 4.0375 s. Fixed by the published model, not by us.
SSL_INPUT_SAMPLES = 64600

#: Index of the spoof class in the two-class output, matching the published
#: evaluation code, which reads column 1 as the bonafide score.
SPOOF_CLASS_INDEX = 0

#: HuggingFace publishes XLS-R under a pretraining wrapper, so its keys carry this
#: prefix. Wav2Vec2Model itself expects them without it.
_HF_WRAPPER_PREFIX = "wav2vec2."

#: Pretraining-only heads present in the checkpoint and absent from Wav2Vec2Model.
#: Discarding them is correct, not a loss.
_PRETRAINING_ONLY = ("quantizer.", "project_q.", "project_hid.")


def _load_published_architecture(directory: Path) -> Any:
    """Import the published model.py with fairseq stubbed out.

    The module imports fairseq at import time and only uses it inside SSLModel,
    which we replace before instantiating anything. The stub raises if that
    replacement is ever missed, so a silent fallback is impossible.
    """
    source = directory / "model.py"
    if not source.exists():
        raise FileNotFoundError(f"missing published model definition: {source}")

    module_name = "satyacheck_external_ssl_aasist"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("fairseq is stubbed; SSLModel must be replaced before use")

    if "fairseq" not in sys.modules:
        stub: Any = types.ModuleType("fairseq")
        stub.checkpoint_utils = types.SimpleNamespace(
            load_model_ensemble_and_task=_refuse
        )
        sys.modules["fairseq"] = stub

    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load a module spec from {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _tile_pad(samples: np.ndarray, target: int) -> np.ndarray:
    """Repeat up to `target` samples, or truncate. Matches the published `pad`."""
    length = samples.shape[0]
    if length == 0:
        raise ValueError("empty audio window")
    if length >= target:
        return samples[:target]
    repeats = target // length + 1
    return np.tile(samples, repeats)[:target]


class SslAasistScorer:
    """SyntheticScorer backed by XLS-R + AASIST. Loads lazily, on first use."""

    def __init__(self, *, device: str | None = None, normalize_input: bool = True) -> None:
        self._requested_device = device
        self._normalize_input = normalize_input
        self._model: Any = None
        self._torch: Any = None
        self._device: Any = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return "xlsr-aasist"

    @property
    def model_version(self) -> str:
        # Names the checkpoint and the fact that this is the ported front end, so a
        # score is always traceable to the weights and the path that produced it.
        return "tak2022-LA-for-DF-hfport"

    def _build_frontend(self, finetuned: dict[str, Any]) -> Any:
        from transformers import Wav2Vec2Config, Wav2Vec2Model

        mapping = json.loads(
            require("ssl_aasist", "fairseq_to_hf.json").read_text(encoding="utf-8")
        )
        config_dir = require("wav2vec2-xls-r-300m")
        encoder = Wav2Vec2Model(Wav2Vec2Config.from_pretrained(config_dir))

        prefix = "ssl_model.model."
        state: dict[str, Any] = {}
        unmapped: list[str] = []
        for key, value in finetuned.items():
            if not key.startswith(prefix):
                continue
            hf_key = mapping.get(key[len(prefix) :])
            if hf_key is None:
                unmapped.append(key)
                continue
            hf_key = hf_key.removeprefix(_HF_WRAPPER_PREFIX)
            if hf_key.startswith(_PRETRAINING_ONLY):
                continue
            state[hf_key] = value

        if unmapped:
            raise RuntimeError(
                f"{len(unmapped)} XLS-R tensors have no mapping, e.g. {unmapped[:3]}. "
                "fairseq_to_hf.json does not match this checkpoint."
            )

        report = encoder.load_state_dict(state, strict=False)
        if report.missing_keys:
            # Loading a partially initialised encoder would produce confident
            # nonsense rather than an error, so refuse instead.
            raise RuntimeError(
                f"XLS-R front end incomplete: {len(report.missing_keys)} tensors "
                f"missing, e.g. {report.missing_keys[:3]}"
            )
        return encoder

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch
            from torch import nn

            ssl_dir = require("ssl_aasist")
            checkpoint = require("Best_LA_model_for_DF.pth")

            raw = torch.load(checkpoint, map_location="cpu", weights_only=True)
            finetuned = {
                key.removeprefix("module."): value
                for key, value in raw.items()
            }

            encoder = self._build_frontend(finetuned)
            normalize_input = self._normalize_input

            class _HfSslModel(nn.Module):
                """Replacement for the published fairseq-backed SSLModel."""

                def __init__(self, _device: Any = None) -> None:
                    super().__init__()
                    self.model = encoder
                    self.out_dim = 1024

                def extract_feat(self, input_data: Any) -> Any:
                    x = input_data[:, :, 0] if input_data.ndim == 3 else input_data
                    if normalize_input:
                        # XLS-R uses a layer-norm feature extractor and was
                        # pretrained on zero-mean unit-variance waveforms. Skipping
                        # this makes the score track input loudness instead of
                        # content, which is measurable and severe.
                        x = (x - x.mean(dim=-1, keepdim=True)) / (
                            x.std(dim=-1, keepdim=True) + 1e-7
                        )
                    return self.model(x).last_hidden_state

            published = _load_published_architecture(ssl_dir)
            published.SSLModel = _HfSslModel
            model = published.Model(args=None, device="cpu")

            head = {k: v for k, v in finetuned.items() if not k.startswith("ssl_model.")}
            report = model.load_state_dict(head, strict=False)
            head_missing = [
                k for k in report.missing_keys if not k.startswith("ssl_model.")
            ]
            if head_missing or report.unexpected_keys:
                raise RuntimeError(
                    f"AASIST head mismatch: {len(head_missing)} missing, "
                    f"{len(report.unexpected_keys)} unexpected"
                )

            if self._requested_device is not None:
                device = torch.device(self._requested_device)
            else:
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

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
        self.score(b"\x00\x00" * SSL_INPUT_SAMPLES, 16000)

    def embed(self, pcm_s16le: bytes, sample_rate: int) -> np.ndarray:
        """Mean-pooled XLS-R features for one window, 1024 dimensions.

        Read-only, and deliberately not part of `SyntheticScorer`. It exists for the
        confidence estimator, which needs to ask how far a window sits from the data
        the model was fine-tuned on. Uses the identical preprocessing `score` uses,
        so a distance and a score always describe the same window.
        """
        self._ensure_loaded()
        torch = self._torch

        samples = np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
        padded = _tile_pad(samples, SSL_INPUT_SAMPLES)
        tensor = torch.from_numpy(padded).unsqueeze(0).to(self._device)
        with torch.no_grad():
            features = self._model.ssl_model.extract_feat(tensor)
        return features.mean(dim=1).squeeze(0).cpu().numpy().astype(np.float32)

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        """Probability in [0, 1] that this window is machine generated."""
        if sample_rate != 16000:
            raise ValueError(f"XLS-R expects 16000 Hz, got {sample_rate}")

        self._ensure_loaded()
        torch = self._torch

        samples = np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
        padded = _tile_pad(samples, SSL_INPUT_SAMPLES)

        tensor = torch.from_numpy(padded).unsqueeze(0).to(self._device)
        with torch.no_grad():
            output = self._model(tensor)
            logits = output[1] if isinstance(output, tuple) else output
            probabilities = torch.softmax(logits, dim=1)
        return float(probabilities[0, SPOOF_CLASS_INDEX].item())
