"""Smoke suite for the LLM leg and the llm -> rules -> none fallback chain.

Fake models only, no inference. What these pin down: a clean response is used, a
malformed or untrustworthy one falls through to the rules scorer, a raising model
falls through, and no path fabricates a mid-range score or stores transcript text.
"""

from __future__ import annotations

import dataclasses
import json

from ml.checks.stt_llm.eval_transcripts import NORMAL_TRANSCRIPTS, SCAM_TRANSCRIPTS
from ml.checks.stt_llm.llm import SYSTEM, analyze, parse_llm_json
from ml.checks.stt_llm.tactics import TACTICS, ScriptAnalysis, analyze_rules

# A scam transcript the rules scorer scores high, used to check the fallback path
# produces a real result rather than an abstention.
SCAM = SCAM_TRANSCRIPTS[0]
assert "OTP" in SCAM


def _payload(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "tactics": {t: 0.1 for t in TACTICS},
        "intent": 0.2,
        "evidence": [],
        "confidence": 0.5,
    }
    body.update(over)
    return body


class _FixedLLM:
    model_name = "fake-llm"
    model_version = "0"

    def __init__(self, response: str) -> None:
        self.response = response
        self.seen_system: str | None = None
        self.calls = 0

    def complete(self, system: str, transcript: str) -> str:
        self.calls += 1
        self.seen_system = system
        return self.response


class _RaisingLLM:
    model_name = "raising-llm"
    model_version = "0"

    def complete(self, system: str, transcript: str) -> str:
        raise RuntimeError("model process died")


def test_clean_response_is_used() -> None:
    resp = json.dumps(
        _payload(
            tactics={**{t: 0.1 for t in TACTICS}, "urgency": 0.9},
            intent=0.8,
            confidence=0.7,
            evidence=["Read me the OTP"],
        )
    )
    a = analyze(SCAM, _FixedLLM(resp))
    assert a.source == "llm"
    assert a.tactics["urgency"] == 0.9
    assert a.intent == 0.8
    assert a.confidence == 0.7


def test_fenced_json_is_parsed() -> None:
    resp = "```json\n" + json.dumps(_payload(intent=0.55)) + "\n```"
    a = analyze(SCAM, _FixedLLM(resp))
    assert a.source == "llm"
    assert a.intent == 0.55


def test_out_of_range_numbers_are_clamped() -> None:
    resp = json.dumps(
        _payload(
            tactics={**{t: 0.1 for t in TACTICS}, "authority": -0.5, "urgency": 1.9},
            intent=1.7,
            confidence=3.0,
        )
    )
    a = parse_llm_json(resp, SCAM)
    assert a is not None
    assert a.tactics["authority"] == 0.0
    assert a.tactics["urgency"] == 1.0
    assert a.intent == 1.0
    assert a.confidence == 1.0


def test_malformed_json_falls_back_to_rules() -> None:
    a = analyze(SCAM, _FixedLLM("{ this is not json"))
    assert a.source == "rules"
    assert a.intent == analyze_rules(SCAM).intent


def test_missing_tactic_key_falls_back() -> None:
    broken = _payload()
    del broken["tactics"]["authority"]  # type: ignore[union-attr]
    a = analyze(SCAM, _FixedLLM(json.dumps(broken)))
    assert a.source == "rules"


def test_tactics_not_a_dict_falls_back() -> None:
    a = analyze(SCAM, _FixedLLM(json.dumps(_payload(tactics=[0.1, 0.2]))))
    assert a.source == "rules"


def test_boolean_intent_is_rejected() -> None:
    assert parse_llm_json(json.dumps(_payload(intent=True)), SCAM) is None


def test_all_evidence_hallucinated_is_discarded() -> None:
    resp = json.dumps(
        _payload(intent=0.9, evidence=["a fragment that appears nowhere in the call"])
    )
    a = analyze(SCAM, _FixedLLM(resp))
    assert a.source == "rules"


def test_partially_grounded_evidence_is_accepted() -> None:
    resp = json.dumps(
        _payload(intent=0.6, evidence=["Read me the OTP", "invented fragment"])
    )
    a = parse_llm_json(resp, SCAM)
    assert a is not None and a.source == "llm"


def test_empty_evidence_is_accepted() -> None:
    a = parse_llm_json(json.dumps(_payload(evidence=[])), SCAM)
    assert a is not None and a.source == "llm"


def test_raising_model_falls_back_to_rules() -> None:
    a = analyze(SCAM, _RaisingLLM())
    assert a.source == "rules"
    assert a.intent == analyze_rules(SCAM).intent


def test_no_llm_is_exactly_the_rules_scorer() -> None:
    for t in (*SCAM_TRANSCRIPTS[:3], *NORMAL_TRANSCRIPTS[:3]):
        assert analyze(t) == analyze_rules(t)


def test_llm_failure_on_thin_transcript_abstains() -> None:
    a = analyze("call me back later", _FixedLLM("garbage"))
    assert a.source == "none"
    assert a.intent == 0.0


def test_result_carries_no_transcript_text() -> None:
    resp = json.dumps(_payload(intent=0.7, evidence=["Read me the OTP"]))
    a = analyze(SCAM, _FixedLLM(resp))
    assert set(dataclasses.asdict(a)) == {
        "tactics",
        "intent",
        "confidence",
        "source",
        "mixed_channel",
    }
    assert isinstance(a, ScriptAnalysis)


def test_system_prompt_reaches_the_model() -> None:
    llm = _FixedLLM(json.dumps(_payload()))
    analyze(SCAM, llm)
    assert llm.seen_system == SYSTEM


def test_asr_noise_skips_the_model_and_abstains() -> None:
    llm = _FixedLLM(json.dumps(_payload(intent=0.99)))
    a = analyze("I am a star " * 12, llm)
    assert llm.calls == 0
    assert a.source == "none"
    assert a.intent == 0.0
