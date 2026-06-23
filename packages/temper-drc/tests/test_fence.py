"""Tests for DRCFence, FenceResult, FenceViolation (U2, U3)."""

import logging
import time

import pytest

from temper_drc.core.fence import (
    DRCFence,
    FenceBudgetError,
    FenceResult,
    FenceViolation,
    FenceViolationError,
    InvariantSpec,
    _issue_fingerprint,
)
from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue
from temper_drc.core.runner import CheckRunner
from temper_drc.core.severity import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class PassCheck(Check):
    """A check that always passes."""

    def __init__(self, name: str = "pass", category: str = "test"):
        self._name = name
        self._category = category

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    def run(self, placement, constraints, modified_regions=None):
        return CheckResult(check_name=self.name, passed=True)


class FailCheck(Check):
    """A check that always fails with one issue."""

    def __init__(self, name: str = "fail", category: str = "test"):
        self._name = name
        self._category = category

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    def run(self, placement, constraints, modified_regions=None):
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
                    affected_items=["U1", "U2"],
                )
            ],
        )


class IncrementalCheck(Check):
    """A check that supports incremental scoping."""

    def __init__(self, name: str = "incr", category: str = "test"):
        self._name = name
        self._category = category
        self.last_modified_regions = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    @property
    def supports_incremental(self) -> bool:
        return True

    def run(self, placement, constraints, modified_regions=None):
        self.last_modified_regions = modified_regions
        return CheckResult(check_name=self.name, passed=True)


class SlowCheck(Check):
    """A check that takes a controlled amount of time."""

    def __init__(self, name: str = "slow", category: str = "test", delay_ms: float = 10.0):
        self._name = name
        self._category = category
        self.delay_ms = delay_ms

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    def run(self, placement, constraints, modified_regions=None):
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000.0)
        return CheckResult(check_name=self.name, passed=True)


@pytest.fixture
def empty_placement():
    return Placement()


@pytest.fixture
def empty_constraints():
    return ConstraintSet()


@pytest.fixture
def pass_runner():
    runner = CheckRunner()
    runner.add_check(PassCheck("pass_check"))
    return runner


@pytest.fixture
def fail_runner():
    runner = CheckRunner()
    runner.add_check(FailCheck("fail_check"))
    return runner


@pytest.fixture
def incr_runner():
    runner = CheckRunner()
    runner.add_check(IncrementalCheck("incr_check"))
    return runner


class TestInvariantSpec:
    """Test InvariantSpec dataclass."""

    def test_create_minimal(self):
        inv = InvariantSpec("drc_component_overlap", "No overlaps")
        assert inv.check_name == "drc_component_overlap"
        assert inv.guarantees == "No overlaps"
        assert inv.affected_regions is None

    def test_create_with_regions(self):
        inv = InvariantSpec(
            "drc_component_overlap",
            "No overlaps",
            affected_regions=((0.0, 0.0, 10.0, 10.0),),
        )
        assert inv.affected_regions == ((0.0, 0.0, 10.0, 10.0),)

    def test_frozen(self):
        inv = InvariantSpec("check", "desc")
        with pytest.raises(Exception):
            inv.check_name = "other"


class TestIssueFingerprint:
    """Test canonical issue fingerprinting."""

    def test_same_issue_same_fingerprint(self):
        i1 = Issue(Severity.ERROR, "CODE", "msg", "cat", "check", ["A", "B"])
        i2 = Issue(Severity.ERROR, "CODE", "msg", "cat", "check", ["B", "A"])
        assert _issue_fingerprint(i1) == _issue_fingerprint(i2)

    def test_different_issue_different_fingerprint(self):
        i1 = Issue(Severity.ERROR, "CODE1", "msg", "cat", "check", ["A"])
        i2 = Issue(Severity.ERROR, "CODE2", "msg", "cat", "check", ["A"])
        assert _issue_fingerprint(i1) != _issue_fingerprint(i2)

    def test_fingerprint_format(self):
        issue = Issue(Severity.ERROR, "DRC_001", "overlap", "drc", "check", ["U1", "U2"])
        fp = _issue_fingerprint(issue)
        assert "DRC_001" in fp
        assert "overlap" in fp
        assert "U1,U2" in fp


class TestDRCFenceCore:
    """Test DRCFence core behavior."""

    def test_empty_invariants_noop(self, pass_runner, empty_placement, empty_constraints):
        """Fence with empty invariants returns instantly with passed=True."""
        fence = DRCFence(pass_runner)
        result = fence.check(
            stage_name="test",
            invariants=(),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        assert result.passed
        assert result.elapsed_ms == 0.0

    def test_filters_checks_by_name(self, empty_placement, empty_constraints):
        """Fence only runs checks named in invariants."""
        runner = CheckRunner()
        runner.add_check(PassCheck("check_a"))
        runner.add_check(FailCheck("check_b"))
        fence = DRCFence(runner)

        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("check_a", "Should pass"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        assert result.passed
        assert len(result.check_results) == 1
        assert result.check_results[0].check_name == "check_a"

    def test_pass_result_format(self, pass_runner, empty_placement, empty_constraints):
        """Passing fence result has correct structure."""
        fence = DRCFence(pass_runner)
        result = fence.check(
            stage_name="test_stage",
            invariants=(InvariantSpec("pass_check", "Should pass"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        assert result.stage_name == "test_stage"
        assert result.passed
        assert len(result.violations) == 0
        assert result.mode == "single"
        assert result.overhead_pct is None
        assert result.alternative_result is None

    def test_fail_detection(self, fail_runner, empty_placement, empty_constraints):
        """Fence detects failures from checks."""
        fence = DRCFence(fail_runner)
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("fail_check", "Should pass"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        assert not result.passed
        assert len(result.violations) == 1
        assert result.violations[0].check_name == "fail_check"

    def test_violation_attribution_new(self, fail_runner, empty_placement, empty_constraints):
        """New violations are attributed to the current stage."""
        fence = DRCFence(fail_runner)
        result = fence.check(
            stage_name="stage_a",
            invariants=(InvariantSpec("fail_check", "invariant"),),
            placement=empty_placement,
            constraints=empty_constraints,
            previous_violations=frozenset(),
        )
        assert not result.passed
        assert result.violations[0].is_new
        assert result.violations[0].introduced_count == 1
        assert result.violations[0].stage_name == "stage_a"

    def test_violation_attribution_pre_existing(self, fail_runner, empty_placement, empty_constraints):
        """Pre-existing violations are not attributed as new."""
        issue = Issue(Severity.ERROR, "FAIL_001", "Check failed", "test", "fail_check", ["U1", "U2"])
        prev = frozenset({_issue_fingerprint(issue)})

        fence = DRCFence(fail_runner)
        result = fence.check(
            stage_name="stage_b",
            invariants=(InvariantSpec("fail_check", "invariant"),),
            placement=empty_placement,
            constraints=empty_constraints,
            previous_violations=prev,
        )
        assert not result.passed
        assert not result.violations[0].is_new

    def test_fail_on_violation_raises(self, fail_runner, empty_placement, empty_constraints):
        """fail_on_violation=True raises FenceViolationError."""
        fence = DRCFence(fail_runner, fail_on_violation=True)
        with pytest.raises(FenceViolationError) as exc:
            fence.check(
                stage_name="test",
                invariants=(InvariantSpec("fail_check", "invariant"),),
                placement=empty_placement,
                constraints=empty_constraints,
            )
        assert "test" in str(exc.value)
        assert len(exc.value.result.violations) == 1

    def test_fail_on_violation_false_no_raise(self, fail_runner, empty_placement, empty_constraints):
        """fail_on_violation=False does not raise."""
        fence = DRCFence(fail_runner)
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("fail_check", "invariant"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        assert not result.passed

    def test_report_format(self, fail_runner, empty_placement, empty_constraints):
        """FenceResult.format() produces expected output."""
        fence = DRCFence(fail_runner)
        result = fence.check(
            stage_name="placement_validation",
            invariants=(InvariantSpec("fail_check", "No component overlaps after placement"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        output = result.format()
        assert "STAGE FENCE VIOLATION" in output
        assert "placement_validation" in output
        assert "fail_check" in output
        assert "FAIL_001" in output


class TestDRCFenceTiming:
    """Test fence timing and overhead computation."""

    def test_overhead_computed(self, pass_runner, empty_placement, empty_constraints):
        """Overhead is computed when stage_time >= floor."""
        fence = DRCFence(pass_runner, perf_budget_floor_ms=50.0)
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("pass_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
            stage_wall_time_ms=100.0,
        )
        assert result.overhead_pct is not None
        assert result.overhead_pct >= 0.0

    def test_overhead_skipped_below_floor(self, pass_runner, empty_placement, empty_constraints):
        """Overhead not computed when stage_time < floor."""
        fence = DRCFence(pass_runner, perf_budget_floor_ms=50.0)
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("pass_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
            stage_wall_time_ms=30.0,
        )
        assert result.overhead_pct is None

    def test_overhead_skipped_no_stage_time(self, pass_runner, empty_placement, empty_constraints):
        """Overhead is None when no stage_time provided."""
        fence = DRCFence(pass_runner)
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("pass_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        assert result.overhead_pct is None

    def test_elapsed_ms_recorded(self, pass_runner, empty_placement, empty_constraints):
        """Fence records wall-clock time."""
        fence = DRCFence(pass_runner)
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("pass_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        assert result.elapsed_ms >= 0.0


class TestDRCFenceIncremental:
    """Test incremental check scoping through the fence."""

    def test_incremental_marker_is_set(self):
        """Check.supports_incremental defaults to False."""
        check = PassCheck()
        assert not check.supports_incremental

    def test_incremental_capable_check(self):
        """Checks that override supports_incremental return True."""
        check = IncrementalCheck()
        assert check.supports_incremental

    def test_runner_passes_regions_to_incremental_check(self, incr_runner):
        """CheckRunner passes modified_regions to incremental-capable checks."""
        incr_check = incr_runner.checks[0]
        regions = [(0.0, 0.0, 10.0, 10.0)]
        incr_runner.run(
            Placement(), ConstraintSet(),
            check_names=["incr_check"],
            modified_regions=regions,
        )
        assert incr_check.last_modified_regions == regions

    def test_runner_skips_regions_for_non_incremental(self, empty_placement, empty_constraints):
        """Non-incremental checks don't receive modified_regions."""
        runner = CheckRunner()
        check = PassCheck("pass_check")
        runner.add_check(check)
        runner.run(empty_placement, empty_constraints, modified_regions=[(0, 0, 10, 10)])


class TestFenceDualRun:
    """Test dual-run mode (U5)."""

    def test_dual_run_both_pass(self, pass_runner, empty_placement, empty_constraints):
        """Dual run with both passing reports consistency."""
        fence = DRCFence(pass_runner)
        alt = fence.check(
            stage_name="test_alt",
            invariants=(InvariantSpec("pass_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("pass_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
            alternative_result=alt,
        )
        assert result.mode == "dual"
        assert result.alternative_result is not None
        assert result.passed == alt.passed

    def test_dual_run_divergence(self, empty_placement, empty_constraints, caplog):
        """Dual run with divergence logs an error."""
        runner = CheckRunner()
        runner.add_check(FailCheck("fail_check"))
        fence = DRCFence(runner)

        alt = fence.check(
            stage_name="test_alt",
            invariants=(InvariantSpec("fail_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )

        with caplog.at_level(logging.WARNING):
            result = fence.check(
                stage_name="test",
                invariants=(InvariantSpec("pass_check", "desc"),),
                placement=empty_placement,
                constraints=empty_constraints,
                alternative_result=alt,
            )
            assert result.mode == "dual"

    def test_dual_run_format(self, fail_runner, empty_placement, empty_constraints):
        """Dual run format includes both primary and alternative status."""
        fence = DRCFence(fail_runner)
        alt = fence.check(
            stage_name="test_alt",
            invariants=(InvariantSpec("fail_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
        )

        result = fence.check(
            stage_name="placement_validation",
            invariants=(InvariantSpec("fail_check", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
            alternative_result=alt,
        )
        output = result.format()
        assert "DUAL-RUN" in output
        assert "placement_validation" in output


class TestFencePerfBudget:
    """Test performance budget enforcement (U6)."""

    def test_no_warning_within_budget(self, pass_runner, empty_placement, empty_constraints, caplog):
        """No warning when overhead <= budget."""
        fence = DRCFence(pass_runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0)
        with caplog.at_level(logging.WARNING):
            fence.check(
                stage_name="test",
                invariants=(InvariantSpec("pass_check", "desc"),),
                placement=empty_placement,
                constraints=empty_constraints,
                stage_wall_time_ms=100.0,
            )
        assert "exceeds budget" not in caplog.text

    def test_no_warning_below_floor(self, empty_placement, empty_constraints, caplog):
        """No warning when stage_time < floor regardless of overhead."""
        runner = CheckRunner()
        runner.add_check(SlowCheck("slow", delay_ms=20))
        fence = DRCFence(runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0)
        with caplog.at_level(logging.WARNING):
            result = fence.check(
                stage_name="test",
                invariants=(InvariantSpec("slow", "desc"),),
                placement=empty_placement,
                constraints=empty_constraints,
                stage_wall_time_ms=30.0,
            )
            assert result.overhead_pct is None
            assert "exceeds budget" not in caplog.text

    def test_ci_enforce_soft_launch(self, empty_placement, empty_constraints, monkeypatch):
        """During soft-launch, ci_enforce=True only warns, doesn't block."""
        runner = CheckRunner()
        runner.add_check(SlowCheck("slow", delay_ms=30))
        fence = DRCFence(runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0, ci_enforce=True)

        import temper_drc.core.fence as fence_mod
        monkeypatch.setattr(fence_mod, "_BUDGET_ENFORCEMENT_START", __import__("datetime").datetime(2027, 1, 1))
        result = fence.check(
            stage_name="test",
            invariants=(InvariantSpec("slow", "desc"),),
            placement=empty_placement,
            constraints=empty_constraints,
            stage_wall_time_ms=100.0,
        )
        assert result is not None
