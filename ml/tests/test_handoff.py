"""The handoff bundle and the latency benchmark.

The bundle is what reaches another machine. Its failure mode is silent: a file that
did not copy, or bytes that arrived intact into an environment that produces
different numbers. Both would surface as "the integration test gives odd scores"
days later, so both are checked explicitly.

Nothing here loads a checkpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ml.tools import handoff, latency


class TestRequiredFiles:
    def test_the_bundle_is_five_files(self) -> None:
        assert len(handoff.REQUIRED) == 5

    def test_the_xlsr_weights_are_not_in_it(self) -> None:
        # 1.2 GB that is never loaded: config.json builds an empty Wav2Vec2Model and
        # every weight comes from the fine-tuned checkpoint. Verified by loading
        # with the file absent.
        assert not any("pytorch_model.bin" in name for name in handoff.REQUIRED)

    def test_the_fairseq_source_is_not_in_it(self) -> None:
        # fairseq/xlsr2_300m.pt is 3.6 GB and was used once to derive the key
        # mapping. The mapping itself, ssl_aasist/fairseq_to_hf.json, is 42 KB and
        # is in the bundle, so the check is on the directory rather than the word.
        assert not any(name.startswith("fairseq/") for name in handoff.REQUIRED)
        assert "ssl_aasist/fairseq_to_hf.json" in handoff.REQUIRED

    def test_the_confidence_reference_is_in_it(self) -> None:
        # Easy to forget: it is new, small, and api.py refuses to load without it.
        assert "confidence_reference.npz" in handoff.REQUIRED

    def test_the_checkpoint_and_the_config_are_both_in_it(self) -> None:
        assert "Best_LA_model_for_DF.pth" in handoff.REQUIRED
        assert "wav2vec2-xls-r-300m/config.json" in handoff.REQUIRED

    def test_stubbed_checks_bring_nothing(self) -> None:
        joined = " ".join(handoff.REQUIRED)
        assert "whisper" not in joined
        assert "ecapa" not in joined


class TestFileSelection:
    def test_aasist_is_opt_in(self, tmp_path: Path) -> None:
        assert handoff.files_for(False, tmp_path) == list(handoff.REQUIRED)

    def test_caches_and_git_are_excluded(self, tmp_path: Path) -> None:
        base = tmp_path / "aasist" / "models"
        (base / "__pycache__").mkdir(parents=True)
        (tmp_path / "aasist" / ".git").mkdir(parents=True)
        (base / "AASIST.pth").write_bytes(b"w")
        (base / "__pycache__" / "x.pyc").write_bytes(b"c")
        (tmp_path / "aasist" / ".git" / "HEAD").write_bytes(b"g")
        names = handoff.files_for(True, tmp_path)
        assert "aasist/models/AASIST.pth" in names
        assert not any("__pycache__" in n for n in names)
        assert not any(".git" in n for n in names)


class TestProbe:
    def test_the_probe_is_reproducible_from_a_seed(self) -> None:
        # Generated rather than shipped, so no audio travels with the bundle.
        assert np.array_equal(handoff.probe_window(), handoff.probe_window())

    def test_it_is_one_analysis_window(self) -> None:
        assert handoff.probe_window().shape == (64600,)


class TestVerify:
    def test_a_bundle_without_a_manifest_is_refused(self, tmp_path: Path) -> None:
        assert handoff.verify(tmp_path) == 1

    def test_a_corrupt_file_is_caught(self, tmp_path: Path) -> None:
        (tmp_path / "a.bin").write_bytes(b"original")
        manifest = {
            "files": {"a.bin": {"sha256": handoff.sha256(tmp_path / "a.bin"), "bytes": 8}},
            "probe": {"seed": 1, "samples": 1, "p_synthetic": "0.5"},
            "env_var": "SATYACHECK_MODEL_DIR",
        }
        (tmp_path / handoff.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        (tmp_path / "a.bin").write_bytes(b"tampered")
        assert handoff.verify(tmp_path) == 1

    def test_a_missing_file_is_caught(self, tmp_path: Path) -> None:
        manifest = {
            "files": {"gone.bin": {"sha256": "0" * 64, "bytes": 1}},
            "probe": {"seed": 1, "samples": 1, "p_synthetic": "0.5"},
            "env_var": "SATYACHECK_MODEL_DIR",
        }
        (tmp_path / handoff.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        assert handoff.verify(tmp_path) == 1

    def test_sha256_changes_with_content(self, tmp_path: Path) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        a.write_bytes(b"one")
        b.write_bytes(b"two")
        assert handoff.sha256(a) != handoff.sha256(b)


class TestLatencyBudget:
    def test_the_budget_matches_agents_md(self) -> None:
        assert latency.STAGE_04_BUDGET_MS == 180.0
        assert latency.END_TO_END_BUDGET_MS == 400.0

    def test_within_budget_uses_the_median_not_the_best_case(self) -> None:
        # A run whose fastest call fits and whose typical call does not is over.
        timing = latency.Timing("cpu", "m", "score", [100.0, 400.0, 420.0, 430.0])
        assert timing.low < latency.STAGE_04_BUDGET_MS
        assert not timing.within

    def test_the_range_is_reported_alongside_the_median(self) -> None:
        timing = latency.Timing("cuda", "m", "score", [28.0, 30.0, 36.0])
        assert timing.median == pytest.approx(30.0)
        assert (timing.low, timing.high) == (28.0, 36.0)

    def test_a_fast_run_is_within_budget(self) -> None:
        assert latency.Timing("cuda", "m", "score", [29.0, 31.0]).within
