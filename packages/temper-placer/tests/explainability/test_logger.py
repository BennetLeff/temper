"""Tests for the explainability.logger module.

This module tests the DecisionLogger class which provides hooks for
automatically capturing placement decisions during optimizer training
and heuristic application.
"""

import math
import time

import pytest

from temper_placer.explainability import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.logger import DecisionLogger
from temper_placer.explainability.serialization import serialize_trace


# =============================================================================
# TestLoggerBasics - Core functionality
# =============================================================================


class TestLoggerBasics:
    """Tests for basic logger creation and state management."""

    def test_create_logger_with_default_trace(self):
        """Logger creates its own DecisionTrace if none provided."""
        logger = DecisionLogger()
        assert logger.trace is not None
        assert isinstance(logger.trace, DecisionTrace)
        assert len(logger.trace) == 0

    def test_create_logger_with_existing_trace(self):
        """Logger uses provided trace."""
        trace = DecisionTrace(run_id="test-run")
        logger = DecisionLogger(trace=trace)
        assert logger.trace is trace
        assert logger.trace.run_id == "test-run"

    def test_logger_enabled_by_default(self):
        """Logger is enabled by default after creation."""
        logger = DecisionLogger()
        assert logger.is_enabled() is True

    def test_enable_disable_toggle(self):
        """enable() and disable() toggle the enabled state."""
        logger = DecisionLogger()
        assert logger.is_enabled() is True

        logger.disable()
        assert logger.is_enabled() is False

        logger.enable()
        assert logger.is_enabled() is True

        # Multiple disables
        logger.disable()
        logger.disable()
        assert logger.is_enabled() is False

    def test_set_phase(self):
        """set_phase() updates the current phase."""
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.SEMANTIC)
        assert logger.current_phase == DecisionPhase.SEMANTIC

        logger.set_phase(DecisionPhase.ROUTING)
        assert logger.current_phase == DecisionPhase.ROUTING

    def test_set_epoch(self):
        """set_epoch() updates the current epoch."""
        logger = DecisionLogger()
        logger.set_epoch(100)
        assert logger.current_epoch == 100

        logger.set_epoch(500)
        assert logger.current_epoch == 500

    def test_set_iteration(self):
        """set_iteration() updates the current iteration."""
        logger = DecisionLogger()
        logger.set_iteration(5)
        assert logger.current_iteration == 5

        logger.set_iteration(10)
        assert logger.current_iteration == 10

    def test_trace_property_returns_trace(self):
        """trace property returns the internal trace object."""
        logger = DecisionLogger()
        trace = logger.trace
        assert isinstance(trace, DecisionTrace)

        # Same object each time
        assert logger.trace is trace


# =============================================================================
# TestPositionLogging - Position decision logging
# =============================================================================


class TestPositionLogging:
    """Tests for log_position() method."""

    def test_log_basic_position(self):
        """Log position with minimal fields."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0))

        assert len(logger.trace) == 1
        decision = logger.trace.decisions[0]
        assert decision.subject == "C1"
        assert decision.value == (10.0, 20.0)

    def test_log_position_with_previous(self):
        """Log position update with previous value."""
        logger = DecisionLogger()
        logger.log_position("C1", (15.0, 25.0), previous=(10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.value == (15.0, 25.0)
        assert decision.previous_value == (10.0, 20.0)

    def test_log_position_with_reason(self):
        """Log position includes reason text."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0), reason="Thermal constraint")

        decision = logger.trace.decisions[0]
        assert decision.reason == "Thermal constraint"

    def test_log_position_with_constraints(self):
        """Log position includes constraint references."""
        logger = DecisionLogger()
        logger.log_position(
            "C1",
            (10.0, 20.0),
            constraint_refs=["thermal.edge", "clearance.hv"],
        )

        decision = logger.trace.decisions[0]
        assert "thermal.edge" in decision.constraint_refs
        assert "clearance.hv" in decision.constraint_refs

    def test_log_position_with_alternatives(self):
        """Log position includes rejected alternatives."""
        logger = DecisionLogger()
        alt = Alternative(
            value=(50.0, 30.0),
            rejection_reason="Violates clearance",
            constraint_violated="clearance.hv_lv",
        )
        logger.log_position("C1", (10.0, 20.0), alternatives=[alt])

        decision = logger.trace.decisions[0]
        assert len(decision.alternatives) == 1
        assert decision.alternatives[0].value == (50.0, 30.0)

    def test_log_position_with_loss_delta(self):
        """Log position includes loss contribution."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0), loss_delta=-0.05)

        decision = logger.trace.decisions[0]
        assert decision.loss_contribution == -0.05

    def test_log_position_uses_current_phase(self):
        """Decision uses phase set by set_phase()."""
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.REFINEMENT)
        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.phase == DecisionPhase.REFINEMENT

    def test_log_position_uses_current_epoch(self):
        """Decision uses epoch set by set_epoch()."""
        logger = DecisionLogger()
        logger.set_epoch(250)
        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.epoch == 250

    def test_log_position_uses_current_iteration(self):
        """Decision uses iteration set by set_iteration()."""
        logger = DecisionLogger()
        logger.set_iteration(7)
        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.iteration == 7

    def test_log_position_when_disabled_no_op(self):
        """Disabled logger doesn't log anything."""
        logger = DecisionLogger()
        logger.disable()
        logger.log_position("C1", (10.0, 20.0))

        assert len(logger.trace) == 0

    def test_log_position_initial_has_correct_type(self):
        """No previous value means INITIAL_POSITION type."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.decision_type == DecisionType.INITIAL_POSITION

    def test_log_position_update_has_correct_type(self):
        """With previous value means POSITION_UPDATE type."""
        logger = DecisionLogger()
        logger.log_position("C1", (15.0, 25.0), previous=(10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.decision_type == DecisionType.POSITION_UPDATE

    def test_log_position_multiple_components(self):
        """Multiple components can be logged separately."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0))
        logger.log_position("C2", (30.0, 40.0))
        logger.log_position("R1", (50.0, 60.0))

        assert len(logger.trace) == 3
        subjects = [d.subject for d in logger.trace.decisions]
        assert subjects == ["C1", "C2", "R1"]


# =============================================================================
# TestRotationLogging - Rotation decision logging
# =============================================================================


class TestRotationLogging:
    """Tests for log_rotation() method."""

    def test_log_basic_rotation(self):
        """Log rotation with minimal fields."""
        logger = DecisionLogger()
        logger.log_rotation("C1", 1)  # 90 degrees

        assert len(logger.trace) == 1
        decision = logger.trace.decisions[0]
        assert decision.subject == "C1"
        assert decision.value == 1

    def test_log_rotation_with_previous(self):
        """Log rotation update with previous value."""
        logger = DecisionLogger()
        logger.log_rotation("C1", 2, previous=0)

        decision = logger.trace.decisions[0]
        assert decision.value == 2
        assert decision.previous_value == 0

    def test_log_rotation_with_reason(self):
        """Log rotation includes reason text."""
        logger = DecisionLogger()
        logger.log_rotation("C1", 1, reason="Pin alignment with net VCC")

        decision = logger.trace.decisions[0]
        assert decision.reason == "Pin alignment with net VCC"

    def test_log_rotation_decision_type_is_rotation(self):
        """Decision type is ROTATION."""
        logger = DecisionLogger()
        logger.log_rotation("C1", 1)

        decision = logger.trace.decisions[0]
        assert decision.decision_type == DecisionType.ROTATION

    def test_log_rotation_uses_current_epoch(self):
        """Decision uses current epoch."""
        logger = DecisionLogger()
        logger.set_epoch(300)
        logger.log_rotation("C1", 2)

        decision = logger.trace.decisions[0]
        assert decision.epoch == 300

    def test_log_rotation_when_disabled_no_op(self):
        """Disabled logger doesn't log rotations."""
        logger = DecisionLogger()
        logger.disable()
        logger.log_rotation("C1", 1)

        assert len(logger.trace) == 0

    def test_log_rotation_values_0_to_3(self):
        """All rotation values (0-3) are valid."""
        logger = DecisionLogger()
        for rot in [0, 1, 2, 3]:
            logger.log_rotation(f"C{rot}", rot)

        assert len(logger.trace) == 4
        values = [d.value for d in logger.trace.decisions]
        assert values == [0, 1, 2, 3]

    def test_log_rotation_uses_current_phase(self):
        """Rotation decision uses current phase."""
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)
        logger.log_rotation("C1", 1)

        decision = logger.trace.decisions[0]
        assert decision.phase == DecisionPhase.GEOMETRIC


# =============================================================================
# TestHeuristicLogging - Heuristic decision logging
# =============================================================================


class TestHeuristicLogging:
    """Tests for log_heuristic() method."""

    def test_log_heuristic_basic(self):
        """Log heuristic decision with name and component."""
        logger = DecisionLogger()
        logger.log_heuristic("thermal_edge", "Q1", (5.0, 95.0))

        assert len(logger.trace) == 1
        decision = logger.trace.decisions[0]
        assert decision.subject == "Q1"
        assert decision.value == (5.0, 95.0)

    def test_log_heuristic_includes_name_in_reason(self):
        """Heuristic name appears in reason."""
        logger = DecisionLogger()
        logger.log_heuristic("thermal_edge", "Q1", (5.0, 95.0))

        decision = logger.trace.decisions[0]
        assert "thermal_edge" in decision.reason

    def test_log_heuristic_with_custom_reason(self):
        """Custom reason overrides default."""
        logger = DecisionLogger()
        logger.log_heuristic(
            "thermal_edge",
            "Q1",
            (5.0, 95.0),
            reason="Placed near top edge for heat dissipation",
        )

        decision = logger.trace.decisions[0]
        assert decision.reason == "Placed near top edge for heat dissipation"

    def test_log_heuristic_uses_topological_phase(self):
        """Phase is TOPOLOGICAL for heuristics by default."""
        logger = DecisionLogger()
        logger.log_heuristic("thermal_edge", "Q1", (5.0, 95.0))

        decision = logger.trace.decisions[0]
        assert decision.phase == DecisionPhase.TOPOLOGICAL

    def test_log_heuristic_with_confidence(self):
        """Confidence value is recorded in loss_contribution."""
        logger = DecisionLogger()
        logger.log_heuristic("thermal_edge", "Q1", (5.0, 95.0), confidence=0.85)

        decision = logger.trace.decisions[0]
        # Confidence stored in loss_contribution as a proxy
        assert decision.loss_contribution == 0.85

    def test_log_heuristic_when_disabled_no_op(self):
        """Disabled logger doesn't log heuristics."""
        logger = DecisionLogger()
        logger.disable()
        logger.log_heuristic("thermal_edge", "Q1", (5.0, 95.0))

        assert len(logger.trace) == 0

    def test_log_heuristic_decision_type_is_initial_position(self):
        """Heuristic placements are INITIAL_POSITION type."""
        logger = DecisionLogger()
        logger.log_heuristic("thermal_edge", "Q1", (5.0, 95.0))

        decision = logger.trace.decisions[0]
        assert decision.decision_type == DecisionType.INITIAL_POSITION

    def test_log_heuristic_multiple_from_same_heuristic(self):
        """Multiple components from same heuristic are logged."""
        logger = DecisionLogger()
        logger.log_heuristic("decoupling_cap", "C1", (10.0, 20.0))
        logger.log_heuristic("decoupling_cap", "C2", (12.0, 22.0))
        logger.log_heuristic("decoupling_cap", "C3", (14.0, 24.0))

        assert len(logger.trace) == 3
        for d in logger.trace.decisions:
            assert "decoupling_cap" in d.reason


# =============================================================================
# TestConstraintLogging - Constraint application logging
# =============================================================================


class TestConstraintLogging:
    """Tests for log_constraint_application() method."""

    def test_log_constraint_single_component(self):
        """Log constraint affecting one component."""
        logger = DecisionLogger()
        logger.log_constraint_application(
            "thermal.edge",
            affected_components=["Q1"],
            action="moved_to_edge",
        )

        assert len(logger.trace) == 1
        decision = logger.trace.decisions[0]
        assert decision.subject == "thermal.edge"

    def test_log_constraint_multiple_components(self):
        """Log constraint affecting multiple components."""
        logger = DecisionLogger()
        logger.log_constraint_application(
            "clearance.hv_lv",
            affected_components=["Q1", "Q2", "D1"],
            action="enforced_spacing",
        )

        decision = logger.trace.decisions[0]
        # Action or affected components should be in reason
        assert "Q1" in decision.reason or "enforced_spacing" in decision.reason

    def test_log_constraint_refs_set_correctly(self):
        """constraint_refs contains the constraint ID."""
        logger = DecisionLogger()
        logger.log_constraint_application(
            "keepout.thermal_zone",
            affected_components=["C1"],
            action="excluded",
        )

        decision = logger.trace.decisions[0]
        assert "keepout.thermal_zone" in decision.constraint_refs

    def test_log_constraint_decision_type(self):
        """Decision type is CONSTRAINT_APPLIED."""
        logger = DecisionLogger()
        logger.log_constraint_application(
            "thermal.edge",
            affected_components=["Q1"],
            action="applied",
        )

        decision = logger.trace.decisions[0]
        assert decision.decision_type == DecisionType.CONSTRAINT_APPLIED

    def test_log_constraint_when_disabled_no_op(self):
        """Disabled logger doesn't log constraints."""
        logger = DecisionLogger()
        logger.disable()
        logger.log_constraint_application(
            "thermal.edge",
            affected_components=["Q1"],
            action="applied",
        )

        assert len(logger.trace) == 0

    def test_log_constraint_subject_is_constraint_id(self):
        """Subject is the constraint ID."""
        logger = DecisionLogger()
        logger.log_constraint_application(
            "my.custom.constraint",
            affected_components=["R1", "R2"],
            action="grouped",
        )

        decision = logger.trace.decisions[0]
        assert decision.subject == "my.custom.constraint"

    def test_log_constraint_with_reason(self):
        """Custom reason can be provided."""
        logger = DecisionLogger()
        logger.log_constraint_application(
            "thermal.edge",
            affected_components=["Q1"],
            action="applied",
            reason="IGBT must be within 5mm of board edge",
        )

        decision = logger.trace.decisions[0]
        assert decision.reason == "IGBT must be within 5mm of board edge"


# =============================================================================
# TestShouldLog - Interval-based logging control
# =============================================================================


class TestShouldLog:
    """Tests for should_log() interval helper."""

    def test_should_log_at_interval_boundaries(self):
        """Returns True at epoch 0, 100, 200, etc."""
        logger = DecisionLogger()
        assert logger.should_log(0, interval=100) is True
        assert logger.should_log(100, interval=100) is True
        assert logger.should_log(200, interval=100) is True
        assert logger.should_log(1000, interval=100) is True

    def test_should_log_between_intervals(self):
        """Returns False at epochs between intervals."""
        logger = DecisionLogger()
        assert logger.should_log(1, interval=100) is False
        assert logger.should_log(50, interval=100) is False
        assert logger.should_log(99, interval=100) is False
        assert logger.should_log(101, interval=100) is False

    def test_should_log_custom_interval(self):
        """Custom interval (e.g., 50) works."""
        logger = DecisionLogger()
        assert logger.should_log(0, interval=50) is True
        assert logger.should_log(50, interval=50) is True
        assert logger.should_log(25, interval=50) is False
        assert logger.should_log(75, interval=50) is False

    def test_should_log_at_epoch_zero(self):
        """Always True at epoch 0 regardless of interval."""
        logger = DecisionLogger()
        assert logger.should_log(0, interval=1000) is True
        assert logger.should_log(0, interval=1) is True

    def test_should_log_at_final_epoch(self):
        """Returns True if is_final=True."""
        logger = DecisionLogger()
        # Not at interval, but final
        assert logger.should_log(777, interval=100, is_final=True) is True
        # At interval and final
        assert logger.should_log(800, interval=100, is_final=True) is True

    def test_should_log_interval_of_one(self):
        """Interval of 1 means always log."""
        logger = DecisionLogger()
        for epoch in [0, 1, 2, 5, 99, 1000]:
            assert logger.should_log(epoch, interval=1) is True


# =============================================================================
# TestSignificantChange - Movement threshold detection
# =============================================================================


class TestSignificantChange:
    """Tests for significant_change() movement detection."""

    def test_significant_change_below_threshold(self):
        """Small movement returns False."""
        logger = DecisionLogger()
        old = (10.0, 20.0)
        new = (10.1, 20.1)  # ~0.14mm movement
        assert logger.significant_change(old, new, threshold=0.5) is False

    def test_significant_change_above_threshold(self):
        """Large movement returns True."""
        logger = DecisionLogger()
        old = (10.0, 20.0)
        new = (11.0, 21.0)  # ~1.41mm movement
        assert logger.significant_change(old, new, threshold=0.5) is True

    def test_significant_change_exact_threshold(self):
        """At exactly threshold returns True."""
        logger = DecisionLogger()
        old = (10.0, 20.0)
        new = (10.5, 20.0)  # Exactly 0.5mm
        assert logger.significant_change(old, new, threshold=0.5) is True

    def test_significant_change_diagonal_movement(self):
        """Euclidean distance is used for diagonal movement."""
        logger = DecisionLogger()
        old = (0.0, 0.0)
        new = (0.3, 0.4)  # 0.5mm (3-4-5 triangle)
        assert logger.significant_change(old, new, threshold=0.5) is True
        assert logger.significant_change(old, new, threshold=0.51) is False

    def test_significant_change_no_movement(self):
        """Zero movement returns False with positive threshold."""
        logger = DecisionLogger()
        pos = (10.0, 20.0)
        # Zero distance with positive threshold returns False
        assert logger.significant_change(pos, pos, threshold=0.5) is False
        assert logger.significant_change(pos, pos, threshold=0.001) is False
        # Note: threshold=0.0 with zero movement returns True (0.0 >= 0.0)

    def test_significant_change_custom_threshold(self):
        """Custom threshold (e.g., 1.0mm) works."""
        logger = DecisionLogger()
        old = (0.0, 0.0)
        new = (0.8, 0.0)
        assert logger.significant_change(old, new, threshold=1.0) is False
        assert logger.significant_change(old, new, threshold=0.5) is True

    def test_significant_change_large_movement(self):
        """Very large movement returns True."""
        logger = DecisionLogger()
        old = (0.0, 0.0)
        new = (100.0, 100.0)
        assert logger.significant_change(old, new, threshold=0.5) is True

    def test_significant_change_negative_coordinates(self):
        """Negative coordinates handled correctly."""
        logger = DecisionLogger()
        old = (-10.0, -20.0)
        new = (-9.0, -19.0)  # ~1.41mm movement
        assert logger.significant_change(old, new, threshold=0.5) is True


# =============================================================================
# TestLoggerIntegration - Simulated training scenarios
# =============================================================================


class TestLoggerIntegration:
    """Integration tests simulating training scenarios."""

    def test_simulate_multi_epoch_training(self):
        """Log decisions over 500 epochs at intervals."""
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)

        components = ["C1", "C2", "C3"]
        for epoch in range(500):
            logger.set_epoch(epoch)
            if logger.should_log(epoch, interval=100):
                for i, comp in enumerate(components):
                    pos = (10.0 + epoch * 0.01, 20.0 + i * 5)
                    logger.log_position(comp, pos, reason=f"Epoch {epoch}")

        # Should log at epochs 0, 100, 200, 300, 400 = 5 times * 3 components
        assert len(logger.trace) == 15

    def test_decisions_captured_at_correct_epochs(self):
        """Only epochs at intervals are logged."""
        logger = DecisionLogger()

        logged_epochs = []
        for epoch in range(250):
            logger.set_epoch(epoch)
            if logger.should_log(epoch, interval=50):
                logger.log_position("C1", (float(epoch), 0.0))
                logged_epochs.append(epoch)

        assert logged_epochs == [0, 50, 100, 150, 200]
        for d in logger.trace.decisions:
            assert d.epoch in [0, 50, 100, 150, 200]

    def test_trace_serializable_after_logging(self):
        """Trace can be serialized to JSON after logging."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0), reason="Test")
        logger.log_rotation("C1", 1, reason="Alignment")

        # Should not raise
        serialized = serialize_trace(logger.trace)
        assert "decisions" in serialized
        assert len(serialized["decisions"]) == 2

    def test_trace_why_works_with_logged_decisions(self):
        """trace.why('C1') returns correct info."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0), reason="Initial placement")
        logger.log_position("C1", (15.0, 25.0), previous=(10.0, 20.0), reason="Moved for clearance")

        result = logger.trace.why("C1")
        assert "C1" in result
        assert "(15.0, 25.0)" in result
        assert "Moved for clearance" in result

    def test_trace_history_shows_progression(self):
        """trace.history('C1') shows all updates."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0), reason="Initial")
        logger.log_position("C1", (12.0, 22.0), previous=(10.0, 20.0), reason="Step 1")
        logger.log_position("C1", (14.0, 24.0), previous=(12.0, 22.0), reason="Step 2")

        history = logger.trace.history("C1")
        assert len(history) == 3
        assert history[0] == ((10.0, 20.0), "Initial")
        assert history[1] == ((12.0, 22.0), "Step 1")
        assert history[2] == ((14.0, 24.0), "Step 2")

    def test_multiple_components_tracked(self):
        """Multiple components are tracked separately."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0))
        logger.log_position("C2", (30.0, 40.0))
        logger.log_position("C1", (11.0, 21.0), previous=(10.0, 20.0))

        c1_decisions = logger.trace.query_subject("C1")
        c2_decisions = logger.trace.query_subject("C2")

        assert len(c1_decisions) == 2
        assert len(c2_decisions) == 1

    def test_phase_transitions_during_training(self):
        """Phase changes mid-training are recorded."""
        logger = DecisionLogger()

        # Heuristic phase
        logger.set_phase(DecisionPhase.TOPOLOGICAL)
        logger.log_position("C1", (10.0, 20.0), reason="Heuristic placement")

        # Optimization phase
        logger.set_phase(DecisionPhase.GEOMETRIC)
        logger.log_position("C1", (11.0, 21.0), previous=(10.0, 20.0), reason="Gradient update")

        # Refinement phase
        logger.set_phase(DecisionPhase.REFINEMENT)
        logger.log_position("C1", (11.5, 21.5), previous=(11.0, 21.0), reason="Final adjustment")

        topo = logger.trace.query_phase(DecisionPhase.TOPOLOGICAL)
        geom = logger.trace.query_phase(DecisionPhase.GEOMETRIC)
        refine = logger.trace.query_phase(DecisionPhase.REFINEMENT)

        assert len(topo) == 1
        assert len(geom) == 1
        assert len(refine) == 1

    def test_mixed_decision_types_in_trace(self):
        """Trace contains position, rotation, and constraint decisions."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0))
        logger.log_rotation("C1", 1)
        logger.log_heuristic("thermal_edge", "Q1", (5.0, 95.0))
        logger.log_constraint_application("clearance.hv", ["C1", "Q1"], "enforced")

        assert len(logger.trace) == 4

        positions = logger.trace.query_type(DecisionType.INITIAL_POSITION)
        rotations = logger.trace.query_type(DecisionType.ROTATION)
        constraints = logger.trace.query_type(DecisionType.CONSTRAINT_APPLIED)

        assert len(positions) == 2  # log_position + log_heuristic
        assert len(rotations) == 1
        assert len(constraints) == 1


# =============================================================================
# TestContextManagers - Optional context manager syntax
# =============================================================================


class TestContextManagers:
    """Tests for optional context manager syntax."""

    def test_phase_context_manager(self):
        """with logger.phase(...) sets and restores phase."""
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)

        with logger.phase(DecisionPhase.ROUTING):
            assert logger.current_phase == DecisionPhase.ROUTING
            logger.log_position("C1", (10.0, 20.0))

        # Restored after context
        assert logger.current_phase == DecisionPhase.GEOMETRIC

        # Decision was logged with ROUTING phase
        decision = logger.trace.decisions[0]
        assert decision.phase == DecisionPhase.ROUTING

    def test_epoch_context_manager(self):
        """with logger.epoch(...) sets and restores epoch."""
        logger = DecisionLogger()
        logger.set_epoch(100)

        with logger.epoch(500):
            assert logger.current_epoch == 500
            logger.log_position("C1", (10.0, 20.0))

        # Restored after context
        assert logger.current_epoch == 100

        # Decision was logged with epoch 500
        decision = logger.trace.decisions[0]
        assert decision.epoch == 500

    def test_nested_context_managers(self):
        """Nested contexts work correctly."""
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.SEMANTIC)
        logger.set_epoch(0)

        with logger.phase(DecisionPhase.TOPOLOGICAL):
            with logger.epoch(100):
                logger.log_position("C1", (10.0, 20.0))
                assert logger.current_phase == DecisionPhase.TOPOLOGICAL
                assert logger.current_epoch == 100

            # Epoch restored, phase still TOPOLOGICAL
            assert logger.current_epoch == 0
            assert logger.current_phase == DecisionPhase.TOPOLOGICAL

        # Both restored
        assert logger.current_phase == DecisionPhase.SEMANTIC
        assert logger.current_epoch == 0

    def test_context_manager_on_exception(self):
        """Phase/epoch restored even on exception."""
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.SEMANTIC)
        logger.set_epoch(50)

        with pytest.raises(ValueError):
            with logger.phase(DecisionPhase.ROUTING):
                with logger.epoch(999):
                    raise ValueError("Test exception")

        # Both restored despite exception
        assert logger.current_phase == DecisionPhase.SEMANTIC
        assert logger.current_epoch == 50


# =============================================================================
# TestEdgeCases - Edge cases and error handling
# =============================================================================


class TestEdgeCases:
    """Edge cases and error handling tests."""

    def test_log_with_empty_component_ref(self):
        """Empty string component is handled."""
        logger = DecisionLogger()
        logger.log_position("", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.subject == ""

    def test_log_with_special_characters_in_ref(self):
        """Component refs with special characters work."""
        logger = DecisionLogger()
        logger.log_position("C1/A", (10.0, 20.0))
        logger.log_position("R_1.2", (20.0, 30.0))
        logger.log_position("U$1", (30.0, 40.0))

        subjects = [d.subject for d in logger.trace.decisions]
        assert "C1/A" in subjects
        assert "R_1.2" in subjects
        assert "U$1" in subjects

    def test_log_with_none_alternative_values(self):
        """None in alternatives handled gracefully."""
        logger = DecisionLogger()
        alt = Alternative(value=None, rejection_reason="Invalid position")
        logger.log_position("C1", (10.0, 20.0), alternatives=[alt])

        decision = logger.trace.decisions[0]
        assert decision.alternatives[0].value is None

    def test_log_negative_epoch(self):
        """Negative epoch is accepted (no validation)."""
        logger = DecisionLogger()
        logger.set_epoch(-1)
        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.epoch == -1

    def test_log_very_large_position(self):
        """Large coordinates handled."""
        logger = DecisionLogger()
        logger.log_position("C1", (1e10, 1e10))

        decision = logger.trace.decisions[0]
        assert decision.value == (1e10, 1e10)

    def test_log_with_empty_constraint_refs(self):
        """Empty constraint list is OK."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0), constraint_refs=[])

        decision = logger.trace.decisions[0]
        assert decision.constraint_refs == []

    def test_log_with_very_long_reason(self):
        """Very long reason strings work."""
        logger = DecisionLogger()
        long_reason = "A" * 10000
        logger.log_position("C1", (10.0, 20.0), reason=long_reason)

        decision = logger.trace.decisions[0]
        assert len(decision.reason) == 10000

    def test_log_with_unicode_in_reason(self):
        """Unicode characters in reason work."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0), reason="Placed for thermal μ = 0.5°C/W")

        decision = logger.trace.decisions[0]
        assert "μ" in decision.reason
        assert "°" in decision.reason

    def test_rapid_logging_performance(self):
        """10,000 logs complete in reasonable time (<1 second)."""
        logger = DecisionLogger()

        start = time.perf_counter()
        for i in range(10000):
            logger.log_position(f"C{i}", (float(i), float(i)))
        elapsed = time.perf_counter() - start

        assert len(logger.trace) == 10000
        assert elapsed < 1.0, f"Logging 10k decisions took {elapsed:.2f}s (should be <1s)"

    def test_float_precision_in_positions(self):
        """Float precision is preserved."""
        logger = DecisionLogger()
        pos = (1.23456789012345, 9.87654321098765)
        logger.log_position("C1", pos)

        decision = logger.trace.decisions[0]
        assert decision.value[0] == pytest.approx(1.23456789012345)
        assert decision.value[1] == pytest.approx(9.87654321098765)

    def test_logging_after_trace_finalized(self):
        """Logging after trace.finalize() still works."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0))
        logger.trace.finalize(positions={"C1": (10.0, 20.0)})

        # Should still be able to log (finalize doesn't lock)
        logger.log_position("C2", (30.0, 40.0))
        assert len(logger.trace) == 2


# =============================================================================
# TestDefaultPhase - Phase default behavior
# =============================================================================


class TestDefaultPhase:
    """Tests for default phase behavior."""

    def test_default_phase_is_geometric(self):
        """Default phase is GEOMETRIC."""
        logger = DecisionLogger()
        assert logger.current_phase == DecisionPhase.GEOMETRIC

    def test_log_position_default_phase(self):
        """Logged positions use GEOMETRIC by default."""
        logger = DecisionLogger()
        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.phase == DecisionPhase.GEOMETRIC

    def test_log_rotation_default_phase(self):
        """Logged rotations use current phase (GEOMETRIC by default)."""
        logger = DecisionLogger()
        logger.log_rotation("C1", 1)

        decision = logger.trace.decisions[0]
        assert decision.phase == DecisionPhase.GEOMETRIC


# =============================================================================
# TestIterationTracking - Iteration within epoch
# =============================================================================


class TestIterationTracking:
    """Tests for iteration tracking within epochs."""

    def test_iteration_defaults_to_none(self):
        """Iteration defaults to None."""
        logger = DecisionLogger()
        assert logger.current_iteration is None

    def test_iteration_in_logged_decision(self):
        """Iteration is recorded in decisions."""
        logger = DecisionLogger()
        logger.set_iteration(3)
        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.iteration == 3

    def test_iteration_and_epoch_independent(self):
        """Iteration and epoch are tracked independently."""
        logger = DecisionLogger()
        logger.set_epoch(100)
        logger.set_iteration(5)

        logger.log_position("C1", (10.0, 20.0))

        decision = logger.trace.decisions[0]
        assert decision.epoch == 100
        assert decision.iteration == 5
