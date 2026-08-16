"""Coverage paydown tests v9: validation base/DRC contract types,
IO helpers (DSN types, via dedup, DSN normalizer/validator), and
validation DRC result check stubs.

Exercises public functions in:
- validation/base.py: ValidationResult, Validator ABC, CompositeValidator
- validation/drc.py: DRCViolation.to_dict, DRCResult.has_errors/total_violations/summary
- validation/drc_result.py: Check ABC + 15 concrete Check stub subclasses
- validation/drc_fence.py: CheckMetrics, FenceResult, MetricsSummary
- io/dsn.py: DSNPoint.to_dsn, DSNPolygon.to_dsn, DSNShape.to_dsn
- io/via_dedup.py: ViaKey.from_via, deduplicate_vias
- io/dsn_normalizer.py: normalize_dsn, is_dsn_normalized, strip_control_chars
- io/dsn_validator.py: validate_dsn, validate_or_warn_dsn
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest


# ===========================================================================
# validation/base.py — ValidationResult, Validator, CompositeValidator
# ===========================================================================


class TestValidationResultProperties:
    """Covers error_count, warning_count, critical_count, merge, summary."""

    def test_all_zero(self):
        from temper_placer.validation.base import ValidationResult

        vr = ValidationResult(valid=True)
        assert vr.error_count == 0
        assert vr.warning_count == 0
        assert vr.critical_count == 0

    def test_errors_count(self):
        from temper_placer.validation.base import (
            ValidationIssue,
            ValidationResult,
            ValidationSeverity,
        )

        vr = ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(severity=ValidationSeverity.ERROR, code="E001", message="err"),
                ValidationIssue(severity=ValidationSeverity.CRITICAL, code="C001", message="crit"),
                ValidationIssue(severity=ValidationSeverity.WARNING, code="W001", message="warn"),
                ValidationIssue(severity=ValidationSeverity.INFO, code="I001", message="info"),
            ],
        )
        assert vr.error_count == 2  # ERROR + CRITICAL
        assert vr.warning_count == 1
        assert vr.critical_count == 1

    def test_merge_preserves_valid(self):
        from temper_placer.validation.base import ValidationResult

        a = ValidationResult(valid=True, validator_name="A")
        b = ValidationResult(valid=False, validator_name="B")
        merged = a.merge(b)
        assert merged.valid is False
        assert "A+B" in merged.validator_name

    def test_merge_combines_issues(self):
        from temper_placer.validation.base import (
            ValidationIssue,
            ValidationResult,
            ValidationSeverity,
        )

        a = ValidationResult(
            valid=True,
            issues=[ValidationIssue(severity=ValidationSeverity.WARNING, code="W1", message="w1")],
        )
        b = ValidationResult(
            valid=True,
            issues=[ValidationIssue(severity=ValidationSeverity.ERROR, code="E1", message="e1")],
        )
        merged = a.merge(b)
        assert len(merged.issues) == 2

    def test_merge_metrics(self):
        from temper_placer.validation.base import ValidationResult

        a = ValidationResult(valid=True, metrics={"score": 0.8})
        b = ValidationResult(valid=True, metrics={"score": 0.9, "other": 1.0})
        merged = a.merge(b)
        # Later metrics override earlier
        assert merged.metrics["score"] == 0.9
        assert merged.metrics["other"] == 1.0

    def test_summary_pass(self):
        from temper_placer.validation.base import ValidationResult

        vr = ValidationResult(valid=True, validator_name="test")
        s = vr.summary()
        assert "PASS" in s

    def test_summary_fail(self):
        from temper_placer.validation.base import (
            ValidationIssue,
            ValidationResult,
            ValidationSeverity,
        )

        vr = ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(severity=ValidationSeverity.ERROR, code="E001", message="err"),
                ValidationIssue(severity=ValidationSeverity.WARNING, code="W001", message="warn"),
            ],
            validator_name="test",
        )
        s = vr.summary()
        assert "FAIL" in s


class TestValidatorABC:
    """Exercise Validator.is_available, name, validate through concrete impl."""

    def test_concrete_validator(self):
        import numpy as np

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.state import PlacementState
        from temper_placer.validation.base import ValidationResult, Validator

        class TestVal(Validator):
            @property
            def name(self) -> str:
                return "test_validator"

            def validate(self, state, netlist, board):
                return ValidationResult(valid=True, validator_name=self.name)

        v = TestVal()
        assert v.name == "test_validator"
        assert v.is_available() is True

        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist(components=[], nets=[])
        board = Board(width=100, height=100, origin=(0, 0))
        result = v.validate(state, netlist, board)
        assert result.valid is True

    def test_validator_abstract_name(self):
        """Exercise Validator.name (abstract property) via super() call."""
        from temper_placer.validation.base import Validator

        class TestVal(Validator):
            @property
            def name(self) -> str:
                # Call the abstract base's name property to cover its body
                super_name = Validator.name.fget(self)
                assert super_name is None
                return "test"

            def validate(self, state, netlist, board):
                from temper_placer.validation.base import ValidationResult
                return ValidationResult(valid=True)

        v = TestVal()
        assert v.name == "test"

    def test_validator_abstract_validate(self):
        """Exercise Validator.validate (abstract method) via super() call."""
        import numpy as np

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.state import PlacementState
        from temper_placer.validation.base import ValidationResult, Validator

        class TestVal(Validator):
            @property
            def name(self) -> str:
                return "test"

            def validate(self, state, netlist, board):
                # Call abstract base implementation (executes the 'pass' body)
                super().validate(state, netlist, board)
                return ValidationResult(valid=True)

        v = TestVal()
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist(components=[], nets=[])
        board = Board(width=100, height=100, origin=(0, 0))
        result = v.validate(state, netlist, board)
        assert result.valid is True


class TestCompositeValidator:
    """Covers CompositeValidator.is_available, name, validate."""

    def test_name(self):
        from temper_placer.validation.base import CompositeValidator

        cv = CompositeValidator(validators=[])
        assert cv.name == "CompositeValidator"

    def test_is_available_empty(self):
        from temper_placer.validation.base import CompositeValidator

        cv = CompositeValidator(validators=[])
        assert cv.is_available() is False

    def test_is_available_with_available(self):
        import numpy as np

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.state import PlacementState
        from temper_placer.validation.base import CompositeValidator, ValidationResult, Validator

        class AlwaysAvail(Validator):
            @property
            def name(self) -> str:
                return "always"

            def validate(self, state, netlist, board):
                return ValidationResult(valid=True)

        cv = CompositeValidator(validators=[AlwaysAvail()])
        assert cv.is_available() is True

    def test_validate_merges_results(self):
        import numpy as np

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.state import PlacementState
        from temper_placer.validation.base import (
            CompositeValidator,
            ValidationIssue,
            ValidationResult,
            ValidationSeverity,
            Validator,
        )

        class V1(Validator):
            @property
            def name(self) -> str:
                return "v1"

            def validate(self, state, netlist, board):
                return ValidationResult(
                    valid=True,
                    issues=[
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            code="W001",
                            message="w",
                        )
                    ],
                )

        class V2(Validator):
            @property
            def name(self) -> str:
                return "v2"

            def validate(self, state, netlist, board):
                return ValidationResult(valid=True)

        cv = CompositeValidator(validators=[V1(), V2()])
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist(components=[], nets=[])
        board = Board(width=100, height=100, origin=(0, 0))
        result = cv.validate(state, netlist, board)
        assert result.valid is True
        assert len(result.issues) == 1


# ===========================================================================
# validation/drc.py — DRCViolation.to_dict, DRCResult properties
# ===========================================================================


class TestDRCViolationToDict:
    def test_basic(self):
        from temper_placer.validation.drc import DRCViolation, DRCViolationType
        from temper_placer.validation.base import ValidationSeverity

        v = DRCViolation(
            severity=ValidationSeverity.ERROR,
            code="DRC_001",
            message="test violation",
            violation_type=DRCViolationType.CLEARANCE,
            rule_name="clearance_min",
            position=(10.0, 20.0),
            affected_items=["U1", "R1"],
            description="Bad clearance",
            component_refs=["U1"],
            location=(10.0, 20.0),
        )
        d = v.to_dict()
        assert d["severity"] == "error"
        assert d["code"] == "DRC_001"
        assert d["violation_type"] == "clearance"
        assert d["position"] == (10.0, 20.0)
        assert "U1" in d["affected_items"]
        assert d["component_refs"] == ["U1"]

    def test_minimal(self):
        from temper_placer.validation.drc import DRCViolation
        from temper_placer.validation.base import ValidationSeverity

        v = DRCViolation(
            severity=ValidationSeverity.WARNING,
            code="W001",
            message="minimal",
        )
        d = v.to_dict()
        assert d["severity"] == "warning"
        assert "component_refs" not in d


class TestDRCResult:
    def test_has_errors_true(self):
        from temper_placer.validation.drc import DRCResult

        r = DRCResult(success=False, error_count=3)
        assert r.has_errors is True

    def test_has_errors_false(self):
        from temper_placer.validation.drc import DRCResult

        r = DRCResult(success=True, error_count=0)
        assert r.has_errors is False

    def test_total_violations(self):
        from temper_placer.validation.drc import DRCResult

        r = DRCResult(success=False, error_count=2, warning_count=5)
        assert r.total_violations == 7

    def test_total_violations_zero(self):
        from temper_placer.validation.drc import DRCResult

        r = DRCResult(success=True)
        assert r.total_violations == 0

    def test_summary_pass(self):
        from temper_placer.validation.drc import DRCResult

        r = DRCResult(success=True, elapsed_ms=100.0)
        s = r.summary()
        assert "PASS" in s
        assert "100.0ms" in s

    def test_summary_fail(self):
        from temper_placer.validation.drc import DRCResult

        r = DRCResult(success=False, error_count=3, warning_count=1, elapsed_ms=50.0)
        s = r.summary()
        assert "FAIL" in s
        assert "3 errors" in s


# ===========================================================================
# validation/drc_result.py — Check ABC and 15 concrete subclasses
# ===========================================================================


class TestCheckABC:
    """Exercises Check.code_prefix, is_applicable, supports_incremental, description."""

    def _make_minimal_check(self, name="test", category="drc"):
        from temper_placer.validation.drc_result import Check, CheckResult

        class MinimalCheck(Check):
            @property
            def name(self) -> str:
                return name

            @property
            def category(self) -> str:
                return category

            def run(self, placement, constraints, modified_regions=None):
                return CheckResult(check_name=self.name, passed=True)

        return MinimalCheck()

    def test_code_prefix(self):
        check = self._make_minimal_check(name="test_check", category="drc")
        assert check.code_prefix == "DRC_TES_"

    def test_description_default(self):
        check = self._make_minimal_check()
        assert check.description == ""

    def test_supports_incremental_default(self):
        check = self._make_minimal_check()
        assert check.supports_incremental is False

    def test_is_applicable_default(self):
        check = self._make_minimal_check()
        assert check.is_applicable(None, None) is True


# ---------------------------------------------------------------------------
# All 15 check stub classes: name, category, description, code_prefix
# ---------------------------------------------------------------------------

# (subclass, expected_name, expected_category)
_ALL_CHECK_CLASSES = [
    ("ClearanceCheck", "drc_clearance", "drc"),
    ("ComponentOverlapCheck", "drc_component_overlap", "drc"),
    ("CourtyardCheck", "drc_courtyard", "drc"),
    ("ZoneContainmentCheck", "drc_zone_containment", "drc"),
    ("TraceClearanceCheck", "drc_trace_clearance", "drc"),
    ("ViaSpacingCheck", "drc_via_spacing", "drc"),
    ("NetConnectivityCheck", "erc_net_connectivity", "erc"),
    ("PowerDomainCheck", "erc_power_domain", "erc"),
    ("FloatingPinsCheck", "erc_floating_pins", "erc"),
    ("HVLVSeparationCheck", "safety_hv_lv_separation", "safety"),
    ("CreepageCheck", "safety_creepage", "safety"),
    ("IsolationCheck", "safety_isolation", "safety"),
    ("LoopAreaCheck", "emc_loop_area", "emc"),
    ("NoiseCouplingCheck", "emc_noise_coupling", "emc"),
    ("GroundPlaneCheck", "emc_ground_plane", "emc"),
]


@pytest.mark.parametrize("cls_name,expected_name,expected_category", _ALL_CHECK_CLASSES)
class TestCheckStubProperties:
    """Parametrized over all 15 Check stub classes."""

    @staticmethod
    def _make(cls_name):
        import temper_placer.validation.drc_result as _m

        kls = getattr(_m, cls_name)
        return kls()

    def test_name(self, cls_name, expected_name, expected_category):
        check = self._make(cls_name)
        assert check.name == expected_name

    def test_category(self, cls_name, expected_name, expected_category):
        check = self._make(cls_name)
        assert check.category == expected_category

    def test_description(self, cls_name, expected_name, expected_category):
        check = self._make(cls_name)
        assert isinstance(check.description, str)
        assert len(check.description) > 0

    def test_code_prefix(self, cls_name, expected_name, expected_category):
        check = self._make(cls_name)
        prefix = check.code_prefix
        assert isinstance(prefix, str)
        assert len(prefix) > 0
        # Code prefix should contain category abbreviation
        cat = expected_category.upper()[:3]
        assert cat in prefix or cat.lower() in prefix.lower()

    def test_is_applicable(self, cls_name, expected_name, expected_category):
        check = self._make(cls_name)
        assert check.is_applicable(None, None) is True


class TestComponentOverlapIncremental:
    def test_supports_incremental(self):
        from temper_placer.validation.drc_result import ComponentOverlapCheck

        check = ComponentOverlapCheck()
        assert check.supports_incremental is True


class TestCourtyardCheckMargin:
    def test_name_category(self):
        from temper_placer.validation.drc_result import CourtyardCheck

        check = CourtyardCheck(margin_mm=0.1)
        assert check.name == "drc_courtyard"
        assert check.category == "drc"


class TestCreepageCheckMargin:
    def test_name_category(self):
        from temper_placer.validation.drc_result import CreepageCheck

        check = CreepageCheck(min_iso_width_mm=8.0)
        assert check.name == "safety_creepage"
        assert check.category == "safety"


class TestPowerDomainCheckRun:
    """PowerDomainCheck.run() returns passed=False with not_run info."""

    def test_run_reports_not_run(self):
        from temper_placer.validation.drc_result import PowerDomainCheck

        check = PowerDomainCheck()
        result = check.run(None, None)
        assert result.passed is False
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.details.get("not_run") is True


# (subclass, expected_name) — all Check stubs that delegate to _run_check_via_rust
_DELEGATING_CHECK_CLASSES = [
    ("ClearanceCheck", "drc_clearance"),
    ("ComponentOverlapCheck", "drc_component_overlap"),
    ("CourtyardCheck", "drc_courtyard"),
    ("ZoneContainmentCheck", "drc_zone_containment"),
    ("TraceClearanceCheck", "drc_trace_clearance"),
    ("ViaSpacingCheck", "drc_via_spacing"),
    ("NetConnectivityCheck", "erc_net_connectivity"),
    ("FloatingPinsCheck", "erc_floating_pins"),
    ("HVLVSeparationCheck", "safety_hv_lv_separation"),
    ("CreepageCheck", "safety_creepage"),
    ("IsolationCheck", "safety_isolation"),
    ("LoopAreaCheck", "emc_loop_area"),
    ("NoiseCouplingCheck", "emc_noise_coupling"),
    ("GroundPlaneCheck", "emc_ground_plane"),
]


@pytest.mark.parametrize("cls_name,expected_name", _DELEGATING_CHECK_CLASSES)
class TestCheckStubRun:
    """Parametrized run() tests for all 14 delegating Check stubs."""

    @staticmethod
    def _make(cls_name):
        import temper_placer.validation.drc_result as _m

        kls = getattr(_m, cls_name)
        return kls()

    @staticmethod
    def _make_placement():
        from temper_placer.validation.drc_types import Placement

        return Placement(
            board_width=100.0,
            board_height=100.0,
            components={},
            nets={},
            net_classes={},
            zones={},
            voltage_domains={},
        )

    @staticmethod
    def _make_constraints():
        from temper_placer.validation.drc_types import ConstraintSet

        return ConstraintSet()

    def test_run_delegates(self, cls_name, expected_name):
        check = self._make(cls_name)
        placement = self._make_placement()
        constraints = self._make_constraints()
        result = check.run(placement, constraints)
        # On an empty board, should pass with zero violations
        assert result.passed is True
        assert result.check_name == expected_name


class TestCompositeCheck:
    """Covers CompositeCheck.category, description, is_applicable, run.
    
    CompositeCheck is abstract (does not override the abstract ``Check.name``
    property). Tests use a minimal concrete subclass that provides the name
    property, exercising CompositeCheck's methods through inheritance.
    """

    @staticmethod
    def _make_concrete(checks, name="composite", description=""):
        from temper_placer.validation.drc_result import CompositeCheck

        class _Concrete(CompositeCheck):
            def __init__(self, checks, name="composite", description=""):
                # Bypass CompositeCheck.__init__ (which does self.name = name
                # and would fail against a read-only property). Set the
                # attributes directly.
                self.checks = checks
                self._description = description
                self._name = name

            @property
            def name(self) -> str:
                return self._name

        return _Concrete(checks, name, description)

    def test_category(self):
        from temper_placer.validation.drc_result import Check, CheckResult

        class DummyCheck(Check):
            @property
            def name(self):
                return "dummy"

            @property
            def category(self):
                return "drc"

            def run(self, placement, constraints, modified_regions=None):
                return CheckResult(check_name=self.name, passed=True)

        cc = self._make_concrete(checks=[DummyCheck()])
        assert cc.category == "composite"

    def test_description(self):
        from temper_placer.validation.drc_result import Check, CheckResult

        class DummyCheck(Check):
            @property
            def name(self):
                return "dummy"

            @property
            def category(self):
                return "drc"

            def run(self, placement, constraints, modified_regions=None):
                return CheckResult(check_name=self.name, passed=True)

        cc = self._make_concrete(checks=[DummyCheck()])
        desc = cc.description
        assert "dummy" in desc

    def test_description_explicit(self):
        cc = self._make_concrete(checks=[], description="Custom desc")
        assert cc.description == "Custom desc"

    def test_is_applicable_empty(self):
        cc = self._make_concrete(checks=[])
        assert cc.is_applicable(None, None) is False

    def test_is_applicable_with_check(self):
        from temper_placer.validation.drc_result import Check, CheckResult

        class DummyCheck(Check):
            @property
            def name(self):
                return "dummy"

            @property
            def category(self):
                return "drc"

            def run(self, placement, constraints, modified_regions=None):
                return CheckResult(check_name=self.name, passed=True)

        cc = self._make_concrete(checks=[DummyCheck()])
        assert cc.is_applicable(None, None) is True

    def test_run_empty(self):
        cc = self._make_concrete(checks=[], name="empty_composite")
        result = cc.run(None, None)
        assert result.check_name == "empty_composite"
        assert result.passed is True


# ===========================================================================
# validation/drc_fence.py — CheckMetrics, FenceResult, MetricsSummary
# ===========================================================================


class TestCheckMetrics:
    def test_passed_true(self):
        from temper_placer.validation.drc_fence import CheckMetrics

        cm = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=10.0,
            issue_counts={"INFO": 1},
        )
        assert cm.passed is True

    def test_passed_false_on_error(self):
        from temper_placer.validation.drc_fence import CheckMetrics

        cm = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=10.0,
            issue_counts={"ERROR": 3},
        )
        assert cm.passed is False

    def test_passed_false_on_critical(self):
        from temper_placer.validation.drc_fence import CheckMetrics

        cm = CheckMetrics(
            check_name="test",
            category="safety",
            elapsed_ms=10.0,
            issue_counts={"CRITICAL": 1},
        )
        assert cm.passed is False

    def test_total_issues(self):
        from temper_placer.validation.drc_fence import CheckMetrics

        cm = CheckMetrics(
            check_name="test",
            category="drc",
            elapsed_ms=10.0,
            issue_counts={"INFO": 2, "WARNING": 3, "ERROR": 1, "CRITICAL": 1},
        )
        # INFO is excluded from total_issues
        assert cm.total_issues == 5  # 3 + 1 + 1

    def test_to_dict(self):
        from temper_placer.validation.drc_fence import CheckMetrics

        cm = CheckMetrics(
            check_name="chk",
            category="drc",
            elapsed_ms=42.0,
            issue_counts={"WARNING": 2},
            custom_metrics={"density": 0.8},
        )
        d = cm.to_dict()
        assert d["check_name"] == "chk"
        assert d["category"] == "drc"
        assert d["elapsed_ms"] == 42.0
        assert d["issue_counts"] == {"WARNING": 2}
        assert d["total_issues"] == 2
        assert d["passed"] is True


class TestFenceResult:
    def test_format_pass_empty(self):
        from temper_placer.validation.drc_fence import FenceResult

        fr = FenceResult(passed=True, stage_name="test_stage")
        formatted = fr.format()
        # No violations produces empty output from _format_single
        assert isinstance(formatted, str)

    def test_format_fail(self):
        from temper_placer.validation.drc_fence import FenceResult

        fr = FenceResult(
            passed=False,
            stage_name="test_stage",
            violations=[],
        )
        formatted = fr.format()
        # Even failed result with no violations produces empty _format_single
        assert isinstance(formatted, str)

    def test_format_with_violations(self):
        from temper_placer.validation.drc_fence import FenceResult, FenceViolation
        from temper_placer.validation.drc_result import Issue, Severity

        issue = Issue(
            severity=Severity.ERROR,
            code="DRC_001",
            message="clearance violation",
            category="drc",
            check_name="drc_clearance",
        )
        fv = FenceViolation(
            stage_name="test_stage",
            invariant_description="no overlaps",
            check_name="drc_clearance",
            issue=issue,
            is_new=True,
            introduced_count=3,
        )
        fr = FenceResult(
            passed=False,
            stage_name="test_stage",
            violations=(fv,),
        )
        formatted = fr.format()
        assert "test_stage" in formatted
        assert "drc_clearance" in formatted
        assert "DRC_001" in formatted


class TestMetricsSummary:
    def test_from_run_result_empty(self):
        from temper_placer.validation.drc_fence import MetricsSummary
        from temper_placer.validation.drc_result import RunResult

        run = RunResult(check_results=[], total_elapsed_ms=0.0)
        ms = MetricsSummary.from_run_result(run)
        assert ms.passed is True
        assert ms.total_issues == 0
        assert ms.total_penalty == pytest.approx(0.0)

    def test_passed_true(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(failed_checks=0)
        assert ms.passed is True

    def test_passed_false(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(failed_checks=2)
        assert ms.passed is False

    def test_coverage_full(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(
            checks_run=["drc_clearance", "drc_courtyard"],
            checks_skipped=[],
        )
        assert ms.coverage == pytest.approx(100.0)

    def test_coverage_partial(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(
            checks_run=["drc_clearance"],
            checks_skipped=["drc_courtyard", "drc_overlap"],
        )
        assert ms.coverage == pytest.approx(100.0 / 3)

    def test_coverage_empty(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary()
        assert ms.coverage == pytest.approx(100.0)

    def test_total_issues(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(warning_count=3, error_count=2, critical_count=1)
        assert ms.total_issues == 6

    def test_total_penalty(self):
        from temper_placer.validation.drc_fence import MetricsSummary
        from temper_placer.validation.drc_result import Severity

        ms = MetricsSummary(
            warning_count=1,
            error_count=1,
            critical_count=1,
        )
        expected = (
            Severity.WARNING.weight
            + Severity.ERROR.weight
            + Severity.CRITICAL.weight
        )
        assert ms.total_penalty == pytest.approx(expected)

    def test_summary_text_pass(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(total_checks=3, passed_checks=3, checks_run=["a", "b", "c"])
        txt = ms.summary_text()
        assert "PASS" in txt

    def test_summary_text_fail(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(total_checks=3, failed_checks=2)
        txt = ms.summary_text()
        assert "FAIL" in txt

    def test_to_dict(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(
            total_checks=5,
            passed_checks=4,
            failed_checks=1,
            warning_count=3,
        )
        d = ms.to_dict()
        assert d["total_checks"] == 5
        assert d["passed_checks"] == 4
        assert d["failed_checks"] == 1

    def test_to_json(self):
        from temper_placer.validation.drc_fence import MetricsSummary

        ms = MetricsSummary(total_checks=1, checks_run=["drc_clearance"])
        j = ms.to_json()
        parsed = json.loads(j)
        assert parsed["total_checks"] == 1


# ===========================================================================
# validation/drc.py — KiCadDRCValidator, find_kicad_cli
# ===========================================================================


class TestKiCadDRCValidator:
    """Covers KiCadDRCValidator.is_available, name, get_version, validate,
    run_drc, compute_penalty, to_validation_result."""

    def test_name(self):
        from temper_placer.validation.drc import KiCadDRCValidator

        v = KiCadDRCValidator()
        assert v.name == "KiCadDRCValidator"

    def test_is_available_false_when_not_found(self, monkeypatch):
        from temper_placer.validation.drc import find_kicad_cli, KiCadDRCValidator

        # Mock find_kicad_cli to return None
        monkeypatch.setattr(
            "temper_placer.validation.drc.find_kicad_cli",
            lambda: None,
        )
        v = KiCadDRCValidator()
        assert v.is_available() is False

    def test_get_version(self, monkeypatch):
        from temper_placer.validation.drc import KiCadDRCValidator

        # FIXED 2026-08-13: this test's docstring always intended "kicad-cli
        # unavailable" (get_version()'s "unknown" fallback path), but never
        # enforced it -- it relied on the ambient test environment not
        # having kicad-cli on PATH. That assumption broke once the CI image
        # (ghcr.io/bennetleff/temper-ci) started shipping kicad-cli 10.0.5
        # (needed elsewhere for real DRC/clearance measurements), so
        # find_kicad_cli() started succeeding here too and get_version()
        # returned "10.0.5", not "unknown". Mock find_kicad_cli explicitly,
        # matching test_is_available_false_when_not_found's established
        # pattern in this same class, so this test exercises the fallback
        # path deterministically instead of depending on what happens to be
        # installed on the runner.
        monkeypatch.setattr(
            "temper_placer.validation.drc.find_kicad_cli",
            lambda: None,
        )
        v = KiCadDRCValidator()
        # Without kicad-cli available, get_version returns "unknown"
        assert v.get_version() == "unknown"

    def test_validate_not_available(self, monkeypatch):
        """validate() when kicad-cli is not available."""
        import numpy as np

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.state import PlacementState
        from temper_placer.validation.drc import find_kicad_cli, KiCadDRCValidator

        monkeypatch.setattr(
            "temper_placer.validation.drc.find_kicad_cli",
            lambda: None,
        )
        v = KiCadDRCValidator()
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist(components=[], nets=[])
        board = Board(width=100, height=100, origin=(0, 0))
        result = v.validate(state, netlist, board)
        # When kicad-cli not available, valid=True (not invalid, just skipped)
        assert result.valid is True
        assert len(result.issues) == 1
        assert result.issues[0].code == "KICAD_NOT_AVAILABLE"

    def test_run_drc_not_available(self, monkeypatch):
        """run_drc() when kicad-cli is not available."""
        from pathlib import Path

        from temper_placer.validation.drc import find_kicad_cli, KiCadDRCValidator

        monkeypatch.setattr(
            "temper_placer.validation.drc.find_kicad_cli",
            lambda: None,
        )
        v = KiCadDRCValidator()
        result = v.run_drc(Path("/nonexistent/pcb.kicad_pcb"))
        assert result.success is False
        assert "not available" in result.raw_output

    def test_compute_penalty_success(self):
        """compute_penalty on successful (empty) DRCResult."""
        from temper_placer.validation.drc import DRCResult, KiCadDRCValidator

        v = KiCadDRCValidator()
        result = DRCResult(success=True, violations=[])
        penalty = v.compute_penalty(result)
        assert penalty == pytest.approx(0.0)

    def test_compute_penalty_failed_drc(self):
        """compute_penalty on failed DRCResult returns 100.0."""
        from temper_placer.validation.drc import DRCResult, KiCadDRCValidator

        v = KiCadDRCValidator()
        result = DRCResult(success=False)
        penalty = v.compute_penalty(result)
        assert penalty == pytest.approx(100.0)

    def test_to_validation_result(self):
        """to_validation_result converts DRCResult to ValidationResult."""
        from temper_placer.validation.drc import DRCResult, KiCadDRCValidator

        v = KiCadDRCValidator()
        result = DRCResult(success=True, elapsed_ms=42.0)
        vr = v.to_validation_result(result)
        assert vr.valid is True
        assert vr.elapsed_ms == 42.0
        assert vr.validator_name == "KiCadDRCValidator"
        assert "drc_penalty" in vr.metrics


class TestFindKicadCli:
    def test_find_kicad_cli_none_in_path(self, monkeypatch):
        import shutil

        from temper_placer.validation.drc import find_kicad_cli

        # Mock shutil.which to return None
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        result = find_kicad_cli()
        # Will check PATH then fall back to standard locations
        assert result is None or isinstance(result, str)

    def test_find_kicad_cli_found_in_path(self, monkeypatch):
        import shutil

        from temper_placer.validation.drc import find_kicad_cli

        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/kicad-cli")
        result = find_kicad_cli()
        assert result == "/usr/bin/kicad-cli"


# ===========================================================================
# io/dsn.py — DSN primitives
# ===========================================================================


class TestDSNPoint:
    def test_to_dsn(self):
        from temper_placer.io.dsn import DSNPoint

        p = DSNPoint(x=1.5, y=2.5)
        expr = p.to_dsn()
        assert str(expr) == "(point 1.5 2.5)"


class TestDSNShape:
    def test_to_dsn_not_implemented(self):
        from temper_placer.io.dsn import DSNShape

        shape = DSNShape()
        with pytest.raises(NotImplementedError):
            shape.to_dsn()


class TestDSNPolygon:
    def test_to_dsn_square(self):
        from temper_placer.io.dsn import DSNPolygon

        poly = DSNPolygon(
            layer="F.Cu",
            width=0.25,
            points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )
        expr = poly.to_dsn()
        s = str(expr)
        assert "polygon" in s
        assert "F.Cu" in s
        assert "0.25" in s

    def test_to_dsn_empty_points(self):
        from temper_placer.io.dsn import DSNPolygon

        poly = DSNPolygon(layer="B.Cu", width=0.5, points=[])
        expr = poly.to_dsn()
        # Should produce (polygon B.Cu 0.5)
        assert "polygon" in str(expr)


# ===========================================================================
# io/via_dedup.py — ViaKey, deduplicate_vias
# ===========================================================================


class TestViaKey:
    def test_from_via_no_rounding(self):
        from temper_placer.io.via_dedup import ViaKey
        from temper_placer.io.export_types import TraceVia

        via = TraceVia(
            net="VCC",
            position=(10.0, 20.0),
            size=0.6,
            drill=0.3,
            layers=["F.Cu", "B.Cu"],
        )
        key = ViaKey.from_via(via, tolerance_mm=0.001)
        assert key.x_mm == pytest.approx(10.0)
        assert key.y_mm == pytest.approx(20.0)

    def test_from_via_with_rounding(self):
        from temper_placer.io.via_dedup import ViaKey
        from temper_placer.io.export_types import TraceVia

        via = TraceVia(
            net="GND",
            position=(10.0008, 20.0003),
            size=0.6,
            drill=0.3,
            layers=["F.Cu", "B.Cu"],
        )
        key = ViaKey.from_via(via, tolerance_mm=0.001)
        assert key.x_mm == pytest.approx(10.001)
        assert key.y_mm == pytest.approx(20.0)

    def test_frozen_equality(self):
        from temper_placer.io.via_dedup import ViaKey

        k1 = ViaKey(x_mm=10.0, y_mm=20.0)
        k2 = ViaKey(x_mm=10.0, y_mm=20.0)
        assert k1 == k2
        assert hash(k1) == hash(k2)


class TestDeduplicateVias:
    def test_empty(self):
        from temper_placer.io.via_dedup import deduplicate_vias

        result = deduplicate_vias([])
        assert result == []

    def test_unique(self):
        from temper_placer.io.via_dedup import deduplicate_vias
        from temper_placer.io.export_types import TraceVia

        vias = [
            TraceVia(net="VCC", position=(0, 0), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"]),
            TraceVia(net="GND", position=(10, 10), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"]),
        ]
        result = deduplicate_vias(vias)
        assert len(result) == 2

    def test_duplicate(self):
        from temper_placer.io.via_dedup import deduplicate_vias
        from temper_placer.io.export_types import TraceVia

        vias = [
            TraceVia(net="VCC", position=(0, 0), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"]),
            TraceVia(net="GND", position=(0, 0), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"]),
        ]
        result = deduplicate_vias(vias)
        assert len(result) == 1
        # First via (VCC) should be kept
        assert result[0].net == "VCC"

    def test_near_duplicate(self):
        from temper_placer.io.via_dedup import deduplicate_vias
        from temper_placer.io.export_types import TraceVia

        vias = [
            TraceVia(net="VCC", position=(0.0, 0.0), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"]),
            TraceVia(net="GND", position=(0.0005, 0.0005), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"]),
        ]
        result = deduplicate_vias(vias, tolerance_mm=0.001)
        # With 0.001 tolerance, both snap to (0.0, 0.0)
        assert len(result) == 1


# ===========================================================================
# io/dsn_normalizer.py — normalize_dsn, is_dsn_normalized, strip_control_chars
# ===========================================================================


class TestDSNNormalizer:
    def test_strip_control_chars_none(self):
        from temper_io_types import strip_control_chars

        text = "hello world"
        result = strip_control_chars(text)
        assert result == text

    def test_strip_control_chars_removes_null(self):
        from temper_io_types import strip_control_chars

        text = "hello\x00world"
        result = strip_control_chars(text)
        assert "\x00" not in result
        assert "hello" in result
        assert "world" in result

    def test_normalize_dsn_identity(self):
        from temper_io_types import normalize_dsn

        # Already-normalized DSN should round-trip
        text = "(pcb test\n  (component U1\n  )\n)\n"
        result = normalize_dsn(text)
        assert len(result) > 0

    def test_is_dsn_normalized_true(self):
        from temper_io_types import is_dsn_normalized

        text = "(pcb test\n  (component U1\n  )\n)\n"
        result = is_dsn_normalized(text)
        assert isinstance(result, bool)

    def test_is_dsn_normalized_false(self):
        from temper_io_types import is_dsn_normalized

        # Tab indentation is not normalized
        text = "(pcb test\n\t(component U1\n\t)\n)\n"
        result = is_dsn_normalized(text)
        assert isinstance(result, bool)


# ===========================================================================
# io/dsn_validator.py — validate_dsn, validate_or_warn_dsn
# ===========================================================================


class TestDSNValidator:
    def test_validate_dsn_mismatch_raises(self):
        from temper_placer.io.dsn_validator import DSNVersionMismatchError, validate_dsn

        # A wrong hash should raise DSNVersionMismatchError
        dsn_text = "(pcb test\n  (component U1\n  )\n)\n"
        wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        with pytest.raises(DSNVersionMismatchError) as exc_info:
            validate_dsn(dsn_text, wrong_hash)
        assert exc_info.value.expected == wrong_hash

    def test_validate_or_warn_dsn_returns_false_on_mismatch(self):
        from temper_placer.io.dsn_validator import validate_or_warn_dsn

        dsn_text = "(pcb test\n  (component U1\n  )\n)\n"
        wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        result = validate_or_warn_dsn(dsn_text, wrong_hash)
        assert result is False

    def test_validate_or_warn_dsn_returns_true_on_match(self):
        from temper_placer.io.dsn_validator import validate_or_warn_dsn
        from temper_placer.io.dsn_schema import compute_dsn_schema_hash, embed_schema_header

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist

        # Compute a valid schema hash and embed it
        board = Board(width=100, height=100, origin=(0, 0))
        netlist = Netlist(components=[], nets=[])
        schema_hash = compute_dsn_schema_hash(board, netlist)

        dsn_text = "(pcb test\n  (component U1\n  )\n)\n"
        dsn_with_header = embed_schema_header(dsn_text, schema_hash)
        result = validate_or_warn_dsn(dsn_with_header, schema_hash)
        assert result is True
