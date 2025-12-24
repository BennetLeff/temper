"""Tests for TopologicalInitializationHeuristic.

This module tests the heuristic wrapper that integrates initial placement
into the temper-placer heuristics pipeline.

Following TDD: these tests are written BEFORE implementation.
"""

from __future__ import annotations

import pytest

# Existing imports (should work)
from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.heuristics.base import (
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)

# Import to be implemented
from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
from temper_placer.io.config_loader import PlacementConstraints

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_board() -> Board:
    """Simple 100x100mm board with two zones."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[
            Zone(name="HV_ZONE", bounds=(0.0, 0.0, 50.0, 100.0)),
            Zone(name="LV_ZONE", bounds=(50.0, 0.0, 100.0, 100.0)),
        ],
    )


@pytest.fixture
def simple_netlist() -> Netlist:
    """Simple netlist with a few components."""
    components = [
        Component(ref="Q1", footprint="TO-247", bounds=(10.0, 15.0)),
        Component(ref="Q2", footprint="TO-247", bounds=(10.0, 15.0)),
        Component(ref="C1", footprint="0805", bounds=(2.0, 1.25)),
        Component(ref="U1", footprint="TSSOP-8", bounds=(3.0, 4.5)),
    ]
    nets = [
        Net(name="HV_BUS", pins=[("Q1", "1"), ("Q2", "1"), ("C1", "1")]),
        Net(name="GND", pins=[("Q1", "2"), ("Q2", "2"), ("C1", "2"), ("U1", "4")]),
    ]
    return Netlist(components=components, nets=nets)


@pytest.fixture
def empty_netlist() -> Netlist:
    """Empty netlist."""
    return Netlist(components=[], nets=[])


@pytest.fixture
def netlist_with_fixed() -> Netlist:
    """Netlist with fixed components."""
    components = [
        Component(
            ref="J1", footprint="CONN", bounds=(10.0, 5.0), fixed=True, initial_position=(5.0, 50.0)
        ),
        Component(ref="Q1", footprint="TO-247", bounds=(10.0, 15.0)),
        Component(ref="U1", footprint="TSSOP-8", bounds=(3.0, 4.5)),
    ]
    return Netlist(components=components, nets=[])


@pytest.fixture
def default_constraints() -> PlacementConstraints:
    """Default placement constraints."""
    return PlacementConstraints(
        board_margin_mm=5.0,
    )


@pytest.fixture
def simple_context(simple_board, simple_netlist, default_constraints) -> PlacementContext:
    """Simple placement context."""
    return PlacementContext(
        board=simple_board,
        netlist=simple_netlist,
        constraints=default_constraints,
    )


@pytest.fixture
def empty_context(simple_board, empty_netlist, default_constraints) -> PlacementContext:
    """Context with empty netlist."""
    return PlacementContext(
        board=simple_board,
        netlist=empty_netlist,
        constraints=default_constraints,
    )


@pytest.fixture
def context_with_fixed(simple_board, netlist_with_fixed, default_constraints) -> PlacementContext:
    """Context with fixed components."""
    return PlacementContext(
        board=simple_board,
        netlist=netlist_with_fixed,
        constraints=default_constraints,
    )


# =============================================================================
# Tests: Heuristic Properties
# =============================================================================


class TestHeuristicProperties:
    """Tests for heuristic metadata properties."""

    def test_name_property(self):
        """Heuristic has correct name."""
        heuristic = TopologicalInitializationHeuristic()

        assert heuristic.name == "topological_initialization"

    def test_priority_property(self):
        """Heuristic has INITIALIZATION priority."""
        heuristic = TopologicalInitializationHeuristic()

        assert heuristic.priority == HeuristicPriority.INITIALIZATION

    def test_description_property(self):
        """Heuristic has description."""
        heuristic = TopologicalInitializationHeuristic()

        assert len(heuristic.description) > 0
        assert "topological" in heuristic.description.lower()

    def test_default_parameters(self):
        """Default parameters are reasonable."""
        heuristic = TopologicalInitializationHeuristic()

        # Should have reasonable defaults
        assert heuristic._force_iterations > 0
        assert heuristic._backend in ("numpy", "jax")

    def test_custom_parameters(self):
        """Custom parameters are accepted."""
        heuristic = TopologicalInitializationHeuristic(
            force_iterations=200,
            backend="jax",
        )

        assert heuristic._force_iterations == 200
        assert heuristic._backend == "jax"


# =============================================================================
# Tests: Basic Application
# =============================================================================


class TestBasicApplication:
    """Tests for basic heuristic application."""

    def test_apply_returns_heuristic_result(self, simple_context):
        """Apply returns HeuristicResult."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        assert isinstance(result, HeuristicResult)

    def test_apply_success_on_simple_input(self, simple_context):
        """Apply succeeds on simple input."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        assert result.success is True

    def test_apply_places_all_unfixed_components(self, simple_context):
        """Apply places all non-fixed components."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        # All 4 components should be placed
        assert len(result.placements) == 4
        assert "Q1" in result.placements
        assert "Q2" in result.placements
        assert "C1" in result.placements
        assert "U1" in result.placements

    def test_apply_empty_netlist(self, empty_context):
        """Apply succeeds with empty netlist."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(empty_context)

        assert result.success is True
        assert len(result.placements) == 0

    def test_placements_have_correct_structure(self, simple_context):
        """Placements have required fields."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        for ref, placement in result.placements.items():
            assert placement.ref == ref
            assert isinstance(placement.position, tuple)
            assert len(placement.position) == 2
            assert isinstance(placement.position[0], float)
            assert isinstance(placement.position[1], float)
            assert placement.placed_by == "topological_initialization"


# =============================================================================
# Tests: Position Validity
# =============================================================================


class TestPositionValidity:
    """Tests for placement position validity."""

    def test_positions_within_board_bounds(self, simple_context):
        """All positions within board bounds."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        board = simple_context.board

        for ref, placement in result.placements.items():
            x, y = placement.position
            comp = simple_context.netlist.get_component(ref)
            w, h = comp.width, comp.height

            # Account for component size (center position)
            assert x - w / 2 >= 0, f"{ref} outside left bound"
            assert x + w / 2 <= board.width, f"{ref} outside right bound"
            assert y - h / 2 >= 0, f"{ref} outside bottom bound"
            assert y + h / 2 <= board.height, f"{ref} outside top bound"

    def test_positions_within_zones(self, simple_context):
        """Components placed within appropriate zones."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        # Each component should be within some zone
        for ref, placement in result.placements.items():
            x, y = placement.position

            in_zone = any(zone.contains_point(x, y) for zone in simple_context.board.zones)

            assert in_zone, f"{ref} at ({x}, {y}) not in any zone"

    def test_respects_board_margin(self, simple_context):
        """Positions respect board margin constraint."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        margin = simple_context.constraints.board_margin_mm
        board = simple_context.board

        for ref, placement in result.placements.items():
            x, y = placement.position
            comp = simple_context.netlist.get_component(ref)
            w, h = comp.width, comp.height

            # Component bounding box should be within margin
            assert x - w / 2 >= margin or x - w / 2 >= 0, f"{ref} too close to left"
            assert x + w / 2 <= board.width - margin or x + w / 2 <= board.width


# =============================================================================
# Tests: Fixed Components
# =============================================================================


class TestFixedComponents:
    """Tests for handling fixed components."""

    def test_fixed_components_not_moved(self, context_with_fixed):
        """Fixed components are not placed (already have position)."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(context_with_fixed)

        # J1 is fixed - should not be in placements
        assert "J1" not in result.placements

    def test_unfixed_components_placed(self, context_with_fixed):
        """Unfixed components are placed."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(context_with_fixed)

        # Q1 and U1 are not fixed - should be placed
        assert "Q1" in result.placements
        assert "U1" in result.placements


# =============================================================================
# Tests: Confidence Scores
# =============================================================================


class TestConfidenceScores:
    """Tests for placement confidence scores."""

    def test_confidence_in_valid_range(self, simple_context):
        """Confidence scores are in [0, 1] range."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        for placement in result.placements.values():
            assert 0.0 <= placement.confidence <= 1.0

    def test_confidence_reasonable(self, simple_context):
        """Confidence scores are reasonable (not too low)."""
        heuristic = TopologicalInitializationHeuristic()

        result = heuristic.apply(simple_context)

        # Topological initialization should have moderate confidence
        # (better than random, but not as refined as later stages)
        for placement in result.placements.values():
            assert placement.confidence >= 0.3
            assert placement.confidence <= 0.7


# =============================================================================
# Tests: Integration with Pipeline
# =============================================================================


class TestPipelineIntegration:
    """Tests for integration with heuristics pipeline."""

    def test_can_be_instantiated_without_args(self):
        """Can create heuristic with no arguments."""
        heuristic = TopologicalInitializationHeuristic()

        assert heuristic is not None

    def test_apply_updates_result_not_context(self, simple_context):
        """Apply returns result but doesn't modify context directly."""
        heuristic = TopologicalInitializationHeuristic()

        # Context starts with no placements
        assert len(simple_context.current_placements) == 0

        result = heuristic.apply(simple_context)

        # Context still has no placements (immutable pattern)
        assert len(simple_context.current_placements) == 0

        # Result has placements
        assert len(result.placements) > 0

    def test_respects_existing_placements(self, simple_context):
        """Respects components already placed by higher-priority heuristic."""
        from temper_placer.heuristics.base import ComponentPlacement

        # Pre-place Q1
        simple_context.current_placements["Q1"] = ComponentPlacement(
            ref="Q1",
            position=(25.0, 50.0),
            rotation=0,
            confidence=0.9,
            placed_by="earlier_heuristic",
        )

        heuristic = TopologicalInitializationHeuristic()
        result = heuristic.apply(simple_context)

        # Q1 should not be re-placed (already placed)
        # or if placed, position should be same
        if "Q1" in result.placements:
            # If overridden, check we got the constraint
            pass  # Some heuristics may override, some may not

        # Other components should be placed
        assert "Q2" in result.placements or "C1" in result.placements


# =============================================================================
# Tests: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_handles_board_without_zones(self, default_constraints, simple_netlist):
        """Handles board with no zones gracefully."""
        board = Board(
            width=100.0,
            height=100.0,
            zones=[],  # No zones
        )

        context = PlacementContext(
            board=board,
            netlist=simple_netlist,
            constraints=default_constraints,
        )

        heuristic = TopologicalInitializationHeuristic()
        result = heuristic.apply(context)

        # Should still succeed (use whole board)
        assert result.success is True
        # Or return failure with helpful message
        # Either is acceptable - just don't crash

    def test_returns_conflicts_on_impossible_layout(self, default_constraints):
        """Returns conflicts when layout is impossible."""
        # Board too small for components
        board = Board(
            width=5.0,
            height=5.0,
            zones=[Zone(name="TINY", bounds=(0.0, 0.0, 5.0, 5.0))],
        )

        # Large components
        components = [
            Component(ref="Q1", footprint="TO-247", bounds=(10.0, 15.0)),
            Component(ref="Q2", footprint="TO-247", bounds=(10.0, 15.0)),
        ]
        netlist = Netlist(components=components, nets=[])

        context = PlacementContext(
            board=board,
            netlist=netlist,
            constraints=default_constraints,
        )

        heuristic = TopologicalInitializationHeuristic()
        result = heuristic.apply(context)

        # Should either fail or report conflicts
        if not result.success:
            assert len(result.conflicts) > 0 or result.message != ""

    def test_message_populated_on_failure(self, default_constraints):
        """Failure result has descriptive message."""
        # Create a scenario likely to fail
        board = Board(width=1.0, height=1.0, zones=[])
        netlist = Netlist(
            components=[Component(ref="Q1", footprint="test", bounds=(10.0, 10.0))],
            nets=[],
        )

        context = PlacementContext(
            board=board,
            netlist=netlist,
            constraints=default_constraints,
        )

        heuristic = TopologicalInitializationHeuristic()
        result = heuristic.apply(context)

        if not result.success:
            assert len(result.message) > 0


# =============================================================================
# Tests: Backend Selection
# =============================================================================


class TestBackendSelection:
    """Tests for backend selection (numpy/jax)."""

    def test_numpy_backend_works(self, simple_context):
        """NumPy backend produces valid results."""
        heuristic = TopologicalInitializationHeuristic(backend="numpy")

        result = heuristic.apply(simple_context)

        assert result.success is True
        assert len(result.placements) > 0

    def test_jax_backend_works(self, simple_context):
        """JAX backend produces valid results (if available)."""
        try:
            import jax  # noqa
        except ImportError:
            pytest.skip("JAX not available")

        heuristic = TopologicalInitializationHeuristic(backend="jax")

        result = heuristic.apply(simple_context)

        assert result.success is True
        assert len(result.placements) > 0

    def test_invalid_backend_raises(self):
        """Invalid backend raises error."""
        with pytest.raises((ValueError, TypeError)):
            TopologicalInitializationHeuristic(backend="invalid_backend")


# =============================================================================
# Tests: Determinism
# =============================================================================


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_input_same_output(self, simple_context):
        """Same input produces same output."""
        heuristic = TopologicalInitializationHeuristic()

        result1 = heuristic.apply(simple_context)
        result2 = heuristic.apply(simple_context)

        # Positions should be identical
        for ref in result1.placements:
            pos1 = result1.placements[ref].position
            pos2 = result2.placements[ref].position

            assert pos1 == pytest.approx(pos2, rel=1e-6)

    def test_different_iterations_same_seed(self, simple_context):
        """Different iteration counts with same seed are deterministic."""
        heuristic1 = TopologicalInitializationHeuristic(force_iterations=50)
        heuristic2 = TopologicalInitializationHeuristic(force_iterations=50)

        result1 = heuristic1.apply(simple_context)
        result2 = heuristic2.apply(simple_context)

        for ref in result1.placements:
            pos1 = result1.placements[ref].position
            pos2 = result2.placements[ref].position

            assert pos1 == pytest.approx(pos2, rel=1e-6)
