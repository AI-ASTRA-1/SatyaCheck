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
  parser, and `analyze()` wiring the llm -> rules -> none chain. Never raises,
  never returns a mid-range guess on failure. The model's `evidence` quotes are
  used only to catch fabrication and are then discarded; nothing transcript-
  derived is stored. The concrete local LLM client is not chosen here.
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
- Tests: `ml/tests/test_stt_llm_script.py`, `test_stt_llm_llm.py`,
  `test_stt_llm_check.py`.

Not built: the rolling transcript buffer (stage 03, R2's folder), the concrete
local LLM client, and calibration of the evidence threshold.
"""

from .asr import FasterWhisperTranscriber, Transcriber
from .check import SttLlmCheck
from .llm import SYSTEM, ScriptLLM, analyze, parse_llm_json
from .tactics import TACTICS, ScriptAnalysis, analyze_rules, looks_like_asr_noise

__all__ = [
    "SYSTEM",
    "TACTICS",
    "FasterWhisperTranscriber",
    "ScriptAnalysis",
    "ScriptLLM",
    "SttLlmCheck",
    "Transcriber",
    "analyze",
    "analyze_rules",
    "looks_like_asr_noise",
    "parse_llm_json",
]
