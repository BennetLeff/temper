"""
Tests for Router V6 Stage 4.6: Update Occupancy Grid

Part of temper-t523
"""

import pytest
import numpy as np

from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.grid_update import update_occupancy_grid
from temper_placer.router_v6.occupancy_grid import CellState, OccupancyGrid


def test_update_empty_grid():
    """Test updating grid with no routes."""
    grid = OccupancyGrid("F.Cu", np.zeros((10, 10), dtype=np.int8), (0, 0), 1.0, 10, 10)
    result = PathfindingResult(routed_paths={}, failed_nets=[])
    
    initial_free = grid.free_cell_count
    update_occupancy_grid(grid, result)
    
    # No change expected
    assert grid.free_cell_count == initial_free


def test_update_grid_single_route():
    """Test updating grid with single routed path."""
    grid = OccupancyGrid("F.Cu", np.zeros((20, 20), dtype=np.int8), (0, 0), 1.0, 20, 20)
    
    # Create a simple route
    path = RoutePath("NET1", [(5.0, 5.0), (10.0, 10.0)], "F.Cu", 7.07)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])
    
    initial_free = grid.free_cell_count
    update_occupancy_grid(grid, result)
    
    # Should have fewer free cells after marking route
    assert grid.free_cell_count < initial_free


def test_update_grid_marks_cells_reserved():
    """Test that updated cells are marked as RESERVED."""
    grid = OccupancyGrid("F.Cu", np.zeros((10, 10), dtype=np.int8), (0, 0), 1.0, 10, 10)
    
    path = RoutePath("NET1", [(5.0, 5.0)], "F.Cu", 0.0)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])
    
    update_occupancy_grid(grid, result, clearance_cells=0)
    
    # Cell at (5, 5) should be reserved
    x_cell, y_cell = grid.world_to_grid(5.0, 5.0)
    assert grid.grid[y_cell, x_cell] == CellState.RESERVED.value


def test_update_grid_with_clearance():
    """Test grid update with clearance inflation."""
    grid = OccupancyGrid("F.Cu", np.zeros((20, 20), dtype=np.int8), (0, 0), 1.0, 20, 20)
    
    path = RoutePath("NET1", [(10.0, 10.0)], "F.Cu", 0.0)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])
    
    # Update with 2-cell clearance
    update_occupancy_grid(grid, result, clearance_cells=2)
    
    # Center cell and surrounding cells should be reserved
    x_cell, y_cell = grid.world_to_grid(10.0, 10.0)
    
    # Check center
    assert grid.grid[y_cell, x_cell] == CellState.RESERVED.value
    
    # Check adjacent cells (within clearance)
    if x_cell + 1 < grid.width_cells:
        assert grid.grid[y_cell, x_cell + 1] == CellState.RESERVED.value


def test_update_grid_multiple_routes():
    """Test updating grid with multiple routes."""
    grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)
    
    paths = {
        "NET1": RoutePath("NET1", [(5.0, 5.0), (10.0, 10.0)], "F.Cu", 7.07),
        "NET2": RoutePath("NET2", [(15.0, 15.0), (20.0, 20.0)], "F.Cu", 7.07),
    }
    result = PathfindingResult(routed_paths=paths, failed_nets=[])
    
    initial_free = grid.free_cell_count
    update_occupancy_grid(grid, result, clearance_cells=1)
    
    # Both routes should reduce free space
    assert grid.free_cell_count < initial_free


def test_update_grid_bounds_checking():
    """Test that grid update handles out-of-bounds coordinates."""
    grid = OccupancyGrid("F.Cu", np.zeros((10, 10), dtype=np.int8), (0, 0), 1.0, 10, 10)
    
    # Route that goes outside grid bounds
    path = RoutePath("NET1", [(-5.0, -5.0), (0.0, 0.0)], "F.Cu", 7.07)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])
    
    # Should not crash
    update_occupancy_grid(grid, result)
