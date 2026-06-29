"""
Tests for Router V6 Stage 2.5: Build Occupancy Grid

Part of temper-8bj1
"""

import numpy as np
from shapely.geometry import MultiPolygon, box

from temper_placer.router_v6.occupancy_grid import (
    build_occupancy_grid,
)
from temper_placer.router_v6.routing_space import RoutingSpace


def test_build_grid_simple():
    """Test basic grid construction."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 10, 10)]),
        total_area=100.0,
        obstacle_area=0.0,
        routing_area=100.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)

    assert grid.layer_name == "F.Cu"
    assert grid.cell_size == 1.0
    assert grid.width_cells > 0
    assert grid.height_cells > 0
    assert grid.free_cell_count > 0


def test_grid_coordinate_conversion():
    """Test world-to-grid and grid-to-world conversion."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 20, 20)]),
        total_area=400.0,
        obstacle_area=0.0,
        routing_area=400.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)

    # Test round-trip conversion
    x_cell, y_cell = grid.world_to_grid(10.0, 10.0)
    x_world, y_world = grid.grid_to_world(x_cell, y_cell)

    # Should be close to original (within cell size)
    assert abs(x_world - 10.0) < grid.cell_size
    assert abs(y_world - 10.0) < grid.cell_size


def test_grid_cell_state_checks():
    """Test is_free and is_blocked methods."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(5, 5, 15, 15)]),  # 10x10 box offset from origin
        total_area=400.0,
        obstacle_area=300.0,
        routing_area=100.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)

    # Cells inside routing area should be free
    center_x, center_y = grid.world_to_grid(10.0, 10.0)
    assert grid.is_free(center_x, center_y)
    assert not grid.is_blocked(center_x, center_y)


def test_grid_occupancy_ratio():
    """Test occupancy ratio calculation."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 10, 10)]),
        total_area=100.0,
        obstacle_area=0.0,
        routing_area=100.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)

    # Occupancy ratio should be reasonable (not all blocked, not all free)
    assert 0.0 <= grid.occupancy_ratio <= 1.0

    # For mostly free space, occupancy should be low
    assert grid.occupancy_ratio < 0.9


def test_grid_properties():
    """Test OccupancyGrid dataclass properties."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 50, 30)]),
        total_area=1500.0,
        obstacle_area=0.0,
        routing_area=1500.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=2.0)

    # Check dimensional properties
    assert grid.width_mm == grid.width_cells * grid.cell_size
    assert grid.height_mm == grid.height_cells * grid.cell_size

    # Total cells
    total_cells = grid.width_cells * grid.height_cells
    assert grid.free_cell_count + grid.blocked_cell_count == total_cells


def test_grid_with_different_cell_sizes():
    """Test grid construction with different cell sizes."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 20, 20)]),
        total_area=400.0,
        obstacle_area=0.0,
        routing_area=400.0,
    )

    # Coarse grid
    grid_coarse = build_occupancy_grid(routing_space, cell_size=2.0)

    # Fine grid
    grid_fine = build_occupancy_grid(routing_space, cell_size=0.5)

    # Fine grid should have more cells
    assert grid_fine.width_cells > grid_coarse.width_cells
    assert grid_fine.height_cells > grid_coarse.height_cells


def test_grid_bounds_checking():
    """Test that is_free/is_blocked handle out-of-bounds correctly."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 10, 10)]),
        total_area=100.0,
        obstacle_area=0.0,
        routing_area=100.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)

    # Out of bounds should return False for is_free
    assert not grid.is_free(-1, 0)
    assert not grid.is_free(0, -1)
    assert not grid.is_free(grid.width_cells + 10, 0)
    assert not grid.is_free(0, grid.height_cells + 10)


def test_grid_numpy_array():
    """Test that grid uses numpy array correctly."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 15, 15)]),
        total_area=225.0,
        obstacle_area=0.0,
        routing_area=225.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)

    # Grid should be a numpy array
    assert isinstance(grid.grid, np.ndarray)
    assert grid.grid.dtype == np.int8
    assert grid.grid.shape == (grid.height_cells, grid.width_cells)
