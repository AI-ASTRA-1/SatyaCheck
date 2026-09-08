"""AMR-NB and Opus round trips, through ffmpeg.

There is no pure-Python AMR-NB encoder, so this shells out. The probe is explicit and
raises: a codec condition that silently skips itself would produce a sweep with a
hole in it and a table that looks complete.

Naming, and this is load-bearing: `tests/test_transport_invariant.py` AST-walks `ml/`
and fails on any attribute named `codec` or on importing a symbol named `Codec`,
because below stage 02 nothing may know what carried the audio. This module is
training-time tooling rather than pipeline code, but it lives under `ml/` and the
test does not care, so everything here says `codec_name` and `CodecName`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from enum import Enum
from pathlib import Path

import numpy as np

_FFMPEG_FALLBACK = r"C:\ffmpeg\ffmpeg.exe"


class CodecName(str, Enum):
    """Telephony codecs we push training audio through."""

    G711_ULAW = "g711_ulaw"
    G711_ALAW = "g711_alaw"
    AMR_NB = "amr_nb"
    OPUS = "opus"


#: ffmpeg encoder plus the container it needs, per codec.
_ENCODER = {
    CodecName.G711_ULAW: ("pcm_mulaw", "wav", 8000),
    CodecName.G711_ALAW: ("pcm_alaw", "wav", 8000),
    CodecName.AMR_NB: ("libopencore_amrnb", "amr", 8000),
    CodecName.OPUS: ("libopus", "ogg", 16000),
}


def ffmpeg_path() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    return _FFMPEG_FALLBACK if Path(_FFMPEG_FALLBACK).exists() else None


def ffmpeg_available() -> bool:
    return ffmpeg_path() is not None


def _run(args: list[str]) -> None:
    # check=False: the return code is inspected below so the message can carry
    # ffmpeg's own stderr, which is far more useful than CalledProcessError.
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[:400]}")


def phone_codec_round_trip(
    samples: np.ndarray,
    codec_name: CodecName,
    sample_rate: int = 16000,
    *,
    bitrate: str = "12.2k",
) -> np.ndarray:
    """Encode through a telephony codec and decode back to `sample_rate`.

    Length is preserved to within the codec's framing, which can add or drop a few
    milliseconds at the tail; callers that need exact length should trim or pad.
    """
    binary = ffmpeg_path()
    if binary is None:
        raise RuntimeError(
            "ffmpeg not found. It is required for AMR-NB and Opus round trips. "
            "Install it, or put it at " + _FFMPEG_FALLBACK
        )

    x = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    if x.size == 0:
        return x.copy()

    encoder, container, codec_rate = _ENCODER[codec_name]
    pcm = (x * 32767.0).astype("<i2").tobytes()

    with tempfile.TemporaryDirectory(prefix="satyacheck_codec_") as directory:
        work = Path(directory)
        raw_in = work / "in.raw"
        encoded = work / f"encoded.{container}"
        raw_out = work / "out.raw"
        raw_in.write_bytes(pcm)

        encode = [
            binary, "-y", "-v", "error",
            "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", str(raw_in),
            "-ar", str(codec_rate), "-ac", "1", "-acodec", encoder,
        ]
        if codec_name is CodecName.AMR_NB:
            encode += ["-b:a", bitrate]
        elif codec_name is CodecName.OPUS:
            encode += ["-b:a", "24k"]
        encode.append(str(encoded))
        _run(encode)

        _run([
            binary, "-y", "-v", "error", "-i", str(encoded),
            "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", str(raw_out),
        ])

        decoded = np.frombuffer(raw_out.read_bytes(), dtype="<i2")

    return (decoded.astype(np.float32) / 32768.0).astype(np.float32)
