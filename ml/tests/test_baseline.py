"""The baseline's anchor gate, tested on constructed rows.

`check_anchors` is the one thing standing between "this environment matches the one
that produced ml/README.md" and a table of plausible-looking numbers from a build
that quietly moved. It has to fail loudly, so these tests assert that it fails, not
just that it passes.

No checkpoint, no audio and no GPU: the rows are built by hand.
"""

from __future__ import annotations

import pytest

from ml.eval import runlog
from ml.tools import baseline

COMMIT = "0" * 40


def row(filename: str, score: float | None, **overrides: object) -> runlog.Row:
    fields: dict[str, object] = {
        "run_id": "baseline",
        "filename": filename,
        "label": "genuine",
        "dataset": "ifd",
        "channel": "broadcast",
        "duration_s": 5.0,
        "vad_status": runlog.VAD_PASS if score is not None else runlog.VAD_FAIL,
        "speech_s": 3.0,
        "score": score,
        "checkpoint": baseline.CHECKPOINT,
        "frozen_commit": COMMIT,
    }
    fields.update(overrides)
    return runlog.Row(**fields)  # type: ignore[arg-type]


def asvspoof(score: float, index: int = 0) -> runlog.Row:
    return row(
        f"LA_E_{index:07d}", score, dataset="asvspoof", channel="studio"
    )


def holding_rows() -> list[runlog.Row]:
    """A run where every anchor is where ml/README.md says it should be."""
    return [
        row("pc_bonafide", 0.029),
        row("pc_deepfake", 0.847, label="spoof", channel="generated"),
        *[asvspoof(0.0001, i) for i in range(10)],
    ]


class TestAnchorsHold:
    def test_a_matching_run_reports_no_failures(self) -> None:
        assert baseline.check_anchors(holding_rows()) == []

    def test_small_drift_inside_tolerance_is_accepted(self) -> None:
        rows = holding_rows()
        rows[0] = row("pc_bonafide", 0.029 + 0.009)
        rows[1] = row("pc_deepfake", 0.847 - 0.04, label="spoof", channel="generated")
        assert baseline.check_anchors(rows) == []


class TestAnchorsDrift:
    """Each of these would otherwise produce a full, plausible, wrong table."""

    def test_a_moved_bonafide_anchor_fails(self) -> None:
        rows = holding_rows()
        rows[0] = row("pc_bonafide", 0.9)
        failures = baseline.check_anchors(rows)
        assert any("pc_bonafide" in f for f in failures)

    def test_a_moved_spoof_anchor_fails(self) -> None:
        rows = holding_rows()
        rows[1] = row("pc_deepfake", 0.2, label="spoof", channel="generated")
        failures = baseline.check_anchors(rows)
        assert any("pc_deepfake" in f for f in failures)

    def test_asvspoof_bonafide_drifting_upward_fails(self) -> None:
        rows = [
            row("pc_bonafide", 0.029),
            row("pc_deepfake", 0.847, label="spoof", channel="generated"),
            *[asvspoof(0.4, i) for i in range(10)],
        ]
        failures = baseline.check_anchors(rows)
        assert any("asvspoof bonafide median" in f for f in failures)

    def test_one_outlier_does_not_trip_the_median(self) -> None:
        rows = [
            row("pc_bonafide", 0.029),
            row("pc_deepfake", 0.847, label="spoof", channel="generated"),
            asvspoof(0.99, 0),
            *[asvspoof(0.0001, i) for i in range(1, 10)],
        ]
        # A median, not a mean, precisely so a single unusual clip is not read as
        # the environment having moved.
        assert baseline.check_anchors(rows) == []

    def test_a_missing_anchor_row_fails_rather_than_passing_silently(self) -> None:
        rows = [r for r in holding_rows() if r.filename != "pc_bonafide"]
        failures = baseline.check_anchors(rows)
        assert any("no score to compare" in f for f in failures)

    def test_an_anchor_that_failed_vad_fails_the_check(self) -> None:
        rows = holding_rows()
        rows[0] = row("pc_bonafide", None)
        failures = baseline.check_anchors(rows)
        assert any("pc_bonafide" in f for f in failures)

    def test_no_asvspoof_rows_at_all_fails(self) -> None:
        rows = [
            row("pc_bonafide", 0.029),
            row("pc_deepfake", 0.847, label="spoof", channel="generated"),
        ]
        failures = baseline.check_anchors(rows)
        assert any("no ASVspoof bonafide rows" in f for f in failures)


class TestRecordedAnchors:
    """The expected values themselves, pinned to what ml/README.md records."""

    def test_the_ifd_anchors_are_the_xlsr_numbers(self) -> None:
        assert baseline.ANCHORS["pc_bonafide"][0] == pytest.approx(0.029)
        assert baseline.ANCHORS["pc_deepfake"][0] == pytest.approx(0.847)

    def test_the_asvspoof_ceiling_is_not_an_aasist_number(self) -> None:
        # 0.005 to 0.006 is the AASIST figure. On xlsr-aasist ASVspoof bonafide is
        # 0.000, so a ceiling loose enough to admit 0.006 would hide real drift.
        assert baseline.ASVSPOOF_BONAFIDE_CEILING <= 0.01

    def test_the_frozen_checkpoint_is_the_published_one(self) -> None:
        assert baseline.CHECKPOINT == "Best_LA_model_for_DF.pth"


class TestSources:
    def test_every_source_is_named_with_its_speaker_and_label(self) -> None:
        for working, (relative, speaker, label) in baseline.SOURCES.items():
            assert working.endswith(".wav")
            assert relative
            assert speaker.startswith("speaker_")
            assert label in {"genuine", "spoof"}

    def test_exactly_one_source_is_the_clone(self) -> None:
        spoofs = [k for k, v in baseline.SOURCES.items() if v[2] == "spoof"]
        assert spoofs == ["nik_clone.wav"]

    def test_five_genuine_recordings_across_three_speakers(self) -> None:
        genuine = [v for v in baseline.SOURCES.values() if v[2] == "genuine"]
        assert len(genuine) == 5
        # n=3 speakers, 5 recordings. Any figure from this set states both.
        assert len({v[1] for v in genuine}) == 3
