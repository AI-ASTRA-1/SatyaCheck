"""Separation, the gap, and the deltas the H+4 gate reads.

The arithmetic here decides which branch the whole workstream takes at H+4, and
every failure mode is silent: a delta computed from a missing cell, an overlap read
as "still separated" when it is zero by construction, a mean over one class that
hides the other moving with it. So each of those is asserted directly.

No checkpoint and no audio: the scores are numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.eval.transplant import describe, gap, overlap_is_meaningful, separation
from ml.tools import transplant


class TestSeparationIsTheAgreedFunction:
    def test_disjoint_classes_do_not_overlap(self) -> None:
        out = separation([0.0, 0.1], [0.8, 0.9])
        assert out["genuine_range"] == (0.0, 0.1)
        assert out["spoof_range"] == (0.8, 0.9)
        assert out["overlap"] == pytest.approx(0.0)

    def test_partial_overlap_is_the_shared_width(self) -> None:
        out = separation([0.0, 0.6], [0.4, 0.9])
        assert out["overlap"] == pytest.approx(0.2)

    def test_a_single_spoof_inside_the_genuine_range_reports_zero_overlap(self) -> None:
        # The exact shape ml/README.md records: a genuine range containing the clone.
        # `overlap` measures the width two ranges share, and one clip is a range of
        # zero width, so it reports 0.0 for the worst case there is. Anything reading
        # "overlap 0.0" as "the classes are separated" would be badly wrong here.
        out = separation([0.72, 0.97], [0.85])
        assert out["overlap"] == 0.0
        assert gap([0.72, 0.97], [0.85]) < 0, "the clone is below the genuine ceiling"

    def test_inverted_classes_report_zero_not_a_negative_width(self) -> None:
        out = separation([0.9, 0.99], [0.0, 0.1])
        assert out["overlap"] == 0.0

    def test_both_means_can_move_while_overlap_stays_zero(self) -> None:
        # The failure the gate is written to catch: reporting means alone would call
        # this a large change, and separation is untouched.
        before = separation([0.0, 0.1], [0.8, 0.9])
        after = separation([0.4, 0.5], [0.95, 0.99])
        assert before["overlap"] == after["overlap"] == 0.0


class TestGapAtSmallN:
    def test_gap_is_positive_when_the_classes_are_ordered(self) -> None:
        assert gap([0.029], [0.847]) == pytest.approx(0.818)

    def test_gap_is_negative_when_the_ordering_is_backwards(self) -> None:
        # An inverted detector. `overlap` cannot express this at n=1 and returns 0.0,
        # which reads as healthy separation.
        assert gap([0.91], [0.81]) == pytest.approx(-0.10)
        assert separation([0.91], [0.81])["overlap"] == 0.0

    def test_overlap_is_degenerate_at_one_clip_per_class(self) -> None:
        assert not overlap_is_meaningful([0.029], [0.847])
        assert not overlap_is_meaningful([0.1, 0.2], [0.5])
        assert overlap_is_meaningful([0.1, 0.2], [0.5, 0.6])

    def test_describe_says_so_at_n_equals_one(self) -> None:
        text = describe([0.029], [0.847])
        assert "carries no information" in text
        assert "+0.8180" in text

    def test_describe_does_not_warn_when_n_supports_overlap(self) -> None:
        assert "carries no information" not in describe([0.0, 0.1], [0.8, 0.9])


def scores(**cells: float) -> dict[tuple[str, str, str], float]:
    """`a_bonafide=0.03` -> {("A", "pc", "bonafide"): 0.03}."""
    out = {}
    for key, value in cells.items():
        path, klass = key.split("_", 1)
        out[(path.upper(), "pc", klass)] = value
    return out


class TestDeltas:
    def test_all_four_deltas_when_every_cell_exists(self) -> None:
        out = transplant.deltas(
            scores(
                a_bonafide=0.03,
                a_deepfake=0.85,
                b_bonafide=0.93,
                b_deepfake=0.90,
                c_bonafide=0.99,
                c_deepfake=0.99,
            ),
            ("pc",),
        )
        assert out["delta_genuine_phone"] == pytest.approx(0.90)
        assert out["delta_spoof_phone"] == pytest.approx(0.05)
        assert out["delta_genuine_exotel"] == pytest.approx(0.96)
        assert out["delta_spoof_exotel"] == pytest.approx(0.14)

    def test_a_missing_cell_gives_none_not_zero(self) -> None:
        # A zero here would read as "the channel changed nothing", which is the
        # opposite of "we did not measure it", and Rule 5 fires on small deltas.
        out = transplant.deltas(scores(a_bonafide=0.03, a_deepfake=0.85), ("pc",))
        assert out["delta_genuine_phone"] is None
        assert out["delta_spoof_phone"] is None

    def test_a_delta_needs_both_ends_of_its_pair(self) -> None:
        out = transplant.deltas(scores(b_bonafide=0.93), ("pc",))
        assert out["delta_genuine_phone"] is None

    def test_deltas_average_across_subjects(self) -> None:
        cells = {
            ("A", "pc", "bonafide"): 0.00,
            ("B", "pc", "bonafide"): 0.40,
            ("A", "alia", "bonafide"): 0.00,
            ("B", "alia", "bonafide"): 0.60,
        }
        out = transplant.deltas(cells, ("pc", "alia"))
        assert out["delta_genuine_phone"] == pytest.approx(0.50)

    def test_every_delta_key_the_gate_reads_is_present(self) -> None:
        out = transplant.deltas({}, ("pc",))
        assert set(out) == {
            "delta_genuine_phone",
            "delta_spoof_phone",
            "delta_genuine_exotel",
            "delta_spoof_exotel",
        }


class TestGateShapes:
    """The four score patterns the H+4 rules are meant to tell apart."""

    @staticmethod
    def deltas_for(b_bonafide: float, b_deepfake: float) -> dict[str, float | None]:
        return transplant.deltas(
            scores(
                a_bonafide=0.03, a_deepfake=0.85,
                b_bonafide=b_bonafide, b_deepfake=b_deepfake,
            ),
            ("pc",),
        )

    def test_rule_3_shape_genuine_moves_and_spoof_does_not(self) -> None:
        out = self.deltas_for(0.95, 0.90)
        assert out["delta_genuine_phone"] > 0.40  # type: ignore[operator]
        assert out["delta_spoof_phone"] < 0.15  # type: ignore[operator]

    def test_rule_4_shape_both_classes_move_together(self) -> None:
        out = self.deltas_for(0.95, 0.85 + 0.14)
        assert out["delta_genuine_phone"] > 0.40  # type: ignore[operator]
        # A ceiling at 1.0 means spoof cannot rise 0.40 from 0.85. Rule 4 as written
        # can therefore never fire on a spoof cell that already scores 0.85, which
        # is worth knowing before the gate is read rather than after.
        assert out["delta_spoof_phone"] < 0.40  # type: ignore[operator]

    def test_rule_5_shape_the_transplant_reproduces_nothing(self) -> None:
        out = self.deltas_for(0.10, 0.86)
        assert out["delta_genuine_phone"] < 0.15  # type: ignore[operator]


class TestCaptureConditions:
    def test_a_missing_file_names_the_controls(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="phone_model"):
            transplant.load_conditions(tmp_path)

    def test_a_blank_control_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / transplant.CONDITIONS_FILE).write_text(
            json.dumps(
                {
                    "speaker_volume": "60%",
                    "phone_model": "",
                    "distance_cm": "30",
                    "room": "bedroom",
                    "background_noise": "quiet",
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit, match="phone_model"):
            transplant.load_conditions(tmp_path)

    def test_a_complete_file_loads(self, tmp_path: Path) -> None:
        recorded = {
            "speaker_volume": "60%",
            "phone_model": "Pixel 7a",
            "distance_cm": "30",
            "room": "bedroom, door closed",
            "background_noise": "quiet, fan off",
        }
        (tmp_path / transplant.CONDITIONS_FILE).write_text(
            json.dumps(recorded), encoding="utf-8"
        )
        assert transplant.load_conditions(tmp_path) == recorded

    def test_the_note_carries_every_control(self, tmp_path: Path) -> None:
        recorded = dict.fromkeys(transplant.REQUIRED_CONDITIONS, "x")
        note = transplant.conditions_note(recorded)
        for key in transplant.REQUIRED_CONDITIONS:
            assert key in note


class TestWiring:
    def test_all_three_paths_and_both_classes_are_covered(self) -> None:
        assert set(transplant.PATHS) == {"A", "B", "C"}
        assert set(transplant.CLASSES) == {"bonafide", "deepfake"}
        # Six cells is the experiment. Fewer would be a different experiment.
        assert len(transplant.PATHS) * len(transplant.CLASSES) == 6

    def test_the_default_subject_is_the_one_with_the_cleanest_separation(self) -> None:
        assert transplant.DEFAULT_SUBJECTS == ("pc",)

    def test_class_scores_splits_by_label_not_by_path(self) -> None:
        cells = scores(a_bonafide=0.03, a_deepfake=0.85, b_bonafide=0.93)
        genuine, spoof = transplant.class_scores(cells, "A")
        assert genuine == [0.03]
        assert spoof == [0.85]
        genuine_b, spoof_b = transplant.class_scores(cells, "B")
        assert genuine_b == [0.93]
        assert spoof_b == []
