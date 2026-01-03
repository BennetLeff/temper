
import numpy as np
import pytest
from shapely.geometry import box
from temper_placer.routing.c_space_builder import SoftCSpaceBuilder
from temper_placer.routing.maze_router import MazeRouter, GridCell

def test_soft_c_space_generation():
    # 10mm x 10mm board
    from temper_placer.routing.c_space_builder import CSpaceConfig
    config = CSpaceConfig(resolution_mm=0.5)
    builder = SoftCSpaceBuilder(width_mm=10, height_mm=10, config=config)
    
    # Add an HV obstacle (AC_L)
    # 2mm x 2mm pad at (5, 5)
    builder.add_pad(center_x=5, center_y=5, width=2, height=2, net="AC_L")
    
    # Build cost grid for LOGIC net
    cost_grid = builder.build_cost_grid(net_class="LOGIC")
    
    # Check dimensions
    assert cost_grid.shape == (20, 20)
    
    # Check that center is infinity (hard obstacle + fatal radius)
    # AC_L fatal radius is 1.5mm. Pad is 2mm wide -> total blocked width is 2 + 1.5*2 = 5mm.
    # From 2.5mm to 7.5mm should be blocked.
    center_idx = 10
    assert cost_grid[center_idx, center_idx] == np.inf
    
    # Check preferred clearance halo (4.5mm for AC_L)
    # AC_L preferred radius is 4.5mm. Pad is 2mm wide -> total preferred width is 2 + 4.5*2 = 11mm.
    # Since board is only 10mm, most of it should be soft zone or hard zone.
    # Let's check a point in the soft zone
    # (3, 5) is 2mm from center (5, 5). Hard zone is 1.5mm from pad (1mm from center).
    # Wait, pad is 2mm wide, so edge is at 4mm and 6mm.
    # Hard zone is 1.5mm from edge -> 2.5mm and 7.5mm.
    # Soft zone is 4.5mm from edge -> -0.5mm and 10.5mm.
    # So basically the whole board is soft zone.
    # (0, 0) is sqrt(5^2 + 5^2) = 7.07mm from center.
    # Distance from pad edge (4, 4) to (0, 0) is sqrt(4^2 + 4^2) = 5.65mm.
    # 5.65mm > 4.5mm, so (0, 0) is indeed OUTSIDE soft zone.
    
    # Let's check (2, 5)
    # (2, 5) is 3mm from center (5, 5). Pad edge is at (4, 5). Distance is 2mm.
    # 2mm < 4.5mm, so (2, 5) should be in soft zone.
    # Index for (2, 5) at 0.5mm resolution is (4, 10).
    assert cost_grid[10, 4] == 50.0

def test_router_avoids_soft_obstacle():
    # 10mm x 10mm board, 1mm resolution
    cell_size = 1.0
    router = MazeRouter(grid_size=(10, 10), cell_size_mm=cell_size)
    
    # Path from (1, 5) to (9, 5)
    start = (1, 5)
    end = (9, 5)
    
    # Without soft obstacles, path should be straight line
    path_straight = router.find_path(start, end)
    assert len(path_straight) == 9 # (1,5) to (9,5) inclusive
    for cell in path_straight:
        assert cell.y == 5
        
    # Now add a soft obstacle in the middle (5, 5)
    # Cost grid: all 1.0 except (5, 5) which is 50.0
    cost_grid = np.ones((10, 10), dtype=np.float32)
    cost_grid[5, 5] = 50.0
    router.soft_c_space = cost_grid
    
    # Path should now go AROUND (5, 5)
    path_around = router.find_path(start, end)
    
    assert path_around is not None
    # Verify (5, 5) is NOT in path
    for cell in path_around:
        assert not (cell.x == 5 and cell.y == 5)
    
    # Length should be longer than 9
    assert len(path_around) > 9

def test_router_can_pass_through_soft_obstacle_if_necessary():
    # 5mm x 5mm board
    router = MazeRouter(grid_size=(5, 5), cell_size_mm=1.0)
    
    # Path from (0, 2) to (4, 2)
    start = (0, 2)
    end = (4, 2)
    
    # Block everything except y=2 row with hard obstacles
    for x in range(5):
        for y in [0, 1, 3, 4]:
            router.occupancy[x, y, 0] = -1
            
    # Now the only path is through y=2.
    # Put a soft obstacle at (2, 2)
    cost_grid = np.ones((5, 5), dtype=np.float32)
    cost_grid[2, 2] = 50.0
    router.soft_c_space = cost_grid
    
    # Path MUST go through (2, 2) because it's the only way
    path = router.find_path(start, end)
    
    assert path is not None
    found_2_2 = False
    for cell in path:
        if cell.x == 2 and cell.y == 2:
            found_2_2 = True
    assert found_2_2
