"""Tests for check module."""

from temper_drc.core.check import Check, CompositeCheck
from temper_drc.core.result import CheckResult, Issue
from temper_drc.core.severity import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class DummyPassingCheck(Check):
    """A check that always passes."""

    @property
    def name(self) -> str:
        return "dummy_passing"

    @property
    def category(self) -> str:
        return "test"

    @property
    def description(self) -> str:
        return "A dummy check that always passes"

    def run(self, _placement: Placement, _constraints: ConstraintSet) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class DummyFailingCheck(Check):
    """A check that always fails."""

    @property
    def name(self) -> str:
        return "dummy_failing"

    @property
    def category(self) -> str:
        return "test"

    @property
    def description(self) -> str:
        return "A dummy check that always fails"

    def run(self, _placement: Placement, _constraints: ConstraintSet) -> CheckResult:
        return CheckResult(
            check_name=self.name,
            passed=False,
            issues=[
                Issue(
                    severity=Severity.ERROR,
                    code="TEST_001",
                    message="Dummy failure",
                    category=self.category,
                    check_name=self.name,
                )
            ],
        )


class DummyWarningCheck(Check):
    """A check that returns warnings."""

    @property
    def name(self) -> str:
        return "dummy_warning"

    @property
    def category(self) -> str:
        return "test"

    @property
    def description(self) -> str:
        return "A dummy check that returns warnings"

    def run(self, _placement: Placement, _constraints: ConstraintSet) -> CheckResult:
        return CheckResult(
            check_name=self.name,
            passed=True,  # Warnings don't fail
            issues=[
                Issue(
                    severity=Severity.WARNING,
                    code="TEST_W01",
                    message="Dummy warning",
                    category=self.category,
                    check_name=self.name,
                )
            ],
        )


class TestCheck:
    """Test Check ABC."""

    def test_check_properties(self):
        """Test check has required properties."""
        check = DummyPassingCheck()
        assert check.name == "dummy_passing"
        assert check.category == "test"
        assert "passes" in check.description

    def test_passing_check(self, simple_placement, empty_constraints):
        """Test a passing check."""
        check = DummyPassingCheck()
        result = check.run(simple_placement, empty_constraints)
        assert result.passed
        assert result.check_name == "dummy_passing"

    def test_failing_check(self, simple_placement, empty_constraints):
        """Test a failing check."""
        check = DummyFailingCheck()
        result = check.run(simple_placement, empty_constraints)
        assert not result.passed
        assert len(result.issues) == 1
        assert result.issues[0].code == "TEST_001"

    def test_warning_check(self, simple_placement, empty_constraints):
        """Test a check with warnings."""
        check = DummyWarningCheck()
        result = check.run(simple_placement, empty_constraints)
        assert result.passed  # Warnings don't fail
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.WARNING

    def test_code_prefix(self):
        """Test code prefix generation."""
        check = DummyPassingCheck()
        # test category, dummy_passing name -> TES_DUM_
        assert check.code_prefix == "TES_DUM_"


class TestCompositeCheck:
    """Test CompositeCheck."""

    def test_empty_composite(self, simple_placement, empty_constraints):
        """Empty composite should pass."""
        composite = CompositeCheck(checks=[], name="empty")
        result = composite.run(simple_placement, empty_constraints)
        assert result.passed
        assert len(result.issues) == 0

    def test_composite_all_pass(self, simple_placement, empty_constraints):
        """Composite with all passing checks should pass."""
        composite = CompositeCheck(
            checks=[DummyPassingCheck(), DummyPassingCheck()],
            name="all_pass",
        )
        result = composite.run(simple_placement, empty_constraints)
        assert result.passed

    def test_composite_one_fails(self, simple_placement, empty_constraints):
        """Composite should fail if any check fails."""
        composite = CompositeCheck(
            checks=[DummyPassingCheck(), DummyFailingCheck()],
            name="mixed",
        )
        result = composite.run(simple_placement, empty_constraints)
        assert not result.passed
        assert len(result.issues) == 1

    def test_composite_merges_issues(self, simple_placement, empty_constraints):
        """Composite should merge issues from all checks."""
        composite = CompositeCheck(
            checks=[DummyWarningCheck(), DummyWarningCheck()],
            name="warnings",
        )
        result = composite.run(simple_placement, empty_constraints)
        assert result.passed
        assert len(result.issues) == 2

    def test_composite_properties(self):
        """Test composite check properties."""
        composite = CompositeCheck(
            checks=[DummyPassingCheck()],
            name="test_composite",
            description="Custom description",
        )
        assert composite.name == "test_composite"
        assert composite.category == "composite"  # Always composite
        assert composite.description == "Custom description"

    def test_composite_default_description(self):
        """Test composite check default description."""
        composite = CompositeCheck(
            checks=[DummyPassingCheck()],
            name="test",
        )
        assert "dummy_passing" in composite.description

    def test_composite_add_check(self):
        """Test adding checks to composite."""
        composite = CompositeCheck(checks=[], name="test")
        assert len(composite.checks) == 0
        # Note: CompositeCheck takes checks at init, no add_check method
        # Testing the checks property
        composite2 = CompositeCheck(
            checks=[DummyPassingCheck(), DummyFailingCheck()],
            name="multi",
        )
        assert len(composite2.checks) == 2

    def test_composite_is_applicable(self, simple_placement, empty_constraints):
        """Test composite applicability."""
        # Empty composite is not applicable
        empty = CompositeCheck(checks=[], name="empty")
        assert not empty.is_applicable(simple_placement, empty_constraints)

        # Composite with checks is applicable
        non_empty = CompositeCheck(
            checks=[DummyPassingCheck()],
            name="non_empty",
        )
        assert non_empty.is_applicable(simple_placement, empty_constraints)
