import pytest
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid, build_occupancy_grid
from temper_placer.router_v6.astar_pathfinding import (
    _mark_route_blocked, _unmark_route_blocked, RoutePath3D
)

def test_pad_erasure_during_ripup():
    """
    TDD Test: Verify that ripping up a route preserves the pad's static blocking.
    """
    # Create a small grid
    grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((10, 10), dtype=np.int16),
        origin=(0.0, 0.0),
        cell_size=1.0,
        width_cells=10,
        height_cells=10
    )
    
    # 1. Setup: Mark (5,5) as a static obstacle (-1)
    grid.grid[5, 5] = -1
    # Initialize static_mask
    grid.static_mask = (grid.grid == -1)
    
    grids = {"F.Cu": grid}
    
    # 2. Simulate Routing: Net 10 occupies (5,5) and (6,5)
    grid.grid[5, 5] = 10
    grid.grid[5, 6] = 10 # Adjacent cell
    
    # 3. Simulate Rip-up: Unmark the route
    route = RoutePath3D(
        net_name="Net1",
        # Segment from cell (5,5) center to (6,5) center
        segments=[(5.5, 5.5, "F.Cu"), (6.5, 5.5, "F.Cu")],
        via_positions=[],
        path_length=1.0, via_count=0, forced_segment_count=0
    )
    
    # Trace width and clearance don't matter much for this point-matching test
    # but we'll use small values to target specific cells
    _unmark_route_blocked(route, grids, trace_width=0.1, clearance=0.1, net_id=10)
    
    # 4. ASSERT: 
    # (5,5) should be RESTORED to -1 (it was in static_mask)
    # (6,5) should be set to 0 (it was NOT in static_mask)
    assert grid.grid[5, 5] == -1, f"Pad at (5,5) was ERASED to {grid.grid[5, 5]}!"
    assert grid.grid[5, 6] == 0, f"Ordinary cell at (6,5) was NOT cleared (remained {grid.grid[5, 6]})!"

if __name__ == "__main__":
    test_pad_erasure_during_ripup()
    print("Success!")
