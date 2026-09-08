"""Tests for the machine_fingerprint check as it runs inside the backend.

Written against the real check, not the pre-merge RMS-energy stub: a check with no
scorer configured is FAILED (never a fabricated signal), a scorer that raises is
FAILED, and a configured check emits a signal whose status depends on window
length. The pipeline's own ~1 s windows are below degraded_window_ms, so DEGRADED
with the caveat attached is what a real window produces; OK needs a longer one.
All fake scorers, so the suite runs without torch; the model itself is covered in
`ml/tests` on the machine that owns it.
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime

from contracts.checks import (
    CheckName,
    CheckStatus,
    MachineFingerprintSignal,
    ReasonCode,
)
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioBatch
from ml.checks.machine_fingerprint.check import MachineFingerprintCheck

N_SAMPLES = 16000  # 1 second at 16 kHz


class _FixedScorer:
    model_name = "fixed-test-scorer"
    model_version = "0"

    def __init__(self, value: float) -> None:
        self.value = value

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        return self.value


class _RaisingScorer:
    model_name = "raising-test-scorer"
    model_version = "0"

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        raise RuntimeError("checkpoint missing")


def _batch(pcm: bytes, window_ms: int = 1000) -> CanonicalAudioBatch:
    now = datetime.now(UTC)
    return CanonicalAudioBatch(
        stream_id="s1",
        call_id="c1",
        start_sequence=0,
        end_sequence=max(window_ms // 20 - 1, 0),
        pcm_s16le=pcm,
        sample_count=len(pcm) // 2,
        capture_started_at=now,
        capture_ended_at=now,
        window_ms=window_ms,
    )


def _silence(samples: int = N_SAMPLES) -> bytes:
    return b"\x00\x00" * samples


def _loud_tone() -> bytes:
    samples = [16000 if i % 2 == 0 else -16000 for i in range(N_SAMPLES)]
    return struct.pack(f"<{N_SAMPLES}h", *samples)


def _context() -> CallContext:
    return CallContext(stream_id="s1", call_id="c1", started_at=datetime.now(UTC))


def test_name_is_machine_fingerprint() -> None:
    assert MachineFingerprintCheck().name is CheckName.MACHINE_FINGERPRINT


def test_no_scorer_configured_is_failed_never_ok() -> None:
    check = MachineFingerprintCheck()
    result = check.run(_batch(_silence()), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None
    assert [item.reason_code for item in result.evidence] == [ReasonCode.DEGRADED_CHECK]


def test_configured_check_returns_signal_for_one_second_window() -> None:
    # The pipeline buffers ~1 s windows, which are below degraded_window_ms
    # (3000), so a real window comes back DEGRADED: signal present, caveated.
    check = MachineFingerprintCheck(_FixedScorer(0.92))
    result = check.run(_batch(_silence()), _context())
    assert result.status is CheckStatus.DEGRADED
    assert isinstance(result.signal, MachineFingerprintSignal)
    assert 0.0 <= result.signal.synthetic_probability <= 1.0
    assert ReasonCode.DEGRADED_CHECK in [item.reason_code for item in result.evidence]


def test_configured_check_returns_ok_for_a_full_length_window() -> None:
    # A window at or above degraded_window_ms reaches the unqualified OK path.
    check = MachineFingerprintCheck(_FixedScorer(0.92))
    result = check.run(_batch(_silence(N_SAMPLES * 4), window_ms=4000), _context())
    assert result.status is CheckStatus.OK
    assert isinstance(result.signal, MachineFingerprintSignal)
    assert 0.0 <= result.signal.synthetic_probability <= 1.0


def test_deterministic_for_same_input() -> None:
    check = MachineFingerprintCheck(_FixedScorer(0.92))
    batch = _batch(_loud_tone())
    context = _context()
    first = check.run(batch, context)
    second = check.run(batch, context)
    assert first.signal is not None and second.signal is not None
    assert first.signal.synthetic_probability == second.signal.synthetic_probability


def test_short_window_is_skipped_without_a_signal() -> None:
    check = MachineFingerprintCheck(_FixedScorer(0.92))
    result = check.run(_batch(_silence(), window_ms=500), _context())
    assert result.status is CheckStatus.SKIPPED
    assert result.signal is None
    assert [item.reason_code for item in result.evidence] == [
        ReasonCode.INSUFFICIENT_AUDIO
    ]


def test_scorer_error_is_failed_and_never_a_verdict() -> None:
    check = MachineFingerprintCheck(_RaisingScorer())
    result = check.run(_batch(_silence()), _context())
    assert result.status is CheckStatus.FAILED
    assert result.signal is None
    assert [item.reason_code for item in result.evidence] == [ReasonCode.DEGRADED_CHECK]
