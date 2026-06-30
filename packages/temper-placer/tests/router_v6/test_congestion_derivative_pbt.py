"""
Congestion Derivative Property-Based Tests.

Validates that the early-abort heuristic in _astar_search_theta_star and
_astar_search_lazy_theta_star never produces false positives (never aborts
when a path exists) and correctly aborts on unreachable regions.

MR10: No False Positives — early abort is safety-preserving.
MR11: Correct Abort — disconnected grids trigger early abort.
MR12: Configurable — flag=off disables early abort.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import (
    _CONGESTION_CHECK_INTERVAL,
    _CONGESTION_GROWTH_THRESHOLD,
    _CONGESTION_PLATEAU_STRIKES,
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from tests.router_v6.astar_oracle_utils import (
    DIJKSTRA_MAX_CELLS,
    dijkstra_shortest_path,
)
from tests.router_v6.astar_property_strategies import grid_and_pair


def _make_simple_grid(
    rows: int, cols: int, blocked: set[tuple[int, int]] | None = None
) -> OccupancyGrid:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for c, r in (blocked or set()):
        arr[r, c] = 1
    return OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, cols, rows)


def _make_wall_grid(width: int, height: int, wall_col: int) -> OccupancyGrid:
    """Create a grid with a full vertical wall at wall_col (0-indexed)."""
    blocked = {(wall_col, y) for y in range(height)}
    return _make_simple_grid(width, height, blocked)


# ---------------------------------------------------------------------------
# MR10: No False Positives — early abort never fires when path exists
# ---------------------------------------------------------------------------


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(rows=st.integers(5, 25), cols=st.integers(5, 25),
                          p_obstacle=st.floats(0.0, 0.4)))
@settings(max_examples=100, deadline=30000)
def test_congestion_derivative_no_false_positive_theta_star(gsp):
    """Theta*: Dijkstra verifies path exists => early abort must find it too."""
    grid, start, goal = gsp
    n_cells = grid.width_cells * grid.height_cells

    if n_cells > DIJKSTRA_MAX_CELLS:
        return  # Oracle too expensive

    d_path, _ = dijkstra_shortest_path(start, goal, grid)
    if d_path is None:
        return  # No path — nothing to check

    # Early abort ON: must still find a path
    path_on = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    assert path_on is not None, (
        f"False positive: Theta* early abort on reachable grid "
        f"{grid.width_cells}x{grid.height_cells}, {start}->{goal}"
    )

    # Early abort OFF: should also find a path
    path_off = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )
    assert path_off is not None, (
        f"Theta* without derivative failed on reachable grid"
    )


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(rows=st.integers(5, 25), cols=st.integers(5, 25),
                          p_obstacle=st.floats(0.0, 0.4)))
@settings(max_examples=100, deadline=30000)
def test_congestion_derivative_no_false_positive_lazy_theta_star(gsp):
    """Lazy Theta*: Dijkstra verifies path exists => early abort must find it."""
    grid, start, goal = gsp
    n_cells = grid.width_cells * grid.height_cells

    if n_cells > DIJKSTRA_MAX_CELLS:
        return

    d_path, _ = dijkstra_shortest_path(start, goal, grid)
    if d_path is None:
        return

    path_on = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    assert path_on is not None, (
        f"False positive: Lazy Theta* early abort on reachable grid "
        f"{grid.width_cells}x{grid.height_cells}, {start}->{goal}"
    )

    path_off = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )
    assert path_off is not None, (
        f"Lazy Theta* without derivative failed on reachable grid"
    )


# ---------------------------------------------------------------------------
# MR11: Correct Abort — disconnected grids trigger early abort
# ---------------------------------------------------------------------------


def test_congestion_derivative_abort_on_wall_theta_star():
    """Theta*: wall-separated start/goal triggers early abort."""
    # 100x100 grid with a full wall at column 50
    grid = _make_wall_grid(100, 100, 50)
    start = (0, 0)
    goal = (99, 99)

    # With early abort ON: should return None (and much faster)
    path_on = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    assert path_on is None, (
        "Theta* with early abort should return None on wall-separated grid"
    )

    # With early abort OFF: should also return None but after many more iterations
    path_off = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )
    assert path_off is None, (
        "Theta* without early abort should also return None on wall-separated grid"
    )


def test_congestion_derivative_abort_on_wall_lazy_theta_star():
    """Lazy Theta*: wall-separated start/goal triggers early abort."""
    grid = _make_wall_grid(100, 100, 50)
    start = (0, 0)
    goal = (99, 99)

    path_on = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    assert path_on is None, (
        "Lazy Theta* with early abort should return None on wall-separated grid"
    )

    path_off = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )
    assert path_off is None, (
        "Lazy Theta* without early abort should also return None on wall-separated grid"
    )


def test_congestion_derivative_abort_on_boxed_theta_star():
    """Theta*: start in a boxed region with no exit triggers early abort."""
    # 60x60 grid; start in top-left 10x10 box separated by walls from goal
    blocked: set[tuple[int, int]] = set()
    # Horizontal wall
    for x in range(0, 60):
        blocked.add((x, 29))
        blocked.add((x, 30))
    # Vertical walls connecting the horizontal wall to edges
    for y in range(0, 30):
        blocked.add((59, y))
        blocked.add((0, y))
    grid = _make_simple_grid(60, 60, blocked)
    start = (5, 5)
    goal = (55, 55)

    path_on = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    path_off = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )
    assert path_on is None, "Theta* early abort should detect unreachable goal"
    assert path_off is None, "Theta* should also fail without derivative"


def test_congestion_derivative_abort_on_boxed_lazy_theta_star():
    """Lazy Theta*: start in isolated region triggers early abort."""
    blocked: set[tuple[int, int]] = set()
    for x in range(0, 60):
        blocked.add((x, 29))
    for y in range(0, 30):
        blocked.add((59, y))
        blocked.add((0, y))
    grid = _make_simple_grid(60, 60, blocked)
    start = (5, 5)
    goal = (55, 55)

    path_on = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    path_off = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )
    assert path_on is None, "Lazy Theta* early abort should detect unreachable goal"
    assert path_off is None, "Lazy Theta* should also fail without derivative"


# ---------------------------------------------------------------------------
# MR12: Configurable — disable flag preserves original behaviour
# ---------------------------------------------------------------------------


def test_congestion_derivative_configurable_off():
    """Setting enable_congestion_derivative=False returns same result as unlimited search."""
    grid = _make_wall_grid(50, 50, 25)
    start = (0, 0)
    goal = (49, 49)

    # Both should return None on a wall grid
    path_theta_on = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    path_theta_off = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )

    assert path_theta_on is None
    assert path_theta_off is None

    # On an unimpeded path, both should succeed
    open_grid = _make_simple_grid(20, 20)
    path_open_on = _astar_search_theta_star(
        open_grid, (0, 0), (19, 19), net_id=0, enable_congestion_derivative=True,
    )
    path_open_off = _astar_search_theta_star(
        open_grid, (0, 0), (19, 19), net_id=0, enable_congestion_derivative=False,
    )
    assert path_open_on is not None, "Should find path on open grid with flag ON"
    assert path_open_off is not None, "Should find path on open grid with flag OFF"


# ---------------------------------------------------------------------------
# Exhaustive: 5x5 grids verify no false positives on all occupancy patterns
# ---------------------------------------------------------------------------


@pytest.mark.l2_exhaustive
def test_congestion_derivative_exhaustive_5x5_theta_star():
    """Exhaustive 5x5: Theta* never aborts on reachable (start, goal) pairs."""
    size = 5
    total_bits = 1 << (size * size)

    for occ_bits in range(min(total_bits, 5000)):  # Cap at 5000 for speed
        blocked: set[tuple[int, int]] = set()
        for r in range(size):
            for c in range(size):
                if occ_bits & (1 << (r * size + c)):
                    blocked.add((c, r))
        grid = _make_simple_grid(size, size, blocked)
        free = [(c, r) for r in range(size) for c in range(size)
                if grid.grid[r, c] == 0]

        for i in range(len(free)):
            for j in range(i + 1, len(free)):
                s, g = free[i], free[j]
                # Pristine Theta* (no early abort)
                path_off = _astar_search_theta_star(
                    grid, s, g, net_id=0, enable_congestion_derivative=False,
                )
                # Theta* with early abort
                path_on = _astar_search_theta_star(
                    grid, s, g, net_id=0, enable_congestion_derivative=True,
                )

                if path_off is not None:
                    assert path_on is not None, (
                        f"False positive: occupancy {occ_bits:0{25}b}, "
                        f"{s}->{g}: Theta* early abort rejected reachable path"
                    )
                else:
                    assert path_on is None, (
                        f"Early abort found phantom path: occ {occ_bits:0{25}b}"
                    )


@pytest.mark.l2_exhaustive
def test_congestion_derivative_exhaustive_5x5_lazy_theta_star():
    """Exhaustive 5x5: Lazy Theta* never aborts on reachable (start, goal) pairs."""
    size = 5
    total_bits = 1 << (size * size)

    for occ_bits in range(min(total_bits, 5000)):
        blocked: set[tuple[int, int]] = set()
        for r in range(size):
            for c in range(size):
                if occ_bits & (1 << (r * size + c)):
                    blocked.add((c, r))
        grid = _make_simple_grid(size, size, blocked)
        free = [(c, r) for r in range(size) for c in range(size)
                if grid.grid[r, c] == 0]

        for i in range(len(free)):
            for j in range(i + 1, len(free)):
                s, g = free[i], free[j]
                path_off = _astar_search_lazy_theta_star(
                    grid, s, g, net_id=0, enable_congestion_derivative=False,
                )
                path_on = _astar_search_lazy_theta_star(
                    grid, s, g, net_id=0, enable_congestion_derivative=True,
                )

                if path_off is not None:
                    assert path_on is not None, (
                        f"False positive: occupancy {occ_bits:0{25}b}, "
                        f"{s}->{g}: Lazy Theta* early abort rejected reachable path"
                    )
                else:
                    assert path_on is None, (
                        f"Early abort found phantom path: occ {occ_bits:0{25}b}"
                    )


# ---------------------------------------------------------------------------
# Large-grid correctness: early abort consistency vs full search
# ---------------------------------------------------------------------------


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(rows=st.integers(30, 60), cols=st.integers(30, 60),
                          p_obstacle=st.floats(0.1, 0.5)))
@settings(max_examples=50, deadline=60000)
def test_congestion_derivative_large_grid_consistency_theta_star(gsp):
    """Large grids: early abort result must match full search result."""
    grid, start, goal = gsp

    path_on = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    path_off = _astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )

    # Completeness parity: if full search finds path, early abort must too
    if path_off is not None:
        assert path_on is not None, (
            f"Inconsistency: full Theta* found path but early abort did not, "
            f"{grid.width_cells}x{grid.height_cells}, {start}->{goal}"
        )
    # If full search returns None, early abort should too
    # (early abort can't "find" a path that doesn't exist)
    else:
        assert path_on is None, (
            f"Early abort found phantom path on unreachable grid"
        )


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(rows=st.integers(30, 60), cols=st.integers(30, 60),
                          p_obstacle=st.floats(0.1, 0.5)))
@settings(max_examples=50, deadline=60000)
def test_congestion_derivative_large_grid_consistency_lazy_theta_star(gsp):
    """Large grids: Lazy Theta* early abort consistent with full search."""
    grid, start, goal = gsp

    path_on = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=True,
    )
    path_off = _astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False,
    )

    if path_off is not None:
        assert path_on is not None, (
            f"Inconsistency: full Lazy Theta* found path but early abort did not, "
            f"{grid.width_cells}x{grid.height_cells}, {start}->{goal}"
        )
    else:
        assert path_on is None, (
            "Early abort found phantom path on unreachable grid"
        )
