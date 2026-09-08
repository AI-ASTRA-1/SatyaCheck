"""Tests for the stage 04 DefaultCheckRunner."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from contracts.checks import (
    CheckName,
    CheckResult,
    CheckStatus,
    MachineFingerprintSignal,
)
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioBatch
from ml.runner.runner import DefaultCheckRunner


def _batch() -> CanonicalAudioBatch:
    now = datetime.now(UTC)
    pcm = b"\x00\x00" * 16000
    return CanonicalAudioBatch(
        stream_id="s1",
        call_id="c1",
        start_sequence=0,
        end_sequence=49,
        pcm_s16le=pcm,
        sample_count=16000,
        capture_started_at=now,
        capture_ended_at=now,
        window_ms=1000,
    )


def _context() -> CallContext:
    return CallContext(stream_id="s1", call_id="c1", started_at=datetime.now(UTC))


def test_every_check_name_gets_exactly_one_result() -> None:
    runner = DefaultCheckRunner()

    async def run() -> None:
        return await runner.run_checks(_batch(), _context())

    result = asyncio.run(run())
    assert {r.check for r in result.results} == set(CheckName)


class _FixedFingerprintScorer:
    model_name = "fixed-test-scorer"
    model_version = "0"

    def warmup(self) -> None:
        return None

    def score(self, pcm_s16le: bytes, sample_rate: int) -> float:
        return 0.92


def test_only_machine_fingerprint_is_implemented_rest_are_skipped() -> None:
    # Inject a configured check: the default no-scorer check is FAILED by design
    # (a model that is not there must never fabricate a signal).
    from ml.checks.machine_fingerprint.check import MachineFingerprintCheck

    runner = DefaultCheckRunner(checks=[MachineFingerprintCheck(_FixedFingerprintScorer())])

    async def run() -> None:
        return await runner.run_checks(_batch(), _context())

    result = asyncio.run(run())
    by_check = {r.check: r for r in result.results}

    # A 1 s batch is below the check's degraded_window_ms, so DEGRADED with a
    # signal present is the honest status the pipeline's real windows produce.
    assert by_check[CheckName.MACHINE_FINGERPRINT].status == CheckStatus.DEGRADED
    assert isinstance(by_check[CheckName.MACHINE_FINGERPRINT].signal, MachineFingerprintSignal)

    for name in (CheckName.SPEAKER_IDENTITY, CheckName.PROSODY, CheckName.STT_LLM):
        assert by_check[name].status == CheckStatus.SKIPPED
        assert by_check[name].signal is None
        assert by_check[name].evidence == []


def test_slow_check_is_marked_failed_and_degraded_without_blocking_the_deadline() -> None:
    class SlowCheck:
        name = CheckName.MACHINE_FINGERPRINT

        def run(self, batch: CanonicalAudioBatch, context: CallContext) -> CheckResult:
            time.sleep(1.0)
            raise AssertionError("should not complete before the runner times out")

    runner = DefaultCheckRunner(checks=[SlowCheck()])

    async def run() -> CheckResult:
        started = time.monotonic()
        result = await runner.run_checks(_batch(), _context())
        elapsed = time.monotonic() - started
        assert elapsed < 0.5
        return result

    result = asyncio.run(run())
    fingerprint_result = next(r for r in result.results if r.check == CheckName.MACHINE_FINGERPRINT)
    assert fingerprint_result.status == CheckStatus.FAILED
    assert CheckName.MACHINE_FINGERPRINT in result.degraded


def test_raising_check_is_marked_failed_without_crashing_the_runner() -> None:
    class RaisingCheck:
        name = CheckName.MACHINE_FINGERPRINT

        def run(self, batch: CanonicalAudioBatch, context: CallContext) -> CheckResult:
            raise RuntimeError("model exploded")

    runner = DefaultCheckRunner(checks=[RaisingCheck()])

    async def run() -> CheckResult:
        return await runner.run_checks(_batch(), _context())

    result = asyncio.run(run())
    fingerprint_result = next(r for r in result.results if r.check == CheckName.MACHINE_FINGERPRINT)
    assert fingerprint_result.status == CheckStatus.FAILED
    assert CheckName.MACHINE_FINGERPRINT in result.degraded
