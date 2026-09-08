"""ASVspoof 2019 LA as a torch Dataset, with the phone channel applied on the fly.

The protocol files are the authority for labels. Audio present on disk but absent
from the protocol is ASV enrolment material, not countermeasure data, and is ignored
rather than silently treated as bonafide.

Augmentation is applied per epoch rather than precomputed, so a given utterance is
seen at many gains, through several codecs and at several SNRs over a run. That is
the point: the failure this training targets is a model that has only ever seen one
recording condition.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from ml.augment.g711 import alaw_round_trip, mulaw_round_trip
from ml.augment.gain import PRESETS, compress, random_gain
from ml.augment.noise import add_noise_at_snr
from ml.augment.phone_codecs import CodecName, ffmpeg_available, phone_codec_round_trip
from ml.augment.room import apply_reverb

#: AASIST's native input, 4.0375 s at 16 kHz.
INPUT_SAMPLES = 64600

SAMPLE_RATE = 16000

#: Label convention from the published evaluation code: index 1 is bonafide.
BONAFIDE = 1
SPOOF = 0

_SPLIT_DIRS = {
    "train": ("ASVspoof2019_LA_train", "ASVspoof2019.LA.cm.train.trn.txt"),
    "dev": ("ASVspoof2019_LA_dev", "ASVspoof2019.LA.cm.dev.trl.txt"),
    "eval": ("ASVspoof2019_LA_eval", "ASVspoof2019.LA.cm.eval.trl.txt"),
}


@dataclass(frozen=True)
class Utterance:
    path: Path
    label: int
    attack_id: str


def read_protocol(root: Path, split: str) -> list[Utterance]:
    """Parse a CM protocol file. Columns: speaker, file, -, attack, label."""
    audio_dir, protocol_name = _SPLIT_DIRS[split]
    protocol = root / "ASVspoof2019_LA_cm_protocols" / protocol_name
    if not protocol.exists():
        raise FileNotFoundError(f"missing protocol: {protocol}")

    flac_dir = root / audio_dir / "flac"
    utterances: list[Utterance] = []
    missing = 0
    for line in protocol.read_text(encoding="utf-8").strip().splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        file_id, attack_id, label = fields[1], fields[3], fields[4]
        path = flac_dir / f"{file_id}.flac"
        if not path.exists():
            missing += 1
            continue
        utterances.append(
            Utterance(path, BONAFIDE if label == "bonafide" else SPOOF, attack_id)
        )

    if missing:
        raise FileNotFoundError(
            f"{missing} files listed in {protocol_name} are not on disk. "
            "The corpus is incomplete; training on it would silently drop data."
        )
    return utterances


def load_flac(path: Path) -> np.ndarray:
    """Read a mono 16 kHz flac to float32 in [-1, 1].

    soundfile rather than torchaudio: torchaudio 2.11 delegates decoding to
    torchcodec, which is a heavier dependency than reading a FLAC warrants.
    """
    import soundfile

    samples, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    mono = samples.mean(axis=1) if samples.shape[1] > 1 else samples[:, 0]
    if rate != SAMPLE_RATE:
        raise ValueError(f"{path} is {rate} Hz, expected {SAMPLE_RATE}")
    return np.ascontiguousarray(mono, dtype=np.float32)


def fixed_length(samples: np.ndarray, target: int, rng: random.Random) -> np.ndarray:
    """Random crop, or tile-pad if short. Matches the published `pad_random`."""
    length = samples.shape[0]
    if length == 0:
        return np.zeros(target, dtype=np.float32)
    if length >= target:
        start = rng.randint(0, length - target)
        return samples[start : start + target]
    repeats = target // length + 1
    return np.tile(samples, repeats)[:target]


class PhoneChannelAugmenter:
    """Applies a randomly drawn phone channel to one utterance.

    Order matters and mirrors reality: gain and compression happen at the handset,
    then the codec, then channel noise. Each stage fires with its own probability so
    the model also sees clean audio and every partial combination.
    """

    def __init__(
        self,
        *,
        seed: int = 0,
        gain_probability: float = 0.9,
        compress_probability: float = 0.3,
        reverb_probability: float = 0.6,
        codec_probability: float = 0.7,
        noise_probability: float = 0.5,
        snr_choices: tuple[float, ...] = (20.0, 15.0, 10.0, 5.0),
        allow_subprocess_codecs: bool = False,
    ) -> None:
        self._seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.gain_probability = gain_probability
        self.compress_probability = compress_probability
        self.reverb_probability = reverb_probability
        self.codec_probability = codec_probability
        self.noise_probability = noise_probability
        self.snr_choices = snr_choices
        # Default off, and this is not a preference. Calling ffmpeg through
        # subprocess pipes inside spawn-based DataLoader workers deadlocks on
        # Windows: the run stalls with the GPU at 4% and no ffmpeg processes alive.
        # G.711 and A-law are pure numpy and cover the dominant telephony codec, so
        # the loss is AMR-NB and Opus breadth, not the phone channel itself. Turn it
        # on for single-process work (num_workers=0) or offline pre-generation,
        # where it is safe.
        self.allow_subprocess_codecs = allow_subprocess_codecs
        self._ffmpeg = allow_subprocess_codecs and ffmpeg_available()

    def for_index(self, index: int) -> PhoneChannelAugmenter:
        """A clone whose randomness is a function of `index`, not of call order.

        Evaluation needs this. Each DataLoader worker receives a *copy* of the
        augmenter, so with per-instance RNG state the degradation applied to a given
        utterance depends on how many workers are running: the same checkpoint on the
        same dev subsample measured 16.29% at 4 workers and 17.50% at 6. Deriving the
        seed from the item index makes the applied channel a property of the
        utterance, so the metric is reproducible.

        Training deliberately does NOT use this: varying the channel across epochs is
        the entire point there.
        """
        twin = PhoneChannelAugmenter(
            seed=self._seed * 1_000_003 + index,
            gain_probability=self.gain_probability,
            compress_probability=self.compress_probability,
            codec_probability=self.codec_probability,
            noise_probability=self.noise_probability,
            reverb_probability=self.reverb_probability,
            snr_choices=self.snr_choices,
            allow_subprocess_codecs=self.allow_subprocess_codecs,
        )
        return twin

    def __call__(self, samples: np.ndarray) -> np.ndarray:
        x = samples

        if self.rng.random() < self.gain_probability:
            x = random_gain(x, self.np_rng)

        if self.rng.random() < self.compress_probability:
            x = compress(x, PRESETS[self.rng.choice(list(PRESETS))])

        # Room comes before the phone: a microphone hears reflections, then the
        # network codes what the microphone heard. Applied to both classes, since
        # augmenting only bonafide would teach "reverb means genuine".
        if self.rng.random() < self.reverb_probability:
            x = apply_reverb(x, self.np_rng)

        if self.rng.random() < self.codec_probability:
            x = self._apply_codec(x)

        if self.rng.random() < self.noise_probability:
            x = add_noise_at_snr(x, self.rng.choice(self.snr_choices), self.np_rng)

        return x.astype(np.float32)

    def _apply_codec(self, x: np.ndarray) -> np.ndarray:
        # The numpy G.711 paths need no subprocess, so they stay available even
        # without ffmpeg. AMR-NB and Opus do need it.
        cheap = [mulaw_round_trip, alaw_round_trip]
        if not self._ffmpeg:
            return self.rng.choice(cheap)(x)

        choice = self.rng.random()
        if choice < 0.4:
            return self.rng.choice(cheap)(x)
        name = CodecName.AMR_NB if choice < 0.8 else CodecName.OPUS
        try:
            out = phone_codec_round_trip(x, name)
        except RuntimeError:
            return self.rng.choice(cheap)(x)
        # Codec framing can shift length by a few ms; callers crop to fixed length.
        return out if out.size else x


class AsvspoofLaDataset(Dataset[tuple[torch.Tensor, int]]):
    """torch Dataset over one ASVspoof 2019 LA split."""

    def __init__(
        self,
        root: Path,
        split: str,
        *,
        augmenter: PhoneChannelAugmenter | None = None,
        seed: int = 0,
        limit: int | None = None,
        deterministic_augmentation: bool = False,
    ) -> None:
        self.utterances = read_protocol(Path(root), split)
        if limit is not None:
            rng = random.Random(seed)
            self.utterances = rng.sample(self.utterances, min(limit, len(self.utterances)))
        self.augmenter = augmenter
        self.deterministic_augmentation = deterministic_augmentation
        self.seed = seed
        self.rng = random.Random(seed)

    def __len__(self) -> int:
        return len(self.utterances)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        utterance = self.utterances[index]
        samples = load_flac(utterance.path)
        if self.augmenter is not None:
            augmenter = (
                self.augmenter.for_index(index)
                if self.deterministic_augmentation
                else self.augmenter
            )
            samples = augmenter(samples)
        # Crop position too: worker copies share an RNG, so derive it from the index.
        crop_rng = (
            random.Random(self.seed * 7_919 + index)
            if self.deterministic_augmentation
            else self.rng
        )
        samples = fixed_length(samples, INPUT_SAMPLES, crop_rng)
        return torch.from_numpy(np.ascontiguousarray(samples)), utterance.label


def class_counts(utterances: list[Utterance]) -> dict[str, int]:
    return {
        "bonafide": sum(1 for u in utterances if u.label == BONAFIDE),
        "spoof": sum(1 for u in utterances if u.label == SPOOF),
    }
