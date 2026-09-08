"""One schema, checked end to end.

RESPONSE_SCHEMA is the wire contract for every `ScriptLLM.complete()` response.
These tests pin that:
- the JSON example baked into the SYSTEM prompt is an instance of it,
- `schema_errors` flags each way a response can depart from it,
- `parse_llm_json` accepts every response `schema_errors` calls clean,
- and every `ScriptAnalysis` that leaves this package has the same locked shape,
  because `__post_init__` refuses to build a malformed one.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from ml.checks.stt_llm import RESPONSE_SCHEMA, SYSTEM, parse_llm_json, schema_errors
from ml.checks.stt_llm.eval_transcripts import NORMAL_TRANSCRIPTS, SCAM_TRANSCRIPTS
from ml.checks.stt_llm.tactics import TACTICS, ScriptAnalysis, _empty, analyze_rules

_ANALYSIS_FIELDS = {"tactics", "intent", "confidence", "source", "mixed_channel"}


def _valid(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "tactics": {t: 0.0 for t in TACTICS},
        "intent": 0.0,
        "evidence": [],
        "confidence": 0.5,
    }
    body.update(over)
    return body


# --- the schema itself -------------------------------------------------------


def test_schema_requires_the_four_keys_and_the_five_tactics() -> None:
    assert set(RESPONSE_SCHEMA["required"]) == {
        "tactics",
        "intent",
        "evidence",
        "confidence",
    }
    tactics = RESPONSE_SCHEMA["properties"]["tactics"]
    assert set(tactics["required"]) == set(TACTICS)
    assert set(tactics["properties"]) == set(TACTICS)


def test_system_prompt_example_is_a_schema_instance() -> None:
    start = SYSTEM.index('{"tactics"')
    example, _end = json.JSONDecoder().raw_decode(SYSTEM[start:])
    assert schema_errors(example) == []


# --- schema_errors ---------------------------------------------------------


def test_a_clean_response_has_no_errors() -> None:
    assert schema_errors(_valid()) == []
    assert schema_errors(_valid(intent=1.0, confidence=1.0, evidence=["a", "b", "c"])) == []


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda d: d.pop("tactics"), "missing 'tactics'"),
        (lambda d: d.pop("intent"), "missing 'intent'"),
        (lambda d: d.pop("evidence"), "missing 'evidence'"),
        (lambda d: d.pop("confidence"), "missing 'confidence'"),
        (lambda d: d.update(extra=1), "unexpected key 'extra'"),
        (lambda d: d["tactics"].pop("authority"), "tactics: missing 'authority'"),
        (lambda d: d["tactics"].update(rage=0.5), "tactics: unexpected 'rage'"),
        (lambda d: d["tactics"].update(urgency="high"), "tactics.urgency"),
        (lambda d: d["tactics"].update(urgency=1.5), "out of [0, 1]"),
        (lambda d: d.update(intent=True), "intent"),
        (lambda d: d.update(intent=2.0), "intent: 2.0 out of [0, 1]"),
        (lambda d: d.update(evidence="a string"), "evidence: not an array"),
        (lambda d: d.update(evidence=["a", "b", "c", "d"]), "evidence: 4 items, max 3"),
        (lambda d: d.update(evidence=[1, 2]), "non-string item"),
    ],
)
def test_schema_errors_flags_each_departure(mutate, needle: str) -> None:
    data = _valid()
    mutate(data)
    errs = schema_errors(data)
    assert any(needle in e for e in errs), f"{needle!r} not in {errs}"


def test_non_object_response() -> None:
    assert schema_errors("[]") == ["top level is not a JSON object"]
    assert schema_errors([1, 2]) == ["top level is not a JSON object"]


# --- schema_errors clean implies parse_llm_json accepts structurally --------

_TRANSCRIPT = "please transfer the money now and share the otp with me right away"


@pytest.mark.parametrize(
    "payload",
    [
        _valid(),
        _valid(intent=0.9, confidence=0.2),
        _valid(intent=0.9, evidence=["transfer the money"]),  # grounded quote
        _valid(tactics={**{t: 0.3 for t in TACTICS}, "authority": 1.0}, intent=0.7),
    ],
)
def test_conformant_response_parses_structurally(payload: dict) -> None:
    assert schema_errors(payload) == []
    result = parse_llm_json(json.dumps(payload), _TRANSCRIPT)
    assert result is not None
    assert result.source == "llm"


def test_fabrication_gate_is_semantic_not_schema() -> None:
    # schema-clean, but every quote is invented and intent is high -> rejected
    payload = _valid(intent=0.9, evidence=["a phrase that is nowhere in the call"])
    assert schema_errors(payload) == []
    assert parse_llm_json(json.dumps(payload), _TRANSCRIPT) is None


# --- ScriptAnalysis is self-validating -----------------------------------


def test_post_init_rejects_wrong_tactic_keys() -> None:
    with pytest.raises(ValueError, match="tactics keys"):
        ScriptAnalysis(tactics={"urgency": 0.0}, intent=0.0, confidence=0.0, source="rules")


@pytest.mark.parametrize("bad", [1.5, -0.1, "x", True, float("nan")])
def test_post_init_rejects_out_of_range_scores(bad: object) -> None:
    with pytest.raises(ValueError):
        ScriptAnalysis(
            tactics={**{t: 0.0 for t in TACTICS}, "urgency": bad},
            intent=0.0,
            confidence=0.0,
            source="rules",
        )


def test_post_init_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="source"):
        ScriptAnalysis(
            tactics={t: 0.0 for t in TACTICS},
            intent=0.0,
            confidence=0.0,
            source="model",  # type: ignore[arg-type]
        )


def test_every_construction_path_has_the_same_shape() -> None:
    from_rules = analyze_rules(SCAM_TRANSCRIPTS[0])
    from_empty = _empty(mixed_channel=True)
    from_parse = parse_llm_json(json.dumps(_valid(intent=0.4)), "transcript")
    assert from_parse is not None
    for result in (from_rules, from_empty, from_parse):
        assert {f.name for f in dataclasses.fields(result)} == _ANALYSIS_FIELDS
        assert set(result.tactics) == set(TACTICS)
        assert 0.0 <= result.intent <= 1.0
        assert result.source in ("llm", "rules", "none")


def test_all_eval_transcripts_produce_valid_analyses() -> None:
    # analyze_rules builds a ScriptAnalysis for each; __post_init__ would raise
    # on a malformed one, so reaching the asserts means all 20 are well formed.
    for text in (*SCAM_TRANSCRIPTS, *NORMAL_TRANSCRIPTS):
        a = analyze_rules(text)
        assert {f.name for f in dataclasses.fields(a)} == _ANALYSIS_FIELDS
