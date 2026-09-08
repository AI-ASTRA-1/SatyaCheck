"""The seam the synthetic-speech model plugs into.

The check layer owns status, evidence and the contract. The scorer owns the model
and nothing else. A pretrained wav2vec2 / XLS-R plus AASIST implementation arrives
behind this Protocol without changing `check.py` or any of its tests.

A scorer raises on failure. It never returns a fallback value, and it never returns
a verdict; `synthetic_probability` is evidence that the risk engine fuses.
"""

from __future__ import annotations

from typing import Protocol


class SyntheticScorer(Protocol):
    """Scores one window of canonical PCM for machine-generated speech."""

    @property
    def model_name(self) -> str:
        """Short model identifier recorded on every EvidenceItem, for example
        "aasist". Non-PII, safe to serialize. Read-only: a scorer's identity is not
        something a caller gets to change after the fact, or the evidence would no
        longer name the model that produced the score. A plain class attribute
        satisfies this."""
        ...

    @property
    def model_version(self) -> str:
        """Checkpoint or revision identifier, so a score can always be traced back
        to the weights that produced it."""
        ...

    def warmup(self) -> None:
        """Load the model and run it once, before any real audio arrives.

        Loading is lazy, so the first scored window otherwise pays seconds against a
        180 ms stage 04 budget. Whoever constructs the check calls this at startup.
        A scorer with nothing to load may implement it as a no-op.
        """
        ...

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        """Probability in [0, 1] that this waveform is machine generated.

        `pcm_s16le` is mono little-endian signed 16-bit PCM at `sample_rate`. It is
        a COPY and must not be mutated. Raise on any model failure; the check turns
        that into CheckStatus.FAILED with no signal, never into a verdict.
        """
        ...
