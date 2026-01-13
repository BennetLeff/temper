import pytest
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.astar_pathfinding import (
    _unblock_net_pads
)

def test_surgical_precision_high_density():
    """
    TDD Test: Verify if surgical unblocking accidentally clears neighbors in 0.5mm pitch.
    """
    grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((40, 40), dtype=np.int16),
        origin=(0.0, 0.0),
        cell_size=0.05,
        width_cells=40,
        height_cells=40
    )
    
    # Pad centers at (1.0, 1.0) and (1.45, 1.0) - 0.45mm pitch
    # Both are 0.2mm diameter (radius 0.1)
    for px, py in [(1.0, 1.0), (1.45, 1.0)]:
        cx, cy = grid.world_to_grid(px, py)
        # Block a 3x3 area
        grid.grid[cy-1:cy+2, cx-1:cx+2] = -1
    
    grid.static_mask = (grid.grid == -1)
        
    pad_centers = {
        "Net1": [(1.0, 1.0, 0.1, "F.Cu")],
        "Net2": [(1.45, 1.0, 0.1, "F.Cu")]
    }
    
    # Unblock Net 1 with 0.3mm inflation
    grids = {"F.Cu": grid}
    # Current code uses effective_unblock_radius = radius + inflation_mm + 1.5*cell_size
    # 0.1 + 0.3 + 0.075 = 0.475.
    # Neighbor is 0.5mm away. 
    # Center-to-center is 0.5.
    # Edge of neighbor pad is at distance 0.4 (1.5 - 0.1).
    # 0.475 > 0.4. So neighbor edge WILL be unblocked.
    
    _unblock_net_pads("Net1", pad_centers, grids, inflation_mm=0.3)
    
    # ASSERT: Net 2's center should STILL be blocked.
    cx2, cy2 = grid.world_to_grid(1.45, 1.0)
    assert grid.grid[cy2, cx2] == -1, f"Net 2 pad was unblocked during Net 1 surgery! (Pitch=0.45mm, Val={grid.grid[cy2, cx2]})"

if __name__ == "__main__":
    test_surgical_precision_high_density()
    print("Success!")
