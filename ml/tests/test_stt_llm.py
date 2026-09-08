"""Smoke suite for check 4. Fake transcribers and the local scorer, no Whisper, no network.

The model halves are swappable by design, so everything here drives the check
through stub implementations. What is asserted is the contract: status
transitions, that a failure never produces a signal, and that the transcript
never reaches an evidence record.
"""

from __future__ import annotations

from datetime import UTC, datetime

from contracts.checks import CheckName, CheckStatus, ReasonCode, SttLlmSignal
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioBatch
from ml.checks.stt_llm.check import SttLlmCheck
from ml.checks.stt_llm.scorer import (
    CATEGORY_AUTHORITY,
    CATEGORY_NONE,
    FallbackScriptScorer,
    KeywordScriptScorer,
    ScriptAssessment,
)

SCAM_LINE = (
    "this is CBI calling, you are under digital arrest, do not tell anyone, "
    "transfer the money immediately to this account"
)
ORDINARY_LINE = "hi mom, i will be home by eight, do you need anything from the market"


class _FakeTranscriber:
    model_name = "fake-whisper"

    def __init__(self, text: str) -> None:
        self.text = text

    def warmup(self) -> None:
        return None

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        return self.text


class _RaisingTranscriber:
    model_name = "raising-whisper"

    def warmup(self) -> None:
        return None

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        raise RuntimeError("weights missing")


class _RaisingScorer:
    name = "raising-scorer"

    def score(self, transcript: str) -> ScriptAssessment:
        raise RuntimeError("api down")


class _OutOfRangeScorer:
    name = "out-of-range"

    def score(self, transcript: str) -> ScriptAssessment:
        return ScriptAssessment(4.2, CATEGORY_NONE, self.name)


def _batch(window_ms: int = 10000) -> CanonicalAudioBatch:
    samples = 16 * window_ms
    now = datetime.now(UTC)
    return CanonicalAudioBatch(
        stream_id="s1",
        call_id="c1",
        start_sequence=0,
        end_sequence=max(window_ms // 20 - 1, 0),
        pcm_s16le=b"\x00\x00" * samples,
        sample_count=samples,
        capture_started_at=now,
        capture_ended_at=now,
        window_ms=window_ms,
    )


def _context() -> CallContext:
    return CallContext(stream_id="s1", call_id="c1", started_at=datetime.now(UTC))


# --- the check's contract ---


def test_name_is_stt_llm() -> None:
    assert SttLlmCheck().name is CheckName.STT_LLM


def test_scam_script_produces_a_high_risk_signal() -> None:
    check = SttLlmCheck(_FakeTranscriber(SCAM_LINE), KeywordScriptScorer())
    result = check.run(_batch(), _context())
    assert result.status is CheckStatus.OK
    assert isinstance(result.signal, SttLlmSignal)
    assert result.signal.script_risk >= 0.5
    assert result.evidence[0].reason_code is ReasonCode.SCRIPT_RISK_HIGH


def test_ordinary_conversation_produces_a_zero_risk_signal() -> None:
    check = SttLlmCheck(_FakeTranscriber(ORDINARY_LINE), KeywordScriptScorer())
    result = check.run(_batch(), _context())
    assert result.status is CheckStatus.OK
    assert result.signal is not None
    assert result.signal.script_risk == 0.0
    assert result.evidence[0].reason_code is ReasonCode.SCRIPT_RISK_ABSENT


def test_silence_transcribes_empty_and_is_not_a_scam() -> None:
    check = SttLlmCheck(_FakeTranscriber(""), KeywordScriptScorer())
    result = check.run(_batch(), _context())
    assert result.status is CheckStatus.OK
    assert result.signal is not None
    assert result.signal.script_risk == 0.0


def test_short_window_is_skipped_without_a_signal() -> None:
    check = SttLlmCheck(_FakeTranscriber(SCAM_LINE), KeywordScriptScorer())
    result = check.run(_batch(window_ms=1000), _context())
    assert result.status is CheckStatus.SKIPPED
    assert result.signal is None
    assert result.evidence[0].reason_code is ReasonCode.INSUFFICIENT_AUDIO


def test_no_models_configured_is_failed_never_ok() -> None:
    result = SttLlmCheck().run(_batch(), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None


def test_transcriber_error_is_failed_and_never_a_verdict() -> None:
    check = SttLlmCheck(_RaisingTranscriber(), KeywordScriptScorer())
    result = check.run(_batch(), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None
    assert result.evidence[0].reason_code is ReasonCode.DEGRADED_CHECK


def test_scorer_error_is_failed_and_never_a_verdict() -> None:
    check = SttLlmCheck(_FakeTranscriber(SCAM_LINE), _RaisingScorer())
    result = check.run(_batch(), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None


def test_out_of_range_score_is_rejected_rather_than_clamped() -> None:
    check = SttLlmCheck(_FakeTranscriber(SCAM_LINE), _OutOfRangeScorer())
    result = check.run(_batch(), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None


def test_evidence_never_contains_the_transcript() -> None:
    """contracts/checks.py requires the words never reach an evidence record."""
    secret = "my account number is 1234 and my mother is in hospital"
    check = SttLlmCheck(_FakeTranscriber(secret), KeywordScriptScorer())
    result = check.run(_batch(), _context())
    blob = " ".join(item.detail for item in result.evidence)
    assert "account number" not in blob
    assert "1234" not in blob
    for word in ("hospital", "mother"):
        assert word not in blob


# --- the local keyword scorer ---


def test_keyword_scorer_scores_ordinary_speech_at_zero() -> None:
    assert KeywordScriptScorer().score(ORDINARY_LINE).script_risk == 0.0


def test_keyword_scorer_flags_the_authority_script() -> None:
    assessment = KeywordScriptScorer().score(SCAM_LINE)
    assert assessment.script_risk >= 0.5
    assert assessment.category == CATEGORY_AUTHORITY


def test_keyword_scorer_never_exceeds_one() -> None:
    piled_on = " ".join([SCAM_LINE] * 10) + " otp cvv upi pin gift card bitcoin"
    assert KeywordScriptScorer().score(piled_on).script_risk <= 1.0


def test_empty_transcript_scores_zero() -> None:
    assert KeywordScriptScorer().score("   ").script_risk == 0.0


# --- the fallback wrapper, which is what keeps check 4 alive without Groq ---


def test_fallback_uses_the_local_scorer_when_the_primary_raises() -> None:
    scorer = FallbackScriptScorer(_RaisingScorer(), KeywordScriptScorer())
    assessment = scorer.score(SCAM_LINE)
    assert assessment.script_risk >= 0.5
    assert assessment.scorer == KeywordScriptScorer.name


def test_fallback_prefers_the_primary_when_it_works() -> None:
    class Working:
        name = "working"

        def score(self, transcript: str) -> ScriptAssessment:
            return ScriptAssessment(0.42, CATEGORY_NONE, self.name)

    scorer = FallbackScriptScorer(Working(), KeywordScriptScorer())
    assert scorer.score(SCAM_LINE).scorer == "working"


def test_fallback_with_no_primary_is_just_the_local_scorer() -> None:
    scorer = FallbackScriptScorer(None, KeywordScriptScorer())
    assert scorer.score(SCAM_LINE).scorer == KeywordScriptScorer.name
