"""
Property-based tests for the bounding-box empty-space shortcut in _line_of_sight.

Verifies that the BB shortcut is conservative: if it returns True (clear),
the full Bresenham traversal would also return True.  Never a false positive.

@req(2026-06-29-feat-los-bb, R4): PBT — random grids + line segments, BB vs Bresenham
"""
from __future__ import annotations

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import (
    _LOS_BB_FALLS_THROUGH,
    _LOS_BB_HITS,
    _line_of_sight,
    get_los_bb_stats,
    reset_los_bb_stats,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from tests.router_v6.astar_property_strategies import grids


# ---------------------------------------------------------------------------
# Reference Bresenham (pure, no BB shortcut)
# ---------------------------------------------------------------------------

def _bresenham_reference(
    p1: tuple[int, int], p2: tuple[int, int], grid: OccupancyGrid, net_id: int = 0,
) -> bool:
    """Pure Bresenham line-of-sight without any shortcut."""
    x0, y0 = p1
    x1, y1 = p2

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0

    while True:
        if not (0 <= x < grid.width_cells and 0 <= y < grid.height_cells):
            return False
        cell_value = grid.grid[y, x]
        if cell_value != 0 and cell_value != net_id:
            return False
        if x == x1 and y == y1:
            return True
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


# ---------------------------------------------------------------------------
# Direct BB check (extracted from the production code logic)
# ---------------------------------------------------------------------------

def _bb_check(p1: tuple[int, int], p2: tuple[int, int], grid: OccupancyGrid) -> bool:
    """Return True if the bounding box is entirely zero (line is provably clear)."""
    x0, y0 = p1
    x1, y1 = p2
    bbox = grid.grid[min(y0, y1):max(y0, y1) + 1, min(x0, x1):max(x0, x1) + 1]
    return not bool(np.any(bbox))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# @req(2026-06-29-feat-los-bb, R4): BB shortcut conservative — no false positives
@pytest.mark.pbt_low_priority
@given(grid=grids())
@settings(max_examples=500, deadline=15000)
def test_bb_shortcut_conservative(grid: OccupancyGrid):
    """If BB shortcut says clear, Bresenham must also say clear (no false positives)."""
    arr = grid.grid
    free_cells = [
        (int(x), int(y))
        for y in range(arr.shape[0])
        for x in range(arr.shape[1])
        if arr[y, x] == 0
    ]
    assume(len(free_cells) >= 2)

    rng = np.random.RandomState(hash(frozenset(arr.flat)) % (2**31 - 1))
    p1 = free_cells[rng.randint(0, len(free_cells))]
    remaining = [c for c in free_cells if c != p1]
    p2 = remaining[rng.randint(0, len(remaining))]

    bb_clear = _bb_check(p1, p2, grid)
    bres_clear = _bresenham_reference(p1, p2, grid, net_id=0)

    assert not bb_clear or bres_clear, (
        f"BB false positive! p1={p1}, p2={p2}, BB={bb_clear}, Bres={bres_clear}"
    )


# @req(2026-06-29-feat-los-bb, R3): endpoints inclusive in BB check
@given(
    row=st.integers(10, 20),
    col=st.integers(10, 20),
    x0=st.integers(1, 4),
    y0=st.integers(1, 4),
)
@settings(max_examples=200, deadline=5000)
def test_bb_endpoints_inclusive(row, col, x0, y0):
    """BB slice includes the (max_x, max_y) endpoint cell."""
    arr = np.zeros((row, col), dtype=np.int8)
    x1 = x0 + 5
    y1 = y0 + 5
    # Ensure endpoint is within bounds
    assume(x1 < col)
    assume(y1 < row)
    arr[y1, x1] = 1  # obstacle at endpoint cell

    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, col, row)
    assert not _bb_check(
        (x0, y0), (x1, y1), grid
    ), "BB should detect obstacle at endpoint (inclusive slice)"


def test_bb_fully_empty():
    """All-zero grid: BB shortcut returns True for any line."""
    arr = np.zeros((20, 20), dtype=np.int8)
    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, 20, 20)
    assert _bb_check((0, 0), (19, 19), grid)
    assert _bb_check((5, 3), (17, 12), grid)
    assert _bb_check((10, 10), (10, 10), grid)  # single-cell


def test_bb_single_obstacle():
    """One obstacle inside the bbox: BB shortcut falls through."""
    arr = np.zeros((10, 10), dtype=np.int8)
    arr[3, 5] = 1  # obstacle at (x=5, y=3)
    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, 10, 10)
    assert not _bb_check(
        (0, 0), (9, 9), grid
    ), "BB with obstacle in bbox should fall through"


def test_bb_obstacle_outside_bbox():
    """Obstacle outside the bbox should not block the shortcut."""
    arr = np.zeros((10, 10), dtype=np.int8)
    arr[0, 0] = 1  # obstacle in corner
    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, 10, 10)
    # bbox from (5,5) to (9,9) should be clear
    assert _bb_check((5, 5), (9, 9), grid)


def test_bb_net_id_conservatism():
    """BB check treats net_id cells as blocked (conservative)."""
    arr = np.zeros((10, 10), dtype=np.int8)
    arr[2:5, 2:5] = 42  # own-net cells
    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, 10, 10)

    bb_clear = _bb_check((0, 0), (9, 9), grid)
    assert not bb_clear, (
        "BB should fall through for net_id cells (conservative)"
    )

    # Bresenham with net_id=42 should be clear
    bres_clear = _bresenham_reference((0, 0), (9, 9), grid, net_id=42)
    assert bres_clear, "Bresenham should be clear for own-net cells"


def test_bb_production_uses_shortcut():
    """The production _line_of_sight uses BB shortcut and increments counters."""
    reset_los_bb_stats()
    arr = np.zeros((10, 10), dtype=np.int8)
    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, 10, 10)

    result = _line_of_sight((0, 0), (9, 9), grid, net_id=0)
    assert result is True

    hits, falls = _LOS_BB_HITS[0], _LOS_BB_FALLS_THROUGH[0]
    assert hits + falls >= 1
    assert hits >= 1  # BB hit on empty grid


def test_bb_stats_counters_increment():
    """Stats counters are non-negative and sum to call count."""
    reset_los_bb_stats()
    arr = np.eye(5, dtype=np.int8)
    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, 5, 5)

    for _i in range(3):
        _line_of_sight((0, 0), (4, 4), grid, net_id=0)

    hits, falls = get_los_bb_stats()
    total = hits + falls
    assert total == 3, f"Expected 3 calls, got {total}"
    assert hits >= 0
    assert falls >= 0
