"""Stage 04 stub: machine_fingerprint check.

Deterministic RMS-energy placeholder standing in for the real XLS-R + AASIST
model. _synthetic_probability_from_energy is the one function a real model swap
replaces; everything else here is just the Check protocol's plumbing.
"""

from __future__ import annotations

import array
import math
from datetime import UTC, datetime

from contracts.checks import (
    CheckName,
    CheckResult,
    CheckStatus,
    EvidenceItem,
    MachineFingerprintSignal,
    ReasonCode,
)
from contracts.context import CallContext
from contracts.pipeline import CanonicalAudioBatch


def _rms_int16(pcm: bytes) -> float:
    """Duplicated from backend/app/pipeline/buffer.py.

    ml/checks/* must never import backend/ (docs/interfaces.md section 8's import
    rule matrix), and there is no existing shared non-contracts location for
    ~6 lines of stdlib math.
    """
    if not pcm:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm)
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return math.sqrt(mean_square)


_ENERGY_MIDPOINT = 4000.0
_ENERGY_SCALE = 2000.0


def _synthetic_probability_from_energy(pcm: bytes) -> float:
    """Deterministic placeholder: higher energy maps to a higher reading.

    Has no bearing on actual synthetic-speech detection. Swap this one function
    for real XLS-R + AASIST inference; the rest of MachineFingerprintCheck stays.
    """
    rms = _rms_int16(pcm)
    scaled = (rms - _ENERGY_MIDPOINT) / _ENERGY_SCALE
    probability = 1.0 / (1.0 + math.exp(-scaled))
    return max(0.0, min(1.0, probability))


class MachineFingerprintCheck:
    """Implements contracts.checks.Check for CheckName.MACHINE_FINGERPRINT."""

    name = CheckName.MACHINE_FINGERPRINT

    def run(self, batch: CanonicalAudioBatch, context: CallContext) -> CheckResult:
        probability = _synthetic_probability_from_energy(batch.pcm_s16le)
        reason = (
            ReasonCode.FINGERPRINT_SYNTHETIC
            if probability >= 0.5
            else ReasonCode.FINGERPRINT_GENUINE
        )
        return CheckResult(
            check=CheckName.MACHINE_FINGERPRINT,
            status=CheckStatus.OK,
            signal=MachineFingerprintSignal(synthetic_probability=probability),
            evidence=[
                EvidenceItem(
                    reason_code=reason,
                    detail="stub: RMS-energy placeholder, not a trained model",
                    model="stub-rms-energy",
                    model_version="0.0.0",
                    window_started_at=batch.capture_started_at,
                )
            ],
            processed_at=datetime.now(UTC),
            window_ms=batch.window_ms,
        )
