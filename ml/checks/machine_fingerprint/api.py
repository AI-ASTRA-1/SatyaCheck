"""The entire ML surface the product team sees. One function.

    from ml.checks.machine_fingerprint.api import score_window, warmup

    warmup()                       # once at startup, loading costs seconds
    result = score_window(pcm)     # a 4 s window of float32 at 16 kHz

Returns three fields and nothing else:

    {"p_synthetic": float | None, "confidence": float, "vad_status": "PASS" | "FAIL"}

**`p_synthetic` is None when no score could be produced, never NaN.** A missing score
and a high score are different facts, and a caller that coerces one into the other has
turned "I could not measure this" into "this is synthetic". Branch on `None`.

**`confidence` is how far the audio sits from what this checkpoint was fine-tuned on**,
1.0 at the centre of that distribution and falling to 0.0 outside it. Measured, on 96
clips with known labels: it separates out-of-domain audio from in-domain with AUC
0.951, and predicts a wrong answer with AUC 0.822. Every group of our own audio, IFD
and the replayed recordings scores below 0.3; held-out ASVspoof averages 0.498.

**It is a graded hint for the risk engine, never a gate.** Nothing should raise or
suppress a warning on `confidence` alone. Read `ml/README.md` before putting either
number in front of a user: on our own recordings this checkpoint does not separate a
real voice clone from genuine speakers, and low confidence is exactly what it reports
there. That is the estimator working, not failing.

**`vad_status` PASS does not mean the audio contains a voice.** The activity gate is
relative to the window's own level, so steady noise passes it. It means a score could
be produced. See the OOD section of `ml/README.md`.
"""

from __future__ import annotations

import threading
from typing import Any, TypedDict

import numpy as np

from ml.checks.machine_fingerprint.ssl_aasist import SSL_INPUT_SAMPLES, SslAasistScorer
from ml.eval import confidence as confidence_module
from ml.eval.activity import VAD_FAIL, VAD_PASS, select_windows

#: The canonical rate below stage 02. Anything else is a caller error, not something
#: to resample here: a second resampling path would silently change every score.
SAMPLE_RATE = 16000

#: Confidence reported when no window could be scored. Zero, because there is no
#: measurement to be confident about.
NO_CONFIDENCE = 0.0

_lock = threading.Lock()
_scorer: SslAasistScorer | None = None
_reference: confidence_module.Reference | None = None


class WindowResult(TypedDict):
    p_synthetic: float | None
    confidence: float
    vad_status: str


def _load() -> tuple[SslAasistScorer, confidence_module.Reference]:
    global _scorer, _reference
    if _scorer is not None and _reference is not None:
        return _scorer, _reference
    with _lock:
        if _scorer is None:
            _scorer = SslAasistScorer()
        if _reference is None:
            path = confidence_module.reference_path()
            if not path.exists():
                raise FileNotFoundError(
                    f"missing the confidence reference at {path}. Build it with:\n"
                    "  .venv\\Scripts\\python.exe -m ml.tools.fit_confidence"
                )
            _reference = confidence_module.Reference.load(path)
    return _scorer, _reference


def warmup() -> None:
    """Load the checkpoint and run once, so the first real call does not pay for it.

    Loading costs seconds and a scored window costs tens of milliseconds. The stage 04
    budget is 180 ms, so the first tick of a call would blow it without this.
    """
    scorer, _ = _load()
    scorer.warmup()
    score_window(np.zeros(SSL_INPUT_SAMPLES, dtype=np.float32))


def score_window(pcm_16k: np.ndarray, sample_rate: int = SAMPLE_RATE) -> WindowResult:
    """Score one window. See the module docstring for what the three fields mean."""
    if sample_rate != SAMPLE_RATE:
        raise ValueError(
            f"expected {SAMPLE_RATE} Hz, got {sample_rate}. Resample at ingestion, "
            "stage 02, so every score comes through one decode path."
        )
    samples = np.asarray(pcm_16k, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        return {
            "p_synthetic": None,
            "confidence": NO_CONFIDENCE,
            "vad_status": VAD_FAIL,
        }

    scorer, reference = _load()
    selection = select_windows(samples, SSL_INPUT_SAMPLES)
    if not selection.windows:
        return {
            "p_synthetic": None,
            "confidence": NO_CONFIDENCE,
            "vad_status": VAD_FAIL,
        }

    scores: list[float] = []
    embeddings: list[np.ndarray] = []
    for window in selection.windows:
        pcm = (np.clip(window, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        scores.append(scorer.score(pcm, SAMPLE_RATE))
        embeddings.append(scorer.embed(pcm, SAMPLE_RATE))

    probability = float(np.mean(scores))
    if not np.isfinite(probability):
        # Cannot happen through a softmax, and if it ever does it must not leave
        # this function as a number.
        return {
            "p_synthetic": None,
            "confidence": NO_CONFIDENCE,
            "vad_status": VAD_FAIL,
        }

    return {
        "p_synthetic": probability,
        "confidence": reference.confidence(np.mean(embeddings, axis=0)),
        "vad_status": VAD_PASS,
    }


def model_identity() -> dict[str, Any]:
    """What produced a score, for evidence and for checking two machines agree."""
    scorer, reference = _load()
    return {
        "model_name": scorer.model_name,
        "model_version": scorer.model_version,
        "window_samples": SSL_INPUT_SAMPLES,
        "sample_rate": SAMPLE_RATE,
        "confidence_reference_size": reference.size,
        "confidence_reference_k": reference.k,
    }
