"""Integration tests for existing constraints working in deterministic pipeline.

This module tests that ComponentSpacingRule and ProximityRule work correctly
with the tier system (hard/soft) when integrated with ConstraintCompiler.
"""

from temper_placer.constraints.compiler import ConstraintCompiler
from temper_placer.io.config_loader import (
    ComponentGroup,
    ComponentSpacingRule,
    PlacementConstraints,
    ProximityRule,
)


class TestComponentSpacingRuleIntegration:
    """Test ComponentSpacingRule with tier system."""

    def test_hard_spacing_rule_rejects_close_slots(self):
        """Hard ComponentSpacingRule should reject slots too close."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="Q1",
                    component_b="Q2",
                    min_separation_mm=15.0,
                    tier="hard",
                    description="Thermal isolation between MOSFETs",
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"Q1": (0.0, 0.0)}

        # Too close (10mm) - should reject
        assert filter_fn((10.0, 0.0), "Q2", placements) is False

        # Just at boundary (15mm) - should accept
        assert filter_fn((15.0, 0.0), "Q2", placements) is True

        # Far enough (20mm) - should accept
        assert filter_fn((20.0, 0.0), "Q2", placements) is True

    def test_soft_spacing_rule_penalizes_close_slots(self):
        """Soft ComponentSpacingRule should penalize close slots but not reject."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="U_15V",
                    component_b="U_3V3",
                    min_separation_mm=10.0,
                    tier="soft",
                    description="Prefer spacing between regulators",
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()
        scorer = compiler.compile_to_slot_scorer()

        placements = {"U_15V": (0.0, 0.0)}

        # Soft constraint - filter should accept all slots
        assert filter_fn((5.0, 0.0), "U_3V3", placements) is True
        assert filter_fn((10.0, 0.0), "U_3V3", placements) is True
        assert filter_fn((20.0, 0.0), "U_3V3", placements) is True

        # But scorer should penalize close slots
        penalty_close = scorer((5.0, 0.0), "U_3V3", placements)
        penalty_boundary = scorer((10.0, 0.0), "U_3V3", placements)
        penalty_far = scorer((20.0, 0.0), "U_3V3", placements)

        # Close slot should have highest penalty
        assert penalty_close > penalty_boundary
        # Far slot should have zero penalty
        assert penalty_far == 0.0

    def test_default_tier_is_soft(self):
        """ComponentSpacingRule without tier should default to soft."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="A",
                    component_b="B",
                    min_separation_mm=10.0,
                    # No tier specified - should default to "soft"
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"A": (0.0, 0.0)}

        # Should accept (soft constraint doesn't filter)
        assert filter_fn((5.0, 0.0), "B", placements) is True


class TestProximityRuleIntegration:
    """Test ProximityRule with tier system."""

    def test_hard_proximity_rule_rejects_far_slots(self):
        """Hard ProximityRule should reject slots too far away."""
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="gate_drive",
                    components=["U_GATE", "Q1"],
                    proximity_rules=[
                        ProximityRule(
                            component_a="U_GATE",
                            component_b="Q1",
                            max_distance_mm=8.0,
                            tier="hard",
                            description="Gate driver must be close to MOSFET",
                        )
                    ],
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"U_GATE": (0.0, 0.0)}

        # Too far (10mm) - should reject
        assert filter_fn((10.0, 0.0), "Q1", placements) is False

        # Just at boundary (8mm) - should accept
        assert filter_fn((8.0, 0.0), "Q1", placements) is True

        # Close enough (5mm) - should accept
        assert filter_fn((5.0, 0.0), "Q1", placements) is True

    def test_soft_proximity_rule_penalizes_far_slots(self):
        """Soft ProximityRule should penalize far slots but not reject."""
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="decoupling",
                    components=["C1", "C2"],
                    proximity_rules=[
                        ProximityRule(
                            component_a="C1",
                            component_b="C2",
                            max_distance_mm=20.0,
                            tier="soft",
                            description="Prefer keeping caps close",
                        )
                    ],
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()
        scorer = compiler.compile_to_slot_scorer()

        placements = {"C1": (0.0, 0.0)}

        # Soft constraint - filter should accept all slots
        assert filter_fn((10.0, 0.0), "C2", placements) is True
        assert filter_fn((20.0, 0.0), "C2", placements) is True
        assert filter_fn((30.0, 0.0), "C2", placements) is True

        # But scorer should penalize far slots
        penalty_close = scorer((10.0, 0.0), "C2", placements)
        penalty_boundary = scorer((20.0, 0.0), "C2", placements)
        penalty_far = scorer((30.0, 0.0), "C2", placements)

        # Far slot should have highest penalty
        assert penalty_far > penalty_boundary
        assert penalty_boundary > penalty_close
        # Close slot (within limit) should have zero penalty
        assert penalty_close == 0.0

    def test_default_tier_is_soft_for_proximity(self):
        """ProximityRule without tier should default to soft."""
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="test",
                    components=["A", "B"],
                    proximity_rules=[
                        ProximityRule(
                            component_a="A",
                            component_b="B",
                            max_distance_mm=10.0,
                            # No tier specified - should default to "soft"
                        )
                    ],
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"A": (0.0, 0.0)}

        # Should accept (soft constraint doesn't filter)
        assert filter_fn((15.0, 0.0), "B", placements) is True


class TestMixedHardAndSoftConstraints:
    """Test scenarios with both hard and soft constraints."""

    def test_hard_and_soft_constraints_together(self):
        """System should handle mix of hard and soft constraints correctly."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                # Hard: Must be separated
                ComponentSpacingRule(
                    component_a="Q1",
                    component_b="Q2",
                    min_separation_mm=15.0,
                    tier="hard",
                ),
                # Soft: Prefer separation
                ComponentSpacingRule(
                    component_a="U1",
                    component_b="U2",
                    min_separation_mm=10.0,
                    tier="soft",
                ),
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()
        scorer = compiler.compile_to_slot_scorer()

        placements = {"Q1": (0.0, 0.0), "U1": (50.0, 0.0)}

        # Hard constraint should reject
        assert filter_fn((10.0, 0.0), "Q2", placements) is False

        # Soft constraint should accept but penalize
        assert filter_fn((55.0, 0.0), "U2", placements) is True
        penalty = scorer((55.0, 0.0), "U2", placements)
        assert penalty > 0.0

    def test_backwards_compatibility(self):
        """Old configs without tier field should still work (default to soft)."""
        # Simulate old config by omitting tier
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="A",
                    component_b="B",
                    min_separation_mm=10.0,
                    # No tier - should default to soft
                )
            ],
            component_groups=[
                ComponentGroup(
                    name="test",
                    components=["C", "D"],
                    proximity_rules=[
                        ProximityRule(
                            component_a="C",
                            component_b="D",
                            max_distance_mm=10.0,
                            # No tier - should default to soft
                        )
                    ],
                )
            ],
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        # Both should be soft (accept everything)
        placements = {"A": (0.0, 0.0), "C": (50.0, 0.0)}
        assert filter_fn((5.0, 0.0), "B", placements) is True  # Spacing violation but soft
        assert filter_fn((65.0, 0.0), "D", placements) is True  # Proximity violation but soft
