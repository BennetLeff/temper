"""Tests for heuristics.base module.

Tests the base classes and data structures for the placement heuristics system:
- HeuristicPriority enum ordering
- ComponentPlacement dataclass
- HeuristicResult merging
- PlacementContext validation helpers
- Heuristic abstract base class
"""

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.io.config_loader import PlacementConstraints


class TestHeuristicPriority:
    """Tests for HeuristicPriority enum."""

    def test_priority_ordering(self):
        """Hard constraints have lowest value (highest priority)."""
        assert HeuristicPriority.HARD < HeuristicPriority.STRUCTURAL
        assert HeuristicPriority.STRUCTURAL < HeuristicPriority.ORGANIZATIONAL
        assert HeuristicPriority.ORGANIZATIONAL < HeuristicPriority.STYLE
        assert HeuristicPriority.STYLE < HeuristicPriority.FILL

    def test_priority_values(self):
        """Priority values are sequential integers."""
        assert HeuristicPriority.HARD == 0
        assert HeuristicPriority.STRUCTURAL == 1
        assert HeuristicPriority.ORGANIZATIONAL == 2
        assert HeuristicPriority.STYLE == 3
        assert HeuristicPriority.FILL == 4

    def test_sortable_by_priority(self):
        """Heuristics can be sorted by priority."""
        priorities = [
            HeuristicPriority.STYLE,
            HeuristicPriority.HARD,
            HeuristicPriority.FILL,
            HeuristicPriority.STRUCTURAL,
        ]
        sorted_priorities = sorted(priorities)
        assert sorted_priorities == [
            HeuristicPriority.HARD,
            HeuristicPriority.STRUCTURAL,
            HeuristicPriority.STYLE,
            HeuristicPriority.FILL,
        ]


class TestComponentPlacement:
    """Tests for ComponentPlacement dataclass."""

    def test_basic_placement(self):
        """Test basic placement properties."""
        placement = ComponentPlacement(
            ref="U1",
            position=(10.0, 20.0),
            rotation=1,
            confidence=0.9,
            placed_by="test_heuristic",
        )
        assert placement.ref == "U1"
        assert placement.position == (10.0, 20.0)
        assert placement.rotation == 1
        assert placement.confidence == 0.9
        assert placement.placed_by == "test_heuristic"

    def test_default_values(self):
        """Test default values for optional fields."""
        placement = ComponentPlacement(ref="R1", position=(0.0, 0.0))
        assert placement.rotation == 0
        assert placement.confidence == 1.0
        assert placement.placed_by == ""


class TestHeuristicResult:
    """Tests for HeuristicResult dataclass."""

    def test_empty_result(self):
        """Test empty result defaults."""
        result = HeuristicResult()
        assert result.placements == {}
        assert result.conflicts == []
        assert result.success is True
        assert result.message == ""

    def test_result_with_placements(self):
        """Test result with placements."""
        placement = ComponentPlacement(ref="U1", position=(10.0, 20.0))
        result = HeuristicResult(
            placements={"U1": placement},
            success=True,
            message="Placed 1 component",
        )
        assert "U1" in result.placements
        assert result.message == "Placed 1 component"

    def test_merge_results(self):
        """Test merging two results."""
        placement1 = ComponentPlacement(ref="U1", position=(10.0, 20.0))
        result1 = HeuristicResult(
            placements={"U1": placement1},
            conflicts=["conflict1"],
            message="First",
        )

        placement2 = ComponentPlacement(ref="R1", position=(30.0, 40.0))
        result2 = HeuristicResult(
            placements={"R1": placement2},
            conflicts=["conflict2"],
            message="Second",
        )

        merged = result1.merge(result2)
        assert "U1" in merged.placements
        assert "R1" in merged.placements
        assert len(merged.conflicts) == 2
        assert "First" in merged.message
        assert "Second" in merged.message

    def test_merge_overwrites_same_component(self):
        """Later result overwrites same component placement."""
        placement1 = ComponentPlacement(ref="U1", position=(10.0, 20.0))
        result1 = HeuristicResult(placements={"U1": placement1})

        placement2 = ComponentPlacement(ref="U1", position=(99.0, 99.0))
        result2 = HeuristicResult(placements={"U1": placement2})

        merged = result1.merge(result2)
        assert merged.placements["U1"].position == (99.0, 99.0)


class TestPlacementContext:
    """Tests for PlacementContext dataclass."""

    @pytest.fixture
    def test_board(self):
        """Create a simple 100x100 board."""
        return Board(width=100.0, height=100.0, origin=(0.0, 0.0))

    @pytest.fixture
    def test_components(self):
        """Create test components."""
        return [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5.0, 4.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
            Component(
                ref="R1",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
            Component(
                ref="C1",
                footprint="0805",
                bounds=(2.0, 1.25),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
        ]

    @pytest.fixture
    def test_netlist(self, test_components):
        """Create test netlist."""
        nets = [Net("NET1", [("U1", "1"), ("R1", "1"), ("C1", "1")])]
        return Netlist(components=test_components, nets=nets)

    @pytest.fixture
    def test_constraints(self):
        """Create test constraints."""
        return PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=5.0,
        )

    @pytest.fixture
    def context(self, test_board, test_netlist, test_constraints, rng_key):
        """Create a placement context for testing."""
        return PlacementContext(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            current_placements={},
            rng_key=rng_key,
        )

    def test_get_unplaced_components(self, context):
        """Test getting unplaced components."""
        unplaced = context.get_unplaced_components()
        assert len(unplaced) == 3
        refs = [c.ref for c in unplaced]
        assert "U1" in refs
        assert "R1" in refs
        assert "C1" in refs

    def test_get_unplaced_excludes_placed(self, context):
        """Placed components are excluded from unplaced list."""
        context.current_placements["U1"] = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        unplaced = context.get_unplaced_components()
        assert len(unplaced) == 2
        refs = [c.ref for c in unplaced]
        assert "U1" not in refs

    def test_get_placed_refs(self, context):
        """Test getting placed component refs."""
        assert context.get_placed_refs() == set()

        context.current_placements["U1"] = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        context.current_placements["R1"] = ComponentPlacement(ref="R1", position=(60.0, 60.0))
        assert context.get_placed_refs() == {"U1", "R1"}

    def test_is_position_valid_within_bounds(self, context):
        """Valid position within board bounds."""
        # Center of board, small component - should be valid
        assert context.is_position_valid(50.0, 50.0, 5.0, 5.0)

    def test_is_position_valid_respects_margin(self, context):
        """Position too close to edge is invalid."""
        # margin is 5mm, component half-width is 2.5mm
        # At x=5 with half_width=2.5, left edge would be at 2.5, violating 5mm margin
        assert not context.is_position_valid(5.0, 50.0, 5.0, 5.0)

    def test_is_position_valid_outside_bounds(self, context):
        """Position outside board is invalid."""
        assert not context.is_position_valid(-10.0, 50.0, 5.0, 5.0)
        assert not context.is_position_valid(110.0, 50.0, 5.0, 5.0)

    def test_check_overlap_no_overlap(self, context):
        """No overlap when components are far apart."""
        context.current_placements["U1"] = ComponentPlacement(ref="U1", position=(25.0, 25.0))
        # R1 at (75, 75) won't overlap with U1 at (25, 25)
        assert not context.check_overlap(75.0, 75.0, 1.6, 0.8)

    def test_check_overlap_with_overlap(self, context):
        """Overlap detected when components intersect."""
        context.current_placements["U1"] = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        # Placing another component at same position should overlap
        assert context.check_overlap(50.0, 50.0, 5.0, 5.0)

    def test_check_overlap_excludes_refs(self, context):
        """Excluded refs are not considered for overlap."""
        context.current_placements["U1"] = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        # Same position but excluding U1 - no overlap
        assert not context.check_overlap(50.0, 50.0, 5.0, 5.0, exclude_refs={"U1"})


class TestHeuristicAbstractClass:
    """Tests for the abstract Heuristic base class."""

    def test_must_implement_all_abstract_methods(self):
        """Heuristic subclass must implement all abstract methods."""
        # We test this indirectly by verifying a valid implementation works
        # and that the abstract class cannot be instantiated directly
        with pytest.raises(TypeError):
            Heuristic()  # type: ignore[abstract]

    def test_valid_heuristic_implementation(self):
        """Valid heuristic implementation works."""

        class GoodHeuristic(Heuristic):
            @property
            def name(self):
                return "good_heuristic"

            @property
            def priority(self):
                return HeuristicPriority.STRUCTURAL

            @property
            def description(self):
                return "A good test heuristic"

            def apply(self, _context):
                return HeuristicResult(success=True, message="Applied successfully")

        h = GoodHeuristic()
        assert h.name == "good_heuristic"
        assert h.priority == HeuristicPriority.STRUCTURAL
        assert h.description == "A good test heuristic"

    def test_default_description_is_empty(self):
        """Default description returns empty string."""

        class MinimalHeuristic(Heuristic):
            @property
            def name(self):
                return "minimal"

            @property
            def priority(self):
                return HeuristicPriority.FILL

            def apply(self, _context):
                return HeuristicResult()

        h = MinimalHeuristic()
        assert h.description == ""

    def test_identify_target_components_default(self, simple_board, simple_netlist, rng_key):
        """Default identify_target_components returns all unplaced."""

        class TestHeuristic(Heuristic):
            @property
            def name(self):
                return "test"

            @property
            def priority(self):
                return HeuristicPriority.FILL

            def apply(self, _context):
                return HeuristicResult()

        constraints = PlacementConstraints()
        context = PlacementContext(
            board=simple_board,
            netlist=simple_netlist,
            constraints=constraints,
            rng_key=rng_key,
        )

        h = TestHeuristic()
        targets = h.identify_target_components(context)
        assert len(targets) == 3  # All components from simple_netlist fixture
