"""The run-log schema, and the canonical decode every diagnostic shares.

Three properties are asserted here rather than trusted, because each one failing
would be invisible in the output and would corrupt a conclusion rather than raise:

  * a NaN or an out-of-range score is rejected at construction, not found in a slide
  * `score is None` and `vad_status == "FAIL"` cannot disagree
  * writing the same rows twice produces the same bytes

The canonical decode is tested against a real wav written by the test, so it needs
no fixture audio and no checkpoint.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from ml.augment.phone_codecs import ffmpeg_available
from ml.eval import canonical, runlog

COMMIT = "0" * 40


def row(**overrides: object) -> runlog.Row:
    fields: dict[str, object] = {
        "run_id": "test",
        "filename": "clip",
        "label": "genuine",
        "dataset": "internal",
        "channel": "phone",
        "duration_s": 4.0,
        "vad_status": runlog.VAD_PASS,
        "speech_s": 3.0,
        "score": 0.5,
        "checkpoint": "ckpt.pth",
        "frozen_commit": COMMIT,
    }
    fields.update(overrides)
    return runlog.Row(**fields)  # type: ignore[arg-type]


class TestSchema:
    def test_row_and_fields_describe_the_same_columns(self) -> None:
        # The module asserts this at import; restated so a failure names this test.
        assert set(row().as_cells()) == set(runlog.FIELDS)

    def test_every_column_is_written(self) -> None:
        cells = row().as_cells()
        assert [*cells] == runlog.FIELDS

    def test_defaults_fill_the_optional_columns(self) -> None:
        cells = row().as_cells()
        assert cells["speaker"] == "n/a"
        assert cells["sample_rate"] == "16000"
        assert cells["notes"] == ""


class TestNoNaNReachesTheFile:
    """A NaN survives every ordinary check and then poisons a mean silently."""

    def test_nan_score_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a probability"):
            row(score=float("nan"))

    def test_infinite_score_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a probability"):
            row(score=float("inf"))

    @pytest.mark.parametrize("value", [-0.001, 1.001, 42.0])
    def test_score_outside_zero_to_one_is_rejected(self, value: float) -> None:
        with pytest.raises(ValueError, match="not a probability"):
            row(score=value)

    def test_a_missing_score_writes_an_empty_cell_not_a_number(self) -> None:
        cells = row(score=None, vad_status=runlog.VAD_FAIL).as_cells()
        assert cells["score"] == ""
        assert "nan" not in cells["score"].lower()


class TestStatusAndScoreCannotDisagree:
    def test_no_score_with_pass_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="vad_status is not FAIL"):
            row(score=None, vad_status=runlog.VAD_PASS)

    def test_a_score_with_fail_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="score with vad_status FAIL"):
            row(score=0.5, vad_status=runlog.VAD_FAIL)

    def test_an_unknown_vad_status_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not PASS or FAIL"):
            row(vad_status="maybe")

    def test_an_unknown_label_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="is not one of"):
            row(label="probably_fine")

    def test_provenance_is_required(self) -> None:
        with pytest.raises(ValueError, match="frozen_commit is required"):
            row(frozen_commit="")


class TestReproducible:
    def test_writing_twice_produces_the_same_bytes(self, tmp_path: Path) -> None:
        rows = [
            row(filename="b", score=0.25),
            row(filename="a", score=0.75),
            row(filename="c", score=None, vad_status=runlog.VAD_FAIL),
        ]
        first = runlog.write(rows, tmp_path / "one.csv").read_bytes()
        second = runlog.write(list(reversed(rows)), tmp_path / "two.csv").read_bytes()
        assert first == second

    def test_rows_are_sorted_by_run_dataset_filename(self, tmp_path: Path) -> None:
        rows = [
            row(filename="z", dataset="ifd"),
            row(filename="a", dataset="internal"),
            row(filename="m", dataset="ifd"),
        ]
        written = runlog.read(runlog.write(rows, tmp_path / "r.csv"))
        assert [r["filename"] for r in written] == ["m", "z", "a"]

    def test_line_endings_are_lf_on_every_platform(self, tmp_path: Path) -> None:
        raw = runlog.write([row()], tmp_path / "r.csv").read_bytes()
        assert b"\r\n" not in raw

    def test_floats_are_fixed_width(self) -> None:
        assert row(score=0.5).as_cells()["score"] == "0.500000"
        assert row(duration_s=4.0).as_cells()["duration_s"] == "4.000000"


class TestReadBack:
    def test_scores_skips_missing_rather_than_zeroing_it(self, tmp_path: Path) -> None:
        rows = [
            row(filename="a", score=0.4),
            row(filename="b", score=None, vad_status=runlog.VAD_FAIL),
            row(filename="c", score=0.6),
        ]
        back = runlog.read(runlog.write(rows, tmp_path / "r.csv"))
        assert len(back) == 3
        # Three rows, two scores. A zero here would drag every mean down.
        assert runlog.scores(back) == [0.4, 0.6]


def write_wav(path: Path, samples: np.ndarray, rate: int, channels: int = 1) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return path


class TestCanonicalRead:
    def test_a_canonical_wav_reads_to_float(self, tmp_path: Path) -> None:
        tone = np.sin(np.linspace(0, 40, 16000)).astype(np.float32) * 0.5
        path = write_wav(tmp_path / "ok.wav", tone, 16000)
        loaded = canonical.read_canonical(path)
        assert loaded.dtype == np.float32
        assert loaded.shape == (16000,)
        assert np.abs(loaded).max() <= 1.0

    @pytest.mark.parametrize(("rate", "channels"), [(8000, 1), (16000, 2), (44100, 1)])
    def test_a_non_canonical_wav_is_refused_not_converted(
        self, tmp_path: Path, rate: int, channels: int
    ) -> None:
        # Refused rather than converted: a silent second decode path here would have
        # different resampling properties from canonical_wav and nothing would say so.
        samples = np.zeros(rate * channels, dtype=np.float32)
        path = write_wav(tmp_path / "wrong.wav", samples, rate, channels)
        with pytest.raises(ValueError, match="canonical"):
            canonical.read_canonical(path)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
class TestCanonicalDecode:
    @staticmethod
    def source(tmp_path: Path) -> Path:
        noise = np.random.default_rng(0).normal(0, 0.2, 44100 * 2).astype(np.float32)
        return write_wav(tmp_path / "src.wav", noise, 44100, channels=1)

    def test_decode_produces_the_canonical_format(self, tmp_path: Path) -> None:
        out = canonical.canonical_wav(self.source(tmp_path), tmp_path / "cache")
        with wave.open(str(out), "rb") as handle:
            assert handle.getframerate() == canonical.SAMPLE_RATE
            assert handle.getnchannels() == canonical.CHANNELS
            assert handle.getsampwidth() == 2

    def test_the_second_call_hits_the_cache(self, tmp_path: Path) -> None:
        source = self.source(tmp_path)
        cache = tmp_path / "cache"
        first = canonical.canonical_wav(source, cache)
        stamp = first.stat().st_mtime_ns
        second = canonical.canonical_wav(source, cache)
        assert first == second
        assert second.stat().st_mtime_ns == stamp

    def test_a_changed_source_gets_a_new_cache_entry(self, tmp_path: Path) -> None:
        source = self.source(tmp_path)
        cache = tmp_path / "cache"
        first = canonical.canonical_wav(source, cache)
        write_wav(source, np.zeros(44100, dtype=np.float32), 44100)
        second = canonical.canonical_wav(source, cache)
        assert first != second, "an edited source must not hit the stale entry"

    def test_no_partial_file_survives_a_successful_decode(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        canonical.canonical_wav(self.source(tmp_path), cache)
        assert not list(cache.glob("*.partial*"))

    def test_a_missing_source_names_the_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="missing audio"):
            canonical.canonical_wav(tmp_path / "nope.mp4", tmp_path / "cache")

    def test_an_undecodable_source_raises_with_ffmpeg_stderr(
        self, tmp_path: Path
    ) -> None:
        junk = tmp_path / "junk.mp4"
        junk.write_bytes(b"this is not audio")
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            canonical.canonical_wav(junk, tmp_path / "cache")

    def test_the_flags_are_the_ones_frozen_md_records(self) -> None:
        # Changing these changes every number in the diagnosis, so they are pinned
        # here as literals rather than compared with themselves.
        assert canonical.FFMPEG_ARGS == ("-ac", "1", "-ar", "16000", "-sample_fmt", "s16")


class TestFfmpegPresence:
    def test_ffmpeg_is_actually_available_in_this_environment(self) -> None:
        # Not a skip. If ffmpeg is missing here, the diagnostics cannot decode the
        # source recordings at all and the whole run is invalid.
        assert ffmpeg_available(), "ffmpeg is required to canonicalise source audio"

    def test_ffmpeg_runs(self) -> None:
        from ml.augment.phone_codecs import ffmpeg_path

        binary = ffmpeg_path()
        assert binary is not None
        result = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0
