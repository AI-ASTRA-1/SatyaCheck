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


#: Used when neither the caller nor GROQ_MODEL says otherwise. Verified against
#: this account on 2026-09-09: it answered 0.95/authority_impersonation on a scam
#: script and 0.0/none on ordinary speech, in about 0.8 s.
#: `qwen/qwen3.8-27b` gave the same answers in about 0.35 s if latency matters.
#: `openai/gpt-oss-20b` returns empty content on some inputs, so avoid it.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def enable_system_certs() -> None:
    """Verify TLS against the OS trust store instead of certifi's bundle.

    This machine sits behind TLS interception: the proxy re-signs every
    connection with a CA that is in the Windows store but not in certifi, so
    certifi-based clients fail. It broke the HuggingFace download of the Whisper
    weights ("CERTIFICATE_VERIFY_FAILED") and every Groq call
    ("APIConnectionError") until this was in place.

    `truststore` reads the platform store, so it fixes both without anyone
    hand-building a PEM or setting SSL_CERT_FILE. Idempotent and safe on a
    machine with no interception, where it simply uses the normal system roots.
    """
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception as exc:  # noqa: BLE001 - a machine without interception needs nothing
        logger.debug("could not enable system certificate verification: %s", exc)


def build_default_scorer(*, groq_model: str | None = None) -> ScriptScorer:
    """Groq in front of the local keyword scorer, or the keyword scorer alone.

    `groq_model` falls back to the GROQ_MODEL environment variable, then to
    DEFAULT_GROQ_MODEL, so the model can be changed from .env without a code
    change.
    """
    groq_model = groq_model or os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
    enable_system_certs()
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
    groq_model: str | None = None,
    warmup: bool = True,
) -> SttLlmCheck:
    """The check the transcript worker should use, configured for this machine.

    `language=None` lets Whisper detect per window, which is what Indian calls
    that switch language mid-sentence need. Pin it only when you know the call
    is single-language.

    The returned check is already warmed, because a cold first transcript costs
    seconds on top of a step that is already the slow one.
    """
    # Before the transcriber, which downloads weights over TLS on first use.
    enable_system_certs()
    transcriber = FasterWhisperTranscriber(
        model_size=model_size, device=device, language=language
    )
    if warmup:
        transcriber.warmup()
    return SttLlmCheck(transcriber, build_default_scorer(groq_model=groq_model))
