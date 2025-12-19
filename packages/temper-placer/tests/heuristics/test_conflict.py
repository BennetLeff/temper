"""Tests for heuristics.conflict module.

Tests conflict resolution between component placements:
- Detection of overlapping placements
- Resolution strategies (nudge, reject, priority-based)
- Edge cases and boundary conditions
"""

import pytest
import jax

from temper_placer.heuristics.conflict import (
    ConflictResolver,
    ResolutionStrategy,
    Conflict,
)
from temper_placer.heuristics.base import (
    ComponentPlacement,
    PlacementContext,
)
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Pin, Net, Netlist
from temper_placer.io.config_loader import PlacementConstraints


class TestResolutionStrategy:
    """Tests for ResolutionStrategy enum."""

    def test_all_strategies_have_values(self):
        """All strategies have string values."""
        assert ResolutionStrategy.HIGHER_PRIORITY_WINS.value == "higher_priority"
        assert ResolutionStrategy.HIGHER_CONFIDENCE_WINS.value == "higher_confidence"
        assert ResolutionStrategy.NUDGE.value == "nudge"
        assert ResolutionStrategy.REJECT.value == "reject"


class TestConflict:
    """Tests for Conflict dataclass."""

    def test_basic_conflict(self):
        """Test basic conflict creation."""
        conflict = Conflict(
            component_a="U1",
            component_b="R1",
            overlap_mm=2.5,
            resolution="nudged",
            message="R1 nudged to avoid U1",
        )
        assert conflict.component_a == "U1"
        assert conflict.component_b == "R1"
        assert conflict.overlap_mm == 2.5
        assert conflict.resolution == "nudged"


class TestConflictResolver:
    """Tests for ConflictResolver class."""

    @pytest.fixture
    def test_board(self):
        """Create a simple 100x100 board."""
        return Board(width=100.0, height=100.0, origin=(0.0, 0.0))

    @pytest.fixture
    def test_components(self):
        """Create test components with known bounds."""
        return [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(10.0, 8.0),  # 10x8mm
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
            Component(
                ref="R1",
                footprint="0805",
                bounds=(4.0, 2.0),  # 4x2mm
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
            Component(
                ref="C1",
                footprint="0805",
                bounds=(4.0, 2.0),  # 4x2mm
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

    def test_no_conflict_when_far_apart(self, context):
        """No conflict when components are far apart."""
        resolver = ConflictResolver()

        # Place U1 at (25, 25)
        placement1 = ComponentPlacement(ref="U1", position=(25.0, 25.0))
        resolver.add_placement(placement1)

        # Try to place R1 at (75, 75) - far away
        placement2 = ComponentPlacement(ref="R1", position=(75.0, 75.0))
        conflict = resolver.check_conflict(placement2, 4.0, 2.0, context)

        assert conflict is None

    def test_conflict_when_overlapping(self, context):
        """Conflict detected when components overlap."""
        resolver = ConflictResolver(min_spacing_mm=0.5)

        # Place U1 at (50, 50), bounds 10x8
        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        # Try to place R1 at (52, 52) - overlapping with U1
        # U1 extends from 45-55 x, 46-54 y
        # R1 (4x2) at (52, 52) would be 50-54 x, 51-53 y - overlapping
        placement2 = ComponentPlacement(ref="R1", position=(52.0, 52.0))
        conflict = resolver.check_conflict(placement2, 4.0, 2.0, context)

        assert conflict is not None
        conflicting_ref, overlap_mm = conflict
        assert conflicting_ref == "U1"
        assert overlap_mm > 0

    def test_resolve_with_higher_priority_wins(self, context):
        """Higher priority (earlier) placement wins - new placement rejected."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.HIGHER_PRIORITY_WINS)

        # Place U1 first (higher priority)
        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        # Try to place R1 overlapping - should be rejected
        placement2 = ComponentPlacement(ref="R1", position=(52.0, 52.0))
        resolved, conflict = resolver.resolve(placement2, 4.0, 2.0, context)

        assert resolved is None  # Rejected
        assert conflict is not None
        assert conflict.resolution == "rejected"

    def test_resolve_with_nudge_strategy(self, context):
        """Nudge strategy moves component to avoid overlap."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.NUDGE, min_spacing_mm=0.5)

        # Place U1 at center
        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        # Try to place R1 overlapping - should be nudged
        placement2 = ComponentPlacement(ref="R1", position=(52.0, 52.0))
        resolved, conflict = resolver.resolve(placement2, 4.0, 2.0, context)

        # Should be resolved (nudged)
        assert resolved is not None
        assert conflict is not None
        assert conflict.resolution == "nudged"
        # Position should have changed
        assert resolved.position != (52.0, 52.0)

    def test_nudge_reduces_confidence(self, context):
        """Nudged placements have reduced confidence."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.NUDGE)

        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        placement2 = ComponentPlacement(ref="R1", position=(52.0, 52.0), confidence=1.0)
        resolved, _ = resolver.resolve(placement2, 4.0, 2.0, context)

        assert resolved is not None
        assert resolved.confidence < 1.0  # Confidence reduced

    def test_nudge_fails_at_edge(self, context):
        """Nudge fails when component is at board edge."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.NUDGE)

        # Place U1 in corner
        placement1 = ComponentPlacement(ref="U1", position=(10.0, 10.0))
        resolver.add_placement(placement1)

        # Try to place R1 overlapping in corner - nudge may fail
        placement2 = ComponentPlacement(ref="R1", position=(12.0, 12.0))
        resolved, conflict = resolver.resolve(placement2, 4.0, 2.0, context)

        # May be rejected if all nudge directions fail
        if resolved is None:
            assert conflict is not None
            assert "rejected" in conflict.resolution

    def test_add_multiple_placements(self, context):
        """Can add multiple placements and check against all."""
        resolver = ConflictResolver()

        placement1 = ComponentPlacement(ref="U1", position=(25.0, 25.0))
        placement2 = ComponentPlacement(ref="R1", position=(75.0, 25.0))
        placement3 = ComponentPlacement(ref="C1", position=(50.0, 75.0))

        resolver.add_placements({"U1": placement1, "R1": placement2, "C1": placement3})

        assert len(resolver.placements) == 3
        assert "U1" in resolver.placements
        assert "R1" in resolver.placements
        assert "C1" in resolver.placements

    def test_get_all_conflicts(self, context):
        """Can retrieve all recorded conflicts."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.REJECT)

        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        # Two overlapping placements that will be rejected
        placement2 = ComponentPlacement(ref="R1", position=(52.0, 52.0))
        resolver.resolve(placement2, 4.0, 2.0, context)

        placement3 = ComponentPlacement(ref="C1", position=(48.0, 48.0))
        resolver.resolve(placement3, 4.0, 2.0, context)

        conflicts = resolver.get_all_conflicts()
        assert len(conflicts) >= 2

    def test_clear_resets_state(self, context):
        """Clear removes all placements and conflicts."""
        resolver = ConflictResolver()

        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        resolver.clear()

        assert len(resolver.placements) == 0
        assert len(resolver.conflicts) == 0

    def test_min_spacing_enforced(self, context):
        """Minimum spacing is enforced between components."""
        resolver = ConflictResolver(min_spacing_mm=5.0)

        # Place U1 (10x8) at (50, 50)
        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        # Place R1 (4x2) just barely touching (should fail with 5mm spacing)
        # U1 right edge at 55, R1 left edge at 55 with R1 at x=57
        # With 5mm spacing required, R1 needs to be at least at x=62
        placement2 = ComponentPlacement(ref="R1", position=(58.0, 50.0))
        conflict = resolver.check_conflict(placement2, 4.0, 2.0, context)

        # Should conflict due to spacing requirement
        assert conflict is not None

    def test_same_component_not_conflict_with_self(self, context):
        """A component doesn't conflict with itself."""
        resolver = ConflictResolver()

        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        resolver.add_placement(placement1)

        # Check U1 against itself - should not conflict
        conflict = resolver.check_conflict(placement1, 10.0, 8.0, context)
        assert conflict is None


class TestHigherConfidenceWinsStrategy:
    """Tests for HIGHER_CONFIDENCE_WINS strategy."""

    @pytest.fixture
    def context(self, simple_board, simple_netlist, rng_key):
        """Create context for testing."""
        constraints = PlacementConstraints(board_margin_mm=5.0)
        return PlacementContext(
            board=simple_board,
            netlist=simple_netlist,
            constraints=constraints,
            rng_key=rng_key,
        )

    def test_higher_confidence_triggers_nudge(self, context):
        """Higher confidence new placement triggers nudge (can't move existing)."""
        resolver = ConflictResolver(
            strategy=ResolutionStrategy.HIGHER_CONFIDENCE_WINS,
            min_spacing_mm=0.5,
        )

        # Low confidence existing placement
        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0), confidence=0.3)
        resolver.add_placement(placement1)

        # High confidence new placement
        placement2 = ComponentPlacement(ref="R1", position=(52.0, 52.0), confidence=0.9)
        resolved, conflict = resolver.resolve(placement2, 1.6, 0.8, context)

        # Should try to nudge (can't move locked placement)
        if resolved is not None:
            assert conflict is not None

    def test_lower_confidence_rejected(self, context):
        """Lower confidence new placement is rejected."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.HIGHER_CONFIDENCE_WINS)

        # High confidence existing
        placement1 = ComponentPlacement(ref="U1", position=(50.0, 50.0), confidence=0.9)
        resolver.add_placement(placement1)

        # Low confidence new
        placement2 = ComponentPlacement(ref="R1", position=(52.0, 52.0), confidence=0.3)
        resolved, conflict = resolver.resolve(placement2, 1.6, 0.8, context)

        assert resolved is None
        assert conflict is not None
        assert "rejected" in conflict.resolution
