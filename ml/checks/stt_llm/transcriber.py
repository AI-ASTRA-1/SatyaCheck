"""Speech to text for check 4. Owner: ML lead B.

faster-whisper (CTranslate2) rather than the transformers Whisper port, because
it runs several times faster on the same GPU and check 4 already pays a language
model round trip after this step.

The transcript this produces is a working artifact and nothing else. It is
handed to a `ScriptScorer`, turned into a number and a category, and dropped.
`contracts/checks.py` requires it never reach `EvidenceItem`, `CheckResult`,
`RiskUpdate` or `AlertRecord`, and nothing here writes it anywhere.

Multilingual by design: Indian calls switch between Hindi, English and a
regional language mid-sentence, so `language=None` lets Whisper detect per
window rather than forcing English and producing confident nonsense.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("satyacheck.stt_llm.transcriber")

#: int16 full scale. PCM arrives as s16le and Whisper wants float32 in [-1, 1).
_INT16_FULL_SCALE = 32768.0

#: Whisper resamples internally, but it expects 16 kHz and everything upstream
#: of this check is already canonical 16 kHz mono.
EXPECTED_SAMPLE_RATE = 16000


_cuda_dlls_added = False


def _ensure_cuda_dlls_visible() -> None:
    """Put torch's bundled CUDA DLLs on the search path CTranslate2 uses.

    faster-whisper runs on CTranslate2, which loads `cublas64_12.dll` and
    `cudnn64_9.dll` by name. On Windows those are not installed system-wide
    here: they ship inside `torch/lib`, and nothing adds that directory to the
    DLL search path, so CT2 raises "Library cublas64_12.dll is not found" on a
    machine that plainly has a working CUDA torch.

    Idempotent, Windows-only in effect, and non-fatal: if torch is missing or
    the directory cannot be added, the caller falls back to the CPU device,
    which needs none of these.
    """
    global _cuda_dlls_added
    if _cuda_dlls_added:
        return
    _cuda_dlls_added = True

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:  # not Windows
        return
    try:
        import torch

        lib = Path(torch.__file__).parent / "lib"
        if lib.is_dir():
            add_dll_directory(str(lib))
            logger.debug("added %s to the DLL search path for CTranslate2", lib)
    except Exception as exc:  # noqa: BLE001 - CPU still works without this
        logger.debug("could not add torch CUDA DLLs to the search path: %s", exc)


class Transcriber(Protocol):
    model_name: str

    def warmup(self) -> None: ...

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str: ...


class FasterWhisperTranscriber:
    """faster-whisper behind the `Transcriber` protocol.

    Device and compute type are resolved once. On a GPU this runs float16; on a
    CPU it drops to int8, which is the only way a CPU transcript lands in a
    useful time, and it is a quality reduction rather than a like-for-like swap.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
        beam_size: int = 1,
    ) -> None:
        self._model_size = model_size
        self._language = language
        self._beam_size = beam_size
        self._device = device or self._default_device()
        self._compute_type = compute_type or ("float16" if self._device == "cuda" else "int8")
        self.model_name = f"faster-whisper-{model_size}"
        self._model = None

    @staticmethod
    def _default_device() -> str:
        try:
            import ctranslate2

            return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:  # noqa: BLE001 - any probe failure means assume CPU
            return "cpu"

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        if self._device == "cuda":
            _ensure_cuda_dlls_visible()
        from faster_whisper import WhisperModel

        logger.info(
            "loading %s on %s (%s)", self.model_name, self._device, self._compute_type
        )
        self._model = WhisperModel(
            self._model_size, device=self._device, compute_type=self._compute_type
        )

    def warmup(self) -> None:
        """Load the weights now. A cold first call costs seconds."""
        self._ensure_model()
        self.transcribe(b"\x00\x00" * EXPECTED_SAMPLE_RATE, EXPECTED_SAMPLE_RATE)

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        if sample_rate != EXPECTED_SAMPLE_RATE:
            raise ValueError(
                f"expected {EXPECTED_SAMPLE_RATE} Hz canonical audio, got {sample_rate}"
            )
        self._ensure_model()

        import numpy as np

        audio = np.frombuffer(pcm_s16le, dtype=np.int16).astype(np.float32) / _INT16_FULL_SCALE
        assert self._model is not None
        segments, _info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=self._beam_size,
            # Whisper hallucinates fluent sentences on silence and on channel
            # noise. On a phone call that would invent a scam script out of hold
            # music, so gate on speech before decoding.
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
