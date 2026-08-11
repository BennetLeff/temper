"""Coverage paydown v13: regression reporter, corpus_runner, metrics_recorder,
manifest, version_gate, quality_score, constraint reporter, and loop_utils
pure-function tests.

Targets allowlist entries across:
- regression/reporter.py (11): MetricDelta.delta_display, MetricDelta.message,
  RegressionReporter.add_battery_verdict, add_result, battery_report, failed,
  has_failures, passed, skipped, summary, total
- regression/corpus_runner.py (7): BaselineSpec.from_dict, allowed_delta, limit,
  CorpusEntry.pcb_path, constraints_path, baseline_path, CorpusBoardResult.failed,
  CorpusManifest.get_board, check_metric
- regression/metrics_recorder.py (2): PipelineMetricsRecord.to_dict, to_jsonl
- regression/manifest.py (4): GoldenBoard.resolve_path, baseline_yaml_path,
  baseline_pcb_path, GoldenManifest.get_board
- testing/version_gate.py (1): check_format_version
- metrics/quality_score.py (2): QualityScore.to_dict, interpret_score
- constraints/reporter.py (2): ConstraintReport.to_json, to_text
- placer/cp_sat/_loop_utils.py (2): positions_equal, deduplicate_deltas
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


# ===========================================================================
# regression/reporter.py
# ===========================================================================


class TestMetricDelta:
    """Covers MetricDelta.delta_display, MetricDelta.message."""

    def test_delta_display_positive(self):
        from temper_placer.regression.reporter import MetricDelta

        m = MetricDelta(name="test", baseline=1.0, current=1.5, delta=0.5)
        assert m.delta_display == "+0.5"

    def test_delta_display_negative(self):
        from temper_placer.regression.reporter import MetricDelta

        m = MetricDelta(name="test", baseline=1.0, current=0.5, delta=-0.5)
        assert m.delta_display == "-0.5"

    def test_delta_display_zero(self):
        from temper_placer.regression.reporter import MetricDelta

        m = MetricDelta(name="test", baseline=1.0, current=1.0, delta=0.0)
        assert m.delta_display == "0.0"

    def test_message(self):
        from temper_placer.regression.reporter import MetricDelta

        m = MetricDelta(name="clearance", baseline=3.0, current=2.5, delta=-0.5)
        msg = m.message()
        assert "clearance" in msg
        assert "2.5" in msg
        assert "3.0" in msg
        assert "-0.5" in msg

    def test_message_regression(self):
        from temper_placer.regression.reporter import MetricDelta

        m = MetricDelta(name="wirelength", baseline=100.0, current=120.0, delta=20.0, regression=True)
        msg = m.message()
        assert "wirelength" in msg
        assert "120.0" in msg


class TestRegressionReporter:
    """Covers RegressionReporter.add_result, add_battery_verdict, total,
    passed, failed, skipped, has_failures, summary, battery_report."""

    def test_add_result_and_counts(self):
        from temper_placer.regression.reporter import BoardResult, RegressionReporter

        reporter = RegressionReporter()
        assert reporter.total == 0
        assert reporter.passed == 0
        assert reporter.failed == 0
        assert reporter.skipped == 0
        assert reporter.has_failures is False

        reporter.add_result(BoardResult(board_id="board1", passed=True))
        assert reporter.total == 1
        assert reporter.passed == 1
        assert reporter.failed == 0
        assert reporter.has_failures is False

        reporter.add_result(BoardResult(board_id="board2", passed=False))
        assert reporter.total == 2
        assert reporter.passed == 1
        assert reporter.failed == 1
        assert reporter.has_failures is True

    def test_skipped(self):
        from temper_placer.regression.reporter import BoardResult, RegressionReporter

        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="b", passed=False, skipped=True, skip_reason="no pcb"))
        assert reporter.skipped == 1
        assert reporter.failed == 0
        assert reporter.has_failures is False

    def test_summary(self):
        from temper_placer.regression.reporter import BoardResult, RegressionReporter

        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="b1", passed=True))
        reporter.add_result(BoardResult(board_id="b2", passed=False))
        s = reporter.summary()
        assert "2" in s
        assert "[PASS] b1" in s
        assert "[FAIL] b2" in s

    def test_add_battery_verdict(self):
        from temper_placer.regression.reporter import BatteryVerdictReport, RegressionReporter

        reporter = RegressionReporter()
        report = BatteryVerdictReport(
            field_name="thermal",
            verdict="keep",
            verdict_details="ok",
            cost_seconds=1.5,
            budget_exceeded=False,
        )
        reporter.add_battery_verdict(report)
        assert len(reporter.battery_verdicts) == 1

    def test_battery_report_empty(self):
        from temper_placer.regression.reporter import RegressionReporter

        reporter = RegressionReporter()
        r = reporter.battery_report()
        assert "No battery verdicts" in r

    def test_battery_report_with_entries(self):
        from temper_placer.regression.reporter import BatteryVerdictReport, RegressionReporter

        reporter = RegressionReporter()
        reporter.add_battery_verdict(
            BatteryVerdictReport(
                field_name="thermal",
                verdict="keep",
                verdict_details="within budget",
                cost_seconds=2.0,
                budget_exceeded=False,
            )
        )
        r = reporter.battery_report()
        assert "thermal" in r
        assert "KEEP" in r
        assert "within budget" in r


# ===========================================================================
# regression/corpus_runner.py
# ===========================================================================


class TestBaselineSpec:
    """Covers BaselineSpec.from_dict, allowed_delta, limit."""

    def test_from_dict_minimal(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec.from_dict({"mean": 100.0})
        assert spec.mean == 100.0
        assert spec.margin_rel == 0.05
        assert spec.margin_abs == 0.0

    def test_from_dict_full(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec.from_dict({"mean": 200.0, "margin_rel": 0.10, "margin_abs": 1.0})
        assert spec.mean == 200.0
        assert spec.margin_rel == 0.10
        assert spec.margin_abs == 1.0

    def test_allowed_delta_rel_dominates(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec(mean=100.0, margin_rel=0.05, margin_abs=1.0)
        assert spec.allowed_delta() == pytest.approx(5.0)

    def test_allowed_delta_abs_dominates(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec(mean=10.0, margin_rel=0.05, margin_abs=2.0)
        assert spec.allowed_delta() == pytest.approx(2.0)

    def test_allowed_delta_zero_mean(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec(mean=0.0, margin_rel=0.05, margin_abs=1.0)
        assert spec.allowed_delta() == pytest.approx(1.0)

    def test_limit(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec(mean=100.0, margin_rel=0.05)
        assert spec.limit() == pytest.approx(105.0)


class TestCorpusEntry:
    """Covers CorpusEntry.pcb_path, constraints_path, baseline_path."""

    def test_pcb_path(self):
        from temper_placer.regression.corpus_runner import CorpusEntry

        entry = CorpusEntry(id="test", pcb="board.kicad_pcb", constraints="c.yaml", baseline="b.json", seed=42, epochs=100)
        p = entry.pcb_path(Path("/corpus"))
        assert p == Path("/corpus/board.kicad_pcb")

    def test_constraints_path(self):
        from temper_placer.regression.corpus_runner import CorpusEntry

        entry = CorpusEntry(id="test", pcb="b.pcb", constraints="c.yaml", baseline="b.json", seed=42, epochs=100)
        p = entry.constraints_path(Path("/data"))
        assert p == Path("/data/c.yaml")

    def test_baseline_path(self):
        from temper_placer.regression.corpus_runner import CorpusEntry

        entry = CorpusEntry(id="test", pcb="b.pcb", constraints="c.yaml", baseline="b.json", seed=42, epochs=100)
        p = entry.baseline_path(Path("/data"))
        assert p == Path("/data/b.json")


class TestCorpusBoardResult:
    """Covers CorpusBoardResult.failed."""

    def test_failed_when_not_passed_and_not_skipped(self):
        from temper_placer.regression.corpus_runner import CorpusBoardResult

        r = CorpusBoardResult(board_id="b", passed=False)
        assert r.failed is True

    def test_failed_when_passed(self):
        from temper_placer.regression.corpus_runner import CorpusBoardResult

        r = CorpusBoardResult(board_id="b", passed=True)
        assert r.failed is False

    def test_failed_when_skipped(self):
        from temper_placer.regression.corpus_runner import CorpusBoardResult

        r = CorpusBoardResult(board_id="b", passed=False, skipped=True)
        assert r.failed is False


class TestCorpusManifest:
    """Covers CorpusManifest.get_board."""

    def test_get_board_found(self):
        from temper_placer.regression.corpus_runner import CorpusEntry, CorpusManifest

        entry = CorpusEntry(id="b1", pcb="b.pcb", constraints="c.yaml", baseline="bl.json", seed=42, epochs=100)
        manifest = CorpusManifest(version=1, boards=[entry])
        assert manifest.get_board("b1") is entry

    def test_get_board_not_found(self):
        from temper_placer.regression.corpus_runner import CorpusEntry, CorpusManifest

        entry = CorpusEntry(id="b1", pcb="b.pcb", constraints="c.yaml", baseline="bl.json", seed=42, epochs=100)
        manifest = CorpusManifest(version=1, boards=[entry])
        assert manifest.get_board("nonexistent") is None


class TestCheckMetric:
    """Covers check_metric."""

    def test_passed(self):
        from temper_placer.regression.corpus_runner import BaselineSpec, check_metric

        spec = BaselineSpec(mean=100.0, margin_rel=0.05)
        result = check_metric("wirelength", 95.0, spec)
        assert result["passed"] is True
        assert result["name"] == "wirelength"
        assert result["actual"] == 95.0
        assert result["baseline"] == 100.0

    def test_failed(self):
        from temper_placer.regression.corpus_runner import BaselineSpec, check_metric

        spec = BaselineSpec(mean=100.0, margin_rel=0.05)
        result = check_metric("wirelength", 110.0, spec)
        assert result["passed"] is False
        assert result["delta"] == 10.0
        assert result["allowed_delta"] == 5.0


# ===========================================================================
# regression/metrics_recorder.py
# ===========================================================================


class TestPipelineMetricsRecord:
    """Covers PipelineMetricsRecord.to_dict, to_jsonl."""

    def test_to_dict_basic(self):
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        rec = PipelineMetricsRecord(
            board="board1",
            stage="closure",
            module="pipeline",
            git_commit="abc123",
            metrics={"completion_pct": 95.0},
        )
        d = rec.to_dict()
        assert d["board"] == "board1"
        assert d["stage"] == "closure"
        assert d["module"] == "pipeline"
        assert d["git_commit"] == "abc123"
        assert d["metrics"] == {"completion_pct": 95.0}
        assert d["schema_version"] == 2
        assert d["stage_name"] == "closure"

    def test_to_dict_with_drc_delta(self):
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        rec = PipelineMetricsRecord(
            board="board1",
            stage="closure",
            drc_delta=5,
        )
        d = rec.to_dict()
        assert d["drc_delta"] == 5

    def test_to_dict_without_drc_delta(self):
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        rec = PipelineMetricsRecord(
            board="board1",
            stage="closure",
            drc_delta=None,
        )
        d = rec.to_dict()
        assert "drc_delta" not in d

    def test_to_jsonl(self):
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        rec = PipelineMetricsRecord(
            board="board1",
            stage="closure",
            git_commit="abc",
        )
        line = rec.to_jsonl()
        assert isinstance(line, str)
        parsed = json.loads(line)
        assert parsed["board"] == "board1"
        assert parsed["stage"] == "closure"


# ===========================================================================
# regression/manifest.py
# ===========================================================================


class TestGoldenBoard:
    """Covers GoldenBoard.resolve_path, baseline_yaml_path, baseline_pcb_path."""

    @pytest.fixture
    def board(self):
        from temper_placer.regression.manifest import GoldenBoard

        return GoldenBoard(
            id="test_board",
            path="power_pcb_dataset/boards/test.kicad_pcb",
            component_count=10,
            net_count=20,
            baseline_git_hash="abc123",
        )

    def test_resolve_path(self, board):
        p = board.resolve_path(Path("/repo"))
        assert p == Path("/repo/power_pcb_dataset/boards/test.kicad_pcb")

    def test_baseline_yaml_path(self, board):
        p = board.baseline_yaml_path(Path("/repo"))
        assert p == Path("/repo/power_pcb_dataset/baselines/test_board_baseline.yaml")

    def test_baseline_pcb_path(self, board):
        p = board.baseline_pcb_path(Path("/repo"))
        assert p == Path("/repo/power_pcb_dataset/baselines/test_board.kicad_pcb")


class TestGoldenManifest:
    """Covers GoldenManifest.get_board."""

    def test_get_board_found(self):
        from temper_placer.regression.manifest import GoldenBoard, GoldenManifest

        board = GoldenBoard(
            id="test", path="b.pcb", component_count=5, net_count=10, baseline_git_hash="abc"
        )
        m = GoldenManifest(version=1, boards=[board])
        assert m.get_board("test") is board

    def test_get_board_not_found(self):
        from temper_placer.regression.manifest import GoldenBoard, GoldenManifest

        board = GoldenBoard(
            id="test", path="b.pcb", component_count=5, net_count=10, baseline_git_hash="abc"
        )
        m = GoldenManifest(version=1, boards=[board])
        assert m.get_board("missing") is None


# ===========================================================================
# testing/version_gate.py
# ===========================================================================


class TestCheckFormatVersion:
    """Covers check_format_version."""

    def test_match(self):
        from temper_placer.testing.version_gate import check_format_version

        assert check_format_version(3, 3) is None

    def test_mismatch(self):
        from temper_placer.testing.version_gate import check_format_version

        err = check_format_version(1, 2)
        assert err is not None
        assert "MISMATCH" in err
        assert "1" in err
        assert "2" in err


# ===========================================================================
# metrics/quality_score.py
# ===========================================================================


class TestQualityScore:
    """Covers QualityScore.to_dict and interpret_score."""

    def test_to_dict_basic(self):
        from temper_placer.metrics.quality_score import QualityScore

        qs = QualityScore(
            overall=85.0,
            placement_score=90.0,
            drc_score=80.0,
            routing_score=75.0,
            interpretation="good",
            pass_quality=True,
            routing_quality=None,
        )
        d = qs.to_dict()
        assert d["overall"] == 85.0
        assert d["placement_score"] == 90.0
        assert d["drc_score"] == 80.0
        assert d["routing_score"] == 75.0
        assert d["routing_quality"] is None
        assert d["interpretation"] == "good"
        assert d["pass_quality"] is True

    def test_to_dict_with_routing_quality(self):
        from temper_placer.metrics.quality_score import QualityScore
        from temper_placer.metrics.routing_quality import RoutingQualityScore

        rq = RoutingQualityScore(
            completion_rate=0.95,
            via_count=10,
            total_length=500.0,
            drc_violations=0,
            is_acceptable=True,
            score=90.0,
        )
        qs = QualityScore(
            overall=85.0,
            placement_score=90.0,
            drc_score=80.0,
            routing_score=75.0,
            interpretation="good",
            pass_quality=True,
            routing_quality=rq,
        )
        d = qs.to_dict()
        assert d["routing_quality"] is not None
        assert d["routing_quality"]["completion_rate"] == 0.95

    def test_interpret_score(self):
        from temper_placer.metrics.quality_score import interpret_score

        result = interpret_score(85.0)
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# constraints/reporter.py
# ===========================================================================


class TestConstraintReport:
    """Covers ConstraintReport.to_json, ConstraintReport.to_text."""

    def test_to_json_empty(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport()
        j = report.to_json()
        data = json.loads(j)
        assert isinstance(data, dict)

    def test_to_json_with_results(self):
        from temper_placer.constraints.reporter import (
            ConstraintReport,
            ConstraintResult,
            ConstraintStatus,
        )

        report = ConstraintReport()
        report.results.append(
            ConstraintResult(
                constraint_type="Spacing",
                status=ConstraintStatus.SATISFIED,
                tier="hard",
                components=["U1", "Q1"],
                message="OK",
            )
        )
        report.results.append(
            ConstraintResult(
                constraint_type="Proximity",
                status=ConstraintStatus.VIOLATED,
                tier="soft",
                components=["U2"],
                message="Too close",
            )
        )
        j = report.to_json()
        data = json.loads(j)
        assert isinstance(data, dict)

    def test_to_text_empty(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport()
        text = report.to_text()
        assert isinstance(text, str)

    def test_to_text_with_results(self):
        from temper_placer.constraints.reporter import (
            ConstraintReport,
            ConstraintResult,
            ConstraintStatus,
        )

        report = ConstraintReport()
        report.results.append(
            ConstraintResult(
                constraint_type="Spacing",
                status=ConstraintStatus.VIOLATED,
                tier="hard",
                components=["U1"],
                message="Spacing violation",
            )
        )
        text = report.to_text()
        assert isinstance(text, str)
        assert len(text) > 0


# ===========================================================================
# placer/cp_sat/_loop_utils.py
# ===========================================================================


class TestPositionsEqual:
    """Covers positions_equal."""

    def test_same_dict(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        d = {"U1": (10.0, 20.0), "Q1": (30.0, 40.0)}
        assert positions_equal(d, d) is True

    def test_equal_dicts(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = {"U1": (10.0, 20.0), "Q1": (30.0, 40.0)}
        b = {"U1": (10.0, 20.0), "Q1": (30.0, 40.0)}
        assert positions_equal(a, b) is True

    def test_unequal_dicts(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = {"U1": (10.0, 20.0)}
        b = {"U1": (10.2, 20.0)}  # delta 0.2 > 0.1
        assert positions_equal(a, b) is False

    def test_unequal_dicts_more_than_tolerance(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = {"U1": (10.0, 20.0)}
        b = {"U1": (10.5, 20.0)}  # delta 0.5 > 0.1
        assert positions_equal(a, b) is False

    def test_within_tolerance(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = {"U1": (10.0, 20.0)}
        b = {"U1": (10.05, 20.05)}  # delta 0.05 <= 0.1
        assert positions_equal(a, b) is True

    def test_different_keys(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = {"U1": (10.0, 20.0)}
        b = {"U2": (10.0, 20.0)}
        assert positions_equal(a, b) is False

    def test_different_types(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = {"U1": (10.0, 20.0)}
        assert positions_equal(a, [1, 2, 3]) is False

    def test_numpy_arrays(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = np.array([[10.0, 20.0], [30.0, 40.0]])
        b = np.array([[10.0, 20.0], [30.0, 40.0]])
        assert positions_equal(a, b) is True

    def test_numpy_arrays_unequal(self):
        from temper_placer.placer.cp_sat._loop_utils import positions_equal

        a = np.array([[10.0, 20.0]])
        b = np.array([[50.0, 60.0]])
        assert positions_equal(a, b) is False
