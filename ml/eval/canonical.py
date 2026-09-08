"""Decode any audio file to the canonical 16 kHz mono s16le the model expects.

One decode path, used by every diagnostic, because the decode is part of the frozen
config. `FROZEN.md` records the exact flags and a changed flag here silently changes
every number downstream.

Why not `speaker_probe.load_audio`, which already loads audio: it goes through
soundfile plus `scipy.resample_poly`. That is a different resampler from the one that
produced every figure in `ml/README.md`, and it cannot open `.mp4`, `.m4a` or `.mpeg`
at all, which is what the source recordings actually are. Mixing the two would put
two resamplers in one table with nothing marking which row used which.

Decoded files are cached. A cache entry is keyed on the source path, its size and its
modification time, so editing a source produces a new entry rather than a stale hit.
"""

from __future__ import annotations

import hashlib
import subprocess
import wave
from pathlib import Path

import numpy as np

from ml.augment.phone_codecs import ffmpeg_path

#: The canonical format below stage 02. Same constants as `contracts.pipeline`,
#: restated as the ffmpeg flags that produce them.
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_FORMAT = "s16"

#: The exact invocation recorded in FROZEN.md. Written out rather than assembled so
#: a diff shows the change.
FFMPEG_ARGS = ("-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-sample_fmt", SAMPLE_FORMAT)


def _cache_key(source: Path) -> str:
    stat = source.stat()
    material = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{FFMPEG_ARGS}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def canonical_wav(source: Path, cache_dir: Path) -> Path:
    """Path to a canonical wav for `source`, decoding it if not already cached."""
    if not source.exists():
        raise FileNotFoundError(f"missing audio: {source}")

    binary = ffmpeg_path()
    if binary is None:
        raise RuntimeError(
            "ffmpeg is required to canonicalise audio and was not found. "
            "Install it, or put it at C:\ffmpeg\ffmpeg.exe."
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{source.stem}.{_cache_key(source)}.16k.wav"
    if target.exists():
        return target

    # Decode to a temporary name and rename, so an interrupted run never leaves a
    # truncated file that a later run would treat as a cache hit. The temporary name
    # keeps the .wav suffix: ffmpeg picks its muxer from the extension, and a
    # ".partial" ending makes it refuse the output rather than write a wav.
    partial = target.with_name(target.name + ".partial.wav")
    result = subprocess.run(
        [binary, "-v", "error", "-y", "-i", str(source), *FFMPEG_ARGS, str(partial)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed on {source.name}: {result.stderr.strip()[:400]}")
    partial.replace(target)
    return target


def read_canonical(path: Path) -> np.ndarray:
    """Read a canonical wav to float32 in [-1, 1). Refuses anything else.

    Refuses rather than converting, because a silent conversion here would be a
    second decode path with different properties from `canonical_wav`.
    """
    with wave.open(str(path), "rb") as handle:
        channels, width, rate = (
            handle.getnchannels(),
            handle.getsampwidth(),
            handle.getframerate(),
        )
        frames = handle.readframes(handle.getnframes())
    if (channels, width, rate) != (CHANNELS, 2, SAMPLE_RATE):
        raise ValueError(
            f"{path} is {rate} Hz, {channels}ch, {width * 8}-bit, not the canonical "
            f"{SAMPLE_RATE} Hz mono 16-bit. Route it through canonical_wav()."
        )
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def load(source: Path, cache_dir: Path) -> np.ndarray:
    """Canonicalise if needed, then read. The one entry point diagnostics use."""
    return read_canonical(canonical_wav(source, cache_dir))
