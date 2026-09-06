"""Canonical audio below stage 02.

Only CanonicalAudioChunk and CanonicalAudioBatch flow through the pipeline, checks
and fusion. By construction they carry no transport, codec or sample-rate field, so
nothing below ingestion can branch on which transport delivered the audio. The
transport invariant is structural, not advisory.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, model_validator

#: 20 ms of mono 16-bit little-endian PCM at 16 kHz = 320 samples = 640 bytes.
#: The ML lead confirms this against the fine-tuned model input specs in the same
#: change that adds stage 04, before the decoder and the checks freeze. It is a
#: single constant for exactly that reason.
CANONICAL_SAMPLE_RATE = 16000
CANONICAL_FRAME_MS = 20
CANONICAL_FRAME_BYTES = CANONICAL_SAMPLE_RATE // (1000 // CANONICAL_FRAME_MS) * 2


class CanonicalAudioChunk(BaseModel):
    """One 20 ms canonical frame. No codec field, no transport field, no sample rate.

    sequence is renumbered from 0 at ingestion. pcm_s16le is mono, little-endian
    signed 16-bit PCM at CANONICAL_SAMPLE_RATE, exactly CANONICAL_FRAME_BYTES per
    non-final frame. is_final marks the short tail of a partial final frame on
    StreamClose; checks must tolerate it.
    """

    stream_id: str
    call_id: str
    sequence: int
    pcm_s16le: bytes
    capture_timestamp: datetime
    ingest_timestamp: datetime
    is_final: bool = False

    @model_validator(mode="after")
    def _exact_frame_size(self) -> CanonicalAudioChunk:
        if not self.is_final and len(self.pcm_s16le) != CANONICAL_FRAME_BYTES:
            raise ValueError(
                f"non-final frame must be {CANONICAL_FRAME_BYTES} bytes, got {len(self.pcm_s16le)}"
            )
        return self


class CanonicalAudioBatch(BaseModel):
    """A contiguous window of canonical PCM handed to the checks.

    This is a COPY. Checks MUST NOT mutate it; the audio is analysed out-of-band on
    a copy while the listener hears the original.
    """

    stream_id: str
    call_id: str
    start_sequence: int
    end_sequence: int
    pcm_s16le: bytes
    sample_count: int
    capture_started_at: datetime
    capture_ended_at: datetime
    window_ms: int