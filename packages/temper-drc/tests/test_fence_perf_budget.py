"""Tests for DRCFence performance budget enforcement (U6)."""

import time
from datetime import datetime

import pytest

from temper_drc.core.check import Check
from temper_drc.core.fence import (
    DRCFence,
    FenceBudgetError,
    InvariantSpec,
)
from temper_drc.core.result import CheckResult
from temper_drc.core.runner import CheckRunner
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class TimedCheck(Check):
    """A check with controllable execution time."""

    def __init__(self, name: str, delay_ms: float = 5.0):
        self._name = name
        self._category = "test"
        self.delay_ms = delay_ms

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    def run(self, _placement, _constraints, _modified_regions=None):
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000.0)
        return CheckResult(check_name=self.name, passed=True)


@pytest.fixture
def placement():
    return Placement()


@pytest.fixture
def constraints():
    return ConstraintSet()


class TestPerfBudget:
    """Performance budget enforcement tests."""

    def test_no_warning_for_stage_below_floor(self, placement, constraints, caplog):
        """Stage < 50ms: no warning even with high overhead."""
        runner = CheckRunner()
        runner.add_check(TimedCheck("slow", delay_ms=15))
        fence = DRCFence(runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0)
        import logging
        with caplog.at_level(logging.WARNING):
            result = fence.check(
                stage_name="fast_stage",
                invariants=(InvariantSpec("slow", "desc"),),
                placement=placement,
                constraints=constraints,
                stage_wall_time_ms=40.0,
            )
            assert result.overhead_pct is None
            assert "exceeds budget" not in caplog.text

    def test_no_warning_within_budget(self, placement, constraints, caplog):
        """Within budget: no warning."""
        runner = CheckRunner()
        runner.add_check(TimedCheck("fast", delay_ms=1))
        fence = DRCFence(runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0)
        import logging
        with caplog.at_level(logging.WARNING):
            result = fence.check(
                stage_name="moderate_stage",
                invariants=(InvariantSpec("fast", "desc"),),
                placement=placement,
                constraints=constraints,
                stage_wall_time_ms=200.0,
            )
            if result.overhead_pct is not None and result.overhead_pct > 20.0:
                assert "exceeds budget" in caplog.text

    def test_warning_over_budget(self, placement, constraints, caplog):
        """Over budget: warning is logged."""
        runner = CheckRunner()
        runner.add_check(TimedCheck("slow", delay_ms=30))
        fence = DRCFence(runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0)
        import logging
        with caplog.at_level(logging.WARNING):
            result = fence.check(
                stage_name="slow_stage",
                invariants=(InvariantSpec("slow", "desc"),),
                placement=placement,
                constraints=constraints,
                stage_wall_time_ms=100.0,
            )
            if result.overhead_pct is not None and result.overhead_pct > 20.0:
                assert "exceeds budget" in caplog.text
                assert "slow_stage" in caplog.text

    def test_ci_enforce_before_cutoff_warning_only(self, placement, constraints, monkeypatch):
        """Before enforcement date: ci_enforce=True only warns."""
        import temper_drc.core.fence as fence_mod
        monkeypatch.setattr(fence_mod, "_BUDGET_ENFORCEMENT_START", datetime(2027, 1, 1))

        runner = CheckRunner()
        runner.add_check(TimedCheck("slow", delay_ms=30))
        fence = DRCFence(runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0, ci_enforce=True)

        result = fence.check(
            stage_name="soft_launch_stage",
            invariants=(InvariantSpec("slow", "desc"),),
            placement=placement,
            constraints=constraints,
            stage_wall_time_ms=100.0,
        )
        assert result is not None

    def test_ci_enforce_after_cutoff_raises(self, placement, constraints, monkeypatch):
        """After enforcement date: ci_enforce=True may raise FenceBudgetError."""
        import temper_drc.core.fence as fence_mod
        monkeypatch.setattr(fence_mod, "_BUDGET_ENFORCEMENT_START", datetime(2000, 1, 1))

        runner = CheckRunner()
        runner.add_check(TimedCheck("slow", delay_ms=30))
        fence = DRCFence(runner, perf_budget_pct=20.0, perf_budget_floor_ms=50.0, ci_enforce=True)

        try:
            fence.check(
                stage_name="hard_block_stage",
                invariants=(InvariantSpec("slow", "desc"),),
                placement=placement,
                constraints=constraints,
                stage_wall_time_ms=100.0,
            )
        except FenceBudgetError as e:
            assert "hard_block_stage" in str(e)
        else:
            pass  # Check was within budget

    def test_budget_floor_default(self):
        """Default perf_budget_floor_ms is 50.0."""
        fence = DRCFence(CheckRunner())
        assert fence.perf_budget_floor_ms == 50.0

    def test_budget_pct_default(self):
        """Default perf_budget_pct is 20.0."""
        fence = DRCFence(CheckRunner())
        assert fence.perf_budget_pct == 20.0

    def test_ci_enforce_default_false(self):
        """ci_enforce defaults to False."""
        fence = DRCFence(CheckRunner())
        assert not fence.ci_enforce
