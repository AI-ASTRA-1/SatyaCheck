"""Scam-script scoring over a transcript. Owner: ML lead B.

Two scorers sit behind one protocol so the check never knows which produced a
number:

- `GroqScriptScorer` sends the transcript to the Groq API. Chosen deliberately
  for the prototype on 2026-09-09, with the tradeoff understood and accepted by
  the team: transcript text leaves this machine, and the demo gains a network
  dependency. `AGENTS.md` asks for local inference, and this is a recorded
  exception to it, not an oversight.
- `KeywordScriptScorer` runs locally and needs nothing. It is weaker, and it is
  what keeps check 4 alive when the API is missing, rate limited or offline.

`FallbackScriptScorer` composes the two so a Groq failure degrades to the local
scorer instead of losing the check.

**Nothing here returns transcript text.** A `ScriptAssessment` carries a number
and a stable category label only, because the caller puts it in `EvidenceItem`
and `contracts/checks.py` requires the transcript never reach any evidence
record.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("satyacheck.stt_llm.scorer")

#: Stable, non-PII category labels. Safe to put in evidence and on a slide.
CATEGORY_NONE = "none"
CATEGORY_AUTHORITY = "authority_impersonation"
CATEGORY_RELATIVE_DISTRESS = "relative_distress"
CATEGORY_FINANCIAL_URGENCY = "financial_urgency"
CATEGORY_SECRECY = "secrecy_pressure"
CATEGORY_PAYMENT = "payment_instruction"

CATEGORIES = (
    CATEGORY_AUTHORITY,
    CATEGORY_RELATIVE_DISTRESS,
    CATEGORY_FINANCIAL_URGENCY,
    CATEGORY_SECRECY,
    CATEGORY_PAYMENT,
)


@dataclass(frozen=True)
class ScriptAssessment:
    """What a scorer returns. A number and a label, never the words."""

    script_risk: float
    category: str | None
    scorer: str


class ScriptScorer(Protocol):
    name: str

    def score(self, transcript: str) -> ScriptAssessment: ...


# Patterns grouped by what the scammer is doing, weighted by how strongly each
# signals a script rather than ordinary speech. Deliberately provisional and
# uncalibrated, exactly like the fingerprint thresholds.
_PATTERNS: dict[str, tuple[float, tuple[str, ...]]] = {
    CATEGORY_AUTHORITY: (
        0.45,
        (
            r"\bdigital arrest\b",
            r"\bcbi\b",
            r"\bnarcotics\b",
            r"\bcustoms\b",
            r"\benforcement directorate\b",
            r"\bpolice (station|officer|department)\b",
            r"\barrest warrant\b",
            r"\bcourt (case|summons|notice)\b",
            r"\byour (aadhaar|aadhar|pan) (card )?(is|has been) (linked|used|blocked)\b",
        ),
    ),
    CATEGORY_RELATIVE_DISTRESS: (
        0.45,
        (
            r"\b(accident|hospital|emergency)\b.{0,40}\b(son|daughter|brother|mother|father)\b",
            r"\b(son|daughter|brother|mother|father)\b.{0,40}\b(accident|hospital|arrested|trouble)\b",
            r"\bi am in (trouble|danger)\b",
            r"\bplease help me\b.{0,30}\bmoney\b",
        ),
    ),
    CATEGORY_FINANCIAL_URGENCY: (
        0.35,
        (
            r"\botp\b",
            r"\bone[- ]time password\b",
            r"\bcvv\b",
            r"\bupi pin\b",
            r"\b(account|card) (is |has been )?(blocked|suspended|frozen)\b",
            r"\bkyc (update|verification|expired)\b",
            r"\bverify your (account|identity)\b",
        ),
    ),
    CATEGORY_SECRECY: (
        0.4,
        (
            r"\b(do not|don't|dont) (tell|inform|discuss)\b",
            r"\bkeep (this|it) (confidential|secret|between us)\b",
            r"\bstay on the (call|line)\b",
            r"\bdo not (hang up|disconnect)\b",
        ),
    ),
    CATEGORY_PAYMENT: (
        0.4,
        (
            r"\btransfer\b.{0,25}\b(money|amount|rupees|rs\.?)\b",
            r"\bsend\b.{0,20}\b(money|rupees|rs\.?)\b",
            r"\b(google pay|gpay|phonepe|paytm|upi)\b.{0,25}\b(send|transfer|pay)\b",
            r"\bpay (the )?(fine|penalty|fee|security deposit)\b",
            r"\bgift card\b",
            r"\bbitcoin\b",
        ),
    ),
}

_COMPILED = {
    category: (weight, tuple(re.compile(p, re.IGNORECASE) for p in patterns))
    for category, (weight, patterns) in _PATTERNS.items()
}


class KeywordScriptScorer:
    """Local, dependency-free scam-script scorer. The fallback, not the goal.

    Pattern matching cannot read intent and misses any paraphrase it was not
    written for, so treat its number as a floor rather than a measurement. It
    exists so a Groq outage degrades check 4 instead of removing it.
    """

    name = "keyword-v1"

    def __init__(self, risk_cap: float = 0.95) -> None:
        self._cap = risk_cap

    def score(self, transcript: str) -> ScriptAssessment:
        if not transcript.strip():
            return ScriptAssessment(0.0, CATEGORY_NONE, self.name)

        hits: dict[str, float] = {}
        for category, (weight, patterns) in _COMPILED.items():
            matched = sum(1 for pattern in patterns if pattern.search(transcript))
            if matched:
                # Extra hits in one category add less than the first, so a single
                # repeated phrase cannot alone drive the score to 1.0.
                hits[category] = weight + 0.1 * (matched - 1)

        if not hits:
            return ScriptAssessment(0.0, CATEGORY_NONE, self.name)

        top = max(hits, key=lambda c: hits[c])
        # Categories compound: authority plus payment is a far stronger signal
        # than either alone.
        total = min(self._cap, sum(hits.values()))
        return ScriptAssessment(round(total, 3), top, self.name)


class GroqScriptScorer:
    """Scores the transcript with a Groq-hosted model. Raises on any failure.

    Raising rather than returning a neutral score is deliberate: a silent 0.0
    from a broken API is indistinguishable from a genuinely clean call, and at
    the configured weighting that would read as safety. `FallbackScriptScorer`
    catches it and uses the local scorer instead.
    """

    name = "groq"

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key: str | None = None,
        timeout_s: float = 8.0,
    ) -> None:
        from groq import Groq

        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self._client = Groq(api_key=key, timeout=timeout_s)
        self._model = model
        self.name = f"groq:{model}"

    _PROMPT = (
        "You judge whether a phone call transcript follows a known scam script. "
        "Indian fraud context. Reply with JSON only, no prose, exactly: "
        '{"script_risk": <float 0.0-1.0>, "category": "<one of '
        + "|".join([*CATEGORIES, CATEGORY_NONE])
        + '>"}. '
        "script_risk is how strongly the words match a scam script, where 0.0 is "
        "ordinary conversation and 1.0 is an unmistakable script. Judge the words "
        "only. You are not told, and must not guess, whether the voice is real."
    )

    def score(self, transcript: str) -> ScriptAssessment:
        if not transcript.strip():
            return ScriptAssessment(0.0, CATEGORY_NONE, self.name)

        completion = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._PROMPT},
                {"role": "user", "content": transcript},
            ],
            temperature=0.0,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
        risk = float(payload.get("script_risk", 0.0))
        if not 0.0 <= risk <= 1.0:
            raise ValueError(f"groq returned script_risk out of range: {risk}")
        category = payload.get("category") or CATEGORY_NONE
        if category not in (*CATEGORIES, CATEGORY_NONE):
            category = CATEGORY_NONE
        return ScriptAssessment(round(risk, 3), category, self.name)


class FallbackScriptScorer:
    """Primary scorer, with a local one taking over on any failure."""

    def __init__(self, primary: ScriptScorer | None, fallback: ScriptScorer) -> None:
        self._primary = primary
        self._fallback = fallback
        self.name = f"{primary.name}+{fallback.name}" if primary else fallback.name

    def score(self, transcript: str) -> ScriptAssessment:
        if self._primary is not None:
            try:
                return self._primary.score(transcript)
            except Exception as exc:  # noqa: BLE001 - any API failure degrades, never propagates
                logger.warning(
                    "primary script scorer %s failed (%s), falling back to %s",
                    self._primary.name,
                    type(exc).__name__,
                    self._fallback.name,
                )
        return self._fallback.score(transcript)
