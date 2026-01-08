"""
Tests for ConstraintCompiler - converting declarative constraints to executable functions.

Part of temper-g54c.2: Constraint compilation for deterministic placement.
"""

from unittest.mock import Mock

import pytest

from temper_placer.constraints.compiler import ConstraintCompiler, ValidationError
from temper_placer.io.config_loader import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)


class TestSlotFilter:
    """Tests for compile_to_slot_filter() - hard constraints."""

    def test_filter_accepts_valid_slot(self):
        """Filter should accept slot with no violations."""
        constraints = PlacementConstraints()
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        assert filter_fn((50, 50), "U_MCU", {}) is True

    def test_filter_rejects_hard_spacing_violation(self):
        """Filter should reject slot too close to another component."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="A",
                    component_b="B",
                    min_separation_mm=10.0,
                    # Note: No tier field - all spacing rules are hard constraints
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"A": (0.0, 0.0)}

        # Too close - should reject
        assert filter_fn((5.0, 0.0), "B", placements) is False

        # Far enough - should accept
        assert filter_fn((15.0, 0.0), "B", placements) is True

    def test_filter_ignores_soft_spacing_rules(self):
        """Filter should always check spacing (no soft/hard distinction yet)."""
        # Skip this test - ComponentSpacingRule doesn't have tier yet
        # All spacing rules are treated as hard constraints
        pytest.skip("ComponentSpacingRule doesn't support tier yet")

    def test_filter_rejects_hard_escape_clearance_violation(self):
        """Filter should reject slot in hard escape clearance zone."""
        constraints = PlacementConstraints(
            escape_clearances=[
                EscapeClearance(
                    component="U_MCU",
                    clearance_mm=10.0,
                    tier="hard",
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"U_MCU": (0.0, 0.0)}

        # Inside clearance zone - reject
        assert filter_fn((5.0, 0.0), "C1", placements) is False

        # Outside clearance zone - accept
        assert filter_fn((15.0, 0.0), "C1", placements) is True

    def test_filter_ignores_soft_escape_clearance(self):
        """Filter should NOT reject soft escape clearance violations."""
        constraints = PlacementConstraints(
            escape_clearances=[
                EscapeClearance(
                    component="U_MCU",
                    clearance_mm=10.0,
                    tier="soft",
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"U_MCU": (0.0, 0.0)}

        # Inside clearance but soft - accept
        assert filter_fn((5.0, 0.0), "C1", placements) is True

    def test_filter_rejects_hard_corridor_violation(self):
        """Filter should reject slot in hard keep-clear corridor."""
        constraints = PlacementConstraints(
            routing_corridors=[
                RoutingCorridor(
                    name="usb_path",
                    from_component="J_USB",
                    to_component="U_MCU",
                    width_mm=6.0,
                    keep_clear=True,
                    tier="hard",
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        placements = {"J_USB": (0.0, 0.0), "U_MCU": (20.0, 0.0)}

        # In the middle of corridor (perpendicular distance < 3mm)
        assert filter_fn((10.0, 2.0), "C1", placements) is False

        # Far from corridor
        assert filter_fn((10.0, 10.0), "C1", placements) is True

    def test_filter_handles_missing_corridor_endpoints(self):
        """Filter should not crash when corridor endpoints not placed yet."""
        constraints = PlacementConstraints(
            routing_corridors=[
                RoutingCorridor(
                    name="test",
                    from_component="A",
                    to_component="B",
                    width_mm=5.0,
                    tier="hard",
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        filter_fn = compiler.compile_to_slot_filter()

        # A not placed yet - should accept (no corridor to check)
        assert filter_fn((10.0, 10.0), "C", {}) is True

        # Only A placed - should accept
        assert filter_fn((10.0, 10.0), "C", {"A": (0.0, 0.0)}) is True


class TestSlotScorer:
    """Tests for compile_to_slot_scorer() - soft constraints."""

    def test_scorer_returns_zero_for_perfect_slot(self):
        """Scorer should return 0 for slot with no violations."""
        constraints = PlacementConstraints()
        compiler = ConstraintCompiler(constraints)
        scorer = compiler.compile_to_slot_scorer()

        score = scorer((50.0, 50.0), "U_MCU", {})
        assert score == 0.0

    def test_scorer_penalizes_proximity_violation(self):
        """Scorer should penalize components far from their group."""
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
                        )
                    ],
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        scorer = compiler.compile_to_slot_scorer()

        placements = {"A": (0.0, 0.0)}

        # Close - low penalty
        close_score = scorer((5.0, 0.0), "B", placements)

        # Far - high penalty
        far_score = scorer((50.0, 0.0), "B", placements)

        assert far_score > close_score
        assert close_score == 0.0  # Within max_distance
        assert far_score > 0.0  # Violation

    def test_scorer_penalizes_thermal_edge_violation(self):
        """Scorer should penalize thermal components far from edge."""
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            thermal_constraints=[
                ThermalConstraint(
                    components=["MOSFET"],
                    prefer_edge=True,
                    max_distance_from_edge_mm=10.0,
                )
            ],
        )
        compiler = ConstraintCompiler(constraints, board_bounds=(0, 0, 100, 100))
        scorer = compiler.compile_to_slot_scorer()

        # Near edge - low penalty
        edge_score = scorer((5.0, 50.0), "MOSFET", {})

        # Center of board - high penalty
        center_score = scorer((50.0, 50.0), "MOSFET", {})

        assert center_score > edge_score
        assert edge_score == 0.0  # Within max_distance
        assert center_score > 0.0  # Too far from edge

    def test_scorer_penalizes_group_spread(self):
        """Scorer should penalize components far from group centroid."""
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="decoupling",
                    components=["C1", "C2", "C3"],
                    max_spread_mm=20.0,
                    weight=1.0,
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        scorer = compiler.compile_to_slot_scorer()

        placements = {"C1": (0.0, 0.0), "C2": (5.0, 0.0)}

        # Close to centroid (2.5, 0)
        close_score = scorer((3.0, 0.0), "C3", placements)

        # Far from centroid
        far_score = scorer((50.0, 0.0), "C3", placements)

        assert far_score > close_score

    def test_scorer_penalizes_soft_spacing_violation(self):
        """Scorer should penalize spacing violations (weight acts as penalty multiplier)."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="A",
                    component_b="B",
                    min_separation_mm=10.0,
                    weight=2.0,
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        scorer = compiler.compile_to_slot_scorer()

        placements = {"A": (0.0, 0.0)}

        # Too close - penalty
        close_score = scorer((5.0, 0.0), "B", placements)

        # Far enough - no penalty
        far_score = scorer((15.0, 0.0), "B", placements)

        assert close_score > far_score
        assert far_score == 0.0
        assert close_score > 0.0

    def test_scorer_penalizes_soft_escape_clearance(self):
        """Scorer should penalize soft escape clearance violations."""
        constraints = PlacementConstraints(
            escape_clearances=[
                EscapeClearance(
                    component="U_MCU",
                    clearance_mm=10.0,
                    tier="soft",
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)
        scorer = compiler.compile_to_slot_scorer()

        placements = {"U_MCU": (0.0, 0.0)}

        # Inside escape zone - penalty
        inside_score = scorer((5.0, 0.0), "C1", placements)

        # Outside escape zone - no penalty
        outside_score = scorer((15.0, 0.0), "C1", placements)

        assert inside_score > outside_score
        assert inside_score == 50.0  # Fixed penalty
        assert outside_score == 0.0


class TestValidation:
    """Tests for validate() - constraint sanity checks."""

    def test_validate_catches_missing_escape_component(self):
        """Validation should catch escape clearance for non-existent component."""
        constraints = PlacementConstraints(escape_clearances=[EscapeClearance(component="TYPO")])
        compiler = ConstraintCompiler(constraints)

        netlist = Mock()
        netlist.components = [Mock(ref="U_MCU"), Mock(ref="U_GATE")]

        errors = compiler.validate(None, netlist)

        assert len(errors) == 1
        assert errors[0].constraint_type == "EscapeClearance"
        assert "TYPO" in errors[0].message
        assert "not found" in errors[0].message

    def test_validate_suggests_similar_component(self):
        """Validation should suggest similar component names."""
        constraints = PlacementConstraints(
            escape_clearances=[EscapeClearance(component="U_MC")]  # Missing U
        )
        compiler = ConstraintCompiler(constraints)

        netlist = Mock()
        netlist.components = [Mock(ref="U_MCU"), Mock(ref="U_GATE")]

        errors = compiler.validate(None, netlist)

        assert len(errors) == 1
        assert errors[0].suggestion is not None
        assert "U_MCU" in errors[0].suggestion

    def test_validate_catches_missing_corridor_components(self):
        """Validation should catch corridors with non-existent endpoints."""
        constraints = PlacementConstraints(
            routing_corridors=[
                RoutingCorridor(
                    name="test",
                    from_component="MISSING_A",
                    to_component="MISSING_B",
                    width_mm=5.0,
                )
            ]
        )
        compiler = ConstraintCompiler(constraints)

        netlist = Mock()
        netlist.components = [Mock(ref="U_MCU")]

        errors = compiler.validate(None, netlist)

        assert len(errors) == 2
        assert any("from_component" in e.message for e in errors)
        assert any("to_component" in e.message for e in errors)

    def test_validate_catches_invalid_zone_assignment(self):
        """Validation should catch zone assignments to undefined zones."""
        constraints = PlacementConstraints(zone_assignments={"U_MCU": "UNDEFINED_ZONE"})
        compiler = ConstraintCompiler(constraints)

        netlist = Mock()
        netlist.components = [Mock(ref="U_MCU")]

        errors = compiler.validate(None, netlist)

        assert len(errors) == 1
        assert "Zone" in errors[0].message
        assert "UNDEFINED_ZONE" in errors[0].message

    def test_validate_passes_valid_constraints(self):
        """Validation should pass for correct constraints."""
        from temper_placer.core.board import Zone

        constraints = PlacementConstraints(
            zones=[Zone(name="Signal", bounds=(0, 0, 100, 100))],
            escape_clearances=[EscapeClearance(component="U_MCU")],
            routing_corridors=[
                RoutingCorridor(
                    name="test",
                    from_component="U_MCU",
                    to_component="U_GATE",
                    width_mm=5.0,
                )
            ],
            zone_assignments={"U_MCU": "Signal"},
        )
        compiler = ConstraintCompiler(constraints)

        netlist = Mock()
        netlist.components = [Mock(ref="U_MCU"), Mock(ref="U_GATE")]

        errors = compiler.validate(None, netlist)

        assert len(errors) == 0


class TestHelperMethods:
    """Tests for internal helper methods."""

    def test_distance_calculation(self):
        """Test Euclidean distance calculation."""
        compiler = ConstraintCompiler(PlacementConstraints())

        dist = compiler._distance((0.0, 0.0), (3.0, 4.0))
        assert dist == 5.0

    def test_centroid_calculation(self):
        """Test centroid computation."""
        compiler = ConstraintCompiler(PlacementConstraints())

        points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        centroid = compiler._centroid(points)

        assert centroid == (5.0, 5.0)

    def test_centroid_empty_list(self):
        """Centroid of empty list should be origin."""
        compiler = ConstraintCompiler(PlacementConstraints())

        centroid = compiler._centroid([])
        assert centroid == (0.0, 0.0)

    def test_min_edge_distance(self):
        """Test minimum distance to board edge."""
        compiler = ConstraintCompiler(
            PlacementConstraints(board_width_mm=100, board_height_mm=100),
            board_bounds=(0, 0, 100, 100),
        )

        # Corner
        assert compiler._min_edge_distance((5.0, 5.0)) == 5.0

        # Center
        assert compiler._min_edge_distance((50.0, 50.0)) == 50.0

        # Near left edge
        assert compiler._min_edge_distance((3.0, 50.0)) == 3.0

    def test_point_to_segment_distance(self):
        """Test point-to-line-segment distance."""
        compiler = ConstraintCompiler(PlacementConstraints())

        # Point perpendicular to segment midpoint
        dist = compiler._point_to_segment_distance(
            (5.0, 5.0),  # Point
            (0.0, 0.0),  # Segment start
            (10.0, 0.0),  # Segment end
        )
        assert dist == 5.0

        # Point beyond segment endpoint
        dist = compiler._point_to_segment_distance(
            (15.0, 0.0),  # Point
            (0.0, 0.0),  # Segment start
            (10.0, 0.0),  # Segment end
        )
        assert dist == 5.0

    def test_find_similar_component(self):
        """Test fuzzy component name matching."""
        compiler = ConstraintCompiler(PlacementConstraints())

        options = {"U_MCU", "U_GATE", "C1", "R5"}

        # Prefix match
        assert compiler._find_similar("U_MC", options) == "U_MCU"

        # Suffix match
        assert compiler._find_similar("X_GATE", options) == "U_GATE"

        # No match
        assert compiler._find_similar("MISSING", options) is None


class TestValidationErrorFormatting:
    """Tests for ValidationError string formatting."""

    def test_basic_error_format(self):
        """Test basic error message formatting."""
        error = ValidationError(
            constraint_type="Test",
            message="Something went wrong",
        )

        assert "Test: Something went wrong" in str(error)

    def test_error_with_component(self):
        """Test error message with component reference."""
        error = ValidationError(
            constraint_type="Test",
            message="Invalid component",
            component="U_MCU",
        )

        s = str(error)
        assert "Test:" in s
        assert "Invalid component" in s
        assert "U_MCU" in s

    def test_error_with_suggestion(self):
        """Test error message with suggestion."""
        error = ValidationError(
            constraint_type="Test",
            message="Component not found",
            component="U_MC",
            suggestion="Did you mean: U_MCU?",
        )

        s = str(error)
        assert "→" in s
        assert "Did you mean: U_MCU?" in s
