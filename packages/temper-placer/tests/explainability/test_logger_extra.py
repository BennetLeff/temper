"""Tests for uncovered DecisionLogger methods.

Covers simple state-setting and query methods that are zero-coverage
in the allowlist despite the logger being used by differential tests.
"""

from temper_placer.explainability.decision import DecisionPhase
from temper_placer.explainability.logger import DecisionLogger


class TestDecisionLoggerState:
    """Test enable/disable and state querying."""

    def test_enable_disable(self):
        logger = DecisionLogger()
        assert logger.is_enabled() is True
        logger.disable()
        assert logger.is_enabled() is False
        logger.enable()
        assert logger.is_enabled() is True

    def test_set_phase(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.ROUTING)
        assert logger.current_phase == DecisionPhase.ROUTING

    def test_set_epoch(self):
        logger = DecisionLogger()
        logger.set_epoch(42)
        assert logger.current_epoch == 42

    def test_set_iteration(self):
        logger = DecisionLogger()
        logger.set_iteration(7)
        assert logger.current_iteration == 7

    def test_phase_context_manager(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)
        with logger.phase(DecisionPhase.ROUTING):
            assert logger.current_phase == DecisionPhase.ROUTING
        assert logger.current_phase == DecisionPhase.GEOMETRIC

    def test_epoch_context_manager(self):
        logger = DecisionLogger()
        logger.set_epoch(100)
        with logger.epoch(200):
            assert logger.current_epoch == 200
        assert logger.current_epoch == 100

    def test_should_log_epoch_zero(self):
        logger = DecisionLogger()
        assert logger.should_log(0, interval=100) is True

    def test_should_log_interval_boundary(self):
        logger = DecisionLogger()
        assert logger.should_log(100, interval=100) is True
        assert logger.should_log(101, interval=100) is False

    def test_should_log_final(self):
        logger = DecisionLogger()
        assert logger.should_log(99, interval=100, is_final=True) is True

    def test_significant_change_above_threshold(self):
        logger = DecisionLogger()
        assert logger.significant_change((0.0, 0.0), (10.0, 0.0), threshold=5.0) is True

    def test_significant_change_below_threshold(self):
        logger = DecisionLogger()
        assert logger.significant_change((0.0, 0.0), (0.1, 0.1), threshold=1.0) is False


class TestDecisionLoggerLogMethods:
    """Test the log_* methods exercise the Rust-delegation path."""

    def test_log_position(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)
        logger.log_position("C1", (10.0, 20.0), reason="test place")
        assert len(logger.trace.decisions) == 1
        assert logger.trace.decisions[0].subject == "C1"

    def test_log_position_disabled(self):
        logger = DecisionLogger()
        logger.disable()
        logger.log_position("C1", (10.0, 20.0), reason="should not log")
        assert len(logger.trace.decisions) == 0

    def test_log_rotation(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)
        logger.log_rotation("C1", 90, previous=0, reason="better thermal")
        assert len(logger.trace.decisions) == 1

    def test_log_heuristic(self):
        logger = DecisionLogger()
        logger.log_heuristic("thermal_edge", "Q1", (30.0, 5.0), reason="edge placement")
        assert len(logger.trace.decisions) == 1

    def test_log_constraint_application(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)
        logger.log_constraint_application(
            "thermal.edge", ["Q1", "Q2"], "moved_to_edge", reason="required"
        )
        assert len(logger.trace.decisions) == 1
