"""Differential tests: Rust Theta*/Lazy Theta* kernels vs the pre-migration
pure-Python reference (``router_v6/_astar_theta_star.py``).

The A*/Theta* cluster (Wave 4) migrates ``router_v6/_astar_theta_star.py``
to ``temper-rust-router-core`` (``theta_star.rs``), exposed through
``temper_rust_router``:

- ``_astar_search_theta_star`` — pinned via ``theta_star_search_py``
  (``lazy=False``) against a VERBATIM copy of the pre-migration function
  (``_oracle_astar_search_theta_star``).
- ``_astar_search_lazy_theta_star`` — pinned via ``theta_star_search_py``
  (``lazy=True``) against ``_oracle_astar_search_lazy_theta_star``.
- ``_line_of_sight`` — the shared Bresenham primitive, copied verbatim as
  ``_oracle_line_of_sight``; the Rust search kernels run the same Bresenham
  internally.  The pure-Python BB-shortcut fast path is boolean-neutral
  (it only short-circuits a bbox that is entirely free, where Bresenham
  would also return True), so omitting it changes no search result.

All comparisons assert exact path cell-sequence equality (or both-``None``).
The searches expose no floating-point result, so there is no ``float.hex()``
comparison here: the only floats are Euclidean distances over integer cell
coordinates, ``sqrt(dx*dx + dy*dy)`` with exact integer operands (catalog
class B7 — integer arithmetic is exact and the double conversion is exact
below 2^53, so Rust and CPython agree bit-for-bit).

Determinism note: the Python frontier is a heapq of ``(f_score, counter,
node)`` tuples where ``counter`` is a per-push incrementing integer — that
is the exact tie-break that makes the search deterministic, and it is what
the differential must pin.  The Rust kernel reproduces it exactly: a binary
min-heap ordered by ``(f_score, counter)`` (unique keys, so pop order is the
sorted key order) and the same neighbor-expansion order
(``_SAME_LAYER_DELTAS`` = E, S, W, N, SE, SW, NW, NE).
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import numpy as np

from tests.router_v6._pending_rust import missing_symbols, rust

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from _astar_theta_star.py AS
# COMMITTED before the Wave-4 migration; do not edit — they are the
# reference).
# ---------------------------------------------------------------------------

# Shared by the oracles.  In the pre-migration module these were imported
# from astar_core.py (`in_bounds`, `_SAME_LAYER_DELTAS`) or defined in the
# module itself (`_CONGESTION_*`).  They are reproduced HERE, with the
# pre-migration names, so the copied function bodies below resolve them
# verbatim and this file imports no module from `temper_placer` at all —
# the differential must not depend on the (unstable, concurrently-rebuilt)
# shared extension environment beyond the kernel under test.
_SAME_LAYER_DELTAS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 0),
    (0, -1),
    (-1, 0),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)

_CONGESTION_CHECK_INTERVAL: int = 1000
_CONGESTION_GROWTH_THRESHOLD: int = 5
_CONGESTION_PLATEAU_STRIKES: int = 3


def in_bounds(x: int, y: int, width_cells: int, height_cells: int) -> bool:
    return 0 <= x < width_cells and 0 <= y < height_cells


def get_monitor_state():
    """Runtime-monitor probe — always inactive in this differential.

    The pre-migration search functions call this once per pop; the real
    implementation (astar_monitor.get_monitor_state) is thread-local state
    that is only ever set inside an ``astar_monitor()`` context.  No
    differential run opens one, so ``None`` is the exact value the oracle
    would observe — reproduced here to keep the file hermetic.
    """
    return None

_LOS_BB_HITS: list[int] = [0]
_LOS_BB_FALLS_THROUGH: list[int] = [0]


def _oracle_line_of_sight_dispatch(p1, p2, grid, net_id: int) -> bool:
    """Bresenham LOS via the pure-Python reference.

    In the pre-migration module this bound ``_line_of_sight_dispatch``,
    which routed through the Rust ``line_of_sight_py`` kernel when the
    extension was loaded.  The differential must not let a Rust arm
    contaminate the oracle, so here the dispatch IS the pure-Python
    reference (boolean-identical to the Rust LOS; the search kernels'
    LOS calls are already validated equal on randomized pairs).
    """
    return _oracle_line_of_sight(p1, p2, grid, net_id)


def _oracle_line_of_sight(
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


def _oracle_astar_search_lazy_theta_star(
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

    los_fn = _oracle_line_of_sight_dispatch

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


def _oracle_astar_search_theta_star(
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

    los_fn = _oracle_line_of_sight_dispatch

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


# ---------------------------------------------------------------------------
# Rust arm adapter — the only place this file's knowledge of the Rust side
# lives (pending-Rust convention: lazy resolution, one named failure per
# missing symbol while red).
# ---------------------------------------------------------------------------

_RUST_MODULE = "temper_rust_router"
_RUST_SYMBOL = "theta_star_search_py"


class _GridAdapter:
    """Minimal OccupancyGrid-compatible view of a numpy occupancy array."""

    def __init__(self, arr: np.ndarray) -> None:
        self.grid = arr
        self.height_cells, self.width_cells = arr.shape


def _rust_theta_star_search(
    arr: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
    enable_congestion_derivative: bool = True,
    lazy: bool = False,
) -> list[tuple[int, int]] | None:
    """Run the Rust Theta* kernel and convert cell indices back to (x, y)."""
    fn = rust(_RUST_MODULE, _RUST_SYMBOL)
    grid_bytes = np.ascontiguousarray(arr, dtype=np.int8).tobytes()
    height, width = arr.shape
    start_idx = start[1] * width + start[0]
    goal_idx = goal[1] * width + goal[0]
    init = None
    if came_from_init:
        init = [(p[1] * width + p[0], q[1] * width + q[0]) for p, q in came_from_init.items()]
    idxs = fn(
        grid_bytes,
        width,
        height,
        start_idx,
        goal_idx,
        net_id,
        init,
        max_iter,
        enable_congestion_derivative,
        lazy,
    )
    if not idxs:
        return None
    return [(int(i % width), int(i // width)) for i in idxs]


def _compare(
    arr: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    *,
    net_id: int = 0,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
    enable_congestion_derivative: bool = True,
    lazy: bool = False,
    ctx: str = "",
) -> None:
    """Assert the pure-Python oracle and the Rust kernel agree bit-exactly."""
    grid = _GridAdapter(arr)
    oracle = (
        _oracle_astar_search_lazy_theta_star
        if lazy
        else _oracle_astar_search_theta_star
    )(
        grid,
        start,
        goal,
        net_id,
        came_from_init,
        max_iter,
        enable_congestion_derivative,
    )
    result = _rust_theta_star_search(
        arr,
        start,
        goal,
        net_id,
        came_from_init,
        max_iter,
        enable_congestion_derivative,
        lazy,
    )
    assert oracle == result, (
        f"{ctx or 'differential'}: oracle {oracle!r} != rust {result!r} "
        f"on {arr.shape} net_id={net_id} start={start} goal={goal} "
        f"max_iter={max_iter} cfd={enable_congestion_derivative} lazy={lazy} "
        f"came_from_init={came_from_init}"
    )


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> np.ndarray:
    """2D occupancy grid: 0 = free, 1 = blocked."""
    arr = np.zeros((rows, cols), dtype=np.int8)
    for c, r in blocked or set():
        if 0 <= r < rows and 0 <= c < cols:
            arr[r, c] = 1
    return arr


def test_rust_symbols_exist() -> None:
    assert missing_symbols(_RUST_MODULE, (_RUST_SYMBOL,)) == []


# ---------------------------------------------------------------------------
# Randomized differential corpus — both variants, both reachable/blocked
# outcomes, net-id ownership, negative sentinels.
# ---------------------------------------------------------------------------


def test_differential_random_obstacles() -> None:
    rng = random.Random(20260808)
    compared = 0
    for trial in range(120):
        rows = rng.choice([4, 6, 8, 12, 20])
        cols = rng.choice([4, 6, 10, 16, 24])
        density = rng.choice([0.0, 0.05, 0.15, 0.3, 0.45])
        arr = _make_grid(rows, cols)
        for y in range(rows):
            for x in range(cols):
                if rng.random() < density:
                    arr[y, x] = 1
        start = (rng.randrange(cols), rng.randrange(rows))
        goal = (rng.randrange(cols), rng.randrange(rows))
        arr[start[1], start[0]] = 0
        arr[goal[1], goal[0]] = 0
        net_id = rng.choice([0, -1, 0, 3])
        cfd = rng.choice([True, False])
        for lazy in (False, True):
            _compare(
                arr,
                start,
                goal,
                net_id=net_id,
                enable_congestion_derivative=cfd,
                lazy=lazy,
                ctx=f"random trial {trial}",
            )
            compared += 1
    assert compared == 240


def test_differential_negative_sentinel_grid() -> None:
    """Static-obstacle -1 sentinels: blocked for net_id=0, open for net_id=-1."""
    rng = random.Random(7)
    arr = _make_grid(15, 15)
    for _ in range(60):
        arr[rng.randrange(15), rng.randrange(15)] = -1
    arr[0, 0] = 0
    arr[14, 14] = 0
    for lazy in (False, True):
        _compare(arr, (0, 0), (14, 14), net_id=0, lazy=lazy, ctx="neg sentinel net0")
        _compare(arr, (0, 0), (14, 14), net_id=-1, lazy=lazy, ctx="neg sentinel net-1")


def test_differential_net_id_ownership() -> None:
    """A net-owned strip is open to its own net, closed to everyone else."""
    arr = np.zeros((12, 12), dtype=np.int8)
    arr[6, 3:10] = 3  # net 3 owns the middle row
    for lazy in (False, True):
        # net 3 may cross its strip; net 0 must detour around it.
        _compare(arr, (0, 6), (11, 6), net_id=3, lazy=lazy, ctx="own strip")
        _compare(arr, (0, 6), (11, 6), net_id=0, lazy=lazy, ctx="foreign strip")


# ---------------------------------------------------------------------------
# Crafted edge cases
# ---------------------------------------------------------------------------


def test_differential_open_grid_both_variants() -> None:
    arr = _make_grid(20, 25)
    for lazy in (False, True):
        _compare(arr, (0, 0), (24, 19), lazy=lazy, ctx="open grid")


def test_differential_start_equals_goal() -> None:
    arr = _make_grid(8, 8)
    for lazy in (False, True):
        _compare(arr, (4, 3), (4, 3), lazy=lazy, ctx="start==goal")


def test_differential_blocked_start_and_goal() -> None:
    arr = _make_grid(6, 6)
    arr[0, 0] = 1  # blocked start
    arr[5, 5] = 1  # blocked goal
    for lazy in (False, True):
        _compare(arr, (0, 0), (5, 5), lazy=lazy, ctx="blocked start/goal")


def test_differential_full_wall_no_path() -> None:
    arr = _make_grid(30, 30)
    arr[:, 15] = 1
    for lazy in (False, True):
        _compare(arr, (0, 0), (29, 29), lazy=lazy, ctx="full wall")


def test_differential_tiny_grids_exhaustive() -> None:
    """Exhaustive over every 2x2 occupancy configuration (both variants)."""
    for occ_bits in range(16):
        arr = _make_grid(2, 2)
        for r in range(2):
            for c in range(2):
                if occ_bits & (1 << (r * 2 + c)):
                    arr[r, c] = 1
        free = [(c, r) for r in range(2) for c in range(2) if arr[r, c] == 0]
        for i in range(len(free)):
            for j in range(i + 1, len(free)):
                for lazy in (False, True):
                    _compare(arr, free[i], free[j], lazy=lazy, ctx=f"2x2 cfg={occ_bits}")


def test_differential_3x3_exhaustive() -> None:
    """Exhaustive over every 3x3 occupancy configuration (both variants)."""
    for occ_bits in range(512):
        arr = _make_grid(3, 3)
        for r in range(3):
            for c in range(3):
                if occ_bits & (1 << (r * 3 + c)):
                    arr[r, c] = 1
        free = [(c, r) for r in range(3) for c in range(3) if arr[r, c] == 0]
        for i in range(len(free)):
            for j in range(i + 1, len(free)):
                for lazy in (False, True):
                    _compare(arr, free[i], free[j], lazy=lazy, ctx=f"3x3 cfg={occ_bits}")


def test_differential_one_row_and_one_col() -> None:
    arr = _make_grid(1, 9)
    for lazy in (False, True):
        _compare(arr, (0, 0), (8, 0), lazy=lazy, ctx="1x9")
    arr = _make_grid(9, 1)
    for lazy in (False, True):
        _compare(arr, (0, 0), (0, 8), lazy=lazy, ctx="9x1")
    arr = _make_grid(1, 1)
    arr[0, 0] = 0
    for lazy in (False, True):
        _compare(arr, (0, 0), (0, 0), lazy=lazy, ctx="1x1")


def test_differential_max_iter_bounds() -> None:
    """Tiny max_iter caps: both sides must agree on when the cap fires."""
    arr = _make_grid(12, 12)
    for lazy in (False, True):
        for cap in (1, 2, 3, 10):
            _compare(
                arr,
                (0, 0),
                (11, 11),
                max_iter=cap,
                lazy=lazy,
                ctx=f"max_iter={cap}",
            )
    # start==goal returns immediately even under a 1-iteration cap
    for lazy in (False, True):
        _compare(arr, (0, 0), (0, 0), max_iter=1, lazy=lazy, ctx="start==goal cap=1")


def test_differential_came_from_init() -> None:
    """Warm-start came_from: seeded parent chains must survive identically.

    The corpus deliberately never maps the START cell: a warm-started parent
    for start that is absent from g_score makes the pre-migration Python
    raise KeyError (``g_score[parent]``), a divergence recorded in
    ``temper-rust-router-core/VERIFICATION.md`` rather than papered over.
    """
    rng = random.Random(99)
    for trial in range(40):
        rows, cols = rng.choice([5, 8, 12]), rng.choice([5, 8, 12])
        arr = _make_grid(rows, cols)
        for y in range(rows):
            for x in range(cols):
                if rng.random() < 0.2:
                    arr[y, x] = 1
        start = (rng.randrange(cols), rng.randrange(rows))
        goal = (rng.randrange(cols), rng.randrange(rows))
        if start == goal:
            continue
        arr[start[1], start[0]] = 0
        arr[goal[1], goal[0]] = 0
        init: dict[tuple[int, int], tuple[int, int]] = {}
        for _ in range(rng.randrange(1, 6)):
            child = (rng.randrange(cols), rng.randrange(rows))
            parent = (rng.randrange(cols), rng.randrange(rows))
            if child == start or child == goal:
                continue
            init[child] = parent
        for lazy in (False, True):
            _compare(
                arr,
                start,
                goal,
                net_id=0,
                came_from_init=init,
                lazy=lazy,
                ctx=f"came_from_init trial {trial}",
            )
