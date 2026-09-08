"""The non-speech probes, and the segment sampling the controls use.

These generators decide what `S_ood` means, and `S_ood` decides whether Rule 1 of
the H+4 gate fires. A probe that is quietly wrong (a "pink" noise that is white, a
"music" bed that is a pure tone, five "different" segments that are the same audio)
would produce a number that looks like a measurement and is not one.

So each generator is checked against the property it is named for, not merely that
it returns an array of the right length.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from ml.eval import probes

WINDOW = 64600


def rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


class TestEveryGenerator:
    @pytest.mark.parametrize("name", sorted(probes.GENERATORS))
    def test_shape_dtype_and_finiteness(self, name: str) -> None:
        out = probes.GENERATORS[name](WINDOW, rng())
        assert out.shape == (WINDOW,)
        assert out.dtype == np.float32
        assert np.isfinite(out).all()

    @pytest.mark.parametrize("name", sorted(probes.GENERATORS))
    def test_the_same_seed_gives_the_same_signal(self, name: str) -> None:
        first = probes.GENERATORS[name](WINDOW, rng(7))
        second = probes.GENERATORS[name](WINDOW, rng(7))
        assert np.array_equal(first, second), "a probe row must regenerate exactly"

    @pytest.mark.parametrize("name", sorted(probes.GENERATORS))
    def test_different_seeds_give_different_signals(self, name: str) -> None:
        # Five identical repetitions would report a range of zero and look like
        # stability rather than like a bug.
        first = probes.GENERATORS[name](WINDOW, rng(0))
        second = probes.GENERATORS[name](WINDOW, rng(1))
        assert not np.array_equal(first, second)

    @pytest.mark.parametrize("name", sorted(probes.GENERATORS))
    def test_nothing_clips(self, name: str) -> None:
        assert np.abs(probes.GENERATORS[name](WINDOW, rng())).max() < 1.0


def band_energy(x: np.ndarray, low: float, high: float) -> float:
    spectrum = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(x.size, 1.0 / probes.SAMPLE_RATE)
    return float(spectrum[(freqs >= low) & (freqs < high)].sum())


class TestWhiteNoise:
    def test_level_is_the_requested_sigma(self) -> None:
        out = probes.white_noise(WINDOW, rng(), sigma=0.05)
        assert out.std() == pytest.approx(0.05, rel=0.05)

    def test_the_spectrum_is_flat(self) -> None:
        out = probes.white_noise(WINDOW, rng())
        low = band_energy(out, 100, 1000)
        high = band_energy(out, 6000, 6900)
        # Equal bandwidths, so equal energy. Generous bound: this is a check that it
        # is not tilted, not a spectral estimate.
        assert 0.5 < low / high < 2.0


class TestPinkNoise:
    def test_level_is_the_requested_sigma(self) -> None:
        out = probes.pink_noise(WINDOW, rng(), sigma=0.05)
        assert out.std() == pytest.approx(0.05, rel=0.05)

    def test_it_is_actually_tilted_not_white(self) -> None:
        # The point of pink is the 1/f tilt. If this were white the probe would be a
        # duplicate of the white_noise condition and S_ood would rest on three
        # conditions while claiming four.
        out = probes.pink_noise(WINDOW, rng())
        assert band_energy(out, 100, 1000) > 10 * band_energy(out, 6000, 6900)

    def test_it_has_no_dc_offset(self) -> None:
        out = probes.pink_noise(WINDOW, rng())
        assert abs(float(out.mean())) < 0.01 * float(out.std())


class TestMusic:
    def test_level_is_the_requested_sigma(self) -> None:
        out = probes.music(WINDOW, rng(), sigma=0.05)
        assert out.std() == pytest.approx(0.05, rel=0.05)

    def test_it_is_harmonic_rather_than_noise(self) -> None:
        out = probes.music(WINDOW, rng())
        spectrum = np.abs(np.fft.rfft(out))
        # A pitched signal concentrates energy in a few bins; noise does not. The
        # loudest bin of noise is a small multiple of the median, of a chord it is
        # several orders of magnitude.
        assert spectrum.max() > 100 * float(np.median(spectrum))

    def test_its_energy_sits_in_the_musical_range(self) -> None:
        out = probes.music(WINDOW, rng())
        assert band_energy(out, 80, 2000) > band_energy(out, 6000, 8000)

    def test_the_level_is_not_constant(self) -> None:
        # A four-second sustained tone at fixed level is not what music sounds like
        # and would probe a narrower thing than intended.
        out = probes.music(WINDOW, rng())
        frames = out[: out.size // 320 * 320].reshape(-1, 320)
        envelope = np.sqrt((frames**2).mean(axis=1))
        assert envelope.max() / envelope.min() > 1.2

    def test_nothing_aliases_above_nyquist(self) -> None:
        out = probes.music(WINDOW, rng())
        total = band_energy(out, 0, probes.SAMPLE_RATE / 2)
        near_nyquist = band_energy(out, 7500, 8000)
        assert near_nyquist / total < 1e-3


class TestSilenceDither:
    def test_it_is_inaudibly_small_but_not_zero(self) -> None:
        out = probes.silence_dither(WINDOW, rng())
        assert 0.0 < out.std() < 1e-3

    def test_it_is_not_exactly_zero(self) -> None:
        # Exact zeros divide by a zero standard deviation inside the model's
        # per-window normalisation.
        assert probes.silence_dither(WINDOW, rng()).any()


class TestSegments:
    @staticmethod
    def ramp(seconds: float) -> np.ndarray:
        n = int(seconds * probes.SAMPLE_RATE)
        return np.linspace(0.0, 1.0, n, dtype=np.float32)

    def test_it_returns_the_requested_count_at_the_window_length(self) -> None:
        out = probes.segments(self.ramp(13.0), 5, WINDOW)
        assert len(out) == 5
        assert all(s.size == WINDOW for s in out)

    def test_segments_are_distinct(self) -> None:
        out = probes.segments(self.ramp(13.0), 5, WINDOW)
        for a, b in itertools.pairwise(out):
            assert not np.array_equal(a, b)

    def test_they_span_the_whole_file_not_just_the_front(self) -> None:
        # The score depends on where a window starts, so sampling only the beginning
        # would measure the beginning. See ml/README.md.
        source = self.ramp(13.0)
        out = probes.segments(source, 5, WINDOW)
        assert out[0][0] == pytest.approx(source[0])
        assert out[-1][-1] == pytest.approx(source[-1])

    def test_a_single_segment_is_the_head(self) -> None:
        source = self.ramp(13.0)
        assert np.array_equal(probes.segments(source, 1, WINDOW)[0], source[:WINDOW])

    def test_a_file_shorter_than_one_window_raises(self) -> None:
        with pytest.raises(ValueError, match="shorter than one"):
            probes.segments(self.ramp(2.0), 5, WINDOW)

    def test_a_count_below_one_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            probes.segments(self.ramp(13.0), 0, WINDOW)


class TestOverlapFraction:
    def test_disjoint_segments_report_zero(self) -> None:
        assert probes.overlap_fraction(WINDOW * 5, 5, WINDOW) == pytest.approx(0.0)

    def test_a_short_file_reports_overlap(self) -> None:
        assert probes.overlap_fraction(int(13.0 * 16000), 5, WINDOW) > 0.4

    def test_one_segment_cannot_overlap(self) -> None:
        assert probes.overlap_fraction(WINDOW * 5, 1, WINDOW) == 0.0


class TestOodWiring:
    """The bookkeeping in `ml/tools/ood.py` that decides what S_ood averages."""

    def test_every_probe_condition_has_a_generator(self) -> None:
        from ml.tools import ood

        assert set(ood.PROBE_CONDITIONS) == set(probes.GENERATORS)

    def test_the_genuine_controls_are_not_in_s_ood(self) -> None:
        from ml.tools import ood

        # S_ood is the model's response to non-speech. Folding the controls in would
        # blend the comparison into the statistic being compared.
        assert "genuine_studio" not in ood.PROBE_CONDITIONS
        assert "genuine_phone" not in ood.PROBE_CONDITIONS

    def test_condition_of_strips_the_repetition_index(self) -> None:
        from ml.tools.ood import condition_of

        assert condition_of("white_noise_3") == "white_noise"
        assert condition_of("silence_dither_0") == "silence_dither"
        assert condition_of("genuine_studio_4") == "genuine_studio"

    def test_condition_of_round_trips_every_generated_name(self) -> None:
        from ml.tools import ood

        for condition in (*ood.PROBE_CONDITIONS, "genuine_studio", "genuine_phone"):
            for index in range(ood.REPETITIONS):
                assert ood.condition_of(f"{condition}_{index}") == condition
