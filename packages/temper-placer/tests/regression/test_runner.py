"""Tests for regression runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.regression.manifest import GoldenBoard, GoldenManifest
from temper_placer.regression.reporter import BoardResult, MetricDelta, RegressionReporter


class TestGoldenManifest:
    def test_load_empty_manifest(self, tmp_path: Path):
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text("version: 1\nboards: []\n")
        manifest = GoldenManifest.load(manifest_path)
        assert manifest.version == 1
        assert len(manifest.boards) == 0

    def test_load_with_boards(self, tmp_path: Path):
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text("""
version: 1
boards:
  - id: test_board
    path: pcb/test.kicad_pcb
    component_count: 5
    net_count: 3
    baseline_git_hash: abc123
    description: "Test board"
""")
        manifest = GoldenManifest.load(manifest_path)
        assert len(manifest.boards) == 1
        board = manifest.boards[0]
        assert board.id == "test_board"
        assert board.path == "pcb/test.kicad_pcb"
        assert board.component_count == 5
        assert board.net_count == 3

    def test_validate_missing_pcb(self, tmp_path: Path):
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text("""
version: 1
boards:
  - id: missing_board
    path: pcb/nonexistent.kicad_pcb
    component_count: 1
    net_count: 1
    baseline_git_hash: unknown
""")
        manifest = GoldenManifest.load(manifest_path)
        errors = manifest.validate(tmp_path)
        assert len(errors) == 1
        assert "nonexistent.kicad_pcb" in errors[0]

    def test_get_board(self):
        board = GoldenBoard(id="b1", path="pcb/b1.kicad_pcb", component_count=5, net_count=3, baseline_git_hash="x")
        manifest = GoldenManifest(version=1, boards=[board])
        assert manifest.get_board("b1") is not None
        assert manifest.get_board("b2") is None


class TestMetricDelta:
    def test_regression_detected(self):
        delta = MetricDelta(name="drc_errors", baseline=10.0, current=15.0, delta=5.0)
        assert delta.regression is False

    def test_no_regression(self):
        delta = MetricDelta(name="drc_errors", baseline=10.0, current=5.0, delta=-5.0)
        assert delta.regression is False

    def test_delta_display(self):
        delta = MetricDelta(name="x", baseline=10.0, current=15.0, delta=5.0)
        assert "+5.0" in delta.delta_display


class TestBoardResult:
    def test_pass(self):
        result = BoardResult(board_id="b1", passed=True)
        assert result.passed
        assert not result.skipped

    def test_fail(self):
        result = BoardResult(board_id="b1", passed=False, errors=["bad"])
        assert not result.passed
        assert not result.skipped

    def test_skip(self):
        result = BoardResult(board_id="b1", passed=False, skipped=True, skip_reason="missing")
        assert result.skipped
        assert result.skip_reason == "missing"


class TestRegressionReporter:
    def test_empty(self):
        reporter = RegressionReporter()
        assert reporter.total == 0
        assert reporter.passed == 0
        assert reporter.failed == 0
        assert not reporter.has_failures

    def test_mixed_results(self):
        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="b1", passed=True))
        reporter.add_result(BoardResult(board_id="b2", passed=False, errors=["fail"]))
        reporter.add_result(BoardResult(board_id="b3", passed=False, skipped=True, skip_reason="missing"))
        assert reporter.total == 3
        assert reporter.passed == 1
        assert reporter.failed == 1
        assert reporter.skipped == 1
        assert reporter.has_failures

    def test_summary(self):
        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="b1", passed=True))
        summary = reporter.summary()
        assert "PASS" in summary
        assert "b1" in summary
