"""
Router V6: any-angle A* search (Theta* / Lazy Theta*) and their shared
line-of-sight primitive.

Part of temper-N6-U6 decomposition -- split from astar_core.py to bring
that module back under the repo's 1000-line cap (``tools/loc_cap_check.py``).
Theta* and Lazy Theta* both delegate their any-angle shortcut decision to
the Rust-backed LOS kernel (``_line_of_sight_rust``, proven bit-identical
to the retired Numba kernel and PBT-equal to the pure-Python reference),
falling back to ``_line_of_sight`` if the extension is missing, and share
the congestion-derivative early-abort constants below, so all three live
together here rather than splitting the line-of-sight check away from its
only two callers.
"""

from __future__ import annotations

import numpy as np

from temper_placer.router_v6.astar_core import _SAME_LAYER_DELTAS, in_bounds
from temper_placer.router_v6.astar_monitor import get_monitor_state

_LOS_BB_HITS: list[int] = [0]
_LOS_BB_FALLS_THROUGH: list[int] = [0]


def _line_of_sight_dispatch(p1, p2, grid, net_id: int) -> bool:
    """Bresenham LOS via the Rust kernel (cleanup C1), falling back to
    the pure-Python reference if ``temper_rust_router`` is missing."""
    from temper_placer.router_v6.astar_core_numba import _line_of_sight_rust

    try:
        return _line_of_sight_rust(p1, p2, grid, net_id)
    except ImportError:  # pragma: no cover -- extension missing/stale
        return _line_of_sight(p1, p2, grid, net_id)


def reset_los_bb_stats() -> None:
    _LOS_BB_HITS[0] = 0
    _LOS_BB_FALLS_THROUGH[0] = 0


def get_los_bb_stats() -> tuple[int, int]:
    return (_LOS_BB_HITS[0], _LOS_BB_FALLS_THROUGH[0])


def log_los_bb_stats() -> None:
    hits, falls = get_los_bb_stats()
    total = hits + falls
    if total > 0:
        rate = hits / total * 100
        print(f"LOS BB shortcut: {hits} hits / {total} total = {rate:.1f}% skip rate")
    else:
        print("LOS BB shortcut: no calls recorded")


def _line_of_sight(
    p1: tuple[int, int],
    p2: tuple[int, int],
    grid,
    net_id: int,
) -> bool:
    """
    Check if there's an unobstructed diagonal line between two grid points.

    Uses Bresenham's line algorithm to check all cells along the path.

    Args:
        p1: Start grid position (x, y)
        p2: End grid position (x, y)
        grid: Occupancy grid
        net_id: Net ID (cells with this ID are allowed)

    Returns:
        True if line is clear
    """
    x0, y0 = p1
    x1, y1 = p2

    # @req(2026-06-29-feat-los-bb, R1): BB empty shortcut
    #
    # Only take the shortcut when both endpoints are on-grid. A negative
    # coordinate makes ``min(...)``/``max(...)+1`` produce a negative slice
    # bound, which numpy interprets as counting from the end of the axis
    # rather than "off the front of the grid" -- silently sampling the
    # wrong region and reporting a false "clear" for an endpoint that is
    # actually out of bounds (see the p1=(0,0), p2=(0,-1) 2x2-grid repro
    # that motivated this guard). Deferring out-of-bounds endpoints to the
    # Bresenham loop below keeps a single source of truth for bounds
    # checking (``in_bounds()``) instead of duplicating that logic here.
    if in_bounds(x0, y0, grid.width_cells, grid.height_cells) and in_bounds(
        x1, y1, grid.width_cells, grid.height_cells
    ):
        bbox = grid.grid[min(y0, y1) : max(y0, y1) + 1, min(x0, x1) : max(x0, x1) + 1]
        if not np.any(bbox):
            _LOS_BB_HITS[0] += 1
            return True
        _LOS_BB_FALLS_THROUGH[0] += 1

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0

    while True:
        if not in_bounds(x, y, grid.width_cells, grid.height_cells):
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


_CONGESTION_CHECK_INTERVAL: int = 1000
_CONGESTION_GROWTH_THRESHOLD: int = 5
_CONGESTION_PLATEAU_STRIKES: int = 3


def _astar_search_lazy_theta_star(
    grid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
    enable_congestion_derivative: bool = True,
) -> list[tuple[int, int]] | None:
    """
    Lazy Theta* pathfinding.

    Optimizes Theta* by delaying the line-of-sight check until a node is expanded.
    This significantly reduces the number of geometric checks.

    Args:
        grid: Occupancy grid
        start_grid: Start position (grid coordinates)
        goal_grid: Goal position (grid coordinates)
        net_id: Net ID for unblocking own cells
        came_from_init: Optional initial came_from for warm-starting
        max_iter: Maximum node expansions before returning None (safety net).
            Default ``None`` = unlimited (backward-compatible).
        enable_congestion_derivative: When True, abort search early if
            frontier growth plateaus (fewer than 5 new cells per 1000
            expansions for 3 consecutive windows). Default True.

    Returns:
        Path as list of (x, y) grid cells, or None if no path
    """
    import math
    from heapq import heappop, heappush

    los_fn = _line_of_sight_dispatch

    # Priority queue: (f_score, counter, current_pos)
    counter = 0
    open_set: list = []
    heappush(open_set, (0.0, counter, start_grid))

    came_from = came_from_init.copy() if came_from_init else {}
    g_score = {start_grid: 0.0}
    closed_set = set()

    # Congestion derivative tracking
    _g_score_size_prev: int = 1  # start cell
    _plateau_count: int = 0

    def euclidean_dist(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def reconstruct_path(current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            # Handle start node case (came_from[start] not in came_from)
            if current == start_grid:
                break
            path.append(current)
        path.reverse()
        return path

    while open_set:
        f_cost, _, current = heappop(open_set)

        if current in closed_set:
            continue

        # LAZY CHECK: Validate LOS only when expanding
        parent = came_from.get(current)

        # Runtime monitor: f-cost monotonicity for Lazy Theta*
        _mon_lazy = get_monitor_state()
        if _mon_lazy is not None:
            _mon_lazy.record_pop(current, float(f_cost))
        if parent and not los_fn(parent, current, grid, net_id):
            # LOS Failed.
            # Standard Lazy Theta* strategy: find a valid parent from closed neighbors
            # This is "Vertex A adjustment" from the paper.
            # However, since we populate using optimistic parents, the 'current'
            # node might not have a valid parent in the closed set that reaches it
            # directly via LOS.
            # Simplified strategy: If LOS from parent fails, treat it as an A* node
            # (but we didn't store the A* parent).
            # Re-evaluate parent from neighbors in closed set.

            best_parent = None
            best_g = float("inf")

            # Check 8-connected neighbors
            cx, cy = current
            for dx, dy in _SAME_LAYER_DELTAS:
                nx, ny = cx + dx, cy + dy
                neighbor = (nx, ny)

                if neighbor in closed_set and neighbor in g_score:
                    # Cost is just distance (1 or 1.414)
                    step_cost = euclidean_dist(neighbor, current)
                    new_g = g_score[neighbor] + step_cost
                    if new_g < best_g:
                        best_g = new_g
                        best_parent = neighbor

            if best_parent:
                came_from[current] = best_parent
                g_score[current] = best_g
                # Continue expansion with corrected parent
            else:
                # Should not happen if we reached 'current'
                continue

        if current == goal_grid:
            return reconstruct_path(current)

        closed_set.add(current)

        if max_iter is not None and len(closed_set) >= max_iter:
            return None

        if enable_congestion_derivative and len(closed_set) % _CONGESTION_CHECK_INTERVAL == 0:
            new_cells = len(g_score) - _g_score_size_prev
            if new_cells < _CONGESTION_GROWTH_THRESHOLD:
                _plateau_count += 1
                if _plateau_count >= _CONGESTION_PLATEAU_STRIKES:
                    return None
            else:
                _plateau_count = 0
            _g_score_size_prev = len(g_score)

        # Get 8-connected neighbors
        cx, cy = current
        neighbors = []
        for dx, dy in _SAME_LAYER_DELTAS:
            nx, ny = cx + dx, cy + dy
            if in_bounds(nx, ny, grid.width_cells, grid.height_cells):
                cell_value = grid.grid[ny, nx]
                if cell_value == 0 or cell_value == net_id:
                    neighbors.append((nx, ny))

        for neighbor in neighbors:
            if neighbor in closed_set:
                continue

            # LAZY OPTIMIZATION: Always assume LOS from parent(current) to neighbor
            # This makes the "parent" pointer jump multiple steps.
            # parent(neighbor) = parent(current)

            grandparent = came_from.get(current)

            # Path 1: Optimistic (grandparent -> neighbor)
            if grandparent:
                tentative_g_lazy = g_score[grandparent] + euclidean_dist(grandparent, neighbor)
                path_source_lazy = grandparent
            else:
                # Start node has no parent
                tentative_g_lazy = float("inf")
                path_source_lazy = None

            # Path 2: A* (current -> neighbor) - always valid if adjacent
            tentative_g_astar = g_score[current] + euclidean_dist(current, neighbor)

            # Choose best (usually optimistic)
            # Standard Lazy Theta* typically just picks the optimistic one if better.
            # But we must ensure g-values are consistent.

            if grandparent and tentative_g_lazy < tentative_g_astar:
                tentative_g = tentative_g_lazy
                path_source = path_source_lazy
            else:
                tentative_g = tentative_g_astar
                path_source = current

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = path_source
                g_score[neighbor] = tentative_g
                f_score = tentative_g + euclidean_dist(neighbor, goal_grid)
                counter += 1
                heappush(open_set, (f_score, counter, neighbor))

    return None


def _astar_search_theta_star(
    grid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
    enable_congestion_derivative: bool = True,
) -> list[tuple[int, int]] | None:
    """
    Theta* pathfinding with any-angle paths.

    Key difference from A*: When expanding a neighbor, checks if parent
    of current has line-of-sight to neighbor. If yes, connects parent
    directly to neighbor (skipping current), creating diagonal shortcuts.

    Args:
        grid: Occupancy grid
        start_grid: Start position (grid coordinates)
        goal_grid: Goal position (grid coordinates)
        net_id: Net ID for unblocking own cells
        came_from_init: Optional initial came_from for warm-starting
        max_iter: Maximum node expansions before returning None (safety net).
            Default ``None`` = unlimited (backward-compatible).
        enable_congestion_derivative: When True, abort search early if
            frontier growth plateaus (fewer than 5 new cells per 1000
            expansions for 3 consecutive windows). Default True.

    Returns:
        Path as list of (x, y) grid cells, or None if no path
    """
    import math
    from heapq import heappop, heappush

    los_fn = _line_of_sight_dispatch

    # Priority queue: (f_score, counter, current_pos)
    counter = 0
    open_set: list = []
    heappush(open_set, (0.0, counter, start_grid))

    came_from = came_from_init.copy() if came_from_init else {}
    g_score = {start_grid: 0.0}
    closed_set = set()

    # Congestion derivative tracking
    _g_score_size_prev: int = 1  # start cell
    _plateau_count: int = 0

    def euclidean_dist(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def reconstruct_path(current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    while open_set:
        _, _, current = heappop(open_set)

        if current in closed_set:
            continue

        if current == goal_grid:
            return reconstruct_path(current)

        closed_set.add(current)

        if max_iter is not None and len(closed_set) >= max_iter:
            return None

        if enable_congestion_derivative and len(closed_set) % _CONGESTION_CHECK_INTERVAL == 0:
            new_cells = len(g_score) - _g_score_size_prev
            if new_cells < _CONGESTION_GROWTH_THRESHOLD:
                _plateau_count += 1
                if _plateau_count >= _CONGESTION_PLATEAU_STRIKES:
                    return None
            else:
                _plateau_count = 0
            _g_score_size_prev = len(g_score)

        # Get 8-connected neighbors
        cx, cy = current
        neighbors = []
        for dx, dy in _SAME_LAYER_DELTAS:
            nx, ny = cx + dx, cy + dy
            if in_bounds(nx, ny, grid.width_cells, grid.height_cells):
                cell_value = grid.grid[ny, nx]
                if cell_value == 0 or cell_value == net_id:
                    neighbors.append((nx, ny))

        for neighbor in neighbors:
            if neighbor in closed_set:
                continue

            # THETA* OPTIMIZATION: Check line-of-sight from parent
            parent = came_from.get(current)
            if parent and los_fn(parent, neighbor, grid, net_id):
                # Path 2: parent -> neighbor (shortcut)
                tentative_g = g_score[parent] + euclidean_dist(parent, neighbor)
                path_source = parent
            else:
                # Path 1: current -> neighbor (standard A*)
                tentative_g = g_score[current] + euclidean_dist(current, neighbor)
                path_source = current

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = path_source
                g_score[neighbor] = tentative_g
                f_score = tentative_g + euclidean_dist(neighbor, goal_grid)
                counter += 1
                heappush(open_set, (f_score, counter, neighbor))

    return None  # No path found
