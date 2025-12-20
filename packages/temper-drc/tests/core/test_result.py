"""Tests for result module."""

from temper_drc.core.result import CheckResult, Issue, Location, RunResult
from temper_drc.core.severity import Severity


class TestLocation:
    """Test Location dataclass."""

    def test_location_str_with_coordinates(self):
        """Test string representation with coordinates."""
        loc = Location(x=10.5, y=20.3)
        assert "(10.50, 20.30)" in str(loc)

    def test_location_str_with_layer(self):
        """Test string representation with layer."""
        loc = Location(x=10.0, y=20.0, layer="F.Cu")
        assert "F.Cu" in str(loc)

    def test_location_str_unknown(self):
        """Test string representation without coordinates."""
        loc = Location()
        assert str(loc) == "unknown"

    def test_to_dict(self):
        """Test dictionary conversion."""
        loc = Location(x=5.0, y=10.0, layer="B.Cu")
        d = loc.to_dict()
        assert d["x"] == 5.0
        assert d["y"] == 10.0
        assert d["layer"] == "B.Cu"


class TestIssue:
    """Test Issue dataclass."""

    def test_issue_creation(self):
        """Test creating an issue."""
        issue = Issue(
            severity=Severity.ERROR,
            code="DRC_CLR_001",
            message="Clearance violation",
            category="drc",
            check_name="clearance",
            affected_items=["Q1", "Q2"],
        )
        assert issue.severity == Severity.ERROR
        assert issue.code == "DRC_CLR_001"
        assert "Q1" in issue.affected_items

    def test_issue_str(self):
        """Test issue string representation."""
        issue = Issue(
            severity=Severity.ERROR,
            code="DRC_CLR_001",
            message="Clearance violation",
            category="drc",
            check_name="clearance",
            affected_items=["Q1", "Q2"],
        )
        s = str(issue)
        assert "DRC_CLR_001" in s
        assert "Clearance violation" in s

    def test_issue_to_dict(self):
        """Test dictionary conversion."""
        issue = Issue(
            severity=Severity.WARNING,
            code="EMC_LOP_001",
            message="Loop area too large",
            category="emc",
            check_name="loop_area",
            location=Location(x=25.0, y=30.0),
        )
        d = issue.to_dict()
        assert d["severity"] == "WARNING"
        assert d["code"] == "EMC_LOP_001"
        assert d["location"]["x"] == 25.0


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_passed_result(self):
        """Test a passing check result."""
        result = CheckResult(check_name="test", passed=True)
        assert result.passed
        assert result.error_count == 0

    def test_failed_result(self):
        """Test a failing check result."""
        result = CheckResult(
            check_name="test",
            passed=False,
            issues=[
                Issue(
                    severity=Severity.ERROR,
                    code="TEST_001",
                    message="Test error",
                    category="test",
                    check_name="test",
                ),
            ],
        )
        assert not result.passed
        assert result.error_count == 1

    def test_issue_counts(self):
        """Test issue counting by severity."""
        result = CheckResult(
            check_name="test",
            passed=False,
            issues=[
                Issue(Severity.INFO, "I1", "info", "test", "test"),
                Issue(Severity.WARNING, "W1", "warn", "test", "test"),
                Issue(Severity.WARNING, "W2", "warn", "test", "test"),
                Issue(Severity.ERROR, "E1", "error", "test", "test"),
                Issue(Severity.CRITICAL, "C1", "critical", "test", "test"),
            ],
        )
        assert result.info_count == 1
        assert result.warning_count == 2
        assert result.error_count == 1
        assert result.critical_count == 1
        assert result.total_issues == 4  # Excludes INFO

    def test_penalty_calculation(self):
        """Test penalty score calculation."""
        result = CheckResult(
            check_name="test",
            passed=False,
            issues=[
                Issue(Severity.WARNING, "W1", "warn", "test", "test"),
                Issue(Severity.ERROR, "E1", "error", "test", "test"),
            ],
        )
        assert result.penalty == 11.0  # 1.0 + 10.0

    def test_merge_results(self):
        """Test merging two results."""
        r1 = CheckResult(
            check_name="test",
            passed=True,
            issues=[Issue(Severity.INFO, "I1", "info", "test", "test")],
            elapsed_ms=10.0,
        )
        r2 = CheckResult(
            check_name="test",
            passed=False,
            issues=[Issue(Severity.ERROR, "E1", "error", "test", "test")],
            elapsed_ms=20.0,
        )
        merged = r1.merge(r2)
        assert not merged.passed
        assert len(merged.issues) == 2
        assert merged.elapsed_ms == 30.0


class TestRunResult:
    """Test RunResult dataclass."""

    def test_empty_run_passes(self):
        """Empty run should pass."""
        result = RunResult()
        assert result.passed
        assert result.total_checks == 0

    def test_run_with_results(self):
        """Test run with multiple check results."""
        result = RunResult(
            check_results=[
                CheckResult(check_name="check1", passed=True),
                CheckResult(
                    check_name="check2",
                    passed=False,
                    issues=[Issue(Severity.ERROR, "E1", "err", "drc", "check2")],
                ),
            ],
            total_elapsed_ms=100.0,
        )
        assert not result.passed
        assert result.total_checks == 2
        assert result.passed_checks == 1
        assert result.failed_checks == 1

    def test_all_issues(self):
        """Test getting all issues across checks."""
        result = RunResult(
            check_results=[
                CheckResult(
                    check_name="c1",
                    passed=False,
                    issues=[Issue(Severity.ERROR, "E1", "e1", "drc", "c1")],
                ),
                CheckResult(
                    check_name="c2",
                    passed=False,
                    issues=[Issue(Severity.WARNING, "W1", "w1", "erc", "c2")],
                ),
            ],
        )
        all_issues = result.all_issues
        assert len(all_issues) == 2

    def test_by_severity(self):
        """Test filtering issues by severity."""
        result = RunResult(
            check_results=[
                CheckResult(
                    check_name="c1",
                    passed=False,
                    issues=[
                        Issue(Severity.ERROR, "E1", "e1", "drc", "c1"),
                        Issue(Severity.WARNING, "W1", "w1", "drc", "c1"),
                    ],
                ),
            ],
        )
        errors = result.by_severity(Severity.ERROR)
        assert len(errors) == 1
        assert errors[0].code == "E1"
