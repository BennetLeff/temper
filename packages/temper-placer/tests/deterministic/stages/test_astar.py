import pytest
import math
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.astar import DeterministicAStar

def test_direct_path_no_obstacles():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    pathfinder = DeterministicAStar(grid)
    
    path = pathfinder.find_path(start=(10, 10), end=(30, 10))
    
    assert path is not None
    assert path[0] == (10, 10)
    assert path[-1] == (30, 10)
    # Path should be mostly straight (allow small deviations for grid alignment)
    assert len(path) < 50  # Direct path ~40 cells

def test_path_around_obstacle():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    # Block a wall between start and end
    for y in range(5, 45):
        grid.block_circle(center=(20, y), radius_mm=0.5, clearance_mm=0.0)
    
    pathfinder = DeterministicAStar(grid)
    path = pathfinder.find_path(start=(10, 25), end=(30, 25))
    
    assert path is not None
    # Path should go around the wall (above or below)
    # The wall is at x=20.0 with 0.5mm radius, so x in [19.5, 20.5] is mostly blocked.
    # We check that it doesn't cross the center line of the wall at x=20.
    x_coords = [p[0] for p in path]
    # If it crosses from x < 20 to x > 20, it must have gone around the wall (y < 5 or y > 45)
    crossed_at_y = [p[1] for p in path if 19.9 < p[0] < 20.1]
    for y in crossed_at_y:
        assert y < 5 or y > 44

def test_no_path_when_fully_blocked():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    # Block all exits from start
    for angle in range(0, 360, 10):
        x = 10 + 2 * math.cos(math.radians(angle))
        y = 10 + 2 * math.sin(math.radians(angle))
        grid.block_circle(center=(x, y), radius_mm=0.5, clearance_mm=0.0)
    
    pathfinder = DeterministicAStar(grid)
    path = pathfinder.find_path(start=(10, 10), end=(40, 40))
    
    assert path is None

def test_astar_is_deterministic():
    '''Same input produces identical path.'''
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    grid.block_circle(center=(20, 25), radius_mm=5, clearance_mm=0.3)
    
    pathfinder = DeterministicAStar(grid)
    
    path1 = pathfinder.find_path(start=(10, 25), end=(30, 25))
    path2 = pathfinder.find_path(start=(10, 25), end=(30, 25))
    
    assert path1 == path2
