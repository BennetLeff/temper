"""Tests for convergence module."""

from unittest.mock import MagicMock

import pytest

from temper_placer.pipeline.convergence import (
    ConvergenceChecker,
    ConvergenceCriteria,
    TerminationReason,
    is_converged,
)


class TestConvergenceChecker:
    """Tests for ConvergenceChecker methods."""

    def test_get_elapsed_seconds_returns_float(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        elapsed = checker.get_elapsed_seconds()
        assert isinstance(elapsed, float)
        assert elapsed >= 0.0

    def test_increment_iteration(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        assert checker.state.iteration == 0
        checker.increment_iteration()
        assert checker.state.iteration == 1
        checker.increment_iteration()
        assert checker.state.iteration == 2

    def test_reset(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.increment_iteration()
        checker.record_loss(10.0)
        assert checker.state.iteration == 1

        checker.reset()
        assert checker.state.iteration == 0
        assert len(checker.state.loss_history) == 0
        assert not checker.state.terminated

    def test_check_iteration_limit_not_reached(self):
        checker = ConvergenceChecker(ConvergenceCriteria(max_iterations=5))
        checker.state.iteration = 3
        assert not checker.check_iteration_limit()
        assert not checker.state.terminated

    def test_check_iteration_limit_reached(self):
        checker = ConvergenceChecker(ConvergenceCriteria(max_iterations=5))
        checker.state.iteration = 5
        assert checker.check_iteration_limit()
        assert checker.state.terminated
        assert checker.state.termination_reason == TerminationReason.MAX_ITERATIONS

    def test_check_iteration_limit_exceeded(self):
        checker = ConvergenceChecker(ConvergenceCriteria(max_iterations=5))
        checker.state.iteration = 10
        assert checker.check_iteration_limit()

    def test_check_timeout_not_exceeded(self):
        checker = ConvergenceChecker(ConvergenceCriteria(timeout_seconds=999999))
        assert not checker.check_timeout()

    def test_check_timeout_exceeded(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(timeout_seconds=0.0)
        )
        assert checker.check_timeout()
        assert checker.state.termination_reason == TerminationReason.TIMEOUT

    def test_record_loss_basic(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.record_loss(100.0)
        assert len(checker.state.loss_history) == 1
        assert checker.state.loss_history[0] == 100.0
        assert checker.state.best_loss == 100.0
        assert checker.state.epochs_since_improvement == 0

    def test_record_loss_improvement(self):
        checker = ConvergenceChecker(ConvergenceCriteria(min_loss_improvement=0.01))
        checker.record_loss(100.0)
        checker.record_loss(90.0)  # 10% improvement
        assert checker.state.best_loss == 90.0
        assert checker.state.epochs_since_improvement == 0

    def test_record_loss_no_improvement(self):
        checker = ConvergenceChecker(ConvergenceCriteria(min_loss_improvement=0.01))
        checker.record_loss(100.0)
        checker.record_loss(99.5)  # Only 0.5% improvement
        assert checker.state.best_loss == 100.0  # Unchanged
        assert checker.state.epochs_since_improvement == 1

    def test_check_stagnation_false_early(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(stagnation_epochs=500)
        )
        checker.record_loss(100.0)
        checker.record_loss(99.9)
        assert not checker.check_stagnation()

    def test_check_stagnation_true(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(stagnation_epochs=5, min_loss_improvement=1.0)
        )
        # Record first loss
        checker.record_loss(100.0)
        # Record 5 more losses without improvement
        for _ in range(5):
            checker.record_loss(100.0)  # Same loss, no improvement
        assert checker.check_stagnation()
        assert checker.state.termination_reason == TerminationReason.NO_PROGRESS

    def test_check_stagnation_empty_history(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        assert not checker.check_stagnation()

    def test_check_success_all_pass(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(
                max_overlap_mm2=0.01,
                max_boundary_violation_mm=0.01,
                min_routing_completion=1.0,
                min_manufacturing_margin_mm=0.05,
            )
        )
        metrics = {
            "overlap_mm2": 0.0,
            "boundary_violation_mm": 0.0,
            "routing_completion": 1.0,
            "manufacturing_margin_mm": 0.1,
        }
        assert checker.check_success(metrics)
        assert checker.state.termination_reason == TerminationReason.SUCCESS

    def test_check_success_overlap_fails(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(max_overlap_mm2=0.01)
        )
        metrics = {"overlap_mm2": 1.0}
        assert not checker.check_success(metrics)

    def test_check_success_routing_fails(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(min_routing_completion=1.0)
        )
        metrics = {"routing_completion": 0.5}
        assert not checker.check_success(metrics)

    def test_check_all_iteration_limit(self):
        checker = ConvergenceChecker(ConvergenceCriteria(max_iterations=3))
        checker.state.iteration = 3
        assert checker.check_all()

    def test_check_all_timeout(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(timeout_seconds=0.0)
        )
        assert checker.check_all()

    def test_check_all_stagnation(self):
        checker = ConvergenceChecker(
            ConvergenceCriteria(stagnation_epochs=3, min_loss_improvement=1.0)
        )
        checker.record_loss(100.0)
        for _ in range(3):
            checker.record_loss(100.0)
        assert checker.check_all()

    def test_check_all_already_terminated(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.state.terminated = True
        assert checker.check_all()

    def test_mark_infeasible(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.mark_infeasible("Constraints impossible")
        assert checker.state.terminated
        assert checker.state.termination_reason == TerminationReason.INFEASIBLE
        assert checker.state.failure_message == "Constraints impossible"

    def test_mark_user_abort(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.mark_user_abort()
        assert checker.state.terminated
        assert checker.state.termination_reason == TerminationReason.USER_ABORT
        assert "User aborted" in checker.state.failure_message

    def test_check_routability_regression_no_previous(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        # Pre-set the dynamic attribute the method checks for None
        checker.state._best_routed_nets = None
        routed = frozenset({"N1", "N2"})
        result = checker.check_routability_regression(routed, 10)
        assert result is False
        assert checker.state._best_routed_nets == routed
        assert checker.state._best_routability == 0.2

    def test_check_routability_regression_improvement(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.state._best_routed_nets = frozenset({"N1"})
        checker.state._best_routability = 0.1
        result = checker.check_routability_regression(
            frozenset({"N1", "N2"}), 10
        )
        assert result is False
        assert checker.state._best_routability == 0.2

    def test_check_routability_regression_detected(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.state._best_routed_nets = frozenset({"N1", "N2", "N3", "N4", "N5"})
        checker.state._best_routability = 0.5  # 5/10
        checker.state._stall_count = 0
        result = checker.check_routability_regression(
            frozenset({"N1"}), 10, regression_threshold=0.5
        )
        # 1/10 = 0.1 which is < 0.5 * 0.5 = 0.25
        assert result is True

    def test_check_routability_convergence(self):
        checker = ConvergenceChecker(ConvergenceCriteria())
        checker.state._best_routed_nets = frozenset({"N1", "N2"})
        checker.state._best_routability = 0.2
        checker.state._stall_count = 0
        routed = frozenset({"N1", "N2"})
        # First stall
        result = checker.check_routability_regression(
            routed, 10, previous_routed_nets=routed, stall_limit=2
        )
        assert result is False
        assert checker.state._stall_count == 1
        # Second stall
        result = checker.check_routability_regression(
            routed, 10, previous_routed_nets=routed, stall_limit=2
        )
        assert result is True
        assert checker.state.termination_reason == TerminationReason.ROUTABILITY_CONVERGED


class TestIsConverged:
    """Tests for is_converged function."""

    def test_empty_current_results(self):
        assert not is_converged({}, None)

    def test_all_success(self):
        r1 = MagicMock()
        r1.success = True
        r1.length = 100.0
        r2 = MagicMock()
        r2.success = True
        r2.length = 200.0
        assert is_converged({"n1": r1, "n2": r2}, None)

    def test_not_all_success_no_previous(self):
        r1 = MagicMock()
        r1.success = True
        r2 = MagicMock()
        r2.success = False
        assert not is_converged({"n1": r1, "n2": r2}, None)

    def test_stagnation_same_results(self):
        r1 = MagicMock()
        r1.success = False
        r1.length = 100.0
        r2 = MagicMock()
        r2.success = False
        r2.length = 200.0
        current = {"n1": r1, "n2": r2}
        prev = {"n1": r1, "n2": r2}
        # Same success count and same total length
        assert is_converged(current, prev)

    def test_no_stagnation_different_length(self):
        r1a = MagicMock()
        r1a.success = False
        r1a.length = 100.0
        r2a = MagicMock()
        r2a.success = False
        r2a.length = 200.0
        current = {"n1": r1a, "n2": r2a}

        r1b = MagicMock()
        r1b.success = False
        r1b.length = 150.0
        r2b = MagicMock()
        r2b.success = False
        r2b.length = 200.0
        prev = {"n1": r1b, "n2": r2b}
        # Total length differs: 300.0 vs 350.0
        assert not is_converged(current, prev)
