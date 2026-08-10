"""Coverage paydown tests — Wave 4 validation gaps.

Covers: CompositeValidator, CompositeCheck, MetricsSummary.coverage,
MetricsSummary.total_penalty, MetricsSummary.from_run_result.
"""

from __future__ import annotations

import pytest

from temper_placer.validation.base import (
    CompositeValidator,
    ValidationResult,
    ValidationSeverity,
    Validator,
)
from temper_placer.validation.drc_fence import (
    CheckMetrics,
    MetricsSummary,
)
from temper_placer.validation.drc_result import (
    Check,
    CheckResult,
    CompositeCheck,
    RunResult,
)


# =============================================================================
#  Minimal concrete implementations for ABC testing
# =============================================================================


class _MinimalValidator(Validator):
    """Minimal concrete Validator for testing."""

    @property
    def name(self) -> str:
        return "minimal"

    def validate(self, state, netlist, board) -> ValidationResult:
        return ValidationResult(valid=True, validator_name=self.name)


class _AlwaysUnavailableValidator(Validator):
    """Validator that is never available."""

    @property
    def name(self) -> str:
        return "always_off"

    def validate(self, state, netlist, board) -> ValidationResult:
        return ValidationResult(valid=True, validator_name=self.name)

    def is_available(self) -> bool:
        return False


class _MinimalCheck(Check):
    """Minimal concrete Check for CompositeCheck testing."""

    @property
    def name(self) -> str:
        return "minimal"

    @property
    def category(self) -> str:
        return "drc"

    def run(self, placement, constraints, modified_regions=None):
        return CheckResult(check_name=self.name, passed=True)


class _FailingCheck(Check):
    """Check that always reports a failure."""

    @property
    def name(self) -> str:
        return "failing"

    @property
    def category(self) -> str:
        return "drc"

    def run(self, placement, constraints, modified_regions=None):
        from temper_placer.validation.drc_result import Issue, Severity

        return CheckResult(
            check_name=self.name,
            passed=False,
            issues=[
                Issue(
                    severity=Severity.ERROR,
                    code="FAIL_001",
                    message="Always fails",
                    category=self.category,
                    check_name=self.name,
                )
            ],
        )


class _NeverApplicableCheck(Check):
    """Check that is never applicable."""

    @property
    def name(self) -> str:
        return "never"

    @property
    def category(self) -> str:
        return "drc"

    def run(self, placement, constraints, modified_regions=None):
        return CheckResult(check_name=self.name, passed=True)

    def is_applicable(self, placement, constraints) -> bool:
        return False


# =============================================================================
#  Validator ABC
# =============================================================================


class TestValidatorABC:
    """Tests for the Validator abstract base class."""

    def test_is_available_default(self):
        v = _MinimalValidator()
        assert v.is_available() is True

    def test_name(self):
        v = _MinimalValidator()
        assert v.name == "minimal"

    def test_validate_returns_result(self):
        v = _MinimalValidator()
        result = v.validate(None, None, None)
        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert result.validator_name == "minimal"

    def test_is_available_override(self):
        v = _AlwaysUnavailableValidator()
        assert v.is_available() is False
        assert v.name == "always_off"


# =============================================================================
#  CompositeValidator
# =============================================================================


class TestCompositeValidator:
    """Tests for CompositeValidator."""

    def test_name(self):
        cv = CompositeValidator(validators=[])
        assert cv.name == "CompositeValidator"

    def test_is_available_empty(self):
        """No validators = none available."""
        cv = CompositeValidator(validators=[])
        assert cv.is_available() is False

    def test_is_available_one_available(self):
        cv = CompositeValidator(
            validators=[_MinimalValidator(), _AlwaysUnavailableValidator()]
        )
        assert cv.is_available() is True

    def test_is_available_none_available(self):
        cv = CompositeValidator(
            validators=[_AlwaysUnavailableValidator()]
        )
        assert cv.is_available() is False

    def test_validate_empty(self):
        cv = CompositeValidator(validators=[])
        result = cv.validate(None, None, None)
        assert isinstance(result, ValidationResult)
        assert result.validator_name == "CompositeValidator"
        assert result.valid is True

    def test_validate_single(self):
        cv = CompositeValidator(validators=[_MinimalValidator()])
        result = cv.validate(None, None, None)
        assert result.valid is True
        assert result.validator_name == "CompositeValidator+minimal"

    def test_validate_skips_unavailable(self):
        """Unavailable validators are skipped."""
        cv = CompositeValidator(
            validators=[_AlwaysUnavailableValidator(), _MinimalValidator()]
        )
        result = cv.validate(None, None, None)
        # Only the minimal validator ran
        assert "minimal" in result.validator_name
        assert "always_off" not in result.validator_name


# =============================================================================
#  CompositeCheck — tested via a concrete subclass that provides ``name``
#  (CompositeCheck itself is abstract because it does not override the
#  abstract ``Check.name`` property — setting ``self.name`` in __init__
#  is an instance attribute, not a property override, so ABC still blocks
#  direct instantiation.)
# =============================================================================


class _ConcreteCompositeCheck(CompositeCheck):
    """Concrete CompositeCheck subclass that provides the ``name`` property.

    CompositeCheck.__init__ sets ``self.name`` as a regular instance
    attribute, which collides with this class's ``name`` property.
    Avoid the collision by bypassing the parent __init__ and setting
    the parent's own attributes directly.
    """

    @property
    def name(self) -> str:
        return self._name

    def __init__(self, checks, name="composite", description=""):
        # Bypass CompositeCheck.__init__ (which does ``self.name = name``
        # and would fail against our read-only property); set the
        # attributes it sets directly.
        self.checks = checks
        self._description = description
        self._name = name


class TestCompositeCheck:
    """Tests for CompositeCheck methods exercised via a concrete subclass."""

    def test_category(self):
        cc = _ConcreteCompositeCheck(checks=[], name="test")
        assert cc.category == "composite"

    def test_name(self):
        cc = _ConcreteCompositeCheck(checks=[], name="my_composite")
        assert cc.name == "my_composite"

    def test_description_with_custom(self):
        cc = _ConcreteCompositeCheck(checks=[], name="test", description="Custom desc")
        assert cc.description == "Custom desc"

    def test_description_auto(self):
        c1 = _MinimalCheck()
        c2 = _FailingCheck()
        cc = _ConcreteCompositeCheck(checks=[c1, c2], name="test")
        desc = cc.description
        assert "Composite of:" in desc
        assert "minimal" in desc
        assert "failing" in desc

    def test_is_applicable_false_when_no_checks(self):
        cc = _ConcreteCompositeCheck(checks=[], name="test")
        assert cc.is_applicable(None, None) is False

    def test_is_applicable_true_when_one_applicable(self):
        cc = _ConcreteCompositeCheck(
            checks=[_NeverApplicableCheck(), _MinimalCheck()], name="test"
        )
        assert cc.is_applicable(None, None) is True

    def test_is_applicable_false_when_none_applicable(self):
        cc = _ConcreteCompositeCheck(
            checks=[_NeverApplicableCheck(), _NeverApplicableCheck()], name="test"
        )
        assert cc.is_applicable(None, None) is False

    def test_run_empty(self):
        cc = _ConcreteCompositeCheck(checks=[], name="test")
        result = cc.run(None, None)
        assert isinstance(result, CheckResult)
        assert result.passed is True
        assert result.check_name == "test"

    def test_run_single_passing(self):
        cc = _ConcreteCompositeCheck(checks=[_MinimalCheck()], name="test")
        result = cc.run(None, None)
        assert result.passed is True

    def test_run_single_failing(self):
        cc = _ConcreteCompositeCheck(checks=[_FailingCheck()], name="test")
        result = cc.run(None, None)
        assert result.passed is False
        assert len(result.issues) == 1

    def test_run_mixed(self):
        cc = _ConcreteCompositeCheck(
            checks=[_MinimalCheck(), _FailingCheck()], name="test"
        )
        result = cc.run(None, None)
        # One check failed -> composite fails
        assert result.passed is False
        assert len(result.issues) == 1

    def test_run_skips_not_applicable(self):
        cc = _ConcreteCompositeCheck(
            checks=[_NeverApplicableCheck(), _MinimalCheck()], name="test"
        )
        result = cc.run(None, None)
        assert result.passed is True


# =============================================================================
#  MetricsSummary: coverage, total_penalty, from_run_result
# =============================================================================


class TestMetricsSummaryGaps:
    """Tests for MetricsSummary properties not already covered."""

    def test_coverage_default(self):
        """Coverage defaults to 100% when no checks exist."""
        ms = MetricsSummary(
            check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        assert ms.coverage == 100.0

    def test_coverage_all_run(self):
        ms = MetricsSummary(
            check_timings={},
            checks_run=["check_a", "check_b", "check_c"],
            checks_skipped=[],
            custom_metrics={},
        )
        assert ms.coverage == 100.0

    def test_coverage_partial(self):
        ms = MetricsSummary(
            check_timings={},
            checks_run=["check_a", "check_b"],
            checks_skipped=["check_c", "check_d"],
            custom_metrics={},
        )
        assert ms.coverage == 50.0

    def test_coverage_none_run(self):
        ms = MetricsSummary(
            check_timings={},
            checks_run=[],
            checks_skipped=["check_a"],
            custom_metrics={},
        )
        assert ms.coverage == 0.0

    def test_total_penalty_zero(self):
        ms = MetricsSummary(
            check_timings={}, checks_run=[], checks_skipped=[], custom_metrics={},
        )
        assert ms.total_penalty == 0.0

    def test_total_penalty_nonzero(self):
        """total_penalty uses Severity weights on counts."""
        ms = MetricsSummary(
            warning_count=2,
            error_count=1,
            critical_count=1,
            check_timings={},
            checks_run=[],
            checks_skipped=[],
            custom_metrics={},
        )
        # Check that penalty is computed (specific value depends on Severity weights)
        assert ms.total_penalty > 0

    def test_total_penalty_no_weighted(self):
        ms = MetricsSummary(
            warning_count=0,
            error_count=0,
            critical_count=0,
            check_timings={},
            checks_run=[],
            checks_skipped=[],
            custom_metrics={},
        )
        assert ms.total_penalty == 0.0

    def test_from_run_result_empty(self):
        """from_run_result on an empty RunResult."""
        rr = RunResult(check_results=[])
        ms = MetricsSummary.from_run_result(rr)
        assert isinstance(ms, MetricsSummary)
        assert ms.total_checks == 0

    def test_from_run_result_with_passing_checks(self):
        """from_run_result with check results."""
        cr1 = CheckResult(check_name="check_a", passed=True)
        cr2 = CheckResult(check_name="check_b", passed=True)
        rr = RunResult(check_results=[cr1, cr2])
        ms = MetricsSummary.from_run_result(rr)
        assert ms.total_checks == rr.total_checks


# =============================================================================
#  CheckMetrics total_issues edge cases
# =============================================================================


class TestCheckMetricsEdgeCases:
    """Edge cases for CheckMetrics not covered in existing tests."""

    def test_total_issues_filters_info(self):
        """INFO-severity issues should be excluded from total_issues."""
        cm = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            issue_counts={"ERROR": 1, "WARNING": 2, "INFO": 10},
            custom_metrics={},
        )
        assert cm.total_issues == 3  # 1 + 2, INFO excluded

    def test_passed_with_critical(self):
        """CRITICAL severity counts as failure."""
        cm = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            issue_counts={"CRITICAL": 1},
            custom_metrics={},
        )
        assert cm.passed is False

    def test_passed_with_warnings_only(self):
        """WARNINGS alone do not fail."""
        cm = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=0.0,
            issue_counts={"WARNING": 5},
            custom_metrics={},
        )
        assert cm.passed is True
        assert cm.total_issues == 5
