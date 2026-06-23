"""Property-based tests for OccupancyGrid invariants."""

import numpy as np
from hypothesis import given, settings, strategies as st

from temper_placer.router_v6.occupancy_grid import CellState, OccupancyGrid


@given(
    width=st.integers(min_value=1, max_value=200),
    height=st.integers(min_value=1, max_value=200),
)
@settings(max_examples=100, deadline=30000)
def test_occupancy_grid_free_le_total(width, height):
    """free_cell_count + blocked_cell_count <= total_cells."""
    grid = np.zeros((height, width), dtype=np.int16)
    # Mark some random cells as blocked
    grid[height // 2, width // 2] = 1

    og = OccupancyGrid(
        layer_name="test",
        grid=grid,
        origin=(0.0, 0.0),
        cell_size=0.1,
        width_cells=width,
        height_cells=height,
    )
    total = width * height
    assert og.free_cell_count <= total
    assert og.blocked_cell_count <= total
    assert og.free_cell_count + og.blocked_cell_count <= total


@given(
    width=st.integers(min_value=1, max_value=100),
    height=st.integers(min_value=1, max_value=100),
    cell_size=st.floats(min_value=0.01, max_value=1.0),
)
@settings(max_examples=100, deadline=30000)
def test_occupancy_grid_coordinate_roundtrip(width, height, cell_size):
    """world_to_grid then grid_to_world returns near-original."""
    grid = np.zeros((height, width), dtype=np.int16)
    og = OccupancyGrid(
        layer_name="test", grid=grid, origin=(0.0, 0.0),
        cell_size=cell_size, width_cells=width, height_cells=height,
    )
    x, y = 5.0, 5.0
    cx, cy = og.world_to_grid(x, y)
    wx, wy = og.grid_to_world(cx, cy)
    assert abs(wx - x) <= cell_size
    assert abs(wy - y) <= cell_size


@given(
    seed=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=100, deadline=30000)
def test_occupancy_grid_downsample(seed):
    """Downsampled grid has factor× fewer cells."""
    import random
    rng = random.Random(seed)
    w = rng.randint(10, 50)
    h = rng.randint(10, 50)
    grid = np.zeros((h, w), dtype=np.int16)
    for _ in range(w * h // 4):
        grid[rng.randint(0, h - 1), rng.randint(0, w - 1)] = 1

    og = OccupancyGrid(
        layer_name="test", grid=grid, origin=(0.0, 0.0),
        cell_size=0.1, width_cells=w, height_cells=h,
    )
    factor = 2
    coarse = og.downsample(factor)
    assert coarse.width_cells == max(1, w // factor)
    assert coarse.height_cells == max(1, h // factor)
    assert coarse.cell_size == og.cell_size * factor


@given(
    width=st.integers(min_value=1, max_value=50),
    height=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=100, deadline=30000)
def test_occupancy_grid_occupancy_ratio_bounded(width, height):
    """occupancy_ratio is always in [0, 1]."""
    grid = np.zeros((height, width), dtype=np.int16)
    og = OccupancyGrid(
        layer_name="test", grid=grid, origin=(0.0, 0.0),
        cell_size=0.1, width_cells=width, height_cells=height,
    )
    assert 0.0 <= og.occupancy_ratio <= 1.0
