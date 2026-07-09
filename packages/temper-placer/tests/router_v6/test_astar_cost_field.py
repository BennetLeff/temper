"""
U8: A* thermal cost-field injection — unit and integration tests.

Verifies that the thermal cost field is consumed additively by the
Numba A* kernel, hard obstacles remain masked (soft weights never
override hard masks), and the field-off path is byte-identical to
today's routing.
"""

import numpy as np
import pytest

from temper_placer.fields.interface import CostFieldInput
from temper_placer.router_v6.astar_core_numba import _astar_search_numba
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _make_grid(rows, cols, blocked=None):
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in (blocked or []):
        arr[r, c] = 1
    return OccupancyGrid("F.Cu", arr, (0.0, 0.0), 1.0, cols, rows)


def _path_cells(path):
    """Extract cell indices for a path from (col, row) tuples."""
    if path is None:
        return None
    rows = max(y for _, y in path) + 1
    cols = [c for c, _ in path]
    cols_b = max(cols) + 1
    return [(c, r) for c, r in path], max(rows, cols_b)


# ---------------------------------------------------------------------------
# K3: hot region causes detour
# ---------------------------------------------------------------------------


@pytest.mark.l4_regression
def test_thermal_field_detours_around_hot_region():
    """A routed net detours around high-cost cells vs the no-field baseline."""
    rows, cols = 20, 20
    grid = _make_grid(rows, cols)

    # Create a thermal field with a "hot wall" across the middle
    thermal_2d = np.zeros((rows, cols), dtype=np.float32)
    # Hot vertical wall at cols 8-12 across the middle rows
    thermal_2d[4:16, 8:12] = 100.0

    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    start = (1, 10)  # (col, row) — left side
    goal = (18, 10)  # (col, row) — right side

    # Field-off baseline: straight shot through the hot region
    path_off = _astar_search_numba(start, goal, grid, max_iterations=5000)

    # Field-on: should detour around the hot wall
    path_on = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        thermal_flat=thermal_flat, thermal_weight=5.0,
    )

    assert path_off is not None, "Baseline path must be found"
    assert path_on is not None, "Field-on path must be found"

    # The field-on path should avoid the hot region cells
    hot_cells = set()
    for r in range(4, 16):
        for c in range(8, 12):
            hot_cells.add((c, r))

    on_traversals = sum(1 for cell in path_on if cell in hot_cells)
    off_traversals = sum(1 for cell in path_off if cell in hot_cells)

    # Field-on path should traverse fewer hot cells than field-off
    assert on_traversals < off_traversals, (
        f"Field-on traversed {on_traversals} hot cells, "
        f"field-off traversed {off_traversals}; expected detour"
    )


# ---------------------------------------------------------------------------
# Edge: zero / UNMEASURED field = byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.l4_regression
def test_thermal_field_off_byte_identical():
    """Zero-weight thermal field leaves routing byte-identical to no field."""
    rows, cols = 30, 30
    grid = _make_grid(rows, cols)

    thermal_2d = np.ones((rows, cols), dtype=np.float32) * 50.0
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    start = (2, 15)
    goal = (27, 15)

    path_no_field = _astar_search_numba(start, goal, grid, max_iterations=5000)
    path_weight_zero = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        thermal_flat=thermal_flat, thermal_weight=0.0,
    )
    path_no_thermal = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        thermal_flat=None, thermal_weight=0.0,
    )

    assert path_no_field is not None
    assert path_weight_zero == path_no_field, (
        "Weight-zero thermal field must produce identical path"
    )
    assert path_no_thermal == path_no_field, (
        "No thermal field must produce identical path"
    )


@pytest.mark.l4_regression
def test_thermal_field_off_byte_identical_with_congestion():
    """Zero-weight thermal + congestion still matches congestion-only path."""
    rows, cols = 30, 30
    grid = _make_grid(rows, cols)

    # Build a minimal congestion tensor (PathFinder-style)
    congestion_2d = np.zeros((rows, cols), dtype=np.float32)
    congestion_2d[10:20, 12:14] = 5.0  # some congested cells

    thermal_2d = np.ones((rows, cols), dtype=np.float32) * 50.0
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    start = (2, 15)
    goal = (27, 15)

    path_congestion_only = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        congestion_flat=congestion_2d.ravel(), congestion_weight=0.1,
    )
    path_congestion_plus_thermal_off = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        congestion_flat=congestion_2d.ravel(), congestion_weight=0.1,
        thermal_flat=thermal_flat, thermal_weight=0.0,
    )

    assert path_congestion_only is not None
    assert path_congestion_plus_thermal_off == path_congestion_only, (
        "Congestion + zero thermal must match congestion-only path"
    )


# ---------------------------------------------------------------------------
# Hard obstacles: soft weights never override hard masks
# ---------------------------------------------------------------------------


@pytest.mark.l4_regression
def test_thermal_field_never_overrides_hard_obstacles():
    """Thermal cost never makes a path traverse a masked (blocked) cell.

    Create a grid where the direct path between start and goal passes
    through a wall of blocked cells with zero thermal cost, tempting
    A* to go through them.  The bit tensor must prevent this.
    """
    rows, cols = 10, 10
    # Wall: vertical line at col=5, rows 0-7 and 9 blocked (gap at row 8)
    blocked = [(r, 5) for r in range(9) if r != 8]
    grid = _make_grid(rows, cols, blocked)

    # High cost everywhere EXCEPT the blocked wall cells (temptation)
    thermal_2d = np.full((rows, cols), 500.0, dtype=np.float32)
    for r, c in blocked:
        thermal_2d[r, c] = 0.0
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    start = (2, 8)  # free cell left of wall
    goal = (8, 8)   # free cell right of wall

    path = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        thermal_flat=thermal_flat, thermal_weight=10.0,
    )

    assert path is not None, "Path must be found (through the gap at row 8)"

    blocked_set = set(blocked)
    for cell in path:
        assert cell not in blocked_set, (
            f"Path traversed blocked cell {cell}"
        )


# ---------------------------------------------------------------------------
# A/B toggle: field-on vs field-off produces divergent routes
# ---------------------------------------------------------------------------


@pytest.mark.l4_regression
def test_thermal_field_ab_toggle_divergent():
    """With a strong hot region blocking the direct path, routes diverge."""
    rows, cols = 30, 30
    grid = _make_grid(rows, cols)

    # Hot region in the center-right — the straight vertical line from
    # start to goal passes directly through it.  Detour around left side
    # is clear.
    thermal_2d = np.zeros((rows, cols), dtype=np.float32)
    thermal_2d[10:20, 13:18] = 500.0  # hot block
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    start = (15, 3)
    goal = (15, 26)

    path_off = _astar_search_numba(start, goal, grid, max_iterations=5000)
    path_on = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        thermal_flat=thermal_flat, thermal_weight=4.0,
    )

    assert path_off is not None
    assert path_on is not None
    # The straight vertical path goes through hot cells (500*4=2000 extra
    # per cell).  The detour left adds ~4 extra columns * ~1.0 each = cheap.
    assert path_on != path_off, (
        "Field-on path must diverge from field-off baseline"
    )


# ---------------------------------------------------------------------------
# CostFieldInput integration
# ---------------------------------------------------------------------------


@pytest.mark.l4_regression
def test_cost_field_input_integration():
    """CostFieldInput contract flows correctly through to A*."""
    rows, cols = 20, 20
    grid = _make_grid(rows, cols)

    thermal_2d = np.zeros((rows, cols), dtype=np.float32)
    thermal_2d[5:15, 5:15] = 100.0  # hot center

    cfi = CostFieldInput(
        cost_flat=np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32),
        weight=2.0,
    )

    start = (1, 10)
    goal = (18, 10)

    path = _astar_search_numba(
        start, goal, grid, max_iterations=5000,
        thermal_flat=cfi.cost_flat, thermal_weight=cfi.weight,
    )

    assert path is not None, "Path must be found with CostFieldInput"
    # Path should avoid the hot center
    hot_cells = {(c, r) for r in range(5, 15) for c in range(5, 15)}
    traversals = sum(1 for cell in path if cell in hot_cells)
    assert traversals < 5, (
        f"Path traversed {traversals} hot center cells; expected detour"
    )
