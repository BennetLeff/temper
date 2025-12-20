"""
Tests for constraint tier system with escalation.

Tests cover:
- ConstraintStatus tracks violation history
- Severity-based escalation
- Persistence-based escalation
- Hard constraint rejection
- Penalty calculation by tier
- TieredConstraintManager integration
"""

import pytest
from temper_placer.pcl.tiers import (
    ConstraintStatus,
    EscalationConfig,
    EscalationReason,
    TieredConstraintManager,
    calculate_penalty,
    check_hard_constraints,
)
from temper_placer.pcl.constraints import (
    ConstraintTier,
    AdjacentConstraint,
    SeparatedConstraint,
    DistanceMetric,
)


class TestConstraintStatus:
    """Test ConstraintStatus tracks violations and escalation."""

    def test_records_violation_history(self):
        """ConstraintStatus should track last N violations."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        status.record_violation(1.5)
        status.record_violation(2.3)
        status.record_violation(0.5)

        assert len(status.violation_history) == 3
        assert status.violation_history == [1.5, 2.3, 0.5]

    def test_limits_history_to_10_violations(self):
        """History should be capped at 10 entries (sliding window)."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        # Record 15 violations
        for i in range(15):
            status.record_violation(float(i))

        assert len(status.violation_history) == 10
        # Should keep last 10 (5-14)
        assert status.violation_history == [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0]

    def test_is_escalated_property(self):
        """is_escalated should detect tier changes."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        assert not status.is_escalated

        status.current_tier = ConstraintTier.STRONG
        assert status.is_escalated

        status.current_tier = ConstraintTier.HARD
        assert status.is_escalated

    def test_escalate_from_soft_to_strong(self):
        """Escalate should move soft → strong."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        status.escalate()
        assert status.current_tier == ConstraintTier.STRONG

    def test_escalate_from_strong_to_hard(self):
        """Escalate should move strong → hard."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.STRONG,
            current_tier=ConstraintTier.STRONG,
            violation_history=[],
        )

        status.escalate()
        assert status.current_tier == ConstraintTier.HARD

    def test_escalate_stops_at_hard(self):
        """Escalate should not go beyond HARD."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.HARD,
            current_tier=ConstraintTier.HARD,
            violation_history=[],
        )

        status.escalate()
        assert status.current_tier == ConstraintTier.HARD  # No change


class TestSeverityEscalation:
    """Test severity-based escalation (large violations trigger escalation)."""

    def test_soft_escalates_on_large_violation(self):
        """Soft constraint should escalate if violation exceeds threshold."""
        config = EscalationConfig(
            severity_thresholds={
                ConstraintTier.SOFT: 5.0,
                ConstraintTier.STRONG: 2.0,
            }
        )

        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        # Small violation - no escalation
        status.record_violation(2.0)
        assert not status.check_escalation(config)

        # Large violation - should escalate
        status.record_violation(7.0)
        assert status.check_escalation(config)
        assert status.escalation_reason == EscalationReason.SEVERITY

    def test_strong_escalates_on_smaller_threshold(self):
        """Strong constraints have tighter threshold (2mm vs 5mm)."""
        config = EscalationConfig(
            severity_thresholds={
                ConstraintTier.SOFT: 5.0,
                ConstraintTier.STRONG: 2.0,
            }
        )

        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.STRONG,
            current_tier=ConstraintTier.STRONG,
            violation_history=[],
        )

        # 3mm violation exceeds 2mm threshold
        status.record_violation(3.0)
        assert status.check_escalation(config)
        assert status.escalation_reason == EscalationReason.SEVERITY

    def test_hard_never_escalates(self):
        """Hard constraints cannot escalate further."""
        config = EscalationConfig(
            severity_thresholds={
                ConstraintTier.SOFT: 5.0,
                ConstraintTier.STRONG: 2.0,
            }
        )

        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.HARD,
            current_tier=ConstraintTier.HARD,
            violation_history=[],
        )

        # Even huge violation doesn't escalate HARD
        status.record_violation(100.0)
        assert not status.check_escalation(config)


class TestPersistenceEscalation:
    """Test persistence-based escalation (repeated failures trigger escalation)."""

    def test_escalates_after_N_consecutive_violations(self):
        """Should escalate if violated for N consecutive iterations."""
        config = EscalationConfig(persistence_window=5)

        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        # Record 4 violations - not enough
        for _ in range(4):
            status.record_violation(0.5)
        assert not status.check_escalation(config)

        # 5th violation triggers escalation
        status.record_violation(0.5)
        assert status.check_escalation(config)
        assert status.escalation_reason == EscalationReason.PERSISTENT

    def test_no_escalation_if_satisfied_in_window(self):
        """If constraint satisfied even once in window, no persistence escalation."""
        config = EscalationConfig(persistence_window=5)

        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        # 4 violations, then satisfied (0), then 2 more violations
        status.record_violation(0.5)
        status.record_violation(0.5)
        status.record_violation(0.5)
        status.record_violation(0.5)
        status.record_violation(0.0)  # Satisfied
        status.record_violation(0.5)
        status.record_violation(0.5)

        # Window contains [0.5, 0.5, 0.0, 0.5, 0.5] - not all violated
        assert not status.check_escalation(config)

    def test_persistence_window_default_is_5(self):
        """Default persistence window should be 5 iterations."""
        config = EscalationConfig()
        assert config.persistence_window == 5


class TestPenaltyCalculation:
    """Test penalty calculation scales with tier."""

    def test_no_penalty_when_satisfied(self):
        """Zero violation should produce zero penalty."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint for penalty",
        )

        penalty = calculate_penalty(constraint, status, violation=0.0)
        assert penalty == 0.0

    def test_soft_constraint_penalty(self):
        """Soft constraints have base weight 1e1."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint for penalty",
        )

        # 2mm violation: penalty = 1e1 * (2.0^2) = 40.0
        penalty = calculate_penalty(constraint, status, violation=2.0)
        assert penalty == pytest.approx(40.0)

    def test_strong_constraint_penalty(self):
        """Strong constraints have base weight 1e3."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.STRONG,
            current_tier=ConstraintTier.STRONG,
            violation_history=[],
        )

        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.STRONG,
            because="Test constraint for penalty",
        )

        # 2mm violation: penalty = 1e3 * (2.0^2) = 4000.0
        penalty = calculate_penalty(constraint, status, violation=2.0)
        assert penalty == pytest.approx(4000.0)

    def test_hard_constraint_penalty(self):
        """Hard constraints have base weight 1e6 (effectively infinite)."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.HARD,
            current_tier=ConstraintTier.HARD,
            violation_history=[],
        )

        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.HARD,
            because="Test constraint for penalty",
        )

        # 2mm violation: penalty = 1e6 * (2.0^2) = 4000000.0
        penalty = calculate_penalty(constraint, status, violation=2.0)
        assert penalty == pytest.approx(4_000_000.0)

    def test_quadratic_penalty(self):
        """Penalty should scale quadratically with violation."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.SOFT,
            violation_history=[],
        )

        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint for penalty",
        )

        penalty_1mm = calculate_penalty(constraint, status, violation=1.0)
        penalty_2mm = calculate_penalty(constraint, status, violation=2.0)
        penalty_3mm = calculate_penalty(constraint, status, violation=3.0)

        # Quadratic scaling: 2^2 / 1^2 = 4, 3^2 / 1^2 = 9
        assert penalty_2mm == pytest.approx(4.0 * penalty_1mm)
        assert penalty_3mm == pytest.approx(9.0 * penalty_1mm)

    def test_escalated_constraint_doubles_penalty(self):
        """Escalated constraints get 2x penalty multiplier."""
        status = ConstraintStatus(
            constraint_id="test-1",
            original_tier=ConstraintTier.SOFT,
            current_tier=ConstraintTier.STRONG,  # Escalated!
            violation_history=[],
        )

        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,  # Original tier
            because="Test constraint for penalty",
        )

        # Base penalty for STRONG = 1e3 * (2.0^2) = 4000.0
        # With escalation multiplier = 4000.0 * 2.0 = 8000.0
        penalty = calculate_penalty(constraint, status, violation=2.0)
        assert penalty == pytest.approx(8000.0)


class TestHardConstraintRejection:
    """Test that hard constraint violations reject placement."""

    def test_all_hard_constraints_satisfied(self):
        """Should return True when all hard constraints satisfied."""
        constraint1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.HARD,
            because="Test constraint 1",
            id="c1",
        )

        constraint2 = SeparatedConstraint(
            a="Q3",
            b="Q4",
            min_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test constraint 2",
            id="c2",
        )

        statuses = {
            "c1": ConstraintStatus("c1", ConstraintTier.HARD, ConstraintTier.HARD, []),
            "c2": ConstraintStatus("c2", ConstraintTier.HARD, ConstraintTier.HARD, []),
        }

        violations = {"c1": 0.0, "c2": 0.0}

        passed, failed = check_hard_constraints([constraint1, constraint2], statuses, violations)
        assert passed
        assert failed == []

    def test_hard_constraint_violation_fails(self):
        """Should return False and list failures when hard constraint violated."""
        constraint1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.HARD,
            because="Test constraint 1",
            id="c1",
        )

        constraint2 = SeparatedConstraint(
            a="Q3",
            b="Q4",
            min_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test constraint 2",
            id="c2",
        )

        statuses = {
            "c1": ConstraintStatus("c1", ConstraintTier.HARD, ConstraintTier.HARD, []),
            "c2": ConstraintStatus("c2", ConstraintTier.HARD, ConstraintTier.HARD, []),
        }

        violations = {"c1": 2.5, "c2": 0.0}  # c1 violated by 2.5mm

        passed, failed = check_hard_constraints([constraint1, constraint2], statuses, violations)
        assert not passed
        assert failed == ["c1"]

    def test_soft_constraint_violations_ignored(self):
        """Soft/strong violations should not fail hard constraint check."""
        constraint1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint 1",
            id="c1",
        )

        constraint2 = SeparatedConstraint(
            a="Q3",
            b="Q4",
            min_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test constraint 2",
            id="c2",
        )

        statuses = {
            "c1": ConstraintStatus("c1", ConstraintTier.SOFT, ConstraintTier.SOFT, []),
            "c2": ConstraintStatus("c2", ConstraintTier.HARD, ConstraintTier.HARD, []),
        }

        violations = {"c1": 10.0, "c2": 0.0}  # Soft violated heavily, hard satisfied

        passed, failed = check_hard_constraints([constraint1, constraint2], statuses, violations)
        assert passed  # Soft violations don't fail check
        assert failed == []

    def test_tolerance_for_small_violations(self):
        """Violations < 1e-6 should be considered satisfied (tolerance)."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.HARD,
            because="Test constraint",
            id="c1",
        )

        statuses = {
            "c1": ConstraintStatus("c1", ConstraintTier.HARD, ConstraintTier.HARD, []),
        }

        violations = {"c1": 1e-7}  # Below tolerance

        passed, failed = check_hard_constraints([constraint], statuses, violations)
        assert passed
        assert failed == []


class TestTieredConstraintManager:
    """Test TieredConstraintManager integration."""

    def test_initializes_with_constraints(self):
        """Manager should create status for each constraint."""
        constraint1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint 1",
            id="c1",
        )

        constraint2 = SeparatedConstraint(
            a="Q3",
            b="Q4",
            min_distance_mm=10.0,
            tier=ConstraintTier.STRONG,
            because="Test constraint 2",
            id="c2",
        )

        manager = TieredConstraintManager([constraint1, constraint2], EscalationConfig())

        assert len(manager.statuses) == 2
        assert "c1" in manager.statuses
        assert "c2" in manager.statuses
        assert manager.statuses["c1"].current_tier == ConstraintTier.SOFT
        assert manager.statuses["c2"].current_tier == ConstraintTier.STRONG

    def test_updates_violation_history(self):
        """Manager.update should record violations for each constraint."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint",
            id="c1",
        )

        manager = TieredConstraintManager([constraint], EscalationConfig())

        manager.update({"c1": 2.5})
        assert manager.statuses["c1"].violation_history == [2.5]

        manager.update({"c1": 3.0})
        assert manager.statuses["c1"].violation_history == [2.5, 3.0]

    def test_triggers_escalation_on_update(self):
        """Manager should escalate constraints when threshold exceeded."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint",
            id="c1",
        )

        config = EscalationConfig(severity_thresholds={ConstraintTier.SOFT: 5.0})
        manager = TieredConstraintManager([constraint], config)

        # Large violation triggers escalation
        manager.update({"c1": 7.0})

        assert manager.statuses["c1"].current_tier == ConstraintTier.STRONG
        assert manager.statuses["c1"].is_escalated

    def test_get_penalty_weights_returns_current_tiers(self):
        """get_penalty_weights should return weights based on current tier."""
        constraint1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint 1",
            id="c1",
        )

        constraint2 = SeparatedConstraint(
            a="Q3",
            b="Q4",
            min_distance_mm=10.0,
            tier=ConstraintTier.STRONG,
            because="Test constraint 2",
            id="c2",
        )

        manager = TieredConstraintManager([constraint1, constraint2], EscalationConfig())

        weights = manager.get_penalty_weights()
        assert weights["c1"] == 1e1  # SOFT
        assert weights["c2"] == 1e3  # STRONG

        # Escalate c1
        manager.statuses["c1"].current_tier = ConstraintTier.STRONG

        weights = manager.get_penalty_weights()
        assert weights["c1"] == 1e3  # Now STRONG
        assert weights["c2"] == 1e3  # Still STRONG

    def test_multiple_constraints_escalate_independently(self):
        """Each constraint should escalate independently."""
        constraint1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint 1",
            id="c1",
        )

        constraint2 = AdjacentConstraint(
            a="Q3",
            b="Q4",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint 2",
            id="c2",
        )

        config = EscalationConfig(severity_thresholds={ConstraintTier.SOFT: 5.0})
        manager = TieredConstraintManager([constraint1, constraint2], config)

        # Only c1 violates severely
        manager.update({"c1": 7.0, "c2": 2.0})

        assert manager.statuses["c1"].current_tier == ConstraintTier.STRONG  # Escalated
        assert manager.statuses["c2"].current_tier == ConstraintTier.SOFT  # Not escalated

    def test_ignores_unknown_constraint_ids(self):
        """Manager should gracefully ignore violations for unknown IDs."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            metric=DistanceMetric.EDGE_TO_EDGE,
            tier=ConstraintTier.SOFT,
            because="Test constraint",
            id="c1",
        )

        manager = TieredConstraintManager([constraint], EscalationConfig())

        # Update with unknown ID shouldn't crash
        manager.update({"c1": 2.0, "unknown_id": 5.0})

        assert manager.statuses["c1"].violation_history == [2.0]
        assert "unknown_id" not in manager.statuses


class TestEscalationConfig:
    """Test EscalationConfig default values and behavior."""

    def test_default_severity_thresholds(self):
        """Default config should have reasonable severity thresholds."""
        config = EscalationConfig()
        assert config.severity_thresholds[ConstraintTier.SOFT] == 5.0
        assert config.severity_thresholds[ConstraintTier.STRONG] == 2.0

    def test_default_persistence_window(self):
        """Default persistence window should be 5."""
        config = EscalationConfig()
        assert config.persistence_window == 5

    def test_default_safety_keywords(self):
        """Default config should include common safety keywords."""
        config = EscalationConfig()
        assert "clearance" in config.safety_keywords
        assert "creepage" in config.safety_keywords
        assert "isolation" in config.safety_keywords
        assert "safety" in config.safety_keywords

    def test_custom_config(self):
        """Should support custom config values."""
        config = EscalationConfig(
            severity_thresholds={
                ConstraintTier.SOFT: 10.0,
                ConstraintTier.STRONG: 5.0,
            },
            persistence_window=10,
            safety_keywords=["custom", "keywords"],
        )

        assert config.severity_thresholds[ConstraintTier.SOFT] == 10.0
        assert config.severity_thresholds[ConstraintTier.STRONG] == 5.0
        assert config.persistence_window == 10
        assert config.safety_keywords == ["custom", "keywords"]
