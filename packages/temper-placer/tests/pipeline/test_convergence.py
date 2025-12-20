"""Tests for convergence criteria - TDD approach.

Tests written BEFORE implementation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import time


# =============================================================================
# Tests for TerminationReason Enum
# =============================================================================


class TestTerminationReason:
    """Tests for TerminationReason enumeration."""

    def test_termination_reason_exists(self):
        """TerminationReason enum should exist."""
        from temper_placer.pipeline.convergence import TerminationReason

        assert TerminationReason is not None

    def test_termination_reason_success(self):
        """TerminationReason should have SUCCESS."""
        from temper_placer.pipeline.convergence import TerminationReason

        assert hasattr(TerminationReason, "SUCCESS")
        assert TerminationReason.SUCCESS.value == "success"

    def test_termination_reason_max_iterations(self):
        """TerminationReason should have MAX_ITERATIONS."""
        from temper_placer.pipeline.convergence import TerminationReason

        assert hasattr(TerminationReason, "MAX_ITERATIONS")
        assert TerminationReason.MAX_ITERATIONS.value == "max_iterations"

    def test_termination_reason_timeout(self):
        """TerminationReason should have TIMEOUT."""
        from temper_placer.pipeline.convergence import TerminationReason

        assert hasattr(TerminationReason, "TIMEOUT")
        assert TerminationReason.TIMEOUT.value == "timeout"

    def test_termination_reason_infeasible(self):
        """TerminationReason should have INFEASIBLE."""
        from temper_placer.pipeline.convergence import TerminationReason

        assert hasattr(TerminationReason, "INFEASIBLE")
        assert TerminationReason.INFEASIBLE.value == "infeasible"

    def test_termination_reason_no_progress(self):
        """TerminationReason should have NO_PROGRESS."""
        from temper_placer.pipeline.convergence import TerminationReason

        assert hasattr(TerminationReason, "NO_PROGRESS")
        assert TerminationReason.NO_PROGRESS.value == "no_progress"

    def test_termination_reason_user_abort(self):
        """TerminationReason should have USER_ABORT."""
        from temper_placer.pipeline.convergence import TerminationReason

        assert hasattr(TerminationReason, "USER_ABORT")
        assert TerminationReason.USER_ABORT.value == "user_abort"


# =============================================================================
# Tests for ConvergenceCriteria
# =============================================================================


class TestConvergenceCriteria:
    """Tests for ConvergenceCriteria dataclass."""

    def test_convergence_criteria_exists(self):
        """ConvergenceCriteria should exist."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        assert ConvergenceCriteria is not None

    def test_default_max_iterations(self):
        """Default max_iterations should be 5."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        criteria = ConvergenceCriteria()
        assert criteria.max_iterations == 5

    def test_default_max_refinement_iterations(self):
        """Default max_refinement_iterations should be 3."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        criteria = ConvergenceCriteria()
        assert criteria.max_refinement_iterations == 3

    def test_default_timeout_seconds(self):
        """Default timeout_seconds should be 600 (10 minutes)."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        criteria = ConvergenceCriteria()
        assert criteria.timeout_seconds == 600.0

    def test_default_phase_timeout_seconds(self):
        """Default phase_timeout_seconds should be 120 (2 minutes)."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        criteria = ConvergenceCriteria()
        assert criteria.phase_timeout_seconds == 120.0

    def test_default_success_thresholds(self):
        """Default success thresholds should be set."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        criteria = ConvergenceCriteria()
        assert criteria.max_overlap_mm2 == 0.01
        assert criteria.max_boundary_violation_mm == 0.01
        assert criteria.min_routing_completion == 1.0
        assert criteria.min_manufacturing_margin_mm == 0.05

    def test_default_progress_detection(self):
        """Default progress detection should be set."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        criteria = ConvergenceCriteria()
        assert criteria.min_loss_improvement == 0.001
        assert criteria.stagnation_epochs == 500

    def test_custom_values(self):
        """ConvergenceCriteria should accept custom values."""
        from temper_placer.pipeline.convergence import ConvergenceCriteria

        criteria = ConvergenceCriteria(
            max_iterations=10,
            timeout_seconds=1200.0,
            min_routing_completion=0.95,
        )
        assert criteria.max_iterations == 10
        assert criteria.timeout_seconds == 1200.0
        assert criteria.min_routing_completion == 0.95


# =============================================================================
# Tests for ConvergenceState
# =============================================================================


class TestConvergenceState:
    """Tests for ConvergenceState dataclass."""

    def test_convergence_state_exists(self):
        """ConvergenceState should exist."""
        from temper_placer.pipeline.convergence import ConvergenceState

        assert ConvergenceState is not None

    def test_convergence_state_requires_start_time(self):
        """ConvergenceState requires start_time."""
        from temper_placer.pipeline.convergence import ConvergenceState

        now = datetime.now()
        state = ConvergenceState(start_time=now)
        assert state.start_time == now

    def test_default_iteration(self):
        """Default iteration should be 0."""
        from temper_placer.pipeline.convergence import ConvergenceState

        state = ConvergenceState(start_time=datetime.now())
        assert state.iteration == 0

    def test_default_loss_history(self):
        """Default loss_history should be empty list."""
        from temper_placer.pipeline.convergence import ConvergenceState

        state = ConvergenceState(start_time=datetime.now())
        assert state.loss_history == []

    def test_default_best_loss(self):
        """Default best_loss should be infinity."""
        from temper_placer.pipeline.convergence import ConvergenceState

        state = ConvergenceState(start_time=datetime.now())
        assert state.best_loss == float("inf")

    def test_default_epochs_since_improvement(self):
        """Default epochs_since_improvement should be 0."""
        from temper_placer.pipeline.convergence import ConvergenceState

        state = ConvergenceState(start_time=datetime.now())
        assert state.epochs_since_improvement == 0

    def test_default_terminated(self):
        """Default terminated should be False."""
        from temper_placer.pipeline.convergence import ConvergenceState

        state = ConvergenceState(start_time=datetime.now())
        assert state.terminated is False

    def test_default_termination_reason(self):
        """Default termination_reason should be None."""
        from temper_placer.pipeline.convergence import ConvergenceState

        state = ConvergenceState(start_time=datetime.now())
        assert state.termination_reason is None


# =============================================================================
# Tests for ConvergenceChecker
# =============================================================================


class TestConvergenceCheckerInit:
    """Tests for ConvergenceChecker initialization."""

    def test_convergence_checker_exists(self):
        """ConvergenceChecker should exist."""
        from temper_placer.pipeline.convergence import ConvergenceChecker

        assert ConvergenceChecker is not None

    def test_convergence_checker_requires_criteria(self):
        """ConvergenceChecker requires ConvergenceCriteria."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)
        assert checker.criteria == criteria

    def test_convergence_checker_creates_state(self):
        """ConvergenceChecker should create initial state."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            ConvergenceState,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)
        assert isinstance(checker.state, ConvergenceState)


# =============================================================================
# Tests for Iteration Limit
# =============================================================================


class TestIterationLimit:
    """Tests for iteration limit checking."""

    def test_within_iteration_limit(self):
        """Should not terminate when within iteration limit."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria(max_iterations=5)
        checker = ConvergenceChecker(criteria)
        checker.state.iteration = 3

        result = checker.check_iteration_limit()
        assert result is False  # Should not terminate

    def test_at_iteration_limit(self):
        """Should terminate when at iteration limit."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria(max_iterations=5)
        checker = ConvergenceChecker(criteria)
        checker.state.iteration = 5

        result = checker.check_iteration_limit()
        assert result is True
        assert checker.state.terminated is True
        assert checker.state.termination_reason == TerminationReason.MAX_ITERATIONS

    def test_beyond_iteration_limit(self):
        """Should terminate when beyond iteration limit."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria(max_iterations=5)
        checker = ConvergenceChecker(criteria)
        checker.state.iteration = 10

        result = checker.check_iteration_limit()
        assert result is True
        assert checker.state.termination_reason == TerminationReason.MAX_ITERATIONS


# =============================================================================
# Tests for Timeout
# =============================================================================


class TestTimeout:
    """Tests for timeout checking."""

    def test_within_timeout(self):
        """Should not terminate when within timeout."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria(timeout_seconds=600.0)
        checker = ConvergenceChecker(criteria)
        # State was created recently, should be within timeout

        result = checker.check_timeout()
        assert result is False

    def test_at_timeout(self):
        """Should terminate when at timeout."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria(timeout_seconds=1.0)
        checker = ConvergenceChecker(criteria)
        # Set start time to past
        checker.state.start_time = datetime.now() - timedelta(seconds=2.0)

        result = checker.check_timeout()
        assert result is True
        assert checker.state.terminated is True
        assert checker.state.termination_reason == TerminationReason.TIMEOUT

    def test_elapsed_time_calculation(self):
        """Should correctly calculate elapsed time."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)
        checker.state.start_time = datetime.now() - timedelta(seconds=30.0)

        elapsed = checker.get_elapsed_seconds()
        assert 29.0 <= elapsed <= 31.0  # Allow small tolerance


# =============================================================================
# Tests for Progress Detection
# =============================================================================


class TestProgressDetection:
    """Tests for progress/stagnation detection."""

    def test_initial_has_no_progress_data(self):
        """Initially should not detect stagnation (no data)."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        result = checker.check_stagnation()
        assert result is False  # No stagnation with no data

    def test_records_loss(self):
        """Should record loss values."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        checker.record_loss(100.0)
        checker.record_loss(90.0)
        checker.record_loss(85.0)

        assert len(checker.state.loss_history) == 3
        assert checker.state.loss_history == [100.0, 90.0, 85.0]

    def test_updates_best_loss(self):
        """Should update best_loss when improved."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        checker.record_loss(100.0)
        assert checker.state.best_loss == 100.0

        checker.record_loss(90.0)
        assert checker.state.best_loss == 90.0

        checker.record_loss(95.0)  # Worse
        assert checker.state.best_loss == 90.0  # Should stay at 90

    def test_tracks_epochs_since_improvement(self):
        """Should track epochs since improvement."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria(min_loss_improvement=0.01)  # 1%
        checker = ConvergenceChecker(criteria)

        checker.record_loss(100.0)
        assert checker.state.epochs_since_improvement == 0

        checker.record_loss(98.0)  # 2% improvement
        assert checker.state.epochs_since_improvement == 0

        checker.record_loss(97.9)  # 0.1% - not enough
        assert checker.state.epochs_since_improvement == 1

        checker.record_loss(97.8)  # Another small change
        assert checker.state.epochs_since_improvement == 2

    def test_detects_stagnation(self):
        """Should detect stagnation after many epochs without improvement."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria(min_loss_improvement=0.01, stagnation_epochs=5)
        checker = ConvergenceChecker(criteria)

        # Record improving losses
        checker.record_loss(100.0)
        checker.record_loss(90.0)

        # Now stagnate
        for _ in range(6):
            checker.record_loss(89.99)  # Not enough improvement

        result = checker.check_stagnation()
        assert result is True
        assert checker.state.termination_reason == TerminationReason.NO_PROGRESS


# =============================================================================
# Tests for Success Thresholds
# =============================================================================


class TestSuccessThresholds:
    """Tests for success threshold checking."""

    def test_check_success_all_passing(self):
        """Should return True when all thresholds pass."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        # Create mock metrics that pass all thresholds
        metrics = {
            "overlap_mm2": 0.0,
            "boundary_violation_mm": 0.0,
            "routing_completion": 1.0,
            "manufacturing_margin_mm": 0.1,
        }

        result = checker.check_success(metrics)
        assert result is True
        assert checker.state.terminated is True
        assert checker.state.termination_reason == TerminationReason.SUCCESS

    def test_check_success_overlap_fails(self):
        """Should return False when overlap exceeds threshold."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria(max_overlap_mm2=0.01)
        checker = ConvergenceChecker(criteria)

        metrics = {
            "overlap_mm2": 1.0,  # Exceeds threshold
            "boundary_violation_mm": 0.0,
            "routing_completion": 1.0,
            "manufacturing_margin_mm": 0.1,
        }

        result = checker.check_success(metrics)
        assert result is False
        assert checker.state.terminated is False

    def test_check_success_routing_fails(self):
        """Should return False when routing completion is low."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria(min_routing_completion=1.0)
        checker = ConvergenceChecker(criteria)

        metrics = {
            "overlap_mm2": 0.0,
            "boundary_violation_mm": 0.0,
            "routing_completion": 0.8,  # Only 80% routed
            "manufacturing_margin_mm": 0.1,
        }

        result = checker.check_success(metrics)
        assert result is False

    def test_check_success_partial_metrics(self):
        """Should handle missing metrics gracefully."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        # Only provide some metrics
        metrics = {
            "overlap_mm2": 0.0,
            "routing_completion": 1.0,
        }

        # Should not crash, but cannot confirm success without all metrics
        result = checker.check_success(metrics)
        # Behavior depends on implementation - missing metrics could be failure or skip


# =============================================================================
# Tests for Combined Check
# =============================================================================


class TestCombinedCheck:
    """Tests for combined check_all method."""

    def test_check_all_not_terminated(self):
        """check_all should return False when no termination conditions met."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria(
            max_iterations=10, timeout_seconds=600.0, stagnation_epochs=500
        )
        checker = ConvergenceChecker(criteria)

        result = checker.check_all()
        assert result is False
        assert checker.state.terminated is False

    def test_check_all_iteration_limit(self):
        """check_all should terminate on iteration limit."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria(max_iterations=2)
        checker = ConvergenceChecker(criteria)
        checker.state.iteration = 3

        result = checker.check_all()
        assert result is True
        assert checker.state.termination_reason == TerminationReason.MAX_ITERATIONS

    def test_check_all_timeout(self):
        """check_all should terminate on timeout."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria(timeout_seconds=0.001)
        checker = ConvergenceChecker(criteria)
        # Force timeout by setting old start time
        checker.state.start_time = datetime.now() - timedelta(seconds=1.0)

        result = checker.check_all()
        assert result is True
        assert checker.state.termination_reason == TerminationReason.TIMEOUT


# =============================================================================
# Tests for Increment Iteration
# =============================================================================


class TestIncrementIteration:
    """Tests for iteration increment."""

    def test_increment_iteration(self):
        """Should increment iteration count."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        assert checker.state.iteration == 0
        checker.increment_iteration()
        assert checker.state.iteration == 1
        checker.increment_iteration()
        assert checker.state.iteration == 2


# =============================================================================
# Tests for Reset State
# =============================================================================


class TestResetState:
    """Tests for state reset."""

    def test_reset_creates_fresh_state(self):
        """reset() should create fresh state."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        # Modify state
        checker.state.iteration = 5
        checker.state.terminated = True
        checker.record_loss(100.0)

        # Reset
        checker.reset()

        assert checker.state.iteration == 0
        assert checker.state.terminated is False
        assert len(checker.state.loss_history) == 0


# =============================================================================
# Tests for Mark Infeasible
# =============================================================================


class TestMarkInfeasible:
    """Tests for marking infeasibility."""

    def test_mark_infeasible(self):
        """Should mark state as infeasible."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
            TerminationReason,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        checker.mark_infeasible("Constraint contradiction detected")

        assert checker.state.terminated is True
        assert checker.state.termination_reason == TerminationReason.INFEASIBLE
        assert checker.state.failure_message == "Constraint contradiction detected"

    def test_check_all_after_infeasible(self):
        """check_all should return True after marked infeasible."""
        from temper_placer.pipeline.convergence import (
            ConvergenceChecker,
            ConvergenceCriteria,
        )

        criteria = ConvergenceCriteria()
        checker = ConvergenceChecker(criteria)

        checker.mark_infeasible("Cannot satisfy constraints")
        result = checker.check_all()

        assert result is True
