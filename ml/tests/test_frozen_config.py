"""FROZEN.md must keep agreeing with the code it claims to describe.

The whole diagnosis rests on one assertion: every experiment between H+0 and H+4 ran
on the same configuration. That assertion is worth nothing if `FROZEN.md` is a
snapshot that drifted. If someone changes `ACTIVITY_FLOOR`, the window size, the
spoof class index or the evidence threshold without touching `FROZEN.md`, these
tests fail and say which field moved.

They do not check `frozen_at` (a timestamp), `frozen_commit` (moves with every
commit) or `checkpoint_sha256` (costs seconds to compute). Those are recorded once
and read by a human.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ml.tools.frozen_config import collect

FROZEN = Path(__file__).resolve().parents[2] / "FROZEN.md"

#: Fields whose value is a timestamp, a commit or an expensive hash. Recorded in
#: FROZEN.md, deliberately not asserted here.
VOLATILE = {"frozen_at", "frozen_commit", "checkpoint_sha256"}


def frozen_block() -> dict[str, str]:
    """The `key : value` pairs from the first fenced block in FROZEN.md."""
    text = FROZEN.read_text(encoding="utf-8")
    blocks = re.findall(r"```\n(.*?)```", text, flags=re.DOTALL)
    assert blocks, "FROZEN.md has no fenced configuration block"
    pairs: dict[str, str] = {}
    for line in blocks[0].splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, _, value = line.partition(":")
        pairs[key.strip()] = value.strip()
    return pairs


class TestFrozenFileExists:
    def test_frozen_md_is_present(self) -> None:
        assert FROZEN.exists(), f"{FROZEN} is missing; the diagnosis has no baseline"

    def test_the_block_parses(self) -> None:
        assert frozen_block(), "the fenced block in FROZEN.md yielded no fields"


class TestNoDrift:
    """Each field FROZEN.md records must still be what the code reports."""

    @pytest.mark.parametrize(
        ("frozen_key", "code_key"),
        [
            ("model_id", "model_id"),
            ("input_sample_rate", "input_sample_rate"),
            ("resample_method", None),
            ("vad_activity_floor", "vad_activity_floor"),
            ("threshold", "threshold"),
        ],
    )
    def test_scalar_field_matches(self, frozen_key: str, code_key: str | None) -> None:
        recorded = frozen_block()[frozen_key]
        if code_key is None:
            # resample_method carries a parenthesised note in the doc, so the
            # assertion is that the ffmpeg flags are a prefix of it.
            assert recorded.startswith(collect()["resample_method"])
            return
        # Several fields carry an explanatory note after the value. The value is the
        # first token; the note is for a human and is not asserted.
        assert recorded.split()[0] == collect()[code_key]

    def test_window_and_hop_match(self) -> None:
        block = frozen_block()
        fields = collect()
        assert block["window_s"].split()[0] == fields["window_s"]
        # hop_s in the doc spans two lines and names both paths.
        assert fields["hop_s"] in block["hop_s"]

    def test_checkpoint_path_matches(self) -> None:
        assert frozen_block()["checkpoint_path"] == collect()["checkpoint_path"]

    def test_torch_version_matches(self) -> None:
        assert frozen_block()["torch_version"] == collect()["torch_version"]


class TestConstantsNotSilentlyChanged:
    """The constants the diagnosis depends on, asserted against literals.

    Deliberately hard-coded rather than read from the module. A test that compares a
    constant with itself passes whatever the constant becomes, which is exactly the
    failure this file exists to prevent.
    """

    def test_window_is_the_published_size(self) -> None:
        assert collect()["window_samples"] == "64600"

    def test_spoof_class_index_is_zero(self) -> None:
        assert collect()["spoof_class_index"] == "0"

    def test_activity_floor_is_the_documented_one(self) -> None:
        assert collect()["vad_activity_floor"] == "0.4"

    def test_input_normalisation_is_on(self) -> None:
        # Off, the score tracks loudness rather than content. Measured, in ml/README.md.
        assert collect()["normalize_input"] == "True"

    def test_the_frozen_checkpoint_is_not_a_finetuned_one(self) -> None:
        path = collect()["checkpoint_path"]
        assert path.endswith("Best_LA_model_for_DF.pth")
        assert "finetuned" not in path
