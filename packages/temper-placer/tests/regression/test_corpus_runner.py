"""Tests for corpus regression runner."""

import json
from pathlib import Path

import pytest

from temper_placer.regression.corpus_runner import (
    BaselineFile,
    BaselineSpec,
    CorpusBoardResult,
    CorpusEntry,
    CorpusManifest,
    CorpusRegressionRunner,
    check_metric,
)


class TestCheckMetric:
    def test_pass_within_tolerance(self):
        spec = BaselineSpec(mean=100.0, margin_rel=0.05, margin_abs=2.0)
        result = check_metric("wirelength", 104.0, spec)
        assert result["passed"] is True
        assert result["delta"] == 4.0

    def test_fail_exceeds_tolerance(self):
        spec = BaselineSpec(mean=100.0, margin_rel=0.05, margin_abs=2.0)
        result = check_metric("wirelength", 106.0, spec)
        assert result["passed"] is False

    def test_uses_abs_margin_when_larger(self):
        spec = BaselineSpec(mean=10.0, margin_rel=0.05, margin_abs=5.0)
        result = check_metric("overlap", 14.0, spec)
        assert result["passed"] is True

    def test_uses_rel_margin_when_larger(self):
        spec = BaselineSpec(mean=100.0, margin_rel=0.20, margin_abs=2.0)
        result = check_metric("loss", 119.0, spec)
        assert result["passed"] is True

    def test_exact_mean_passes(self):
        spec = BaselineSpec(mean=50.0, margin_rel=0.05, margin_abs=1.0)
        result = check_metric("hpwl", 50.0, spec)
        assert result["passed"] is True


class TestBaselineSpec:
    def test_allowed_delta_uses_max(self):
        spec = BaselineSpec(mean=100.0, margin_rel=0.05, margin_abs=10.0)
        assert spec.allowed_delta() == 10.0

    def test_limit(self):
        spec = BaselineSpec(mean=200.0, margin_rel=0.10, margin_abs=5.0)
        assert spec.limit() == 220.0

    def test_from_dict_defaults(self):
        spec = BaselineSpec.from_dict({"mean": 42.0})
        assert spec.mean == 42.0
        assert spec.margin_rel == 0.05
        assert spec.margin_abs == 0.0

    def test_from_dict_full(self):
        spec = BaselineSpec.from_dict({"mean": 42.0, "margin_rel": 0.10, "margin_abs": 3.0})
        assert spec.mean == 42.0
        assert spec.margin_rel == 0.10
        assert spec.margin_abs == 3.0


class TestBaselineFile:
    def test_load_valid(self, tmp_path: Path):
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps({
            "board_id": "test",
            "extracted_at": "2026-01-01T00:00:00",
            "git_hash": "abc12345",
            "config": {"seed": 42, "epochs": 1000},
            "metrics": {
                "final_loss": {"mean": 100.0, "margin_rel": 0.05, "margin_abs": 10.0},
                "wirelength_final": {"mean": 500.0, "margin_rel": 0.10, "margin_abs": 50.0},
            },
        }))
        baseline = BaselineFile.load(baseline_path)
        assert baseline.board_id == "test"
        assert baseline.git_hash == "abc12345"
        assert "final_loss" in baseline.metrics
        assert "wirelength_final" in baseline.metrics
        assert baseline.metrics["final_loss"].mean == 100.0
        assert baseline.metrics["wirelength_final"].margin_rel == 0.10


class TestCorpusEntry:
    def test_paths(self, tmp_path: Path):
        entry = CorpusEntry(
            id="test",
            pcb="test/pcb.kicad_pcb",
            constraints="test/constraints.yaml",
            baseline="test/baseline.json",
            seed=42,
            epochs=8000,
        )
        assert entry.pcb_path(tmp_path) == tmp_path / "test" / "pcb.kicad_pcb"
        assert entry.constraints_path(tmp_path) == tmp_path / "test" / "constraints.yaml"
        assert entry.baseline_path(tmp_path) == tmp_path / "test" / "baseline.json"


class TestCorpusManifest:
    def test_load_valid(self, tmp_path: Path):
        manifest_content = """
version: 1
boards:
  - id: temper
    pcb: temper/temper.kicad_pcb
    constraints: temper/constraints.yaml
    baseline: temper/baseline.json
    seed: 42
    epochs: 8000
    description: "Test board"
"""
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text(manifest_content)
        manifest = CorpusManifest.load(manifest_path)
        assert manifest.version == 1
        assert len(manifest.boards) == 1
        assert manifest.boards[0].id == "temper"
        assert manifest.boards[0].seed == 42
        assert manifest.boards[0].epochs == 8000

    def test_get_board(self, tmp_path: Path):
        entry = CorpusEntry(id="b1", pcb="b1/pcb.kicad_pcb", constraints="b1/c.yaml",
                            baseline="b1/b.json", seed=1, epochs=100)
        manifest = CorpusManifest(version=1, boards=[entry])
        assert manifest.get_board("b1") is not None
        assert manifest.get_board("b2") is None

    def test_load_missing_file(self, tmp_path: Path):
        manifest_path = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError, match="manifest not found"):
            CorpusManifest.load(manifest_path)


class TestCorpusBoardResult:
    def test_pass(self):
        result = CorpusBoardResult(board_id="b1", passed=True)
        assert result.passed
        assert not result.skipped
        assert not result.failed

    def test_fail(self):
        result = CorpusBoardResult(board_id="b1", passed=False)
        assert not result.passed
        assert result.failed

    def test_skip(self):
        result = CorpusBoardResult(board_id="b1", passed=False, skipped=True,
                                   skip_reason="Missing PCB")
        assert result.skipped
        assert not result.failed


class TestCorpusRegressionRunner:
    def test_run_with_missing_pcb(self, tmp_path: Path):
        corpus_root = tmp_path
        manifest_path = corpus_root / "manifest.yaml"
        manifest_path.write_text("""
version: 1
boards:
  - id: missing
    pcb: missing/missing.kicad_pcb
    constraints: missing/constraints.yaml
    baseline: missing/baseline.json
    seed: 42
    epochs: 100
""")
        runner = CorpusRegressionRunner(corpus_root=corpus_root)
        # Board should skip since PCB doesn't exist
        result = runner._run_board(runner.manifest.boards[0])
        assert result.skipped
        assert not result.passed
        assert "PCB file not found" in result.skip_reason

    def test_run_with_missing_baseline(self, tmp_path: Path):
        corpus_root = tmp_path
        manifest_path = corpus_root / "manifest.yaml"
        board_dir = corpus_root / "board"
        board_dir.mkdir(parents=True)
        (board_dir / "board.kicad_pcb").touch()
        (board_dir / "constraints.yaml").touch()

        manifest_path.write_text("""
version: 1
boards:
  - id: board
    pcb: board/board.kicad_pcb
    constraints: board/constraints.yaml
    baseline: board/baseline.json
    seed: 42
    epochs: 100
""")
        runner = CorpusRegressionRunner(corpus_root=corpus_root)
        result = runner._run_board(runner.manifest.boards[0])
        assert result.skipped
        assert "Baseline file not found" in result.skip_reason

    def test_run_with_invalid_baseline(self, tmp_path: Path):
        corpus_root = tmp_path
        manifest_path = corpus_root / "manifest.yaml"
        board_dir = corpus_root / "board"
        board_dir.mkdir(parents=True)
        (board_dir / "board.kicad_pcb").touch()
        (board_dir / "constraints.yaml").touch()
        (board_dir / "baseline.json").write_text("not valid json")

        manifest_path.write_text("""
version: 1
boards:
  - id: board
    pcb: board/board.kicad_pcb
    constraints: board/constraints.yaml
    baseline: board/baseline.json
    seed: 42
    epochs: 100
""")
        runner = CorpusRegressionRunner(corpus_root=corpus_root)
        result = runner._run_board(runner.manifest.boards[0])
        assert result.skipped
        assert "Failed to load baseline" in result.skip_reason

    def test_run_success_path(self, tmp_path: Path):
        """Integration test using minimal board fixture."""
        corpus_root = tmp_path
        manifest_path = corpus_root / "manifest.yaml"
        board_dir = corpus_root / "minimal"
        board_dir.mkdir(parents=True)

        # Copy minimal board and constraints
        fixtures = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
        import shutil
        shutil.copy(fixtures / "minimal_board.kicad_pcb", board_dir / "minimal_board.kicad_pcb")
        shutil.copy(fixtures / "constraints_minimal.yaml", board_dir / "constraints_minimal.yaml")

        # Create a baseline with very generous margins
        (board_dir / "baseline.json").write_text(json.dumps({
            "board_id": "minimal",
            "extracted_at": "2026-01-01T00:00:00",
            "git_hash": "test",
            "config": {"seed": 43, "epochs": 50, "curriculum": True, "heuristics": True},
            "metrics": {
                "final_loss": {"mean": 0.0, "margin_rel": 1.0, "margin_abs": 1e6},
                "wirelength_final": {"mean": 0.0, "margin_rel": 1.0, "margin_abs": 1e6},
                "overlap_loss_final": {"mean": 0.0, "margin_rel": 1.0, "margin_abs": 1e6},
                "boundary_loss_final": {"mean": 0.0, "margin_rel": 1.0, "margin_abs": 1e6},
                "hpwl_final": {"mean": 0.0, "margin_rel": 1.0, "margin_abs": 1e6},
            },
        }))

        manifest_path.write_text("""
version: 1
boards:
  - id: minimal
    pcb: minimal/minimal_board.kicad_pcb
    constraints: minimal/constraints_minimal.yaml
    baseline: minimal/baseline.json
    seed: 43
    epochs: 50
""")
        runner = CorpusRegressionRunner(corpus_root=corpus_root)
        result = runner._run_board(runner.manifest.boards[0])
        assert result.passed, f"Expected PASS, got errors: {result.errors}"
        assert len(result.metric_checks) >= 1
        assert result.metrics["final_loss"] > 0
