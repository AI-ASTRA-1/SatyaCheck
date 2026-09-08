"""ITU-T G.711 mu-law and A-law, vectorised in numpy.

Implemented here rather than taken from a package because `audioop` was removed from
the standard library in Python 3.13, and this keeps the training pipeline free of a
runtime dependency for what is forty lines of bit manipulation. It follows the
reference G.711 implementation exactly; ffmpeg is the oracle in the tests, not the
source of the values.

G.711 is the codec on an ordinary telephone call. A model that has never seen its
quantisation noise has never seen a phone call. A-law is the variant used across
most of the world including India, mu-law is North America and Japan, so both are
here.
"""

from __future__ import annotations

import numpy as np

_BIAS = 0x84  # 132
_MULAW_CLIP = 8159
_ALAW_CLIP = 0xFFF

_SEG_UEND = np.array([0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF], dtype=np.int32)
_SEG_AEND = np.array([0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF], dtype=np.int32)


def _to_int16(samples: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(samples, dtype=np.float32) * 32768.0, -32768, 32767).astype(np.int32)


def _to_float(pcm: np.ndarray) -> np.ndarray:
    return (np.clip(pcm, -32768, 32767).astype(np.float32) / 32768.0).astype(np.float32)


def _segment(value: np.ndarray, table: np.ndarray) -> np.ndarray:
    """Index of the first table entry the value does not exceed, 0 to 8."""
    return (value[:, None] > table[None, :]).sum(axis=1).astype(np.int32)


def mulaw_encode(samples: np.ndarray) -> np.ndarray:
    """float32 in [-1, 1] to 8-bit mu-law."""
    pcm = _to_int16(samples) >> 2
    negative = pcm < 0
    magnitude = np.where(negative, -pcm, pcm)
    mask = np.where(negative, 0x7F, 0xFF).astype(np.int32)

    magnitude = np.minimum(magnitude, _MULAW_CLIP) + (_BIAS >> 2)
    segment = _segment(magnitude, _SEG_UEND)

    shift = np.minimum(segment + 1, 15)
    encoded = ((segment << 4) | ((magnitude >> shift) & 0x0F)) ^ mask
    encoded = np.where(segment >= 8, 0x7F ^ mask, encoded)
    return encoded.astype(np.uint8)


def mulaw_decode(encoded: np.ndarray) -> np.ndarray:
    """8-bit mu-law to float32 in [-1, 1]."""
    value = (~np.asarray(encoded, dtype=np.uint8).astype(np.int32)) & 0xFF
    magnitude = (((value & 0x0F) << 3) + _BIAS) << ((value & 0x70) >> 4)
    pcm = np.where((value & 0x80) != 0, _BIAS - magnitude, magnitude - _BIAS)
    return _to_float(pcm)


def alaw_encode(samples: np.ndarray) -> np.ndarray:
    """float32 in [-1, 1] to 8-bit A-law."""
    pcm = _to_int16(samples) >> 3
    negative = pcm < 0
    magnitude = np.where(negative, -pcm - 1, pcm)
    mask = np.where(negative, 0x55, 0xD5).astype(np.int32)

    magnitude = np.minimum(magnitude, _ALAW_CLIP)
    segment = _segment(magnitude, _SEG_AEND)

    mantissa = np.where(
        segment < 2,
        (magnitude >> 1) & 0x0F,
        (magnitude >> np.minimum(segment, 15)) & 0x0F,
    )
    encoded = ((segment << 4) | mantissa) ^ mask
    encoded = np.where(segment >= 8, 0x7F ^ mask, encoded)
    return encoded.astype(np.uint8)


def alaw_decode(encoded: np.ndarray) -> np.ndarray:
    """8-bit A-law to float32 in [-1, 1]."""
    value = np.asarray(encoded, dtype=np.uint8).astype(np.int32) ^ 0x55
    mantissa = (value & 0x0F) << 4
    segment = (value & 0x70) >> 4

    magnitude = np.where(
        segment == 0,
        mantissa + 8,
        (mantissa + 0x108) << np.maximum(segment - 1, 0),
    )
    pcm = np.where((value & 0x80) != 0, magnitude, -magnitude)
    return _to_float(pcm)


def mulaw_round_trip(samples: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Encode to mu-law and back. Length and dtype preserved, detail is not."""
    return mulaw_decode(mulaw_encode(samples))


def alaw_round_trip(samples: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Encode to A-law and back. Length and dtype preserved, detail is not."""
    return alaw_decode(alaw_encode(samples))
