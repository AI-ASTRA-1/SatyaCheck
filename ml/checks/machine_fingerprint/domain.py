"""A scorer that reports domain distance alongside the score.

Wraps `SslAasistScorer` and the fitted reference from `ml/eval/confidence.py` into
one object satisfying `ConfidenceScorer`, so `MachineFingerprintCheck` gets both
numbers from a single forward pass.

Kept out of `ssl_aasist.py` on purpose. That module's job is the model and nothing
else; where the training distribution sits is a separate, separately fitted fact,
and a checkpoint swap must not silently keep an old reference.
"""

from __future__ import annotations

import numpy as np

from ml.eval import confidence as confidence_module

from .ssl_aasist import SslAasistScorer


class DomainAwareScorer:
    """`SslAasistScorer` plus a confidence estimate. Satisfies `ConfidenceScorer`."""

    def __init__(
        self,
        scorer: SslAasistScorer | None = None,
        reference: confidence_module.Reference | None = None,
    ) -> None:
        self._scorer = scorer or SslAasistScorer()
        self._reference = reference

    @property
    def model_name(self) -> str:
        return self._scorer.model_name

    @property
    def model_version(self) -> str:
        return self._scorer.model_version

    def _ensure_reference(self) -> confidence_module.Reference:
        if self._reference is None:
            path = confidence_module.reference_path()
            if not path.exists():
                raise FileNotFoundError(
                    f"missing the confidence reference at {path}. Build it with "
                    "`python -m ml.tools.fit_confidence`, or construct this scorer "
                    "with an explicit reference."
                )
            self._reference = confidence_module.Reference.load(path)
        return self._reference

    def warmup(self) -> None:
        self._ensure_reference()
        self._scorer.warmup()

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        return self._scorer.score(pcm_s16le, sample_rate)

    def score_with_confidence(
        self, pcm_s16le: bytes, sample_rate: int
    ) -> tuple[float, float]:
        reference = self._ensure_reference()
        probability, embedding = self._scorer.score_and_embed(pcm_s16le, sample_rate)
        return probability, reference.confidence(np.asarray(embedding))
