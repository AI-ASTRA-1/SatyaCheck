"""Cosine similarity between speaker embeddings, for deciding whether the speaker
identity check can carry a demo.

    .venv\\Scripts\\python.exe -m ml.tools.speaker_probe --rec-dir <dir>

Why this is not one number. A single "genuine 0.96 versus clone 0.76" comparison
cannot be interpreted, because two different effects lower a cosine similarity and
one measurement cannot tell them apart:

  * the speaker really is different, which is the effect we want, and
  * the recording channel is different, which is an artefact.

`nik_clean` is a person in a room on a phone; `nik_clone` is text-to-speech. Those
differ in channel as well as in speaker, so a low similarity between them proves
nothing on its own. This is the same trap that inverted the anti-spoofing model,
where "no room reverberation" was being read as "genuine".

So the probe always reports three groups, and the clone is judged against them:

  same speaker, different session   the ceiling, and it already carries channel
                                    mismatch, so it is the honest ceiling
  different speaker                 the floor
  clone against its target          the number under test

A clone is only detectable this way if it sits near the floor rather than inside
the ceiling group. If the ceiling and the floor overlap, no threshold exists on
this data, whatever the clone scores.

This reports a measurement. It is NOT clone detection: it answers "the voiceprint
does not match", never "this audio is synthetic". See AGENTS.md.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import dataclass
from math import gcd
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000

#: Segment length for the per-segment count. Long enough for ECAPA to be stable,
#: short enough to get several independent looks at a one-minute recording.
DEFAULT_SEGMENT_S = 4.0

#: Fraction of the 95th-percentile frame RMS below which a frame counts as silence.
#: Relative, not absolute: an absolute gate returned nan on quiet phone recordings.
_ACTIVITY_GATE = 0.15

#: A segment must be at least this fraction speech to be embedded. Silence embeds
#: to a channel fingerprint rather than to a speaker.
_MIN_ACTIVE_FRACTION = 0.5


@dataclass(frozen=True)
class Recording:
    """One audio file, with what we independently know about who is speaking."""

    label: str
    path: Path
    speaker: str
    #: True when the audio is text-to-speech rather than a person.
    synthetic: bool = False


def _model_dir() -> Path:
    from ml.paths import model_root

    return model_root() / "spkrec-ecapa-voxceleb"


def load_audio(path: Path) -> np.ndarray:
    """Mono float32 at 16 kHz."""
    import soundfile

    samples, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    mono = samples.mean(axis=1) if samples.shape[1] > 1 else samples[:, 0]
    if rate != SAMPLE_RATE:
        from scipy.signal import resample_poly

        divisor = gcd(int(rate), SAMPLE_RATE)
        mono = resample_poly(mono, SAMPLE_RATE // divisor, int(rate) // divisor)
    return np.ascontiguousarray(mono, dtype=np.float32)


def active_segments(
    samples: np.ndarray, segment_s: float = DEFAULT_SEGMENT_S
) -> list[np.ndarray]:
    """Speech-active fixed-length segments, taken on an overlapping hop.

    The hop is deliberately shorter than the segment. With non-overlapping windows
    the segment grid is arbitrary relative to the speech, so a recording made with
    pauses between takes has most windows straddling a pause: one such file yielded
    2 usable segments where comparable files yielded 12. That is not a property of
    the speaker, it is a property of where the grid happened to fall, and it made
    the pooled embedding far noisier for that one file than for the others it was
    being compared against.
    """
    frame = 320  # 20 ms
    usable = samples[: samples.size // frame * frame]
    if usable.size == 0:
        return []
    rms = np.sqrt((usable.reshape(-1, frame) ** 2).mean(axis=1))
    threshold = float(np.percentile(rms, 95)) * _ACTIVITY_GATE
    active = rms > threshold

    per_segment = int(segment_s * SAMPLE_RATE) // frame
    hop = max(per_segment // 4, 1)
    kept: list[np.ndarray] = []
    for start in range(0, len(active) - per_segment + 1, hop):
        window = active[start : start + per_segment]
        if window.mean() >= _MIN_ACTIVE_FRACTION:
            kept.append(usable[start * frame : (start + per_segment) * frame])
    return kept


class EcapaEmbedder:
    """ECAPA-TDNN speaker embeddings from the local checkpoint.

    CPU by default: this is meant to run while the GPU is busy training, and a
    minute of audio embeds in seconds either way.
    """

    def __init__(self, device: str = "cpu") -> None:
        import torch
        from speechbrain.inference.speaker import EncoderClassifier

        directory = _model_dir()
        if not directory.exists():
            raise SystemExit(f"missing ECAPA checkpoint: {directory}")

        self._torch = torch
        # hyperparams.yaml points `pretrained_path` at the HuggingFace repo id.
        # Redirecting it at the local directory keeps this offline, which is the
        # rule for demo day: no external API to fail on.
        self._model = EncoderClassifier.from_hparams(
            source=str(directory),
            savedir=str(directory),
            run_opts={"device": device},
            overrides={"pretrained_path": str(directory)},
        )

    def embed(self, samples: np.ndarray) -> np.ndarray:
        """One L2-normalised embedding, so cosine similarity is a dot product."""
        with self._torch.no_grad():
            tensor = self._torch.from_numpy(samples).unsqueeze(0)
            vector = self._model.encode_batch(tensor).squeeze().cpu().numpy()
        return vector / (np.linalg.norm(vector) + 1e-12)

    def embed_file(self, path: Path) -> tuple[np.ndarray, int]:
        """Return (file embedding, number of speech-active segments pooled)."""
        segments = active_segments(load_audio(path))
        if not segments:
            raise SystemExit(f"no speech-active audio in {path}")
        stacked = np.stack([self.embed(s) for s in segments])
        pooled = stacked.mean(axis=0)
        return pooled / (np.linalg.norm(pooled) + 1e-12), len(segments)


def team_preset(root: Path) -> list[Recording]:
    """The recordings we actually have, with who is in them.

    Three separate genuine sessions from one speaker are what make a
    same-speaker-different-session ceiling possible at all. Without that, a low
    clone similarity could not be told apart from ordinary session mismatch.

    Speakers carry opaque ids rather than names. These recordings are a real person
    and a clone of that person, and this file is committed while the audio
    deliberately is not; naming the person here would defeat that. Filenames stay as
    they are on disk, because the tool has to open them.
    """
    return [
        Recording("target_s1", root / "nik_clean.wav", "speaker_c"),
        Recording("target_s2", root / "spk_03b_source.wav", "speaker_c"),
        Recording("target_s3", root / "spk_03_source.wav", "speaker_c"),
        Recording("target_clone", root / "nik_clone.wav", "speaker_c", synthetic=True),
        Recording("other_a", root / "spk_01_source.wav", "speaker_a"),
        Recording("other_b", root / "spk_02_source.wav", "speaker_b"),
    ]


#: The three groups every pair falls into. Named so the classifier and its test
#: cannot drift apart on a typo.
SAME_SPEAKER = "same speaker"
DIFFERENT_SPEAKER = "different speaker"
CLONE_VS_TARGET = "clone vs target"


def classify_pair(a: Recording, b: Recording) -> str:
    """Which comparison group a pair belongs to.

    Separated out because getting this wrong does not raise, it just moves a number
    into the wrong column and changes the conclusion. A clone against a *different*
    speaker is an ordinary impostor pair and must not be counted as the case under
    test, or the clone group would be diluted with easy pairs.
    """
    if a.synthetic or b.synthetic:
        return CLONE_VS_TARGET if a.speaker == b.speaker else DIFFERENT_SPEAKER
    return SAME_SPEAKER if a.speaker == b.speaker else DIFFERENT_SPEAKER


def _describe(name: str, values: list[float]) -> str:
    if not values:
        return f"{name:32s}  (none)"
    array = np.asarray(values)
    return (
        f"{name:32s}  n={array.size:2d}  "
        f"mean {array.mean():6.4f}  min {array.min():6.4f}  max {array.max():6.4f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rec-dir",
        type=Path,
        required=True,
        help="directory holding the converted 16 kHz recordings",
    )
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--segment-seconds", type=float, default=DEFAULT_SEGMENT_S)
    args = parser.parse_args(argv)

    everything = team_preset(args.rec_dir)
    recordings = [r for r in everything if r.path.exists()]
    absent = [r.label for r in everything if not r.path.exists()]
    if absent:
        print(f"skipping (not on disk): {', '.join(absent)}", flush=True)
    if len(recordings) < 2:
        raise SystemExit("need at least two recordings to compare")

    embedder = EcapaEmbedder(args.device)

    pooled: dict[str, np.ndarray] = {}
    for recording in recordings:
        vector, count = embedder.embed_file(recording.path)
        pooled[recording.label] = vector
        print(f"  {recording.label:14s} {count:3d} segments", flush=True)

    by_label = {r.label: r for r in recordings}

    ceiling: list[float] = []
    floor: list[float] = []
    clone: list[float] = []
    rows: list[tuple[str, str, float, str]] = []

    for left, right in itertools.combinations(sorted(pooled), 2):
        a, b = by_label[left], by_label[right]
        similarity = float(pooled[left] @ pooled[right])

        group = classify_pair(a, b)
        {SAME_SPEAKER: ceiling, DIFFERENT_SPEAKER: floor, CLONE_VS_TARGET: clone}[
            group
        ].append(similarity)
        rows.append((left, right, similarity, group))

    print(f"\n{'=' * 74}")
    print("pairwise cosine similarity, ECAPA-TDNN (spkrec-ecapa-voxceleb)")
    print("=" * 74)
    for left, right, similarity, group in sorted(rows, key=lambda r: -r[2]):
        print(f"  {left:14s} {right:14s}  {similarity:7.4f}   {group}")

    print(f"\n{'-' * 74}")
    print(_describe("same speaker, diff session", ceiling))
    print(_describe("different speaker", floor))
    print(_describe("clone vs its target", clone))
    print("-" * 74)

    if ceiling and floor:
        separated = min(ceiling) > max(floor)
        print(
            f"\ngenuine floor {min(ceiling):.4f} vs impostor ceiling {max(floor):.4f}: "
            f"{'separated' if separated else 'OVERLAPPING, no threshold exists'}"
        )
        if separated and clone:
            midpoint = (min(ceiling) + max(floor)) / 2
            caught = sum(1 for c in clone if c < midpoint)
            print(
                f"at a threshold of {midpoint:.4f}, "
                f"{caught}/{len(clone)} clone pairs fall below it"
            )

    speakers = {r.speaker for r in recordings if not r.synthetic}
    synthetic = sum(1 for r in recordings if r.synthetic)
    print(
        f"\nscale: n={len(speakers)} speakers, {synthetic} clone, 1 cloning tool. "
        "Not a benchmark."
    )
    print(
        "This measures voiceprint match, NOT whether audio is synthetic. "
        "A clone built to match would pass."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
