import pytest
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.astar_pathfinding import (
    _unblock_net_pads
)

def test_unblock_blindness_shorts_neighbor():
    """
    TDD Test: Prove that surgical unblocking correctly preserves neighbor obstacles.
    """
    # Grid with two pads 0.5mm apart (center-to-center)
    grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((50, 50), dtype=np.int16),
        origin=(0.0, 0.0),
        cell_size=0.05,
        width_cells=50,
        height_cells=50
    )
    
    # Net 1 Pad at (1.0, 1.0), Radius 0.1
    # Net 2 (GND) Pad at (1.5, 1.0), Radius 0.1
    for px, py in [(1.0, 1.0), (1.5, 1.0)]:
        cx, cy = grid.world_to_grid(px, py)
        # Block a 3x3 area to simulate Pad + inflation
        grid.grid[cy-2:cy+3, cx-2:cx+3] = -1
        
    pad_centers = {
        "Net1": [(1.0, 1.0, 0.1, "F.Cu")],
    }
    
    # Unblock Net 1.
    grids = {"F.Cu": grid}
    _unblock_net_pads("Net1", pad_centers, grids)
    
    # EXPECTATION: Net 2's pad area at (1.5, 1.0) should STILL be blocked (-1).
    cx2, cy2 = grid.world_to_grid(1.5, 1.0)
    assert grid.grid[cy2, cx2] == -1, "FAIL: Neighboring pad was accidentally unblocked!"
    
    # EXPECTATION: Net 1's pad at (1.0, 1.0) SHOULD BE unblocked (0).
    cx1, cy1 = grid.world_to_grid(1.0, 1.0)
    assert grid.grid[cy1, cx1] == 0, "FAIL: Net's own pad was not unblocked!"

if __name__ == "__main__":
    test_unblock_blindness_shorts_neighbor()
    print("Success!")
