"""Tests for runner module."""


from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue
from temper_drc.core.runner import CheckRunner
from temper_drc.core.severity import Severity
from temper_drc.input.placement import Placement
from temper_drc.input.constraints import ConstraintSet


class PassCheck(Check):
    """A check that passes."""

    def __init__(self, name: str = "pass", category: str = "test"):
        self._name = name
        self._category = category

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    @property
    def description(self) -> str:
        return "A passing check"

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class FailCheck(Check):
    """A check that fails."""

    def __init__(self, name: str = "fail", category: str = "test"):
        self._name = name
        self._category = category

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    @property
    def description(self) -> str:
        return "A failing check"

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        return CheckResult(
            check_name=self.name,
            passed=False,
            issues=[
                Issue(
                    severity=Severity.ERROR,
                    code="FAIL_001",
                    message="Check failed",
                    category=self.category,
                    check_name=self.name,
                )
            ],
        )


class CriticalCheck(Check):
    """A check that finds critical issues."""

    @property
    def name(self) -> str:
        return "critical"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "A safety-critical check"

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        return CheckResult(
            check_name=self.name,
            passed=False,
            issues=[
                Issue(
                    severity=Severity.CRITICAL,
                    code="SAF_001",
                    message="Safety violation",
                    category=self.category,
                    check_name=self.name,
                )
            ],
        )


class TestCheckRunner:
    """Test CheckRunner class."""

    def test_empty_runner(self, simple_placement, empty_constraints):
        """Empty runner should pass."""
        runner = CheckRunner()
        result = runner.run(simple_placement, empty_constraints)
        assert result.passed
        assert result.total_checks == 0

    def test_add_check(self):
        """Test adding a check."""
        runner = CheckRunner()
        check = PassCheck()
        runner.add_check(check)
        assert len(runner.checks) == 1
        assert runner.checks[0].name == "pass"

    def test_add_checks_bulk(self):
        """Test adding multiple checks at once."""
        runner = CheckRunner()
        runner.add_checks([PassCheck("p1"), PassCheck("p2"), PassCheck("p3")])
        assert len(runner.checks) == 3

    def test_all_pass(self, simple_placement, empty_constraints):
        """All passing checks should result in passing run."""
        runner = CheckRunner()
        runner.add_checks([PassCheck("p1"), PassCheck("p2")])
        result = runner.run(simple_placement, empty_constraints)
        assert result.passed
        assert result.total_checks == 2
        assert result.passed_checks == 2
        assert result.failed_checks == 0

    def test_one_fails(self, simple_placement, empty_constraints):
        """One failing check should fail the run."""
        runner = CheckRunner()
        runner.add_checks([PassCheck("p1"), FailCheck("f1")])
        result = runner.run(simple_placement, empty_constraints)
        assert not result.passed
        assert result.total_checks == 2
        assert result.passed_checks == 1
        assert result.failed_checks == 1

    def test_filter_by_category(self, simple_placement, empty_constraints):
        """Test filtering checks by category."""
        runner = CheckRunner()
        runner.add_checks([
            PassCheck("drc1", category="drc"),
            PassCheck("erc1", category="erc"),
            FailCheck("drc2", category="drc"),
        ])
        result = runner.run(
            simple_placement, empty_constraints, categories=["drc"]
        )
        assert not result.passed
        assert result.total_checks == 2  # Only drc checks
        assert result.failed_checks == 1

    def test_filter_multiple_categories(self, simple_placement, empty_constraints):
        """Test filtering by multiple categories."""
        runner = CheckRunner()
        runner.add_checks([
            PassCheck("drc1", category="drc"),
            PassCheck("erc1", category="erc"),
            PassCheck("safety1", category="safety"),
        ])
        result = runner.run(
            simple_placement, empty_constraints, categories=["drc", "safety"]
        )
        assert result.passed
        assert result.total_checks == 2  # drc + safety

    def test_elapsed_time_recorded(self, simple_placement, empty_constraints):
        """Test that elapsed time is recorded."""
        runner = CheckRunner()
        runner.add_check(PassCheck())
        result = runner.run(simple_placement, empty_constraints)
        assert result.total_elapsed_ms >= 0

    def test_critical_issues(self, simple_placement, empty_constraints):
        """Test critical issues are captured."""
        runner = CheckRunner()
        runner.add_check(CriticalCheck())
        result = runner.run(simple_placement, empty_constraints)
        assert not result.passed
        critical_issues = result.by_severity(Severity.CRITICAL)
        assert len(critical_issues) == 1

    def test_check_names_property(self):
        """Test listing available checks."""
        runner = CheckRunner()
        runner.add_checks([
            PassCheck("check1", category="drc"),
            PassCheck("check2", category="erc"),
        ])
        checks = runner.check_names
        assert len(checks) == 2
        assert "check1" in checks
        assert "check2" in checks

    def test_categories_property(self):
        """Test listing available categories."""
        runner = CheckRunner()
        runner.add_checks([
            PassCheck("c1", category="drc"),
            PassCheck("c2", category="erc"),
            PassCheck("c3", category="drc"),  # duplicate category
        ])
        categories = runner.categories
        assert "drc" in categories
        assert "erc" in categories
        assert len(categories) == 2  # no duplicates
