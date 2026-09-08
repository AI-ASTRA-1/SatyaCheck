"""Rules-only script analysis. Pure, offline, no network, no model.

The bottom of the intended LLM -> rules -> none chain (Round 2). This module is
the part that cannot fail: it runs with the standard library alone, so a demo
keeps a script signal when the venue wifi or an API key does not.

What it produces is an internal ``ScriptAnalysis``, NOT a contract type. The check
boundary (``contracts.checks.SttLlmSignal``) exposes only ``script_risk`` and
``script_category``. The per-tactic breakdown and any transcript-derived text stay
inside the check and are discarded on return; nothing here is ever put on an
``EvidenceItem``, a ``CheckResult`` or a ``RiskUpdate``. No transcript at rest.

Round 1 status: Check 4 is an evidence channel only. A product-level transcript
warning is Round 2 and this module is a Round 2 spike.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

#: The five social-engineering tactics scored independently. Order is load-bearing:
#: it is the tie-break order when two tactics score equally.
TACTICS: tuple[str, ...] = (
    "urgency",
    "secrecy",
    "verification_block",
    "authority",
    "irreversible_ask",
)

#: Below this many words there is too little transcript to judge; the analyzer
#: abstains (source "none", all zeros) rather than guessing.
MIN_WORDS = 12

#: Word count at or above which the "how much text did we have" confidence is 1.0.
_FULL_CONFIDENCE_WORDS = 45

#: ASR-hallucination guards, both at or above MIN_WORDS. faster-whisper still
#: produces repetitive output on degraded or non-English audio with
#: condition_on_previous_text off. A pure loop ("star star star") has a low
#: distinct-word ratio; a messier one ("I am a star what is your name I am a
#: star") keeps the ratio up but repeats word pairs.
#:
#: Thresholds judged, not calibrated, against a small measured sample (STT run
#: over 30 s windows): genuine read-script windows score 0.00 repeated-bigram
#: ratio, genuine spontaneous speech up to 0.10 across four speakers and four
#: codecs; the non-English Exotel-call windows score 0.08, 0.16, 0.39, 0.44. So
#: 0.15 clears genuine spontaneous speech and catches the repetitive hallucinated
#: windows, but not a garbled non-repetitive one (the 0.08 window passes). n=4
#: speakers, one script; treat as provisional.
MIN_UNIQUE_WORD_RATIO = 0.30
MAX_REPEATED_BIGRAM_RATIO = 0.15

Source = Literal["llm", "rules", "none"]


def _compile(*sources: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(s, re.IGNORECASE) for s in sources)


#: Tactic -> the patterns that count as one hit each. A tactic scores
#: ``min(1.0, hits / 2)``: one phrasing is a weak signal, two is the tactic.
_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "urgency": _compile(
        r"\bright now\b",
        r"\bimmediately\b",
        r"\bact now\b",
        r"within (?:the next )?\d+ (?:minute|hour|min|sec)",
        r"before (?:the )?(?:bank|office|branch|day) (?:closes|close|closing|ends)",
        r"(?:last|final) (?:chance|warning|reminder)",
        r"\bexpire[sd]?\b",
        r"\burgent(?:ly)?\b",
        r"cannot wait\b",
        r"no time to (?:lose|waste)",
    ),
    "secrecy": _compile(
        r"(?:don'?t|do not) (?:tell|inform|share|discuss) "
        r"(?:this|it|anyone|anybody|your|the|him|her|them|with)",
        r"between (?:you and me|us)\b",
        r"keep (?:this|it) (?:confidential|private|quiet|to yourself|between)",
        r"\bconfidential\b",
        r"no one (?:else )?(?:should|needs to|can|will) know",
        r"\bquietly\b",
    ),
    "verification_block": _compile(
        r"(?:don'?t|do not|no need to) hang up",
        r"stay (?:on|with me on) the (?:line|call|phone)",
        r"(?:no|not enough|there'?s no) time (?:to|for) "
        r"(?:check|verify|confirm|think|visit|call)",
        r"(?:don'?t|do not) call (?:back|the bank|anyone|your)",
        r"(?:don'?t|do not) (?:disconnect|cut|end) (?:the|this) call",
    ),
    "authority": _compile(
        r"(?:cyber ?crime|\bCBI\b|\bED\b|enforcement directorate|income tax|"
        r"\bRBI\b|\bTRAI\b|customs (?:department|officer))",
        r"\b(?:police|inspector|sub-inspector)\b",
        r"fraud (?:department|team|division|cell|desk)",
        r"this is (?:your|the) (?:manager|ceo|director|senior|head office|branch head)",
        r"your account (?:has been |is |will be |may be )?"
        r"(?:suspended|blocked|frozen|deactivated|under investigation)",
        r"arrest warrant",
        r"legal action",
        r"money laundering",
    ),
    "irreversible_ask": _compile(
        r"\bOTP\b",
        r"one[- ]time (?:password|pin|code)",
        r"transfer\s+(?:\w+\s+){0,3}"
        r"(?:money|funds|amount|rupees|balance|cash|fee|fine|charge|penalty|deposit|back)",
        r"\bgift ?cards?\b",
        r"\bUPI\b (?:pin|id|number)",
        r"\bCVV\b",
        r"share (?:your |the )?(?:pin|password|otp|code|card number|cvv|account number)",
        r"\b(?:bitcoin|crypto|usdt|cryptocurrency)\b",
        r"scan (?:this|the) (?:qr|code|barcode)",
        r"read (?:me |out )?(?:me )?the (?:otp|code|number|pin)",
        r"(?:send|pay|deposit) (?:the |a )?(?:fee|fine|charge|penalty|tax|deposit)\b",
    ),
}

#: Sentences that read as the recipient pushing back, or as the caller disclaiming
#: (a real bank saying "we will never ask for your OTP"). Dropped before matching so
#: a mono transcript carrying both speakers does not score the recipient's words or
#: a genuine disclaimer as caller tactics.
_REFUSAL = re.compile(
    r"\bi (?:won'?t|will not|am not going to|refuse to|can'?t|cannot)\b"
    r"|\bno,? i\b"
    r"|why (?:would|should) i\b"
    r"|that'?s not (?:right|going to happen|how)"
    r"|i (?:don'?t|do not) (?:think|want|believe|trust)"
    r"|let me (?:check|verify|call|think|speak|confirm)"
    r"|i(?:'| a)m (?:going to |gonna )?(?:hang up|call (?:the bank|back|you back))"
    r"|(?:we|i) (?:will |would )?never (?:ask|call|request|send|share|need)"
    r"|(?:are|is|am) not (?:asking|going to ask|requesting)",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+")


@dataclass(frozen=True)
class ScriptAnalysis:
    """Internal result of the script channel. Not a wire type.

    ``tactics`` and any quoted text never cross the ``SttLlmSignal`` boundary. The
    check maps ``intent`` -> ``script_risk`` and ``script_category()`` ->
    ``script_category``, and drops the rest.

    ``__post_init__`` enforces the output schema at every construction site
    (``parse_llm_json``, ``analyze_rules``, ``_empty``): tactics keys are exactly
    ``TACTICS``, every score and ``intent`` / ``confidence`` is a real number in
    [0, 1], and ``source`` is one of the three literals. A violation is a bug
    upstream, so it raises rather than passes a malformed result to fusion.
    """

    tactics: dict[str, float]
    intent: float
    confidence: float
    source: Source
    mixed_channel: bool = True

    def __post_init__(self) -> None:
        if set(self.tactics) != set(TACTICS):
            raise ValueError(f"tactics keys {sorted(self.tactics)} != {sorted(TACTICS)}")
        for name, score in self.tactics.items():
            if not _is_unit(score):
                raise ValueError(f"tactics[{name!r}] = {score!r} not in [0, 1]")
        for field_name in ("intent", "confidence"):
            if not _is_unit(getattr(self, field_name)):
                raise ValueError(f"{field_name} = {getattr(self, field_name)!r} not in [0, 1]")
        if self.source not in ("llm", "rules", "none"):
            raise ValueError(f"source = {self.source!r} not one of llm/rules/none")
        if not isinstance(self.mixed_channel, bool):
            raise TypeError(f"mixed_channel = {self.mixed_channel!r} is not a bool")

    def top_tactics(self, n: int = 2) -> list[tuple[str, float]]:
        ranked = sorted(self.tactics.items(), key=lambda kv: kv[1], reverse=True)
        return [(name, score) for name, score in ranked[:n] if score > 0.0]

    def script_category(self) -> str | None:
        """The single highest-scoring tactic, or None when nothing fired.

        Ties break on ``TACTICS`` order via the stable sort in ``top_tactics``.
        """
        top = self.top_tactics(1)
        return top[0][0] if top else None


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _is_unit(x: object) -> bool:
    """True for a real number (not bool) in the closed unit interval."""
    return not isinstance(x, bool) and isinstance(x, (int, float)) and 0.0 <= x <= 1.0


def _empty(mixed_channel: bool) -> ScriptAnalysis:
    return ScriptAnalysis(
        tactics={t: 0.0 for t in TACTICS},
        intent=0.0,
        confidence=0.0,
        source="none",
        mixed_channel=mixed_channel,
    )


def _strip_refusals(transcript: str) -> str:
    kept = [s for s in _SENTENCE_SPLIT.split(transcript) if not _REFUSAL.search(s)]
    return " ".join(kept)


def _score_tactic(text: str, tactic: str) -> float:
    hits = sum(1 for pat in _PATTERNS[tactic] if pat.search(text))
    return _clamp(hits / 2.0)


def looks_like_asr_noise(transcript: str) -> bool:
    """True when a transcript is a repetitive ASR hallucination.

    Short input is left to the MIN_WORDS gate; this only judges input long enough
    to score. Trips on a pure loop ("hello hello hello ...") via the distinct-word
    ratio and on a messier hallucination (a phrase repeated among other junk) via
    the repeated word-pair ratio. Ordinary speech trips neither.
    """
    words = transcript.lower().split()
    if len(words) < MIN_WORDS:
        return False
    distinct_ratio = len(set(words)) / len(words)
    bigrams = list(pairwise(words))
    repeated_bigram_ratio = 1.0 - len(set(bigrams)) / len(bigrams)
    return (
        distinct_ratio < MIN_UNIQUE_WORD_RATIO
        or repeated_bigram_ratio > MAX_REPEATED_BIGRAM_RATIO
    )


def analyze_rules(transcript: str, *, mixed_channel: bool = True) -> ScriptAnalysis:
    """Score a transcript for social-engineering tactics with patterns only.

    On too little text (before or after refusal stripping), or a repetition-loop
    ASR hallucination, it abstains: source "none", every score 0.0. It never
    returns a mid-range guess, so a channel that cannot read its input contributes
    nothing to fusion rather than voting 0.5.

    ``mixed_channel`` True (the default, matching Exotel's mono both-speaker
    stream) runs the refusal/disclaimer strip first. Sentence splitting needs
    terminal punctuation; an unpunctuated transcript is treated as one sentence.
    """
    text = (transcript or "").strip()
    if len(text.split()) < MIN_WORDS:
        return _empty(mixed_channel)
    if looks_like_asr_noise(text):
        return _empty(mixed_channel)

    scored = _strip_refusals(text) if mixed_channel else text
    if len(scored.split()) < MIN_WORDS:
        return _empty(mixed_channel)

    tactics = {t: _score_tactic(scored, t) for t in TACTICS}
    ranked = sorted(tactics.values(), reverse=True)
    intent = _clamp(0.65 * ranked[0] + 0.25 * ranked[1] + 0.10 * ranked[2])
    confidence = _clamp(len(scored.split()) / _FULL_CONFIDENCE_WORDS)

    return ScriptAnalysis(
        tactics=tactics,
        intent=intent,
        confidence=confidence,
        source="rules",
        mixed_channel=mixed_channel,
    )
