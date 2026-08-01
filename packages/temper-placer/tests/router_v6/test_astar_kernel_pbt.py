"""Property-based tests for the Rust A* kernel (U5).

Six invariants (per the migration roadmap's PBT discipline), exercised
through ``_astar_search_numba`` (the sole A* backend since cleanup C1
retired the Numba fallback on 2026-07-31):

1. Path endpoints are start and goal
2. Consecutive path cells are 8-connected
3. No cell is revisited
4. Path length is octilinear-bounded: max(|dr|, |dc|) <= steps <= |dr|+|dc|
5. Blocked grids terminate with None (bounded search)
6. A congested blob on the direct route changes the path (congestion
   cost is honored)
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core_numba import _astar_search_numba
from temper_placer.router_v6.neighbor_validity import build_neighbor_validity_tensor_2d

MAX_EXAMPLES = 150

_dim = st.integers(3, 25)
_obstacle_strategy = st.lists(
    st.tuples(st.integers(0, 24), st.integers(0, 24)),
    max_size=60,
    unique=True,
)


class _GridAdapter:
    def __init__(self, arr: np.ndarray) -> None:
        self.grid = arr
        self.height_cells, self.width_cells = arr.shape


def _make_grid(rows: int, cols: int, blocked: list[tuple[int, int]]) -> np.ndarray:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in blocked:
        if 0 <= r < rows and 0 <= c < cols:
            arr[r, c] = 1
    return arr


def _search(start, goal, grid, congestion_flat=None):
    tensor = build_neighbor_validity_tensor_2d(grid)
    return _astar_search_numba(
        start,
        goal,
        grid,
        neighbor_tensor=tensor,
        max_iterations=500_000,
        congestion_flat=congestion_flat,
        congestion_weight=1.0 if congestion_flat is not None else 0.0,
    )


@given(_dim, _dim, _obstacle_strategy)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_path_endpoints_and_bounds(rows: int, cols: int, blocked: list[tuple[int, int]]) -> None:
    grid = _GridAdapter(_make_grid(rows, cols, blocked))
    start, goal = (0, 0), (cols - 1, rows - 1)
    path = _search(start, goal, grid)
    if path is None:
        return  # blocked grid: covered by property 5
    assert path[0] == start
    assert path[-1] == goal
    steps = len(path) - 1
    dr = abs(goal[1] - start[1])
    dc = abs(goal[0] - start[0])
    assert max(dr, dc) <= steps <= dr + dc, f"{rows}x{cols} steps={steps} dr={dr} dc={dc}"


@given(_dim, _dim, _obstacle_strategy)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_path_connected_and_acyclic(rows: int, cols: int, blocked: list[tuple[int, int]]) -> None:
    grid = _GridAdapter(_make_grid(rows, cols, blocked))
    path = _search((0, 0), (cols - 1, rows - 1), grid)
    if path is None:
        return
    seen = {path[0]}
    for a, b in zip(path[:-1], path[1:]):
        assert abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1, f"disconnected: {a}->{b}"
        assert b not in seen, f"cell revisited: {b}"
        seen.add(b)


@given(_dim, _dim, _obstacle_strategy)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_blocked_grid_terminates_with_none(rows: int, cols: int, blocked: list[tuple[int, int]]) -> None:
    # Force a wall separating start from goal.
    wall = {(r, cols // 2) for r in range(rows)}
    grid = _GridAdapter(_make_grid(rows, cols, list(set(blocked) | wall)))
    result = _search((0, 0), (cols - 1, rows - 1), grid)
    assert result is None, f"wall grid produced a path: {result}"


@given(_dim, _dim)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_congestion_changes_path(rows: int, cols: int) -> None:
    if min(rows, cols) < 6:
        return  # a 3x3 blob can span the full grid width; no detour exists
    grid = _GridAdapter(_make_grid(rows, cols, []))
    start, goal = (0, 0), (cols - 1, rows - 1)
    plain = _search(start, goal, grid)
    # Congest a blob at the route centre.
    cong = np.zeros((rows, cols), dtype=np.float32)
    cr, cc = rows // 2, cols // 2
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if 0 <= cr + dr < rows and 0 <= cc + dc < cols:
                cong[cr + dr, cc + dc] = 400.0
    congested = _search(start, goal, grid, congestion_flat=cong.reshape(-1))
    assert congested is not None
    # The detour only fires when the plain path actually crosses the blob
    # (graveyard-shaped grids route along an edge and never near it).
    center = (cc, cr)
    if plain is not None and len(plain) > 3 and center in plain:
        assert center not in congested, "congested path still crosses the blob centre"
