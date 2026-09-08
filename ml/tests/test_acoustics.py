"""Channel statistics, each tested against the thing it claims to measure.

A statistic that is quietly wrong produces a correlation table that looks like a
result and is not one. So each is checked by constructing a signal with a known
value of that property, rather than by asserting the function returns a float.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.eval import acoustics

RATE = acoustics.SAMPLE_RATE


def tone(hz: float, seconds: float = 2.0, amplitude: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def noisy_speech(snr_db: float, seconds: float = 3.0, seed: int = 0) -> np.ndarray:
    """Loud bursts over a quiet floor, with a controlled level difference."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    floor = 0.001
    signal = rng.normal(0.0, floor, n).astype(np.float32)
    loud = floor * (10 ** (snr_db / 20))
    for start in range(0, n - RATE, RATE):
        signal[start : start + RATE // 2] += rng.normal(0.0, loud, RATE // 2)
    return signal


class TestSnr:
    @pytest.mark.parametrize("target", [10.0, 20.0, 40.0])
    def test_it_recovers_a_constructed_ratio(self, target: float) -> None:
        measured = acoustics.snr_db(noisy_speech(target))
        assert measured == pytest.approx(target, abs=4.0)

    def test_it_survives_a_gain_change(self) -> None:
        # A ratio, so it must not move when the whole file gets louder. Level is a
        # cue this model has been caught using; it must not enter through here.
        quiet = noisy_speech(20.0)
        assert acoustics.snr_db(quiet * 8.0) == pytest.approx(
            acoustics.snr_db(quiet), abs=0.5
        )

    def test_empty_input_does_not_raise(self) -> None:
        assert np.isfinite(acoustics.snr_db(np.zeros(0, dtype=np.float32)))


class TestLevels:
    def test_noise_floor_is_below_the_speech_level(self) -> None:
        x = noisy_speech(25.0)
        assert acoustics.noise_floor_dbfs(x) < acoustics.speech_level_dbfs(x)

    def test_levels_are_absolute_and_move_with_gain(self) -> None:
        # Unlike snr_db, these are dBFS and must track loudness: doubling is +6 dB.
        x = noisy_speech(20.0)
        assert acoustics.speech_level_dbfs(x * 2.0) == pytest.approx(
            acoustics.speech_level_dbfs(x) + 6.0, abs=0.5
        )

    def test_silence_is_finite_not_negative_infinity(self) -> None:
        assert np.isfinite(acoustics.noise_floor_dbfs(np.zeros(RATE, dtype=np.float32)))


class TestCrestFactor:
    def test_a_sine_is_about_three_db(self) -> None:
        # Peak over RMS for a sine is sqrt(2), which is 3.01 dB. A textbook value,
        # so a wrong implementation shows up immediately.
        assert acoustics.crest_factor_db(tone(300.0)) == pytest.approx(3.01, abs=0.1)

    def test_gaussian_noise_is_higher_than_a_sine(self) -> None:
        noise = np.random.default_rng(0).normal(0, 0.1, RATE).astype(np.float32)
        assert acoustics.crest_factor_db(noise) > acoustics.crest_factor_db(tone(300.0))

    def test_hard_clipping_lowers_it(self) -> None:
        noise = np.random.default_rng(1).normal(0, 0.3, RATE).astype(np.float32)
        squashed = np.clip(noise, -0.3, 0.3)
        assert acoustics.crest_factor_db(squashed) < acoustics.crest_factor_db(noise)


class TestSpectralCentroid:
    def test_a_high_tone_has_a_higher_centroid_than_a_low_one(self) -> None:
        assert acoustics.spectral_centroid_hz(tone(3000.0)) > acoustics.spectral_centroid_hz(
            tone(300.0)
        )

    def test_it_lands_near_the_tone(self) -> None:
        assert acoustics.spectral_centroid_hz(tone(1000.0)) == pytest.approx(
            1000.0, rel=0.25
        )

    def test_silence_returns_zero_rather_than_dividing(self) -> None:
        assert acoustics.spectral_centroid_hz(np.zeros(RATE, dtype=np.float32)) == 0.0


class TestEffectiveBandwidth:
    def test_a_band_limited_signal_reports_a_lower_bandwidth(self) -> None:
        rng = np.random.default_rng(2)
        wide = rng.normal(0, 0.2, RATE * 2).astype(np.float32)
        spectrum = np.fft.rfft(wide)
        freqs = np.fft.rfftfreq(wide.size, 1.0 / RATE)
        spectrum[freqs > 3400] = 0
        narrow = np.fft.irfft(spectrum, wide.size).astype(np.float32)
        assert acoustics.effective_bandwidth_hz(narrow) < acoustics.effective_bandwidth_hz(
            wide
        )

    def test_a_telephone_band_lands_near_its_cutoff(self) -> None:
        rng = np.random.default_rng(3)
        wide = rng.normal(0, 0.2, RATE * 2).astype(np.float32)
        spectrum = np.fft.rfft(wide)
        freqs = np.fft.rfftfreq(wide.size, 1.0 / RATE)
        spectrum[(freqs < 300) | (freqs > 3400)] = 0
        narrow = np.fft.irfft(spectrum, wide.size).astype(np.float32)
        assert 2800 < acoustics.effective_bandwidth_hz(narrow) < 3600

    def test_silence_returns_zero(self) -> None:
        assert acoustics.effective_bandwidth_hz(np.zeros(RATE, dtype=np.float32)) == 0.0


class TestClipping:
    def test_clean_audio_reports_none(self) -> None:
        assert acoustics.clipping_fraction(tone(300.0)) == 0.0

    def test_a_saturated_signal_reports_all(self) -> None:
        assert acoustics.clipping_fraction(np.ones(100, dtype=np.float32)) == 1.0


class TestCorrelationHelpers:
    def test_pearson_is_one_for_a_line(self) -> None:
        x = np.arange(10.0)
        assert acoustics.pearson(x, 2 * x + 1) == pytest.approx(1.0)

    def test_spearman_catches_a_monotone_curve_pearson_understates(self) -> None:
        x = np.arange(1.0, 11.0)
        y = x**4
        assert acoustics.spearman(x, y) == pytest.approx(1.0)
        assert acoustics.pearson(x, y) < 0.95

    def test_ties_do_not_break_the_rank_correlation(self) -> None:
        x = np.array([1.0, 1.0, 2.0, 2.0, 3.0])
        assert np.isfinite(acoustics.spearman(x, np.array([1.0, 2.0, 3.0, 4.0, 5.0])))

    def test_a_constant_column_is_nan_not_zero(self) -> None:
        # Zero would read as "measured, no relationship". NaN reads as "undefined",
        # which is what a constant column actually is.
        constant = np.ones(10)
        assert np.isnan(acoustics.pearson(constant, np.arange(10.0)))

    def test_too_few_points_is_nan(self) -> None:
        assert np.isnan(acoustics.pearson(np.array([1.0, 2.0]), np.array([1.0, 2.0])))


class TestDescribe:
    def test_it_returns_every_named_statistic(self) -> None:
        described = acoustics.describe(noisy_speech(20.0))
        assert set(described) == set(acoustics.STATISTICS)
        assert all(np.isfinite(v) for v in described.values())

    def test_the_five_the_brief_names_are_all_present(self) -> None:
        for name in (
            "snr_db",
            "effective_bandwidth_hz",
            "noise_floor_dbfs",
            "spectral_centroid_hz",
            "crest_factor_db",
        ):
            assert name in acoustics.STATISTICS
