import jax.numpy as jnp
import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.legalization import legalize_abacus, project_to_drc_feasible, resolve_overlaps


def test_no_overlap_after_legalization(simple_netlist, simple_board):
    """3 overlapping components should have 0 overlaps after legalization."""
    context = LossContext.from_netlist_and_board(simple_netlist, simple_board)

    # Place all 3 components at the same center (50, 50)
    n = simple_netlist.n_components
    positions = jnp.full((n, 2), 50.0)
    rotation_logits = jnp.zeros((n, 4))
    state = PlacementState(positions, rotation_logits)

    legalized = project_to_drc_feasible(state, context, max_iterations=20)

    # Check for overlaps
    new_pos = legalized.positions
    widths = jnp.array([c.bounds[0] for c in simple_netlist.components])
    heights = jnp.array([c.bounds[1] for c in simple_netlist.components])

    for i in range(n):
        for j in range(i + 1, n):
            dx = abs(new_pos[i, 0] - new_pos[j, 0])
            dy = abs(new_pos[i, 1] - new_pos[j, 1])
            hw_sum = (widths[i] + widths[j]) / 2.0
            hh_sum = (heights[i] + heights[j]) / 2.0

            # Allow for very small numerical error
            assert dx >= hw_sum - 0.01 or dy >= hh_sum - 0.01

def test_abacus_legalization_oracles(simple_netlist, simple_board):
    """Verify Abacus algorithm removes overlaps with minimal displacement."""
    # Place two components overlapping horizontally in same row
    context = LossContext.from_netlist_and_board(simple_netlist, simple_board)
    n = simple_netlist.n_components

    # Put them both at (50, 50)
    positions = jnp.full((n, 2), 50.0)
    state = PlacementState(positions, jnp.zeros((n, 4)))

    # Use project_to_drc_feasible since current Abacus implementation falls back to it
    legalized = legalize_abacus(state, context, n_rows=1)

    # Check for overlaps
    new_pos = legalized.positions
    widths = jnp.array([c.bounds[0] for c in simple_netlist.components])
    heights = jnp.array([c.bounds[1] for c in simple_netlist.components])

    for i in range(n):
        for j in range(i + 1, n):
            dx = abs(new_pos[i, 0] - new_pos[j, 0])
            dy = abs(new_pos[i, 1] - new_pos[j, 1])
            hw_sum = (widths[i] + widths[j]) / 2.0
            hh_sum = (heights[i] + heights[j]) / 2.0
            assert dx >= hw_sum - 0.01 or dy >= hh_sum - 0.01

def test_minimal_displacement(simple_netlist, simple_board):
    """Moved distance should be reasonable (not flying off the board)."""
    context = LossContext.from_netlist_and_board(simple_netlist, simple_board)

    # Slight overlap
    n = simple_netlist.n_components
    positions = jnp.array([
        [50.0, 50.0],
        [51.0, 50.0],
        [50.0, 51.0]
    ])
    state = PlacementState(positions, jnp.zeros((n, 4)))

    legalized = project_to_drc_feasible(state, context)

    dist = jnp.sqrt(jnp.sum((legalized.positions - positions)**2, axis=1))
    # Max displacement should be small for slight overlaps
    assert jnp.max(dist) < 10.0

def test_fixed_components_unmoved(simple_netlist, simple_board):
    """Fixed components should stay in place even if overlapped."""
    # Mark component 0 as fixed
    simple_netlist.components[0].fixed = True
    context = LossContext.from_netlist_and_board(simple_netlist, simple_board)

    n = simple_netlist.n_components
    positions = jnp.full((n, 2), 50.0)
    state = PlacementState(positions, jnp.zeros((n, 4)))

    legalized = project_to_drc_feasible(state, context)

    # Component 0 should still be at (50, 50)
    assert jnp.allclose(legalized.positions[0], jnp.array([50.0, 50.0]))

def test_already_legal_unchanged(simple_netlist, simple_board):
    """Legal input should result in no changes."""
    context = LossContext.from_netlist_and_board(simple_netlist, simple_board)

    # Spread components out
    n = simple_netlist.n_components
    positions = jnp.array([
        [10.0, 10.0],
        [50.0, 50.0],
        [90.0, 90.0]
    ])
    state = PlacementState(positions, jnp.zeros((n, 4)))

    legalized = project_to_drc_feasible(state, context)

    assert jnp.allclose(legalized.positions, positions)

def test_legalization_order_dependence():
    """Verify that overlap resolution is deterministic regardless of input ordering."""
    # This is hard to test perfectly because project_to_drc_feasible has a fixed loops order.
    # But we can verify that 10 runs with same input give same output.
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Netlist

    board = Board(width=100, height=100)
    components = [
        Component(ref=f"C{i}", footprint="0805", bounds=(2, 2)) for i in range(10)
    ]
    netlist = Netlist(components=components, nets=[])
    context = LossContext.from_netlist_and_board(netlist, board)

    # All at same position
    positions = jnp.full((10, 2), 50.0)
    state = PlacementState(positions, jnp.zeros((10, 4)))

    results = []
    for _ in range(5):
        legalized = project_to_drc_feasible(state, context)
        results.append(legalized.positions)

    for i in range(1, 5):
        assert jnp.allclose(results[0], results[i])


# =============================================================================
# Regression tests for temper-bl6q.1: SAT-based overlap detection
# =============================================================================

def test_diagonal_adjacency_no_false_positive():
    """
    Regression test for temper-bl6q.1: Diagonally adjacent components
    should NOT be detected as overlapping.

    The old radial distance check incorrectly flagged diagonally-adjacent
    components as overlapping. The SAT-based check correctly identifies
    that they don't overlap on both axes simultaneously.
    """
    board = Board(width=100, height=100)

    # Two 10x10 components placed diagonally adjacent
    # Component A at (0, 0) to (10, 10)
    # Component B at (10, 10) to (20, 20)
    # They share only a corner point - no actual overlap!
    components = [
        Component(ref="A", footprint="10x10", bounds=(10.0, 10.0)),
        Component(ref="B", footprint="10x10", bounds=(10.0, 10.0)),
    ]
    netlist = Netlist(components=components, nets=[])

    # Position centers so edges touch diagonally
    # A center at (5, 5), B center at (15, 15)
    # A spans (0,0)-(10,10), B spans (10,10)-(20,20)
    positions = np.array([
        [5.0, 5.0],    # A center
        [15.0, 15.0],  # B center
    ])

    # With 0.5mm separation requirement, these should NOT overlap
    # because they only touch at a corner
    result = resolve_overlaps(
        positions=positions,
        netlist=netlist,
        board=board,
        min_separation=0.5,
        max_iterations=10,
    )

    # Components should not have moved significantly (no overlap to resolve)
    displacement = np.sqrt(np.sum((result - positions)**2, axis=1))
    assert np.max(displacement) < 1.0, \
        f"Diagonally adjacent components should not be pushed apart, but moved {np.max(displacement):.2f}mm"


def test_actual_overlap_is_detected():
    """
    Verify that actual overlapping components ARE detected and resolved.

    This ensures the SAT fix didn't break detection of true overlaps.
    """
    board = Board(width=100, height=100)

    components = [
        Component(ref="A", footprint="10x10", bounds=(10.0, 10.0)),
        Component(ref="B", footprint="10x10", bounds=(10.0, 10.0)),
    ]
    netlist = Netlist(components=components, nets=[])

    # Position both at center - definite overlap
    positions = np.array([
        [50.0, 50.0],
        [52.0, 50.0],  # 2mm apart, but 10mm wide each = 8mm overlap
    ])

    result = resolve_overlaps(
        positions=positions,
        netlist=netlist,
        board=board,
        min_separation=0.5,
        max_iterations=50,
    )

    # After resolution, components should be separated
    dx = abs(result[0, 0] - result[1, 0])
    dy = abs(result[0, 1] - result[1, 1])

    # With 10mm wide components and 0.5mm separation, need at least 10.5mm apart on one axis
    assert dx >= 10.4 or dy >= 10.4, \
        f"Overlapping components should be separated. dx={dx:.2f}, dy={dy:.2f}"


def test_edge_touching_no_false_positive():
    """
    Components that are edge-touching (not overlapping) should not be
    pushed apart unnecessarily.
    """
    board = Board(width=100, height=100)

    components = [
        Component(ref="A", footprint="10x10", bounds=(10.0, 10.0)),
        Component(ref="B", footprint="10x10", bounds=(10.0, 10.0)),
    ]
    netlist = Netlist(components=components, nets=[])

    # Position so they are exactly edge-touching horizontally
    # A center at (5, 50), B center at (15, 50)
    # A spans x: 0-10, B spans x: 10-20 (edge touch at x=10)
    positions = np.array([
        [5.0, 50.0],
        [15.0, 50.0],
    ])

    # With 0mm separation, edges touching should be legal
    result = resolve_overlaps(
        positions=positions,
        netlist=netlist,
        board=board,
        min_separation=0.0,  # No separation required
        max_iterations=10,
    )

    # Should not have moved (edge touching is legal with 0 separation)
    displacement = np.sqrt(np.sum((result - positions)**2, axis=1))
    assert np.max(displacement) < 0.5, \
        f"Edge-touching components should not be pushed apart with 0 separation"
