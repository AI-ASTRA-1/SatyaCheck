"""What is being said: speech-to-text then language model. Is this a scam script.
Owner: ML lead B.

Returns SttLlmSignal (script_risk, script_category). The transcript is an
in-memory working artifact of this check only, discarded on return, never in any
evidence record. Check 4 is Round 1 as an evidence channel; a product-level
transcript warning feature is Round 2.

The check layer and the models are separate, the same split the fingerprint
check uses. `SttLlmCheck` owns status, evidence and the contract; a
`Transcriber` produces the words and a `ScriptScorer` judges them.

**This check does not run inside the 180 ms stage 04 budget.** Transcription
plus a language model takes seconds. `backend/app/pipeline/transcript_worker.py`
runs it out of band on a rolling buffer and fusion reads the latest result along
with its age, so a slow or failed transcript is visible rather than silently
absent.

`build_default_check()` resolves the device, loads the Whisper weights, warms
them, and picks a scorer: Groq when `GROQ_API_KEY` is set, otherwise the local
keyword scorer. Importing this package costs no model load; the factory imports
lazily.
"""

from .check import (
    DEFAULT_MIN_WINDOW_MS,
    DEFAULT_SCRIPT_RISK_THRESHOLD,
    SttLlmCheck,
)
from .factory import build_default_check, build_default_scorer
from .scorer import (
    CATEGORIES,
    CATEGORY_NONE,
    FallbackScriptScorer,
    KeywordScriptScorer,
    ScriptAssessment,
    ScriptScorer,
)
from .transcriber import Transcriber

__all__ = [
    "CATEGORIES",
    "CATEGORY_NONE",
    "DEFAULT_MIN_WINDOW_MS",
    "DEFAULT_SCRIPT_RISK_THRESHOLD",
    "FallbackScriptScorer",
    "KeywordScriptScorer",
    "ScriptAssessment",
    "ScriptScorer",
    "SttLlmCheck",
    "Transcriber",
    "build_default_check",
    "build_default_scorer",
]
