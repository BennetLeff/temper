"""Tests for metrics module."""

from temper_drc.core.metrics import CheckMetrics, MetricsSummary
from temper_drc.core.result import CheckResult, Issue, RunResult
from temper_drc.core.severity import Severity


class TestCheckMetrics:
    """Test CheckMetrics dataclass."""

    def test_basic_creation(self):
        """Test creating check metrics."""
        metrics = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=50.0,
            issue_counts={"ERROR": 1, "WARNING": 2},
        )
        assert metrics.check_name == "test"
        assert metrics.category == "drc"
        assert metrics.elapsed_ms == 50.0
        assert metrics.issue_counts["ERROR"] == 1

    def test_total_issues_excludes_info(self):
        """Test that total_issues excludes INFO."""
        metrics = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            issue_counts={
                "INFO": 5,
                "WARNING": 2,
                "ERROR": 1,
            },
        )
        assert metrics.total_issues == 3  # WARNING + ERROR, not INFO

    def test_passed_property(self):
        """Test passed property."""
        # Passed: no errors or critical
        passed_metrics = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            issue_counts={"WARNING": 2, "INFO": 1},
        )
        assert passed_metrics.passed

        # Failed: has error
        failed_metrics = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            issue_counts={"ERROR": 1},
        )
        assert not failed_metrics.passed

        # Failed: has critical
        critical_metrics = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            issue_counts={"CRITICAL": 1},
        )
        assert not critical_metrics.passed

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=25.0,
        )
        d = metrics.to_dict()
        assert d["check_name"] == "test"
        assert d["category"] == "drc"
        assert d["elapsed_ms"] == 25.0
        assert d["passed"] is True

    def test_custom_metrics(self):
        """Test custom metrics."""
        metrics = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            custom_metrics={"loop_area_mm2": 150.5, "clearance_mm": 2.0},
        )
        assert metrics.custom_metrics["loop_area_mm2"] == 150.5
        assert metrics.custom_metrics["clearance_mm"] == 2.0


class TestMetricsSummary:
    """Test MetricsSummary class."""

    def test_empty_run(self):
        """Test summary from empty run."""
        run_result = RunResult()
        summary = MetricsSummary.from_run_result(run_result)
        assert summary.total_checks == 0
        assert summary.passed_checks == 0
        assert summary.failed_checks == 0
        assert summary.passed  # Empty run passes

    def test_all_passed(self):
        """Test summary when all checks pass."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="c1", passed=True, elapsed_ms=10.0),
                CheckResult(check_name="c2", passed=True, elapsed_ms=20.0),
            ],
            total_elapsed_ms=30.0,
        )
        summary = MetricsSummary.from_run_result(run_result)
        assert summary.total_checks == 2
        assert summary.passed_checks == 2
        assert summary.failed_checks == 0
        assert summary.passed
        assert summary.total_elapsed_ms == 30.0

    def test_mixed_results(self):
        """Test summary with mixed pass/fail."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="pass1", passed=True),
                CheckResult(
                    check_name="fail1",
                    passed=False,
                    issues=[Issue(Severity.ERROR, "E1", "err", "drc", "fail1")],
                ),
                CheckResult(check_name="pass2", passed=True),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        assert summary.total_checks == 3
        assert summary.passed_checks == 2
        assert summary.failed_checks == 1
        assert not summary.passed

    def test_severity_counts(self):
        """Test counting issues by severity."""
        run_result = RunResult(
            check_results=[
                CheckResult(
                    check_name="multi",
                    passed=False,
                    issues=[
                        Issue(Severity.INFO, "I1", "info", "test", "multi"),
                        Issue(Severity.WARNING, "W1", "warn", "test", "multi"),
                        Issue(Severity.WARNING, "W2", "warn", "test", "multi"),
                        Issue(Severity.ERROR, "E1", "error", "test", "multi"),
                        Issue(Severity.CRITICAL, "C1", "crit", "test", "multi"),
                    ],
                ),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        assert summary.info_count == 1
        assert summary.warning_count == 2
        assert summary.error_count == 1
        assert summary.critical_count == 1

    def test_category_counts(self):
        """Test counting issues by category."""
        run_result = RunResult(
            check_results=[
                CheckResult(
                    check_name="c1",
                    passed=False,
                    issues=[
                        Issue(Severity.ERROR, "E1", "err", "drc", "c1"),
                        Issue(Severity.ERROR, "E2", "err", "drc", "c1"),
                    ],
                ),
                CheckResult(
                    check_name="c2",
                    passed=False,
                    issues=[
                        Issue(Severity.ERROR, "E3", "err", "erc", "c2"),
                    ],
                ),
                CheckResult(
                    check_name="c3",
                    passed=False,
                    issues=[
                        Issue(Severity.CRITICAL, "C1", "crit", "safety", "c3"),
                    ],
                ),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        assert summary.drc_issues == 2
        assert summary.erc_issues == 1
        assert summary.safety_issues == 1

    def test_total_penalty(self):
        """Test total penalty calculation."""
        run_result = RunResult(
            check_results=[
                CheckResult(
                    check_name="c1",
                    passed=False,
                    issues=[
                        Issue(Severity.WARNING, "W1", "w", "test", "c1"),  # 1.0
                        Issue(Severity.ERROR, "E1", "e", "test", "c1"),    # 10.0
                    ],
                ),
                CheckResult(
                    check_name="c2",
                    passed=False,
                    issues=[
                        Issue(Severity.CRITICAL, "C1", "c", "test", "c2"),  # 100.0
                    ],
                ),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        assert summary.total_penalty == 111.0

    def test_checks_run_list(self):
        """Test that checks_run is populated."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="check_a", passed=True, elapsed_ms=10.0),
                CheckResult(check_name="check_b", passed=False, elapsed_ms=20.0),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        assert len(summary.checks_run) == 2
        assert "check_a" in summary.checks_run
        assert "check_b" in summary.checks_run

    def test_check_timings(self):
        """Test that check timings are captured."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="fast", passed=True, elapsed_ms=5.0),
                CheckResult(check_name="slow", passed=True, elapsed_ms=100.0),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        assert summary.check_timings["fast"] == 5.0
        assert summary.check_timings["slow"] == 100.0

    def test_to_dict(self):
        """Test dictionary conversion."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="test", passed=True, elapsed_ms=15.0),
            ],
            total_elapsed_ms=15.0,
        )
        summary = MetricsSummary.from_run_result(run_result)
        d = summary.to_dict()
        assert d["total_checks"] == 1
        assert d["passed_checks"] == 1
        assert d["passed"] is True
        assert "by_severity" in d
        assert "by_category" in d
        assert "check_timings" in d

    def test_coverage(self):
        """Test coverage calculation."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="c1", passed=True),
                CheckResult(check_name="c2", passed=True),
            ],
        )
        summary = MetricsSummary.from_run_result(
            run_result,
            skipped_checks=["c3", "c4"],  # 2 skipped
        )
        # 2 run, 2 skipped = 50% coverage
        assert summary.coverage == 50.0

    def test_summary_text(self):
        """Test human-readable summary."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="test", passed=True),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        text = summary.summary_text()
        assert "PASSED" in text
        assert "1" in text  # 1 check

    def test_to_json(self):
        """Test JSON serialization."""
        run_result = RunResult(
            check_results=[
                CheckResult(check_name="test", passed=True),
            ],
        )
        summary = MetricsSummary.from_run_result(run_result)
        json_str = summary.to_json()
        assert '"total_checks": 1' in json_str
        assert '"passed": true' in json_str
