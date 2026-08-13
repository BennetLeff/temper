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


# ---------------------------------------------------------------------------
# C-space erosion guard (2026-08-12)
# ---------------------------------------------------------------------------
#
# `build_occupancy_grid`'s erosion used to be guarded by `if inflation_mm >
# 0.1`, a magnitude threshold commented "Threshold to avoid tiny/empty
# buffers".  `OccupancyGridStage` passes `default_trace_width_mm / 2`, so once
# that width was corrected 0.25 -> 0.20 the inflation became exactly 0.100 and
# the STRICT `>` switched the entire C-space off at precisely the production
# value.  Measured on the #1082 placed board: 94,991 cells across the four
# layers that were reserved before became free -- the ring hugging every
# obstacle boundary -- and DRC reported 191 clearance violations at
# `actual 0.0000 mm`.  See docs/evidence/2026-08-12-clearance-floor-reland.md.


def _square_space(side: float = 10.0) -> RoutingSpace:
    return RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, side, side)]),
        total_area=side * side,
        obstacle_area=0.0,
        routing_area=side * side,
    )


def test_erosion_applies_at_exactly_the_production_inflation():
    """inflation == 0.1 must erode.

    This is the regression: it is the value `OccupancyGridStage` passes for a
    0.2mm default trace, and the old `> 0.1` predicate excluded it by one ULP
    of intent.  Asserted against the un-eroded grid so it cannot pass
    vacuously.
    """
    space = _square_space()
    none_ = build_occupancy_grid(space, cell_size=0.1, inflation_mm=0.0)
    prod = build_occupancy_grid(space, cell_size=0.1, inflation_mm=0.1)

    assert prod.free_cell_count < none_.free_cell_count, (
        "inflation_mm=0.1 left the grid identical to inflation_mm=0.0: the "
        "C-space erosion is being skipped at exactly the inflation the "
        "production pipeline passes"
    )


def test_erosion_is_monotonic_in_inflation():
    """More reservation never means more free space, across the boundary.

    Note this one does NOT fail on the old `> 0.1` predicate: discarding the
    erosion below the threshold makes the sequence FLAT there, not
    increasing, and flat is still sorted.  It is here to constrain the shape
    of any future replacement predicate; the test above is the one that pins
    the defect.  (Verified by mutation -- reinstating `> 0.1` fails
    `test_erosion_applies_at_exactly_the_production_inflation` and nothing
    else in this file.)
    """
    space = _square_space()
    counts = [
        build_occupancy_grid(space, cell_size=0.1, inflation_mm=i).free_cell_count
        for i in (0.0, 0.001, 0.05, 0.1, 0.100001, 0.125, 0.3)
    ]
    assert counts == sorted(counts, reverse=True), counts


def test_tiny_inflation_is_applied_and_harmless():
    """The "tiny buffers" half of the old comment: a sub-micron erosion is
    valid, non-empty and cheap, so there is nothing for a threshold to
    protect.  It only ever removes cells, never adds them."""
    space = _square_space()
    none_ = build_occupancy_grid(space, cell_size=0.1, inflation_mm=0.0)
    tiny = build_occupancy_grid(space, cell_size=0.1, inflation_mm=1e-9)

    assert tiny.free_cell_count > 0
    assert tiny.free_cell_count <= none_.free_cell_count


def test_erosion_that_empties_the_layer_blocks_it_rather_than_falling_back():
    """The "empty buffers" half.  An erosion larger than the layer's inradius
    means no trace of that width fits anywhere on it.  Blocking every cell is
    the true answer; silently reverting to the un-eroded area would emit
    copper that violates by construction."""
    space = _square_space(side=10.0)
    grid = build_occupancy_grid(space, cell_size=0.1, inflation_mm=50.0)
    assert grid.free_cell_count == 0
