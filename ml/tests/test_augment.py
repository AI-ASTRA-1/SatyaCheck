"""Tests for the augmentation pipeline.

The G.711 tests deliberately do NOT assert byte-equality with ffmpeg. Both are
conformant encoders that disagree on about 1.5% of samples: this implementation
follows the ITU reference, which truncates, while ffmpeg builds its table by
inverting the decoder and picking the nearest level. Measured round-trip error is
identical, so the tests assert that bound instead, which is the property that
actually matters for training data.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.augment.g711 import (
    alaw_decode,
    alaw_encode,
    alaw_round_trip,
    mulaw_decode,
    mulaw_encode,
    mulaw_round_trip,
)
from ml.augment.gain import (
    AGGRESSIVE_RECORDER,
    MILD_HANDSET,
    PRESETS,
    compress,
    crest_factor_db,
    random_gain,
)
from ml.augment.noise import (
    active_speech_rms,
    add_noise_at_snr,
    measured_snr_db,
    pink_noise,
)
from ml.augment.phone_codecs import CodecName, ffmpeg_available, phone_codec_round_trip

SAMPLE_RATE = 16000


def speech_like(seconds: float = 1.0, seed: int = 0) -> np.ndarray:
    """A voiced-ish signal with silence at both ends, so gating is exercised."""
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * seconds)
    t = np.arange(n) / SAMPLE_RATE
    tone = 0.5 * np.sin(2 * np.pi * 150 * t) + 0.2 * np.sin(2 * np.pi * 450 * t)
    signal = (tone + 0.02 * rng.normal(0, 1, n)).astype(np.float32)
    quiet = n // 5
    signal[:quiet] *= 0.001
    signal[-quiet:] *= 0.001
    return np.clip(signal, -1.0, 1.0).astype(np.float32)


def loud_then_quiet(seconds: float = 2.0, gap_db: float = 22.0) -> np.ndarray:
    """First half loud, second half `gap_db` quieter. For testing compression."""
    n = int(SAMPLE_RATE * seconds)
    base = speech_like(seconds=seconds, seed=1)
    envelope = np.ones(n, dtype=np.float32)
    envelope[n // 2 :] *= float(10.0 ** (-gap_db / 20.0))
    return np.clip(base[:n] * envelope, -1.0, 1.0).astype(np.float32)


def section_gap_db(x: np.ndarray) -> float:
    """Level difference in dB between the first and second halves."""
    half = x.size // 2
    loud = float(np.sqrt(np.mean(x[:half] ** 2)) + 1e-12)
    quiet = float(np.sqrt(np.mean(x[half:] ** 2)) + 1e-12)
    return 20.0 * float(np.log10(loud / quiet))


class TestG711:
    @pytest.mark.parametrize("round_trip", [mulaw_round_trip, alaw_round_trip])
    def test_length_and_dtype_preserved(self, round_trip) -> None:
        x = speech_like()
        out = round_trip(x)
        assert out.shape == x.shape
        assert out.dtype == np.float32

    @pytest.mark.parametrize(
        ("round_trip", "bound"), [(mulaw_round_trip, 0.03), (alaw_round_trip, 0.03)]
    )
    def test_round_trip_error_inside_quantisation_bound(self, round_trip, bound) -> None:
        x = speech_like()
        assert np.abs(round_trip(x) - x).max() < bound

    @pytest.mark.parametrize("encode", [mulaw_encode, alaw_encode])
    def test_encodes_to_one_byte_per_sample(self, encode) -> None:
        x = speech_like(seconds=0.1)
        encoded = encode(x)
        assert encoded.dtype == np.uint8
        assert encoded.shape == x.shape

    @pytest.mark.parametrize(
        ("encode", "decode"), [(mulaw_encode, mulaw_decode), (alaw_encode, alaw_decode)]
    )
    def test_silence_survives(self, encode, decode) -> None:
        x = np.zeros(320, dtype=np.float32)
        assert np.abs(decode(encode(x))).max() < 0.01

    def test_input_is_not_mutated(self) -> None:
        x = speech_like()
        before = x.copy()
        mulaw_round_trip(x)
        alaw_round_trip(x)
        assert np.array_equal(x, before)

    def test_full_scale_does_not_wrap(self) -> None:
        """A wrapped sign bit would turn a loud sample into a loud opposite one."""
        x = np.array([1.0, -1.0, 0.999, -0.999], dtype=np.float32)
        for round_trip in (mulaw_round_trip, alaw_round_trip):
            out = round_trip(x)
            assert np.sign(out[0]) == 1.0
            assert np.sign(out[1]) == -1.0


class TestGain:
    def test_random_gain_stays_in_range(self) -> None:
        rng = np.random.default_rng(0)
        for _ in range(20):
            out = random_gain(speech_like(), rng)
            assert np.abs(out).max() <= 1.0
            assert out.dtype == np.float32

    def test_random_gain_actually_varies(self) -> None:
        """If this ever stops varying, level invariance stops being trained."""
        rng = np.random.default_rng(0)
        x = speech_like()
        levels = {float(np.sqrt(np.mean(random_gain(x, rng) ** 2))) for _ in range(10)}
        assert len(levels) >= 8

    def test_compression_reduces_the_loud_to_quiet_gap(self) -> None:
        """The definition of compression, tested directly.

        Crest factor is a poor assertion here: on a near-steady signal it is already
        near its floor, and compressor overshoot at onsets can push it the wrong way.
        The gap between a loud and a quiet passage is unambiguous.
        """
        x = loud_then_quiet()
        before = section_gap_db(x)
        after = section_gap_db(compress(x, AGGRESSIVE_RECORDER))
        assert after < before - 5.0

    def test_higher_ratio_compresses_harder(self) -> None:
        x = loud_then_quiet()
        mild = section_gap_db(compress(x, MILD_HANDSET))
        hard = section_gap_db(compress(x, AGGRESSIVE_RECORDER))
        assert hard < mild

    def test_crest_factor_ignores_silence(self) -> None:
        """Measured over the whole buffer, a mostly-silent clip reports nonsense."""
        loud = speech_like(seconds=1.0)
        padded = np.concatenate([np.zeros(32000, dtype=np.float32), loud])
        assert crest_factor_db(padded) == pytest.approx(crest_factor_db(loud), abs=1.5)

    def test_compression_does_not_clip_or_change_length(self) -> None:
        x = speech_like()
        out = compress(x, AGGRESSIVE_RECORDER)
        assert out.shape == x.shape
        assert np.abs(out).max() <= 1.0

    def test_presets_are_named_for_reporting(self) -> None:
        assert set(PRESETS) == {"mild_handset", "aggressive_recorder", "broadcast"}
        for name, preset in PRESETS.items():
            assert preset.name == name

    def test_empty_input_is_handled(self) -> None:
        assert compress(np.array([], dtype=np.float32)).size == 0


class TestNoise:
    def test_active_rms_ignores_silence(self) -> None:
        """The whole point: a clip that is mostly silence must not read as quiet."""
        loud = np.full(16000, 0.5, dtype=np.float32)
        padded = np.concatenate([np.zeros(48000, dtype=np.float32), loud])
        assert active_speech_rms(padded) == pytest.approx(0.5, abs=0.02)
        assert float(np.sqrt(np.mean(padded**2))) < 0.3  # naive RMS is badly wrong

    @pytest.mark.parametrize("snr", [20.0, 10.0, 5.0, 0.0])
    def test_measured_snr_matches_requested(self, snr: float) -> None:
        rng = np.random.default_rng(0)
        x = speech_like(seconds=2.0)
        noisy = add_noise_at_snr(x, snr, rng)
        assert measured_snr_db(x, noisy) == pytest.approx(snr, abs=0.5)

    def test_lower_snr_is_noisier(self) -> None:
        rng = np.random.default_rng(0)
        x = speech_like(seconds=2.0)
        quiet_noise = np.abs(add_noise_at_snr(x, 20.0, rng) - x).mean()
        loud_noise = np.abs(add_noise_at_snr(x, 5.0, rng) - x).mean()
        assert loud_noise > quiet_noise

    def test_supplied_noise_is_tiled_to_length(self) -> None:
        rng = np.random.default_rng(0)
        x = speech_like(seconds=2.0)
        room_tone = pink_noise(1000, rng)
        out = add_noise_at_snr(x, 10.0, rng, noise=room_tone)
        assert out.shape == x.shape

    def test_empty_noise_raises(self) -> None:
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError):
            add_noise_at_snr(speech_like(), 10.0, rng, noise=np.array([], dtype=np.float32))

    def test_input_is_not_mutated(self) -> None:
        rng = np.random.default_rng(0)
        x = speech_like()
        before = x.copy()
        add_noise_at_snr(x, 10.0, rng)
        assert np.array_equal(x, before)


needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not on this machine")


class TestPhoneCodecs:
    @needs_ffmpeg
    @pytest.mark.parametrize("codec_name", list(CodecName))
    def test_round_trip_returns_usable_audio(self, codec_name: CodecName) -> None:
        x = speech_like(seconds=1.0)
        out = phone_codec_round_trip(x, codec_name)
        assert out.dtype == np.float32
        assert np.abs(out).max() <= 1.0
        # Codec framing can shift length slightly; 5% either way is tolerated.
        assert abs(out.size - x.size) < x.size * 0.05

    @needs_ffmpeg
    def test_narrowband_codecs_remove_high_frequencies(self) -> None:
        """G.711 runs at 8 kHz, so nothing above 4 kHz can survive it."""
        t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
        high = (0.5 * np.sin(2 * np.pi * 6000 * t)).astype(np.float32)
        out = phone_codec_round_trip(high, CodecName.G711_ULAW)
        assert float(np.sqrt(np.mean(out**2))) < 0.05

    def test_codec_names_are_stable_strings(self) -> None:
        assert CodecName.AMR_NB.value == "amr_nb"
        assert CodecName.G711_ULAW.value == "g711_ulaw"
