"""Tests for the machine_fingerprint stub check."""

from __future__ import annotations

import struct
from datetime import UTC, datetime

from contracts.checks import CheckStatus, MachineFingerprintSignal
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioBatch
from ml.checks.machine_fingerprint.check import MachineFingerprintCheck

N_SAMPLES = 16000  # 1 second at 16 kHz


def _batch(pcm: bytes) -> CanonicalAudioBatch:
    now = datetime.now(UTC)
    return CanonicalAudioBatch(
        stream_id="s1",
        call_id="c1",
        start_sequence=0,
        end_sequence=49,
        pcm_s16le=pcm,
        sample_count=len(pcm) // 2,
        capture_started_at=now,
        capture_ended_at=now,
        window_ms=1000,
    )


def _silence() -> bytes:
    return b"\x00\x00" * N_SAMPLES


def _loud_tone() -> bytes:
    samples = [16000 if i % 2 == 0 else -16000 for i in range(N_SAMPLES)]
    return struct.pack(f"<{N_SAMPLES}h", *samples)


def _context() -> CallContext:
    return CallContext(stream_id="s1", call_id="c1", started_at=datetime.now(UTC))


def test_returns_ok_with_probability_in_range() -> None:
    check = MachineFingerprintCheck()
    result = check.run(_batch(_silence()), _context())
    assert result.status == CheckStatus.OK
    assert isinstance(result.signal, MachineFingerprintSignal)
    assert 0.0 <= result.signal.synthetic_probability <= 1.0


def test_deterministic_for_same_input() -> None:
    check = MachineFingerprintCheck()
    batch = _batch(_loud_tone())
    context = _context()
    first = check.run(batch, context)
    second = check.run(batch, context)
    assert first.signal.synthetic_probability == second.signal.synthetic_probability


def test_silence_and_loud_tone_differ() -> None:
    check = MachineFingerprintCheck()
    context = _context()
    quiet = check.run(_batch(_silence()), context)
    loud = check.run(_batch(_loud_tone()), context)
    assert quiet.signal.synthetic_probability != loud.signal.synthetic_probability
