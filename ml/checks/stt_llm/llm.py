"""The LLM leg of the script channel, plus the chain that falls back past it.

`analyze()` is the entry point: it tries the language model, then the rules
scorer, then abstains. It never raises and never returns a mid-range guess on
failure, so a channel that cannot read its input contributes nothing to fusion
rather than voting 0.5.

The model plugs in behind the `ScriptLLM` Protocol, the same seam pattern as
`SyntheticScorer` in machine_fingerprint: this module owns the prompt, the
defensive parse and the fallback chain; the model owns inference and nothing
else. All inference is local (deck: no external API to fail on demo day); the
concrete client and model choice are not made here.

The model is asked for `evidence` quotes, but only to catch fabrication: a
response whose every quote is absent from the transcript is discarded. No quote,
and no other transcript-derived text, is stored on `ScriptAnalysis` or reaches
any evidence record. No transcript at rest.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

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

        Raise on any failure. `analyze()` turns that into a rules fallback, never
        a verdict. Must not stream the transcript to an external API.
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


def _grounded_quotes(evidence: object, transcript: str) -> tuple[int, int]:
    """(quotes found verbatim in the transcript, quotes provided)."""
    if not isinstance(evidence, list):
        return (0, 0)
    quotes = [e.strip() for e in evidence if isinstance(e, str) and e.strip()]
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

    intent = _num(data.get("intent"), None)
    if intent is None:
        return None
    confidence = _clamp(_num(data.get("confidence"), 0.5))

    grounded, provided = _grounded_quotes(data.get("evidence"), transcript)
    if provided and grounded == 0:
        return None

    return ScriptAnalysis(
        tactics=tactics,
        intent=_clamp(intent),
        confidence=confidence,
        source="llm",
        mixed_channel=mixed_channel,
    )


def analyze(
    transcript: str,
    llm: ScriptLLM | None = None,
    *,
    mixed_channel: bool = True,
) -> ScriptAnalysis:
    """Score a transcript: LLM if one is given and its output parses, else the
    rules scorer, else abstain. Never raises.

    The model sees the raw transcript and is instructed to ignore the recipient's
    words; the rules fallback does its own refusal strip. A transcript that reads
    as an ASR hallucination loop skips the model entirely and abstains.
    """
    text = (transcript or "").strip()
    if llm is not None and not looks_like_asr_noise(text):
        try:
            raw = llm.complete(SYSTEM, text)
            parsed = parse_llm_json(raw, text, mixed_channel=mixed_channel)
        except Exception:  # noqa: BLE001 - any model failure degrades, never a verdict
            parsed = None
        if parsed is not None:
            return parsed
    return analyze_rules(text, mixed_channel=mixed_channel)
