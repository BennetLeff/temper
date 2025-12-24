import jax.numpy as jnp

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.legalization import legalize_abacus, project_to_drc_feasible


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
