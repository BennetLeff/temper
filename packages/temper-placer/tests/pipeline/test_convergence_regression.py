"""Tests for routability regression detection (U4)."""

import pytest

from temper_placer.pipeline.convergence import (
    ConvergenceChecker,
    ConvergenceCriteria,
    TerminationReason,
)


class TestRoutabilityRegression:
    """ConvergenceChecker detects routability regression and convergence."""

    def _checker(self, max_iterations: int = 10) -> ConvergenceChecker:
        return ConvergenceChecker(ConvergenceCriteria(max_iterations=max_iterations))

    def test_improvement_continues(self):
        checker = self._checker()
        routed_0 = frozenset({"A", "B", "C"})
        should_stop = checker.check_routability_regression(routed_0, 10)
        assert not should_stop
        assert not checker.state.terminated

        routed_1 = frozenset({"A", "B", "C", "D"})
        should_stop = checker.check_routability_regression(routed_1, 10, previous_routed_nets=routed_0)
        assert not should_stop
        assert not checker.state.terminated

    def test_net_loss_triggers_regression(self):
        checker = self._checker()
        routed_0 = frozenset({"A", "B", "C", "D", "E"})  # 5/5 = 1.0
        checker.check_routability_regression(routed_0, 5)

        routed_1 = frozenset({"A", "B"})  # 2/5 = 0.4 < 1.0 * 0.95 = 0.95
        should_stop = checker.check_routability_regression(routed_1, 5, previous_routed_nets=routed_0)
        assert should_stop
        assert checker.state.terminated
        assert checker.state.termination_reason == TerminationReason.ROUTABILITY_REGRESSION

    def test_ratio_drop_triggers_regression(self):
        checker = self._checker()
        routed_0 = frozenset({"A", "B", "C", "D", "E", "F"})  # 6/10 = 0.6
        checker.check_routability_regression(routed_0, 10)

        routed_1 = frozenset({"A", "B", "C", "D"})  # 4/10 = 0.4 < 0.6*0.95 = 0.57
        should_stop = checker.check_routability_regression(routed_1, 10, previous_routed_nets=routed_0)
        assert should_stop
        assert checker.state.termination_reason == TerminationReason.ROUTABILITY_REGRESSION

    def test_identical_nets_converges(self):
        checker = self._checker()
        routed = frozenset({"A", "B", "C"})
        checker.check_routability_regression(routed, 10)  # iteration 0

        should_stop = checker.check_routability_regression(routed, 10, previous_routed_nets=routed)  # iteration 1
        assert not should_stop, "First identical iteration should not converge"

        should_stop = checker.check_routability_regression(routed, 10, previous_routed_nets=routed)  # iteration 2
        assert should_stop
        assert checker.state.termination_reason == TerminationReason.ROUTABILITY_CONVERGED

    def test_different_nets_same_ratio_continues(self):
        """Stable ratio with different net sets = oscillation, not convergence."""
        checker = self._checker()
        routed_a = frozenset({"A", "B", "C"})
        routed_b = frozenset({"D", "E", "F"})

        checker.check_routability_regression(routed_a, 10)
        should_stop = checker.check_routability_regression(routed_b, 10, previous_routed_nets=routed_a)
        assert not should_stop, "Different net sets should not trigger convergence"

    def test_improvement_then_stall_converges(self):
        checker = self._checker()
        routed_0 = frozenset({"A"})
        routed_1 = frozenset({"A", "B", "C"})
        checker.check_routability_regression(routed_0, 10)
        checker.check_routability_regression(routed_1, 10, previous_routed_nets=routed_0)

        should_stop = checker.check_routability_regression(routed_1, 10, previous_routed_nets=routed_1)
        assert not should_stop

        should_stop = checker.check_routability_regression(routed_1, 10, previous_routed_nets=routed_1)
        assert should_stop
        assert checker.state.termination_reason == TerminationReason.ROUTABILITY_CONVERGED

    def test_max_iterations_fallback(self):
        """The iteration limit cap still applies."""
        checker = ConvergenceChecker(ConvergenceCriteria(max_iterations=3))
        routed = frozenset({"A"})
        for _ in range(4):
            checker.increment_iteration()
            checker.check_routability_regression(routed, 10, previous_routed_nets=routed)
        assert checker.check_iteration_limit()
