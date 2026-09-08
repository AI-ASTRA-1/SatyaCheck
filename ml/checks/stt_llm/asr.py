"""Local speech-to-text for the script channel. faster-whisper small, offline.

The transcript this produces is a working artifact of the check only. It is a
local variable in `SttLlmCheck.run`, handed to `analyze()`, and dropped when
`run()` returns. It is never put on an EvidenceItem, a CheckResult, a RiskUpdate,
an AlertRecord, or a log line. No transcript at rest.

The model plugs in behind `Transcriber`, the same seam pattern as
`SyntheticScorer` in machine_fingerprint. Weights load from the local model
directory (`ml.paths`) with `local_files_only`; audio is never streamed to an
external API.
"""

from __future__ import annotations

import threading
from typing import Protocol

import numpy as np

from ml.paths import require

#: The only sample rate below stage 02 (contracts.pipeline.CANONICAL_SAMPLE_RATE).
_EXPECTED_SAMPLE_RATE = 16000

#: faster-whisper model size. `small` is 3-4x faster than the HF pipeline on the
#: same weights, which matters on a rolling buffer; the WER cost is small.
_MODEL_SIZE = "small"


class Transcriber(Protocol):
    """Turns one window of canonical PCM into text. The seam STT plugs into."""

    @property
    def model_name(self) -> str:
        """Short, non-PII model identifier, recorded on the check's evidence."""
        ...

    @property
    def model_version(self) -> str:
        """Revision identifier, so a result traces back to the weights."""
        ...

    def warmup(self) -> None:
        """Load the model and run it once, before the first real call.

        Loading is lazy and costs seconds; a windowed transcription costs far
        less. Whoever constructs the check calls this at startup.
        """
        ...

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        """Return the recognised text for this window.

        `pcm_s16le` is mono little-endian signed 16-bit PCM at `sample_rate`, a
        COPY that must not be mutated. Raise on any model failure; the check turns
        that into CheckStatus.FAILED with no signal, never a verdict.
        """
        ...


class FasterWhisperTranscriber:
    """Transcriber backed by faster-whisper small. Loads lazily, on first use.

    English is pinned: auto-detect flips language mid-call on Hinglish
    code-switching and each flip changes transcript style. Greedy decoding
    (`beam_size=1`) for speed. `condition_on_previous_text` is off because it
    makes Whisper hallucinate repeating loops on the short, partial windows this
    check is fed.
    """

    def __init__(self, *, device: str | None = None) -> None:
        self._requested_device = device
        self._model: object | None = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return f"faster-whisper-{_MODEL_SIZE}"

    @property
    def model_version(self) -> str:
        return "ct2-en-greedy-vad"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            model_dir = require(f"faster-whisper-{_MODEL_SIZE}")

            device = self._requested_device
            if device is None:
                try:
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:  # noqa: BLE001 - no torch means CPU
                    device = "cpu"
            compute_type = "float16" if device == "cuda" else "int8"

            self._model = WhisperModel(
                str(model_dir),
                device=device,
                compute_type=compute_type,
                local_files_only=True,
            )

    def warmup(self) -> None:
        self._ensure_loaded()
        self.transcribe(b"\x00\x00" * _EXPECTED_SAMPLE_RATE, _EXPECTED_SAMPLE_RATE)

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        if sample_rate != _EXPECTED_SAMPLE_RATE:
            raise ValueError(
                f"faster-whisper path expects {_EXPECTED_SAMPLE_RATE} Hz, got {sample_rate}"
            )
        self._ensure_loaded()
        assert self._model is not None  # set by _ensure_loaded

        samples = np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(  # type: ignore[attr-defined]
            samples,
            language="en",
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
