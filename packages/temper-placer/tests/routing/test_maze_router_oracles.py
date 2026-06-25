import jax.numpy as jnp

from temper_placer.routing.maze_router import GridCell, MazeRouter

# =============================================================================
# temper-1w8u.1: Level 0: GridCell arithmetic oracles
# =============================================================================

def test_gridcell_equality_reflexive():
    """Verify GridCell equality."""
    c1 = GridCell(10, 20, 0)
    c2 = GridCell(10, 20, 0)
    c3 = GridCell(10, 20, 1)
    c4 = GridCell(11, 20, 0)

    assert c1 == c2
    assert c1 != c3
    assert c1 != c4
    assert c1 == c1

def test_gridcell_hash_consistency():
    """Verify GridCell hashing."""
    c1 = GridCell(10, 20, 0)
    c2 = GridCell(10, 20, 0)

    # Same cells must have same hash
    assert hash(c1) == hash(c2)

    # Store in set
    s = {c1, c2}
    assert len(s) == 1

def test_neighbors_returns_exactly_4_cardinal():
    """Verify neighbor computation (MazeRouter._get_neighbors)."""
    # Note: _get_neighbors is an internal method of MazeRouter
    router = MazeRouter(grid_size=(10, 10))
    cell = GridCell(5, 5, 0)

    # On a single layer, empty grid, should have 4 neighbors
    neighbors = router._get_neighbors(cell)
    assert len(neighbors) == 4

    # Check coords
    coords = {(n.x, n.y) for n in neighbors}
    assert coords == {(5, 6), (5, 4), (6, 5), (4, 5)}

def test_neighbors_with_layers():
    """Verify neighbors including layer transitions."""
    router = MazeRouter(grid_size=(10, 10), num_layers=2)
    cell = GridCell(5, 5, 0)

    # allow_layer_change=True should add layer 1 neighbor
    neighbors = router._get_neighbors(cell, allow_layer_change=True)
    assert len(neighbors) == 5 # 4 cardinal + 1 via

    layers = {n.layer for n in neighbors}
    assert 0 in layers
    assert 1 in layers

# =============================================================================
# temper-1w8u.2: Level 1: A* on empty grid oracles
# =============================================================================

def test_straight_line_horizontal():
    """3x1 grid, exactly 3 cells."""
    router = MazeRouter(grid_size=(3, 3))
    start = (0, 1)
    end = (2, 1)

    path = router.find_path(start, end)
    assert path is not None
    assert len(path) == 3
    assert path[0] == GridCell(0, 1, 0)
    assert path[1] == GridCell(1, 1, 0)
    assert path[2] == GridCell(2, 1, 0)

def test_straight_line_vertical():
    """1x3 grid, exactly 3 cells."""
    router = MazeRouter(grid_size=(3, 3))
    start = (1, 0)
    end = (1, 2)

    path = router.find_path(start, end)
    assert path is not None
    assert len(path) == 3
    assert path[0] == GridCell(1, 0, 0)
    assert path[1] == GridCell(1, 1, 0)
    assert path[2] == GridCell(1, 2, 0)

def test_diagonal_manhattan():
    """3x3 corner to corner, exactly 5 cells."""
    router = MazeRouter(grid_size=(3, 3))
    start = (0, 0)
    end = (2, 2)

    path = router.find_path(start, end)
    assert path is not None
    # Manhattan distance 2+2=4, so path length is 5 cells (inclusive)
    assert len(path) == 5

def test_same_start_goal():
    """Returns single cell when start == goal."""
    router = MazeRouter(grid_size=(3, 3))
    start = (1, 1)
    end = (1, 1)

    path = router.find_path(start, end)
    assert path is not None
    assert len(path) == 1
    assert path[0] == GridCell(1, 1, 0)

# =============================================================================
# temper-1w8u.3: Level 2: A* with single obstacle oracles
# =============================================================================

def test_obstacle_forces_one_step_detour():
    """Verify path goes around a single obstacle."""
    router = MazeRouter(grid_size=(5, 5))
    start = (0, 2)
    end = (4, 2)

    # Block (2, 2) which is on the straight line
    router.occupancy = router.occupancy.at[2, 2, 0].set(1)

    path = router.find_path(start, end)
    assert path is not None
    # Straight path would be (0,2)-(1,2)-(2,2)-(3,2)-(4,2) - 5 cells
    # With (2,2) blocked, must detour to (2,1) or (2,3)
    # New path: (0,2)-(1,2)-(1,1)-(2,1)-(3,1)-(3,2)-(4,2) - wait, simplified:
    # (0,2)-(1,2)-(2,3)-(3,2)-(4,2) is not possible in 4-connectivity
    # (0,2)-(1,2)-(1,3)-(2,3)-(3,3)-(3,2)-(4,2) - 7 cells
    assert len(path) == 7
    assert GridCell(2, 2, 0) not in path

def test_obstacle_blocks_only_path_returns_none():
    """Verify returns None when path is impossible."""
    router = MazeRouter(grid_size=(3, 3))
    start = (0, 1)
    end = (2, 1)

    # Block entire column 1
    router.occupancy = router.occupancy.at[1, :, 0].set(1)

    path = router.find_path(start, end)
    assert path is None

def test_obstacle_at_start_returns_none():
    """Verify returns None if start cell is blocked."""
    router = MazeRouter(grid_size=(3, 3))
    start = (1, 1)
    end = (2, 2)

    router.occupancy = router.occupancy.at[1, 1, 0].set(1)
    path = router.find_path(start, end)
    assert path is None

def test_obstacle_at_goal_returns_none():

    """Verify returns None if goal cell is blocked."""

    router = MazeRouter(grid_size=(3, 3))

    start = (0, 0)

    end = (1, 1)



    router.occupancy = router.occupancy.at[1, 1, 0].set(1)

    path = router.find_path(start, end)

    assert path is None



# =============================================================================

# temper-1w8u.6: Level 4: Escape route oracles

# =============================================================================



def test_pin_escapes_perpendicular():

    """Verify that a pin on component edge escapes perpendicularly."""


    from temper_placer.core.netlist import Component, Pin



    # 10x10 board, 1mm cells

    router = MazeRouter(grid_size=(10, 10))

    # 4x4 component at center (5,5)

    comp = Component(ref="U1", footprint="SOIC", bounds=(4, 4), pins=[

        Pin("1", "1", (2, 0)) # Right edge

    ])



    # Block component

    positions = jnp.array([[5.0, 5.0]])

    router.block_components([comp], positions, margin=0.0, escape_length=3)



    # Pin is at (7, 5)

    # Escape direction should be (1, 0)

    # Check if cells (7,5), (8,5), (9,5) are free

    assert int(router.occupancy[7, 5, 0]) == 0

    assert int(router.occupancy[8, 5, 0]) == 0

    assert int(router.occupancy[9, 5, 0]) == 0



    # Check that a cell deep inside component is still blocked

    assert int(router.occupancy[5, 5, 0]) == -1



def test_corner_pin_escapes():

    """Verify corner pin escape."""

    from temper_placer.core.netlist import Component, Pin



    router = MazeRouter(grid_size=(10, 10))

    comp = Component(ref="U1", footprint="SOIC", bounds=(4, 4), pins=[

        Pin("1", "1", (2, 2)) # Top-right corner

    ])



    positions = jnp.array([[5.0, 5.0]])

    # Pin absolute: (7, 7)

    # Escape length 2

    router.block_components([comp], positions, margin=0.0, escape_length=2)



    # Direction: outward from center. dx=2, dy=2. Primary is vertical (abs(dx)==abs(dy))

    # Wait, current implementation: if abs(dx) >= abs(dy), step_x=1, step_y=0.

    assert int(router.occupancy[7, 7, 0]) == 0

    assert int(router.occupancy[8, 7, 0]) == 0



# =============================================================================
# temper-1w8u.7: Level 5: Multi-net routing oracles
# =============================================================================

def test_two_parallel_nets_both_succeed():
    """Verify that two parallel nets can both be routed."""
    from temper_placer.routing.layer_assignment import Layer, LayerAssignment

    router = MazeRouter(grid_size=(10, 10))
    # Net 1: (1,1) to (8,1)
    # Net 2: (1,3) to (8,3)

    assign = LayerAssignment("N1", Layer.L1_TOP, {Layer.L1_TOP})

    res1 = router.route_net("N1", [(1.0, 1.0), (8.0, 1.0)], assign)
    res2 = router.route_net("N2", [(1.0, 3.0), (8.0, 3.0)], assign)

    assert res1.success
    assert res2.success
    # Check that paths don't overlap
    cells1 = set(res1.cells)
    cells2 = set(res2.cells)
    assert cells1.isdisjoint(cells2)

def test_crossing_nets_one_uses_via():
    """Verify that crossing nets use different layers if available."""
    from temper_placer.routing.layer_assignment import Layer, LayerAssignment

    router = MazeRouter(grid_size=(5, 5), num_layers=2)
    # Net 1: (0,2) to (4,2) - horizontal
    # Net 2: (2,0) to (2,4) - vertical, crossing at (2,2)

    # N1 restricted to TOP
    assign1 = LayerAssignment("N1", Layer.L1_TOP, {Layer.L1_TOP})
    # N2 allowed to use BOTTOM
    assign2 = LayerAssignment("N2", Layer.L1_TOP, {Layer.L1_TOP, Layer.L4_BOT})

    res1 = router.route_net("N1", [(0.0, 2.0), (4.0, 2.0)], assign1)
    res2 = router.route_net("N2", [(2.0, 0.0), (2.0, 4.0)], assign2)

    assert res1.success
    assert res2.success
    assert res2.via_count > 0 # Must have used a via to cross N1


