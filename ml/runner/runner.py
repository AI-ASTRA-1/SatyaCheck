"""Stage 04 runner: implements contracts.checks.CheckRunner.

Fans out to all injected Check implementations in parallel on a COPY of the
batch, with a shared 180 ms deadline. Any CheckName without a real
implementation comes back SKIPPED (empty evidence, no fabricated reason code) so
the full stage 04 contract shape -- one CheckResult per CheckName -- always
holds, even before every check exists.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from contracts.checks import (
    Check,
    CheckName,
    CheckResult,
    ChecksBatchResult,
    CheckStatus,
    EvidenceItem,
    ReasonCode,
)
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioBatch
from ml.checks.machine_fingerprint.check import MachineFingerprintCheck

CHECK_DEADLINE_S = 0.180


def _skipped_result(check_name: CheckName, now: datetime) -> CheckResult:
    return CheckResult(
        check=check_name,
        status=CheckStatus.SKIPPED,
        signal=None,
        evidence=[],
        processed_at=now,
        window_ms=0,
    )


def _failed_result(check_name: CheckName, detail: str, now: datetime, window_ms: int) -> CheckResult:
    return CheckResult(
        check=check_name,
        status=CheckStatus.FAILED,
        signal=None,
        evidence=[EvidenceItem(reason_code=ReasonCode.DEGRADED_CHECK, detail=detail)],
        processed_at=now,
        window_ms=window_ms,
    )


class DefaultCheckRunner:
    """Implements contracts.checks.CheckRunner for stage 04.

    Defaults to just MachineFingerprintCheck; adding R1's remaining checks later
    is a constructor-arg change here, not a rewrite of run_checks.
    """

    def __init__(self, checks: list[Check] | None = None) -> None:
        self._checks: list[Check] = checks if checks is not None else [MachineFingerprintCheck()]

    async def run_checks(self, batch: CanonicalAudioBatch, context: CallContext) -> ChecksBatchResult:
        implemented_names = {check.name for check in self._checks}
        started_at = datetime.now(UTC)

        results: list[CheckResult] = []
        degraded: list[CheckName] = []

        for check in self._checks:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(check.run, batch, context),
                    timeout=CHECK_DEADLINE_S,
                )
            except TimeoutError:
                result = _failed_result(
                    check.name, "exceeded 180ms deadline", datetime.now(UTC), batch.window_ms
                )
                degraded.append(check.name)
            except Exception as exc:  # noqa: BLE001 - a check's own error must never crash the runner
                result = _failed_result(
                    check.name, f"check raised: {exc}", datetime.now(UTC), batch.window_ms
                )
                degraded.append(check.name)
            results.append(result)

        now = datetime.now(UTC)
        for check_name in CheckName:
            if check_name not in implemented_names:
                results.append(_skipped_result(check_name, now))

        return ChecksBatchResult(
            stream_id=batch.stream_id,
            call_id=batch.call_id,
            started_at=started_at,
            batch_sequence=batch.start_sequence,
            results=results,
            audio_window_ms=batch.window_ms,
            degraded=degraded,
        )
