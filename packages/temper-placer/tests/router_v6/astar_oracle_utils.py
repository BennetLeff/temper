"""
Dijkstra oracle for octile-weighted 2D grids.

Provides the computation-as-truth anchor for the A* validation suite.
Independently verifiable -- no dependency on ``astar_core.py``.

Reference Dijkstra with octile edge weights:
  - cardinal moves cost 1.0
  - diagonal moves cost sqrt(2) ~ 1.41421356

Smoke tests TS1-TS4 are inline and self-validating (R10).
"""

from __future__ import annotations

import heapq
import itertools
import math

import numpy as np

SQRT2: float = math.sqrt(2.0)
DIJKSTRA_MAX_CELLS: int = 900  # 30x30 gate (R9)

_DIRS_8: tuple[tuple[int, int], ...] = (
    (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1),
)


def _grid_shape(grid) -> tuple[int, int]:
    """Return (width_cells, height_cells) for a numpy array or OccupancyGrid."""
    if isinstance(grid, np.ndarray):
        return int(grid.shape[1]), int(grid.shape[0])
    return int(grid.width_cells), int(grid.height_cells)


def _cell_value(grid, x: int, y: int) -> int:
    """Return the cell value: 0=free, 1=obstacle, >1=net-owned (treated as free)."""
    if isinstance(grid, np.ndarray):
        return int(grid[y, x])
    return int(grid.grid[y, x])


def _is_free(grid, x: int, y: int, net_id: int = 0) -> bool:
    """Check if cell (x, y) is free (0 or owned by net)."""
    v = _cell_value(grid, x, y)
    return v == 0 or v == net_id


def _in_bounds(width: int, height: int, x: int, y: int) -> bool:
    return 0 <= x < width and 0 <= y < height


def _reconstruct_path(came_from: dict, current: tuple[int, int]) -> list[tuple[int, int]]:
    path: list[tuple[int, int]] = []
    while current is not None:
        path.append(current)
        current = came_from.get(current)
    path.reverse()
    return path


# @req(2026-06-28-001, R7): Dijkstra oracle implementation
def dijkstra_shortest_path(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid,
    net_id: int = 0,
) -> tuple[list[tuple[int, int]] | None, float]:
    """
    Dijkstra shortest path on an octile-weighted 2D grid.

    Args:
        start: (x, y) start coordinate.
        goal: (x, y) goal coordinate.
        grid: numpy 2D int8 array or OccupancyGrid.  0=free, 1=obstacle.
        net_id: cells with this value (>0) are treated as free.

    Returns:
        (path, cost) where path is a list of (x, y) cells, or
        (None, float('inf')) when unreachable.
    """
    width, height = _grid_shape(grid)

    if not _in_bounds(width, height, *start):
        return (None, float("inf"))
    if not _in_bounds(width, height, *goal):
        return (None, float("inf"))

    frontier: list[tuple[float, int, tuple[int, int]]] = []
    counter = itertools.count()
    heapq.heappush(frontier, (0.0, next(counter), start))

    g_score: dict[tuple[int, int], float] = {start: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while frontier:
        g, _, current = heapq.heappop(frontier)

        if g > g_score.get(current, float("inf")):
            continue

        if current == goal:
            return (_reconstruct_path(came_from, current), g)

        sx, sy = current
        for dx, dy in _DIRS_8:
            nx, ny = sx + dx, sy + dy
            if not _in_bounds(width, height, nx, ny):
                continue
            if not _is_free(grid, nx, ny, net_id):
                continue

            move_cost = SQRT2 if dx != 0 and dy != 0 else 1.0
            new_g = g + move_cost

            if new_g < g_score.get((nx, ny), float("inf")):
                g_score[(nx, ny)] = new_g
                came_from[(nx, ny)] = current
                heapq.heappush(frontier, (new_g, next(counter), (nx, ny)))

    return (None, float("inf"))


# @req(2026-06-28-001, R21): Heuristic admissibility checker needs cost-only
def dijkstra_cost_only(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid,
    net_id: int = 0,
) -> float:
    """Faster variant that stops at the goal and returns only the cost."""
    _, cost = dijkstra_shortest_path(start, goal, grid, net_id)
    return cost


# ---------------------------------------------------------------------------
# Smoke tests (TS1-TS4) -- self-validating oracle (R10)
# ---------------------------------------------------------------------------

import pytest


def _make_array(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> np.ndarray:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in (blocked or set()):
        arr[r, c] = 1
    return arr


def test_ts1_empty_3x3_straight():
    """TS1. Empty 3x3 straight path: (0,0)->(2,0) cost=2.0, len=3."""
    grid = _make_array(3, 3)
    path, cost = dijkstra_shortest_path((0, 0), (2, 0), grid)
    assert abs(cost - 2.0) < 1e-12, f"Expected cost 2.0, got {cost}"
    assert len(path) == 3, f"Expected 3 path cells, got {len(path)}"
    assert path[0] == (0, 0)
    assert path[-1] == (2, 0)
    for x, y in path:
        assert grid[y, x] == 0


def test_ts2_empty_3x3_diagonal():
    """TS2. Empty 3x3 diagonal: (0,0)->(2,2) cost = 2*sqrt(2)~2.828, len=3."""
    grid = _make_array(3, 3)
    path, cost = dijkstra_shortest_path((0, 0), (2, 2), grid)
    expected = 2.0 * SQRT2
    assert abs(cost - expected) < 1e-12, f"Expected {expected}, got {cost}"
    assert path[0] == (0, 0)
    assert path[-1] == (2, 2)


def test_ts3_unreachable_wall():
    """TS3. Wall separating start/goal -> (None, inf)."""
    grid = _make_array(5, 5, {(r, 2) for r in range(5)})
    path, cost = dijkstra_shortest_path((0, 0), (4, 4), grid)
    assert path is None
    assert math.isinf(cost)


def test_ts4_brute_force_3x3():
    """TS4. All 512 3x3 configs x all start/goal pairs verified via brute force.

    Brute force enumerates all 8-connected paths up to 6 hops (3x3 max hops = 6
    for a snake through all 9 cells). For each reachable pair Dijkstra cost
    must match the minimum brute-force cost.
    """
    total_checked = 0

    for occ_bits in range(512):
        blocked: set[tuple[int, int]] = set()
        for r in range(3):
            for c in range(3):
                bit_idx = r * 3 + c
                if occ_bits & (1 << bit_idx):
                    blocked.add((r, c))
        grid = _make_array(3, 3, blocked)

        free_cells = [(c, r) for r in range(3) for c in range(3) if grid[r, c] == 0]

        best_cost: dict[tuple, float] = {}
        for start in free_cells:
            visited_mask = 1 << (start[1] * 3 + start[0])
            queue: list[tuple[float, tuple[int, int], int]] = [(0.0, start, visited_mask)]
            while queue:
                min_idx = 0
                for i in range(1, len(queue)):
                    if queue[i][0] < queue[min_idx][0]:
                        min_idx = i
                cost, (x, y), mask = queue.pop(min_idx)

                key = (start, (x, y))
                current_best = best_cost.get(key, float("inf"))
                if cost >= current_best:
                    continue
                best_cost[key] = cost

                for dx, dy in _DIRS_8:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < 3 and 0 <= ny < 3):
                        continue
                    if grid[ny, nx] != 0:
                        continue
                    nbit = 1 << (ny * 3 + nx)
                    if mask & nbit:
                        continue
                    move_cost = SQRT2 if dx != 0 and dy != 0 else 1.0
                    queue.append((cost + move_cost, (nx, ny), mask | nbit))

        for i in range(len(free_cells)):
            for j in range(i + 1, len(free_cells)):
                s, g = free_cells[i], free_cells[j]
                d_path, d_cost = dijkstra_shortest_path(s, g, grid)
                b_cost = best_cost.get((s, g), float("inf"))
                if b_cost == float("inf"):
                    assert d_path is None, (
                        f"Config {occ_bits}: Dijkstra found path {s}->{g} "
                        f"but brute force says unreachable"
                    )
                else:
                    assert abs(d_cost - b_cost) < 1e-12, (
                        f"Config {occ_bits}: {s}->{g} Dijkstra={d_cost} brute={b_cost}"
                    )
                total_checked += 1

    assert total_checked > 0
