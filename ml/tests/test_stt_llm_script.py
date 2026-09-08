"""Smoke suite for the rules-only script channel. No model, no network.

What these pin down: the scam and ordinary transcript sets separate on ``intent``;
too little text abstains rather than guessing; the mixed-channel refusal strip
removes the recipient's words and a genuine disclaimer; every output stays in
range.
"""

from __future__ import annotations

import pytest

from ml.checks.stt_llm.eval_transcripts import NORMAL_TRANSCRIPTS, SCAM_TRANSCRIPTS
from ml.checks.stt_llm.tactics import (
    MIN_WORDS,
    TACTICS,
    analyze_rules,
    looks_like_asr_noise,
)

ALL_TRANSCRIPTS = SCAM_TRANSCRIPTS + NORMAL_TRANSCRIPTS


def test_transcript_sets_are_the_expected_size() -> None:
    assert len(SCAM_TRANSCRIPTS) == 10
    assert len(NORMAL_TRANSCRIPTS) == 10
    assert all(len(t.split()) >= MIN_WORDS for t in ALL_TRANSCRIPTS)


def test_scam_and_ordinary_separate_on_intent() -> None:
    scam = [analyze_rules(t).intent for t in SCAM_TRANSCRIPTS]
    normal = [analyze_rules(t).intent for t in NORMAL_TRANSCRIPTS]
    assert min(scam) > max(normal), (
        f"overlap: scam min {min(scam):.2f} vs ordinary max {max(normal):.2f}; "
        f"scam range {min(scam):.2f}-{max(scam):.2f}, "
        f"ordinary range {min(normal):.2f}-{max(normal):.2f}"
    )
    # Margin, not a bare inequality: a one-off pattern hit on an ordinary call
    # must not land anywhere near the scam band.
    assert min(scam) - max(normal) > 0.3


def test_every_scam_transcript_reads_as_a_script() -> None:
    for t in SCAM_TRANSCRIPTS:
        a = analyze_rules(t)
        assert a.source == "rules"
        assert a.intent >= 0.8, f"weak scam intent {a.intent:.2f} for: {t[:60]}..."


def test_every_ordinary_transcript_stays_below_the_elevated_line() -> None:
    for t in NORMAL_TRANSCRIPTS:
        assert analyze_rules(t).intent < 0.5


@pytest.mark.parametrize("transcript", ALL_TRANSCRIPTS)
def test_all_outputs_in_range(transcript: str) -> None:
    a = analyze_rules(transcript)
    assert 0.0 <= a.intent <= 1.0
    assert 0.0 <= a.confidence <= 1.0
    assert a.source in {"rules", "none"}
    assert set(a.tactics) == set(TACTICS)
    assert all(0.0 <= v <= 1.0 for v in a.tactics.values())


def test_short_transcript_abstains() -> None:
    a = analyze_rules("please call me back later today")
    assert a.source == "none"
    assert a.intent == 0.0
    assert a.confidence == 0.0
    assert all(v == 0.0 for v in a.tactics.values())


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_empty_transcript_abstains(blank: str) -> None:
    assert analyze_rules(blank).source == "none"


def test_refusal_and_disclaimer_sentences_are_stripped() -> None:
    transcript = (
        "I will not share the OTP or my UPI pin with you people. "
        "I am going to call the bank on the printed number to check this myself."
    )
    # Raw text: the OTP / UPI phrasing is present and scores.
    raw = analyze_rules(transcript, mixed_channel=False)
    assert raw.mixed_channel is False
    assert raw.tactics["irreversible_ask"] == 1.0

    # Mixed-channel: both sentences read as the recipient, get dropped, and what
    # is left is too short to judge, so the channel abstains.
    stripped = analyze_rules(transcript, mixed_channel=True)
    assert stripped.source == "none"
    assert stripped.tactics["irreversible_ask"] == 0.0


def test_bank_disclaimer_is_not_scored_as_a_tactic() -> None:
    # A real bank saying it will never ask for an OTP must not fire irreversible_ask.
    transcript = (
        "Good afternoon, this is a routine card check from your bank about a "
        "recent purchase at a fuel station. Nothing is wrong with your account. "
        "We will never ask for your OTP, PIN or card number on this call."
    )
    assert analyze_rules(transcript).tactics["irreversible_ask"] == 0.0


def test_script_category_is_the_dominant_tactic() -> None:
    credential_grab = (
        "Just tell me your account number, the OTP that arrives, your UPI pin and "
        "the card CVV, and read out the code from the message. It is a quick "
        "verification and takes only a minute of your time to finish."
    )
    a = analyze_rules(credential_grab)
    assert a.script_category() == "irreversible_ask"
    assert a.tactics[a.script_category()] == max(a.tactics.values())


def test_authority_and_secrecy_led_scam_names_one_of_its_top_tactics() -> None:
    a = analyze_rules(SCAM_TRANSCRIPTS[1])  # CBI / arrest-warrant script
    top_score = max(a.tactics.values())
    assert a.tactics[a.script_category()] == top_score
    assert {"authority", "secrecy"} & {name for name, _ in a.top_tactics(3)}


# Pure loops (low distinct-word ratio).
_HALLUCINATION_LOOP = "I am a star " * 12
_HELLO_LOOP = "hello " * 20

# Messier hallucinations, shaped like the real faster-whisper output on the two
# non-English Exotel calls: a phrase repeated among other junk, so the
# distinct-word ratio stays up but word pairs repeat.
_REAL_SHAPED = (
    (
        "Hello Hello Hello who is this guy I am a star what is your name "
        "I am a star say your name I am a star I am a star I am a star yes"
    ),
    (
        "he is like a soldier he is like a soldier he is like a soldier "
        "where are the girls they are near the beach did you come here yes I did"
    ),
)


def test_pure_repetition_loop_abstains() -> None:
    for loop in (_HALLUCINATION_LOOP, _HELLO_LOOP):
        assert looks_like_asr_noise(loop)
        a = analyze_rules(loop)
        assert a.source == "none"
        assert a.intent == 0.0
        assert all(v == 0.0 for v in a.tactics.values())


def test_messy_hallucination_abstains() -> None:
    for text in _REAL_SHAPED:
        assert looks_like_asr_noise(text)
        assert analyze_rules(text).source == "none"


def test_short_input_is_not_flagged_as_noise() -> None:
    # left to the MIN_WORDS gate, not this guard
    assert not looks_like_asr_noise("hello hello hello")


def test_real_transcripts_are_not_mistaken_for_noise() -> None:
    for t in ALL_TRANSCRIPTS:
        assert not looks_like_asr_noise(t)
