
from temper_placer.routing.maze_router import GridCell, MazeRouter


def test_via_cost_increases_layer_change_cost():
    """
    GIVEN a router with via_cost=5.0
    WHEN computing cost from cell (5,5,layer=0) to (5,5,layer=1)
    THEN cost should be 1.0 (base) + 5.0 (via) = 6.0
    """
    router = MazeRouter(grid_size=(100, 100), via_cost=5.0)

    current = GridCell(5, 5, 0)
    neighbor = GridCell(5, 5, 1)  # Same position, different layer

    cost = router._get_neighbor_cost(current, neighbor)

    assert cost == 6.0, f'Expected 6.0, got {cost}'

def test_same_layer_movement_base_cost():
    """
    GIVEN a router with via_cost=5.0
    WHEN computing cost from (5,5,0) to (6,5,0) (same layer)
    THEN cost should be 1.0 (base cost only)
    """
    router = MazeRouter(grid_size=(100, 100), via_cost=5.0)

    current = GridCell(5, 5, 0)
    neighbor = GridCell(6, 5, 0)  # Adjacent, same layer

    cost = router._get_neighbor_cost(current, neighbor)

    assert cost == 1.0, f'Expected 1.0, got {cost}'

def test_high_via_cost_prefers_same_layer_detour():
    """
    GIVEN start and end on same layer with obstacle between
    AND via_cost=10.0 (high)
    WHEN pathfinding is performed
    THEN path should go around obstacle on same layer (not via over)
    
    Setup:
    S . . X . . E    (S=start, E=end, X=obstacle, layer 0)
    . . . . . . .    (layer 1 is clear)
    
    With high via cost, should prefer: S -> down -> around -> up -> E
    Not: S -> via -> over obstacle -> via -> E
    """
    router = MazeRouter(grid_size=(20, 20), num_layers=2, via_cost=10.0)

    # Block rect at (3, 0) size 1x5 on layer 0
    router.block_rect(3, 0, 1, 5, layer=0)

    path = router.find_path(
        start=(0, 0),
        end=(6, 0),
        layer=0,
        allow_layer_change=True
    )

    assert path is not None, "Path should be found"

    # Count vias in path
    via_count = sum(1 for i in range(len(path)-1) if path[i].layer != path[i+1].layer)

    assert via_count == 0, f'Expected 0 vias (go around), got {via_count}'

def test_low_via_cost_allows_layer_change():
    """
    GIVEN same setup as Test 3 but via_cost=0.5 (low)
    WHEN pathfinding is performed
    THEN path may use vias (shorter total distance)
    """
    router = MazeRouter(grid_size=(20, 20), num_layers=2, via_cost=0.5)

    # Block larger obstacle to make detour expensive
    router.block_rect(3, 0, 1, 5, layer=0)

    path = router.find_path(
        start=(0, 0),
        end=(6, 0),
        layer=0,
        allow_layer_change=True
    )

    assert path is not None, "Path should be found"

    via_count = sum(1 for i in range(len(path)-1) if path[i].layer != path[i+1].layer)
    path_length = len(path)

    # With low via cost and large obstacle, vias should be used
    # Path with 2 vias: 0->via->over->via->6 = ~8 cells (cost: 8 + 2*0.5 = 9)
    # Path around: 0->down5->right->up5->6 = ~18 cells (cost: 18)
    assert via_count >= 2, f'Expected vias to be used, got {via_count}'
