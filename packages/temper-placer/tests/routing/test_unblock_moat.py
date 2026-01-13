import pytest
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.astar_pathfinding import (
    _unblock_net_pads, run_astar_pathfinding
)
from temper_placer.router_v6.channel_mapping import ChannelPath, ChannelMapping
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

@pytest.fixture
def design_rules():
    return DesignRules(
        net_classes={"Default": NetClassRules("Default", 0.2, 0.2, 0.6, 0.4)},
        net_class_assignments={},
        default_trace_width_mm=0.2,
        default_clearance_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.4
    )

def test_terminal_accessibility_moat(design_rules):
    """
    Prove that surgical unblocking with ONLY pad radius creates a 'moat'
    of inflation that prevents A* from reaching the pad center.
    """
    grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((50, 50), dtype=np.int16),
        origin=(0.0, 0.0),
        cell_size=0.1,
        width_cells=50,
        height_cells=50
    )
    
    # Simulate a Pad at (2.5, 2.5) with global inflation of 0.3mm
    # So every cell within 0.3mm of (2.5, 2.5) is blocked
    px, py = 2.5, 2.5
    for y in range(grid.height_cells):
        for x in range(grid.width_cells):
            wx, wy = grid.grid_to_world(x, y)
            dist = ((wx - px)**2 + (wy - py)**2)**0.5
            if dist <= 0.3:
                grid.grid[y, x] = -1
                
    pad_centers = {
        "Net1": [(2.5, 2.5, 0.1, "F.Cu")], # Pad radius is only 0.1
    }
    
    # UNBLOCK surgically. Using inflation knowledge.
    grids = {"F.Cu": grid}
    _unblock_net_pads("Net1", pad_centers, grids, inflation_mm=0.2) # radius 0.1 + inflation 0.2 = 0.3
    
    # VERIFY MOAT IS GONE for Net 1:
    # Cell at (2.2, 2.5) should now be 0 (unblocked)
    cx_moat, cy_moat = grid.world_to_grid(2.2, 2.5)
    assert grid.grid[cy_moat, cx_moat] == 0, "Moat should be unblocked!"
    
    # NOW TRY ROUTING
    mapping = ChannelMapping(channel_paths={
        "Net1": ChannelPath(net_name="Net1", waypoints=[(1.0, 2.5), (2.5, 2.5)], 
                            channel_sequence=[], total_length=1.5, preferred_layer="F.Cu")
    })
    
    result = run_astar_pathfinding(mapping, grid, design_rules)
    path = result.routed_paths["Net1"]
    
    # Path should now be valid (0 forced segments)
    assert path.forced_segment_count == 0, "A* should have reached the terminal via the unblocked path!"

if __name__ == "__main__":
    try:
        test_terminal_accessibility_moat(None)
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")
