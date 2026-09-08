"""What is being said: speech-to-text then language model. Is this a scam script.
Owner: ML lead B.

Returns SttLlmSignal (script_risk, script_category). The transcript is an
in-memory working artifact of this check only, discarded on return, never in any
evidence record. Check 4 is Round 1 as an evidence channel; a product-level
transcript warning feature is Round 2.

Round 2 spike:

- `tactics.py`  rules-only tactic scorer. Pure, offline, stdlib only. Produces an
  internal `ScriptAnalysis` (five tactic scores, `intent`, `confidence`,
  `source`). The tactic breakdown and any quoted text do NOT cross the
  `SttLlmSignal` boundary. `looks_like_asr_noise` here makes both `analyze_rules`
  and `analyze()` abstain on repetition-loop hallucinations (degraded or
  non-English audio; STT is English-only this round).
- `llm.py`  the `ScriptLLM` Protocol seam, the system prompt, a defensive JSON
  parser, and `analyze()` wiring an ordered LLM chain -> rules -> none. Never
  raises, never returns a mid-range guess on failure. The model's `evidence`
  quotes are used only to catch fabrication and are then discarded; nothing
  transcript-derived is stored. Back ends: `AnthropicScriptLLM` (`claude-sonnet-5`),
  `GroqScriptLLM` (OpenAI-compatible, `openai/gpt-oss-120b`), `QwenScriptLLM`
  (local `qwen2.5-3b-instruct`). The Anthropic and Groq back ends send the
  transcript to an external API -> diverges from the deck's local-only claim.
  `RESPONSE_SCHEMA` is the one wire contract: the SYSTEM prompt's JSON is an
  instance of it, `schema_errors()` reports departures, the API back ends pass it
  to the provider as a structured-output constraint, and `ScriptAnalysis`
  self-validates its shape in `__post_init__`.
- `asr.py`  the `Transcriber` Protocol seam and `FasterWhisperTranscriber`
  (faster-whisper small, English pinned, greedy, VAD on,
  `condition_on_previous_text` off). Local weights only, no external API.
- `check.py`  `SttLlmCheck` implementing `contracts.checks.Check`. Maps
  `analyze()` to `SttLlmSignal(script_risk=intent, script_category=top tactic)`.
  Short window or thin transcript -> SKIPPED; transcriber error -> FAILED, no
  signal. The transcript is a local var in `run()`, discarded on return, never in
  evidence, the result, or a log.
- `eval_transcripts.py`  20 hand-written transcripts, 10 scam and 10 ordinary,
  for offline separation testing. Not a benchmark.
- `ml/tools/compare_script_llms.py`  scores the eval set through each back end
  (paid for the API configs); `--schema-check` reports raw-response conformance.
- Tests: `ml/tests/test_stt_llm_script.py`, `test_stt_llm_llm.py`,
  `test_stt_llm_check.py`, `test_stt_llm_schema.py`.

Not built: the rolling transcript buffer (stage 03, R2's folder) and calibration
of the evidence threshold.
"""

from .asr import FasterWhisperTranscriber, Transcriber
from .check import SttLlmCheck
from .llm import (
    RESPONSE_SCHEMA,
    SYSTEM,
    AnthropicScriptLLM,
    GroqScriptLLM,
    QwenScriptLLM,
    ScriptLLM,
    analyze,
    default_chain,
    parse_llm_json,
    schema_errors,
)
from .tactics import TACTICS, ScriptAnalysis, analyze_rules, looks_like_asr_noise

__all__ = [
    "RESPONSE_SCHEMA",
    "SYSTEM",
    "TACTICS",
    "AnthropicScriptLLM",
    "FasterWhisperTranscriber",
    "GroqScriptLLM",
    "QwenScriptLLM",
    "ScriptAnalysis",
    "ScriptLLM",
    "SttLlmCheck",
    "Transcriber",
    "analyze",
    "analyze_rules",
    "default_chain",
    "looks_like_asr_noise",
    "parse_llm_json",
    "schema_errors",
]
