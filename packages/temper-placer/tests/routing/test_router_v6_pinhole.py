import pytest
import numpy as np
from shapely.geometry import Point
from temper_placer.router_v6.occupancy_grid import OccupancyGrid, build_occupancy_grid
from temper_placer.router_v6.astar_pathfinding import (
    run_astar_pathfinding
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

def create_grid_with_pad(layer_name, pad_center=(5.5, 5.5)):
    # Create a grid where (5,5) is a pad cell
    grid = OccupancyGrid(
        layer_name=layer_name,
        grid=np.zeros((10, 10), dtype=np.int16),
        origin=(0.0, 0.0),
        cell_size=1.0,
        width_cells=10,
        height_cells=10
    )
    # Mark (5,5) as a static obstacle (Pad)
    cx, cy = grid.world_to_grid(pad_center[0], pad_center[1])
    grid.grid[cy, cx] = -1
    return grid

def test_pad_proximity_short(design_rules):
    """
    TDD Test: Verify that the router currently doesn't respect pad clearance 
    because pads aren't inflated on the grid.
    """
    front_grid = create_grid_with_pad("F.Cu", pad_center=(5.5, 5.5))
    
    # Route a net at (4.5, 5.5) which is adjacent to the pad at (5.5, 5.5).
    # Since cell size is 1.0mm, (4,5) is adjacent to (5,5).
    # Clearance is 0.2, trace width is 0.2. Total radius 0.3mm.
    # On a 1.0mm grid, 4.5 and 5.5 are separated by 1.0mm.
    # Wait, 1.0mm is plenty of room for 0.3mm radius.
    
    # Let's use a smaller grid to see the fix.
    # We NEED a RoutingSpace to use build_occupancy_grid
    from temper_placer.router_v6.routing_space import RoutingSpace
    from shapely.geometry import MultiPolygon, Polygon
    
    board = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    pad = Point(1.0, 1.0).buffer(0.01) # Tiny pad to simulate static obstacle
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([board.difference(pad)]),
        total_area=4.0, obstacle_area=0.0, routing_area=4.0
    )
    
    # Required inflation = 0.3mm
    grid = build_occupancy_grid(routing_space, cell_size=0.1, margin=0.0, inflation_mm=0.3)
    
    mapping = ChannelMapping(channel_paths={
        "Net2": ChannelPath(net_name="Net2", waypoints=[(0.5, 0.5), (0.5, 1.5)], 
                            channel_sequence=[], total_length=1.0, preferred_layer="F.Cu")
    })
    
    # Net at x=0.5 should be fine. But what if we try to force it through x=0.8?
    # (0.8, 1.0) is only 0.2mm from pad at (1.0, 1.0).
    # Since inflation is 0.3mm, (0.8, 1.0) should be BLOCKED.
    
    assert grid.grid[10, 8] == -1 # (0.8, 1.0) is blocked!
    
    # Try routing a net that MUST detour
    mapping = ChannelMapping(channel_paths={
        "Net2": ChannelPath(net_name="Net2", waypoints=[(0.5, 1.0), (1.5, 1.0)], 
                            channel_sequence=[], total_length=1.0, preferred_layer="F.Cu")
    })
    
    result = run_astar_pathfinding(mapping, grid, design_rules)
    path = result.routed_paths["Net2"]
    path_points = [p[:2] for p in (path.segments if hasattr(path, 'segments') else path.coordinates)]
    
    for px, py in path_points:
        dist = ((px - 1.0)**2 + (py - 1.0)**2)**0.5
        assert dist >= 0.29, f"Short! Path at ({px}, {py}) is only {dist:.2f}mm from pad at (1.0, 1.0)"

if __name__ == "__main__":
    # For manual debugging
    try:
        test_pad_proximity_short(DesignRules(
            net_classes={"Default": NetClassRules("Default", 0.2, 0.2, 0.6, 0.4)},
            net_class_assignments={},
            default_trace_width_mm=0.2,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.4
        ))
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")
