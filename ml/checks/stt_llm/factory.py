"""One call that hands the transcript worker a configured check.

    from ml.checks.stt_llm import build_default_check

    check = build_default_check()   # already warmed

Mirrors `ml/checks/machine_fingerprint/factory.py`, with one deliberate
difference: this one does not refuse to build on a CPU. The fingerprint check
runs inside the 180 ms stage 04 budget, so a CPU build there would miss every
deadline and back the call buffer up. Check 4 runs out of band on its own
cadence, so a slow transcript is late rather than fatal, and lateness is already
visible to fusion through the signal's age.

Scorer selection, in order:

1. `GROQ_API_KEY` present, so Groq is primary with the keyword scorer behind it.
2. No key, so the keyword scorer alone, and a warning saying so.

Either way the returned check has a working scorer. Check 4 never silently
becomes a no-op.
"""

from __future__ import annotations

import logging
import os

from .check import SttLlmCheck
from .scorer import FallbackScriptScorer, KeywordScriptScorer, ScriptScorer
from .transcriber import FasterWhisperTranscriber

logger = logging.getLogger("satyacheck.stt_llm.factory")


def build_default_scorer(*, groq_model: str = "llama-3.3-70b-versatile") -> ScriptScorer:
    """Groq in front of the local keyword scorer, or the keyword scorer alone."""
    fallback = KeywordScriptScorer()
    if not os.environ.get("GROQ_API_KEY"):
        logger.warning(
            "GROQ_API_KEY is not set, so check 4 scores scripts with the local "
            "keyword scorer only. It matches fixed patterns and misses paraphrase; "
            "set the key to use the language model."
        )
        return fallback

    try:
        from .scorer import GroqScriptScorer

        primary = GroqScriptScorer(model=groq_model)
    except Exception as exc:  # noqa: BLE001 - a bad key must not stop the pipeline
        logger.warning(
            "could not build the Groq scorer (%s), using the local keyword scorer",
            type(exc).__name__,
        )
        return fallback

    return FallbackScriptScorer(primary, fallback)


def build_default_check(
    *,
    model_size: str = "small",
    device: str | None = None,
    language: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
    warmup: bool = True,
) -> SttLlmCheck:
    """The check the transcript worker should use, configured for this machine.

    `language=None` lets Whisper detect per window, which is what Indian calls
    that switch language mid-sentence need. Pin it only when you know the call
    is single-language.

    The returned check is already warmed, because a cold first transcript costs
    seconds on top of a step that is already the slow one.
    """
    transcriber = FasterWhisperTranscriber(
        model_size=model_size, device=device, language=language
    )
    if warmup:
        transcriber.warmup()
    return SttLlmCheck(transcriber, build_default_scorer(groq_model=groq_model))
