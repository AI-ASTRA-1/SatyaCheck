"""The LLM leg of the script channel, plus the chain that falls back past it.

`analyze()` is the entry point: it tries the language model, then the rules
scorer, then abstains. It never raises and never returns a mid-range guess on
failure, so a channel that cannot read its input contributes nothing to fusion
rather than voting 0.5.

The model plugs in behind the `ScriptLLM` Protocol, the same seam pattern as
`SyntheticScorer` in machine_fingerprint: this module owns the prompt, the
defensive parse and the fallback chain; the model owns inference and nothing
else. `analyze()` accepts one `ScriptLLM` or an ordered list, tried in turn.

Two implementations ship: `AnthropicScriptLLM` (primary, best output) and
`QwenScriptLLM` (local resilience fallback). **`AnthropicScriptLLM` sends the
transcript to the Anthropic API.** That contradicts the deck's "all inference is
local, no external API to fail on demo day" and touches the DPDP/privacy section;
those are human-owned docs. See `ml/README.md` Repo state.

The model is asked for `evidence` quotes, but only to catch fabrication: a
response whose every quote is absent from the transcript is discarded. No quote,
and no other transcript-derived text, is stored on `ScriptAnalysis` or reaches
any evidence record. No transcript at rest.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Sequence
from typing import Protocol

from ml.paths import require

from .tactics import TACTICS, ScriptAnalysis, analyze_rules, looks_like_asr_noise

SYSTEM = """You analyse phone-call transcripts for social-engineering fraud patterns.

You are given a partial transcript of a live call. Decide whether the CALLER is running
a social-engineering script. Judge ONLY what is present in the text. Do not infer from
tone, accent, or from who the speaker claims to be. The transcript may contain both
speakers; score only statements that read as the caller instructing or pressuring the
recipient, never the recipient's own words.

Score each tactic independently, 0.0 to 1.0:

- urgency            : pressure to act now; deadlines; consequences for any delay
- secrecy            : telling the person not to inform family, colleagues, or the bank
- verification_block : discouraging hanging up, calling back, or checking independently
- authority          : claiming to be police, bank fraud team, a senior executive, government
- irreversible_ask   : requesting a transfer, OTP, gift cards, crypto, or credentials

Return ONLY this JSON. No prose, no markdown fences, no explanation.

{"tactics":{"urgency":0.0,"secrecy":0.0,"verification_block":0.0,
"authority":0.0,"irreversible_ask":0.0},
"intent":0.0,"evidence":["short quoted fragment"],"confidence":0.0}

intent     = your overall judgement that this is a fraud script, 0.0 to 1.0.
confidence = how much usable transcript you had, 0.0 to 1.0.
evidence   = at most three short fragments quoted verbatim from the transcript.

An ordinary conversation scores near 0.0 on everything. A person discussing a payment
with someone they know is NOT a scam. Do not invent tactics that are not in the text."""


#: The one wire contract every `ScriptLLM.complete()` response is held to. The
#: JSON block in SYSTEM is an instance of it; `schema_errors()` checks against it;
#: the API back ends pass it to the provider as a structured-output constraint.
RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tactics", "intent", "evidence", "confidence"],
    "properties": {
        "tactics": {
            "type": "object",
            "additionalProperties": False,
            "required": list(TACTICS),
            "properties": {
                t: {"type": "number", "minimum": 0.0, "maximum": 1.0} for t in TACTICS
            },
        },
        "intent": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
}


def schema_errors(data: object) -> list[str]:
    """Every way `data` departs from RESPONSE_SCHEMA. Empty list means conformant.

    A reporting/validation helper. `parse_llm_json` is deliberately more lenient
    than this: it clamps an out-of-range number and fills a missing `confidence`
    or `evidence`. It hard-fails only on the structural problems flagged here for
    `tactics` and `intent`.
    """
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["top level is not a JSON object"]
    for key in data:
        if key not in ("tactics", "intent", "evidence", "confidence"):
            errs.append(f"unexpected key {key!r}")
    for key in ("tactics", "intent", "evidence", "confidence"):
        if key not in data:
            errs.append(f"missing {key!r}")

    tactics = data.get("tactics")
    if isinstance(tactics, dict):
        for key in tactics:
            if key not in TACTICS:
                errs.append(f"tactics: unexpected {key!r}")
        for name in TACTICS:
            if name not in tactics:
                errs.append(f"tactics: missing {name!r}")
                continue
            value = _num(tactics[name], None)
            if value is None:
                errs.append(f"tactics.{name}: {tactics[name]!r} is not a number")
            elif not 0.0 <= value <= 1.0:
                errs.append(f"tactics.{name}: {value} out of [0, 1]")
    elif tactics is not None:
        errs.append("tactics: not an object")

    for key in ("intent", "confidence"):
        if key in data:
            value = _num(data[key], None)
            if value is None:
                errs.append(f"{key}: {data[key]!r} is not a number")
            elif not 0.0 <= value <= 1.0:
                errs.append(f"{key}: {value} out of [0, 1]")

    evidence = data.get("evidence")
    if isinstance(evidence, list):
        if len(evidence) > 3:
            errs.append(f"evidence: {len(evidence)} items, max 3")
        if any(not isinstance(item, str) for item in evidence):
            errs.append("evidence: contains a non-string item")
    elif evidence is not None:
        errs.append("evidence: not an array")
    return errs


class ScriptLLM(Protocol):
    """A local language model that scores one transcript. The seam the model
    plugs into; this module owns everything around it."""

    @property
    def model_name(self) -> str:
        """Short, non-PII model identifier, recorded on evidence downstream."""
        ...

    @property
    def model_version(self) -> str:
        """Checkpoint or revision identifier, so a score traces to its weights."""
        ...

    def complete(self, system: str, transcript: str) -> str:
        """Return the model's raw text response to `system` over `transcript`.

        Raise on any failure. `analyze()` turns that into the next model in the
        chain, then the rules fallback, never a verdict.
        """
        ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _num(value: object, default: float | None) -> float | None:
    # bool is an int subclass; a JSON `true` is not a score.
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


_QUOTE_CHARS = "\"'`“”‘’"


def _grounded_quotes(evidence: object, transcript: str) -> tuple[int, int]:
    """(quotes found in the transcript, quotes provided). Surrounding quote marks
    and whitespace are stripped first; models routinely wrap the fragment."""
    if not isinstance(evidence, list):
        return (0, 0)
    quotes = [
        cleaned
        for e in evidence
        if isinstance(e, str)
        for cleaned in [e.strip().strip(_QUOTE_CHARS).strip()]
        if cleaned
    ]
    hay = transcript.lower()
    grounded = sum(1 for q in quotes if q.lower() in hay)
    return (grounded, len(quotes))


def parse_llm_json(
    raw: str, transcript: str, *, mixed_channel: bool = True
) -> ScriptAnalysis | None:
    """Parse a model response into a `ScriptAnalysis`, or None if it cannot be trusted.

    None on: non-JSON, wrong shape, a missing or non-numeric tactic score, a
    missing or non-numeric `intent`, or a response whose every `evidence` quote is
    absent from the transcript (the model fabricated its justification). All
    numeric fields are clamped to [0, 1].
    """
    text = _FENCE.sub("", (raw or "").strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    tactics_in = data.get("tactics")
    if not isinstance(tactics_in, dict):
        return None
    tactics: dict[str, float] = {}
    for name in TACTICS:
        value = _num(tactics_in.get(name), None)
        if value is None:
            return None
        tactics[name] = _clamp(value)

    raw_intent = _num(data.get("intent"), None)
    if raw_intent is None:
        return None
    intent = _clamp(raw_intent)
    confidence = _clamp(_num(data.get("confidence"), 0.5))

    # Fabrication gate: reject a response that raises a real concern (intent >=
    # 0.5) while every quote it offers as justification is absent from the
    # transcript. A low-intent response is not worth discarding over quote
    # formatting; abstaining there just loses signal.
    grounded, provided = _grounded_quotes(data.get("evidence"), transcript)
    if provided and grounded == 0 and intent >= 0.5:
        return None

    return ScriptAnalysis(
        tactics=tactics,
        intent=intent,
        confidence=confidence,
        source="llm",
        mixed_channel=mixed_channel,
    )


def _as_chain(
    llm: ScriptLLM | Sequence[ScriptLLM] | None,
) -> tuple[ScriptLLM, ...]:
    if llm is None:
        return ()
    if hasattr(llm, "complete"):  # a single ScriptLLM
        return (llm,)  # type: ignore[return-value]
    return tuple(llm)


def analyze(
    transcript: str,
    llm: ScriptLLM | Sequence[ScriptLLM] | None = None,
    *,
    mixed_channel: bool = True,
) -> ScriptAnalysis:
    """Score a transcript: each LLM in `llm` in order until one parses, else the
    rules scorer, else abstain. Never raises.

    `llm` is one `ScriptLLM` or an ordered list (primary, then fallbacks). Each is
    tried: a raise or an untrusted parse moves to the next. The model sees the raw
    transcript and is instructed to ignore the recipient's words; the rules
    fallback does its own refusal strip. A transcript that reads as an ASR
    hallucination loop skips every model and abstains.
    """
    text = (transcript or "").strip()
    if not looks_like_asr_noise(text):
        for model in _as_chain(llm):
            try:
                raw = model.complete(SYSTEM, text)
                parsed = parse_llm_json(raw, text, mixed_channel=mixed_channel)
            except Exception:  # noqa: BLE001 - a model failure degrades, never a verdict
                parsed = None
            if parsed is not None:
                return parsed
    return analyze_rules(text, mixed_channel=mixed_channel)


class AnthropicScriptLLM:
    """Primary `ScriptLLM`: the Anthropic API. Best output on borderline cases.

    Sends the transcript to Anthropic. This diverges from the deck's local-only
    claim (see the module docstring and `ml/README.md`). The API key is read from
    the environment by the SDK; nothing here stores it.
    """

    def __init__(
        self, model: str = "claude-sonnet-5", *, max_tokens: int = 1024
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client: object | None = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return f"anthropic-{self._model}"

    @property
    def model_version(self) -> str:
        return self._model

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        with self._lock:
            if self._client is None:
                import anthropic

                self._client = anthropic.Anthropic()

    def warmup(self) -> None:
        self._ensure_client()

    def complete(self, system: str, transcript: str) -> str:
        self._ensure_client()
        assert self._client is not None
        response = self._client.messages.create(  # type: ignore[attr-defined]
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": transcript}],
            output_config={
                "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}
            },
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )


class GroqScriptLLM:
    """`ScriptLLM` over the Groq API (OpenAI-compatible chat completions).

    Same external-API caveat as `AnthropicScriptLLM`: the transcript leaves the
    machine, and Groq's free tier has no data-processing agreement. Intended for
    a free measurement of a 70B-class model on this task, not production. Key from
    the `GROQ_API_KEY` environment variable unless passed.
    """

    _URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        model: str = "openai/gpt-oss-120b",
        *,
        api_key: str | None = None,
        max_tokens: int = 1024,
        timeout: float = 45.0,
        use_schema: bool = True,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._timeout = timeout
        # json_schema enforces RESPONSE_SCHEMA on the wire; not every Groq model
        # supports it, so a 400 flips this off and retries with json_object.
        self._use_schema = use_schema

    @property
    def model_name(self) -> str:
        return f"groq-{self._model}"

    @property
    def model_version(self) -> str:
        return self._model

    def warmup(self) -> None:
        return None

    def complete(self, system: str, transcript: str) -> str:
        import os
        import time

        import httpx2 as httpx

        key = self._api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")

        def _payload() -> dict[str, object]:
            fmt: dict[str, object] = (
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "script_analysis",
                        "schema": RESPONSE_SCHEMA,
                        "strict": True,
                    },
                }
                if self._use_schema
                else {"type": "json_object"}
            )
            return {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": transcript},
                ],
                "max_tokens": self._max_tokens,
                "temperature": 0.0,
                "response_format": fmt,
            }

        for attempt in range(4):
            response = httpx.post(
                self._URL,
                headers={"Authorization": f"Bearer {key}"},
                json=_payload(),
                timeout=self._timeout,
            )
            if response.status_code == 429 and attempt < 3:
                retry_after = float(response.headers.get("retry-after", "2"))
                time.sleep(min(retry_after, 20.0))
                continue
            if (
                response.status_code == 400
                and self._use_schema
                and "json_schema" in response.text
            ):
                self._use_schema = False  # this model lacks it; drop to json_object
                continue
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        response.raise_for_status()  # exhausted retries
        return response.json()["choices"][0]["message"]["content"]


class QwenScriptLLM:
    """Local resilience fallback: Qwen2.5-3B-Instruct via transformers.

    Runs when the API is unreachable (venue wifi, rate limit). Loads lazily from
    the local model directory, 4-bit if bitsandbytes is usable, else fp16. Weights
    only; no network at inference.
    """

    def __init__(
        self,
        *,
        model_dir_name: str = "qwen2.5-3b-instruct",
        max_new_tokens: int = 220,  # the JSON is ~120 tokens; keeps gen ~5 s
        device: str | None = None,
    ) -> None:
        self._model_dir_name = model_dir_name
        self._max_new_tokens = max_new_tokens
        self._requested_device = device
        self._model: object | None = None
        self._tokenizer: object | None = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_dir_name

    @property
    def model_version(self) -> str:
        return "qwen2.5-3b-instruct-hf"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            path = str(require(self._model_dir_name))
            self._tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
            try:
                from transformers import BitsAndBytesConfig

                self._model = AutoModelForCausalLM.from_pretrained(
                    path,
                    local_files_only=True,
                    device_map="auto",
                    quantization_config=BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.float16,
                    ),
                )
            except Exception:  # noqa: BLE001 - bnb wheel/CUDA mismatch -> fp16
                device = self._requested_device or (
                    "cuda" if torch.cuda.is_available() else "cpu"
                )
                self._model = AutoModelForCausalLM.from_pretrained(
                    path, local_files_only=True, torch_dtype=torch.float16
                ).to(device)

    def warmup(self) -> None:
        self._ensure_loaded()

    def complete(self, system: str, transcript: str) -> str:
        self._ensure_loaded()
        import torch

        assert self._tokenizer is not None and self._model is not None
        inputs = self._tokenizer.apply_chat_template(  # type: ignore[attr-defined]
            [
                {"role": "system", "content": system},
                {"role": "user", "content": transcript},
            ],
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to(self._model.device)  # type: ignore[attr-defined]
        prompt_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            generated = self._model.generate(  # type: ignore[attr-defined]
                **inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,  # type: ignore[attr-defined]
            )
        return self._tokenizer.decode(  # type: ignore[attr-defined]
            generated[0][prompt_len:], skip_special_tokens=True
        )


def default_chain() -> list[ScriptLLM]:
    """Anthropic primary, local Qwen fallback. `analyze()` adds rules then none."""
    return [AnthropicScriptLLM(), QwenScriptLLM()]
