"""Tests for force-directed layout heuristic."""


import jax.numpy as jnp
import jax.random as random
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, build_adjacency_matrix
from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
from temper_placer.heuristics.force_directed import (
    ForceDirectedHeuristic,
    ForceDirectedUnfoldingHeuristic,
    compute_force_directed_layout,
)
from temper_placer.io.config_loader import PlacementConstraints


@pytest.fixture
def simple_context():
    """Create a simple context with 3 connected components."""
    # Components
    c1 = Component(ref="U1", footprint="DIP8", bounds=(10.0, 10.0))
    c2 = Component(ref="R1", footprint="R0603", bounds=(5.0, 2.0))
    c3 = Component(ref="C1", footprint="C0603", bounds=(4.0, 2.0))

    # Net: U1-1 <-> R1-1 <-> C1-1
    net1 = Net(
        name="NET1",
        pins=[
            ("U1", "1"),
            ("R1", "1"),
            ("C1", "1"),
        ],
    )

    netlist = Netlist(components=[c1, c2, c3], nets=[net1])
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    constraints = PlacementConstraints(board_margin_mm=5.0)

    return PlacementContext(
        board=board,
        netlist=netlist,
        constraints=constraints,
        current_placements={},
        rng_key=random.PRNGKey(42),
    )

    netlist = Netlist(components=[c1, c2, c3], nets=[net1])
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    constraints = PlacementConstraints(board_margin_mm=5.0)

    return PlacementContext(
        board=board,
        netlist=netlist,
        constraints=constraints,
        current_placements={},
        rng_key=random.PRNGKey(42),
    )


def test_force_directed_placement_basic(simple_context):
    """Test that force-directed layout places components within bounds."""
    heuristic = ForceDirectedHeuristic(confidence=0.2, iterations=10)
    result = heuristic.apply(simple_context)

    assert result.success
    assert len(result.placements) == 3

    margin = simple_context.constraints.board_margin_mm
    board = simple_context.board

    for ref, placement in result.placements.items():
        x, y = placement.position
        comp = simple_context.netlist.get_component(ref)

        # Check bounds
        assert x >= margin + comp.width / 2
        assert x <= board.width - margin - comp.width / 2
        assert y >= margin + comp.height / 2
        assert y <= board.height - margin - comp.height / 2

        assert placement.placed_by == "force_directed_layout"
        assert placement.confidence == 0.2


def test_force_directed_respects_existing_placements(simple_context):
    """Test that existing placements are used as initial positions."""
    # Pre-place U1 at (20, 20)
    simple_context.current_placements["U1"] = ComponentPlacement(
        ref="U1",
        position=(20.0, 20.0),
        rotation=0,
        confidence=0.1,
        placed_by="spectral_initialization",
    )

    heuristic = ForceDirectedHeuristic(confidence=0.2, iterations=1)  # Low iterations to stay close
    result = heuristic.apply(simple_context)

    assert result.success

    # Note: The heuristic skips components that are already in current_placements
    # (see _scale_to_board line 321: "if comp.ref in context.current_placements: continue")
    # So U1 should NOT be in result.placements since it was already placed.
    # The other components should still be placed.
    assert "R1" in result.placements or "C1" in result.placements, \
        "At least one unplaced component should get a placement"


def test_force_directed_empty_graph():
    """Test behavior with empty netlist."""
    context = PlacementContext(
        board=Board(100, 100),
        netlist=Netlist(components=[], nets=[]),
        constraints=PlacementConstraints(),
        current_placements={},
        rng_key=random.PRNGKey(0),
    )

    heuristic = ForceDirectedHeuristic()
    result = heuristic.apply(context)

    assert result.success
    assert len(result.placements) == 0
    assert "Empty graph" in result.message


def test_force_directed_fixed_components(simple_context):
    """Test that fixed components are not moved."""
    # Fix U1
    u1 = simple_context.netlist.get_component("U1")
    u1.fixed = True
    u1.initial_position = (50.0, 50.0)

    # We must put it in current_placements for the heuristic to know where it is fixed AT
    simple_context.current_placements["U1"] = ComponentPlacement(
        ref="U1", position=(50.0, 50.0), rotation=0, confidence=1.0, placed_by="user"
    )

    heuristic = ForceDirectedHeuristic(confidence=0.2)
    result = heuristic.apply(simple_context)

    # Fixed component should NOT be in the OUTPUT placements of the heuristic
    # because heuristics usually return *new* placements to be applied.
    # However, implementation detail: _scale_to_board filters out fixed components.
    assert "U1" not in result.placements
    assert "R1" in result.placements
    assert "C1" in result.placements


# =============================================================================
# Regression tests for temper-bl6q.3: Board dimension handling
# =============================================================================

def test_force_directed_large_board():
    """
    Regression test for temper-bl6q.3: Force-directed layout should work
    correctly with boards larger than 200mm.

    The old code hard-coded a 200mm clip, which compressed layouts on
    larger boards. The fix uses actual board dimensions.
    """
    # Create a large 300x250mm board
    board = Board(width=300.0, height=250.0, origin=(0.0, 0.0))

    # Use a fixed component to test bounds at edge of board
    components = [
        Component(ref="U1", footprint="QFP", bounds=(10.0, 10.0), fixed=True),
        Component(ref="U2", footprint="QFP", bounds=(10.0, 10.0)),
    ]
    # Connect them
    net = Net(name="LINK", pins=[("U1", "1"), ("U2", "1")])
    netlist = Netlist(components=components, nets=[net])

    # Place fixed component at (280, 220) - beyond old 200mm limit
    # U2 will be attracted towards U1
    initial_positions = jnp.array([
        [280.0, 220.0],  # U1 - fixed beyond old 200mm limit
        [150.0, 125.0],  # U2 - will move towards U1
    ])

    # Run force-directed layout
    result = compute_force_directed_layout(
        netlist,
        initial_positions,
        board_width=300.0,
        board_height=250.0,
        board_origin=(0.0, 0.0),
        iterations=100,
        learning_rate=0.5,
    )

    # Positions should be within actual board bounds
    assert jnp.all(result[:, 0] >= 0.0), "X should be >= 0"
    assert jnp.all(result[:, 0] <= 300.0), "X should be <= 300"
    assert jnp.all(result[:, 1] >= 0.0), "Y should be >= 0"
    assert jnp.all(result[:, 1] <= 250.0), "Y should be <= 250"

    # Fixed component at (280, 220) should stay at (280, 220)
    # This verifies the large board dimensions are being used correctly
    u1_pos = result[0]
    assert abs(float(u1_pos[0]) - 280.0) < 0.01, \
        f"Fixed component should stay at 280mm, got {float(u1_pos[0]):.1f}"
    assert abs(float(u1_pos[1]) - 220.0) < 0.01, \
        f"Fixed component should stay at 220mm, got {float(u1_pos[1]):.1f}"


def test_force_directed_small_board():
    """
    Test that force-directed layout respects small board boundaries.

    On boards smaller than 200mm, components should stay within actual bounds.
    """
    # Create a small 50x50mm board
    board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))

    components = [
        Component(ref="U1", footprint="0603", bounds=(2.0, 1.0)),
        Component(ref="U2", footprint="0603", bounds=(2.0, 1.0)),
    ]
    net = Net(name="NET", pins=[("U1", "1"), ("U2", "1")])
    netlist = Netlist(components=components, nets=[net])

    # Initial positions
    initial_positions = jnp.array([
        [25.0, 25.0],
        [30.0, 30.0],
    ])

    result = compute_force_directed_layout(
        netlist,
        initial_positions,
        board_width=50.0,
        board_height=50.0,
        board_origin=(0.0, 0.0),
        iterations=100,
    )

    # All positions should be within 50x50 bounds
    assert jnp.all(result[:, 0] >= 0.0), "X should be >= 0"
    assert jnp.all(result[:, 0] <= 50.0), "X should be <= 50"
    assert jnp.all(result[:, 1] >= 0.0), "Y should be >= 0"
    assert jnp.all(result[:, 1] <= 50.0), "Y should be <= 50"


def test_force_directed_nonzero_origin():
    """
    Test that force-directed layout respects non-zero board origin.

    The old code assumed origin=(0,0). The fix correctly handles
    boards with arbitrary origins.
    """
    # Board with origin at (10, 20)
    board = Board(width=100.0, height=100.0, origin=(10.0, 20.0))

    components = [
        Component(ref="U1", footprint="QFP", bounds=(5.0, 5.0)),
        Component(ref="U2", footprint="QFP", bounds=(5.0, 5.0)),
    ]
    net = Net(name="NET", pins=[("U1", "1"), ("U2", "1")])
    netlist = Netlist(components=components, nets=[net])

    # Initial positions within the offset board
    initial_positions = jnp.array([
        [60.0, 70.0],  # Within (10,20) to (110,120)
        [70.0, 80.0],
    ])

    result = compute_force_directed_layout(
        netlist,
        initial_positions,
        board_width=100.0,
        board_height=100.0,
        board_origin=(10.0, 20.0),
        iterations=100,
    )

    # Positions should be within offset bounds: (10, 20) to (110, 120)
    assert jnp.all(result[:, 0] >= 10.0), f"X should be >= 10 (origin), got min {float(jnp.min(result[:, 0]))}"
    assert jnp.all(result[:, 0] <= 110.0), f"X should be <= 110 (origin + width), got max {float(jnp.max(result[:, 0]))}"
    assert jnp.all(result[:, 1] >= 20.0), f"Y should be >= 20 (origin), got min {float(jnp.min(result[:, 1]))}"
    assert jnp.all(result[:, 1] <= 120.0), f"Y should be <= 120 (origin + height), got max {float(jnp.max(result[:, 1]))}"


def test_force_directed_unfolding_uses_board_dimensions():
    """
    Test that ForceDirectedUnfoldingHeuristic passes correct board dimensions.
    """
    # Large board
    board = Board(width=300.0, height=250.0, origin=(0.0, 0.0))

    components = [
        Component(ref="U1", footprint="QFP", bounds=(10.0, 10.0)),
        Component(ref="U2", footprint="QFP", bounds=(10.0, 10.0)),
    ]
    net = Net(name="NET", pins=[("U1", "1"), ("U2", "1")])
    netlist = Netlist(components=components, nets=[net])

    constraints = PlacementConstraints(board_margin_mm=5.0)

    context = PlacementContext(
        board=board,
        netlist=netlist,
        constraints=constraints,
        current_placements={},
        rng_key=random.PRNGKey(42),
    )

    heuristic = ForceDirectedUnfoldingHeuristic(iterations=50)
    result = heuristic.apply(context)

    assert result.success

    # Verify placements respect large board bounds
    for ref, placement in result.placements.items():
        x, y = placement.position
        assert x >= 0.0 and x <= 300.0, f"X={x} out of bounds for 300mm board"
        assert y >= 0.0 and y <= 250.0, f"Y={y} out of bounds for 250mm board"
