"""Tests for validation.drc_fence module (metrics types)."""

from temper_placer.validation.drc_fence import (
    CheckMetrics,
    FenceResult,
    MetricsSummary,
)


class TestCheckMetrics:
    """Tests for CheckMetrics."""

    def test_defaults(self):
        cm = CheckMetrics(check_name="drc_clearance", category="drc",
                          elapsed_ms=0.0, issue_counts={}, custom_metrics={})
        assert cm.passed is True
        assert cm.total_issues == 0

    def test_to_dict(self):
        cm = CheckMetrics(
            check_name="drc_clearance",
            category="drc",
            elapsed_ms=42.0,
            issue_counts={"ERROR": 3},
            custom_metrics={"overlap_mm": 0.5},
        )
        d = cm.to_dict()
        assert d["check_name"] == "drc_clearance"
        assert d["elapsed_ms"] == 42.0
        assert d["total_issues"] == 3
        assert d["passed"] is False

    def test_total_issues_sums_error_counts(self):
        cm = CheckMetrics(
            check_name="test", category="drc",
            elapsed_ms=0.0,
            issue_counts={"ERROR": 2, "WARNING": 3},
            custom_metrics={},
        )
        assert cm.total_issues == 5


class TestMetricsSummary:
    """Tests for MetricsSummary (Rust-backed contract)."""

    def test_defaults(self):
        ms = MetricsSummary(
            check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        assert ms.total_checks == 0
        assert ms.passed_checks == 0
        assert ms.failed_checks == 0
        assert ms.passed is True

    def test_to_dict(self):
        ms = MetricsSummary(
            total_checks=10,
            passed_checks=8,
            failed_checks=2,
            error_count=3,
            warning_count=1,
            check_timings={"drc_clearance": 42.0},
            checks_run=["drc_clearance"],
            checks_skipped=[],
            custom_metrics={},
        )
        d = ms.to_dict()
        assert d["total_checks"] == 10
        assert d["passed_checks"] == 8
        assert d["failed_checks"] == 2
        assert d["by_severity"]["error"] == 3

    def test_to_json(self):
        ms = MetricsSummary(
            total_checks=0, check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        j = ms.to_json()
        assert isinstance(j, str)
        assert "total_checks" in j

    def test_summary_text(self):
        ms = MetricsSummary(
            total_checks=0, check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        s = ms.summary_text()
        assert isinstance(s, str)
        assert "Check Summary" in s

    def test_total_issues(self):
        ms = MetricsSummary(
            error_count=3, warning_count=2, info_count=1,
            check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        # total_issues counts ERROR + WARNING (not INFO)
        assert ms.total_issues == 5

    def test_total_penalty(self):
        ms = MetricsSummary(
            check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        assert ms.total_penalty == 0.0

    def test_passed_with_failures(self):
        ms = MetricsSummary(
            total_checks=5, passed_checks=3, failed_checks=2,
            check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        assert ms.passed is False


class TestFenceResult:
    """Tests for FenceResult."""

    def test_format(self):
        fr = FenceResult(stage_name="placement", passed=True, elapsed_ms=100.0)
        s = fr.format()
        assert isinstance(s, str)
