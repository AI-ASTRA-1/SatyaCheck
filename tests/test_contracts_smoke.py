"""Contract verification: types import, JSON round-trip, framing rules.

These two files are permissioned in the contracts-only phase because they verify
the contract itself, not application logic. No pipeline, server, models or app code
exists yet.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter

import contracts as c


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_every_public_type_imports() -> None:
    for name in c.__all__:
        assert getattr(c, name) is not None


def test_risk_update_round_trips() -> None:
    update = c.RiskUpdate(
        stream_id="s1",
        call_id="c1",
        sequence=1,
        timestamp=_now(),
        score=73,
        verdict=c.RiskVerdict.SYNTHETIC,
        risk_level=c.RiskLevel.HIGH,
        confidence=0.81,
        reasons=[c.ReasonCode.FINGERPRINT_SYNTHETIC],
        contributing_checks=[c.CheckName.MACHINE_FINGERPRINT],
    )
    assert c.RiskUpdate.model_validate_json(update.model_dump_json()) == update


def test_canonical_chunk_round_trips() -> None:
    chunk = c.CanonicalAudioChunk(
        stream_id="s1",
        call_id="c1",
        sequence=0,
        pcm_s16le=b"\x00\x00" * (c.CANONICAL_FRAME_BYTES // 2),
        capture_timestamp=_now(),
        ingest_timestamp=_now(),
    )
    assert c.CanonicalAudioChunk.model_validate_json(chunk.model_dump_json()) == chunk


def test_canonical_chunk_rejects_wrong_frame_size() -> None:
    with pytest.raises(ValueError):
        c.CanonicalAudioChunk(
            stream_id="s1",
            call_id="c1",
            sequence=0,
            pcm_s16le=b"\x00\x00" * 10,
            capture_timestamp=_now(),
            ingest_timestamp=_now(),
        )


def test_final_chunk_may_be_short() -> None:
    chunk = c.CanonicalAudioChunk(
        stream_id="s1",
        call_id="c1",
        sequence=5,
        pcm_s16le=b"\x00\x00",
        capture_timestamp=_now(),
        ingest_timestamp=_now(),
        is_final=True,
    )
    assert chunk.is_final


def test_canonical_chunk_has_no_transport_fields() -> None:
    fields = set(c.CanonicalAudioChunk.model_fields)
    assert "transport" not in fields
    assert "codec" not in fields
    assert "sample_rate" not in fields


def test_app_message_discriminates_on_kind() -> None:
    payload = {
        "kind": "risk_update",
        "stream_id": "s1",
        "call_id": "c1",
        "sequence": 2,
        "timestamp": "2026-09-06T10:00:00Z",
        "score": 50,
        "verdict": "unknown",
        "risk_level": "low",
        "confidence": 0.5,
    }
    msg = TypeAdapter(c.AppMessage).validate_python(payload)
    assert isinstance(msg, c.RiskUpdate)


def test_default_band_mapping_matches_risk_levels() -> None:
    assert set(c.DEFAULT_BAND_MAPPING.values()) <= set(c.RiskLevel)
    assert c.DEFAULT_BAND_MAPPING[0] == c.RiskLevel.LOW