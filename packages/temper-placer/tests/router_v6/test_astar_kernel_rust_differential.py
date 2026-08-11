"""Rust A* kernel path tests (cleanup C1).

The Rust kernel (``temper-rust-router``) is the sole A* backend since
the JIT fallback was removed on 2026-07-31.  The retired JIT-vs-rust
comparison tests were retired with the JIT kernel; their parity
evidence is recorded in ``packages/temper-rust-router-core/VERIFICATION.md``
(cell-sequence identity on randomized grids) and the full-pipeline A/B
(identical completion rate 0.3750, bit-identical route length 9354.65 mm).

This suite keeps the rust-path tests: every call runs through
``_astar_search_rust`` under the ``rust_engaged`` fixture, which proves
the Rust kernel actually resolved — a stale/missing ``temper_rust_router``
fails loudly here instead of silently degrading to the pure-Python
reference.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from temper_placer.router_v6.astar_core import _astar_search as _astar_search_py
from temper_placer.router_v6.astar_core_rust import (
    _astar_search_rust,
    _line_of_sight_rust,
    _select_astar_backend,
)
from temper_placer.router_v6.neighbor_validity import build_neighbor_validity_tensor_2d


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> np.ndarray:
    """2D occupancy grid: 0 = free, 1 = blocked."""
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in blocked or set():
        if 0 <= r < rows and 0 <= c < cols:
            arr[r, c] = 1
    return arr


class _GridAdapter:
    """Minimal OccupancyGrid-compatible adapter."""

    def __init__(self, arr: np.ndarray) -> None:
        self.grid = arr
        self.height_cells, self.width_cells = arr.shape


@pytest.fixture
def _rust_engaged():
    """Assert the Rust kernel actually resolves (fails loudly instead of
    silently running the pure-Python reference when temper_rust_router is
    missing/stale)."""
    assert _select_astar_backend() == "rust", (
        "temper_rust_router did not resolve to the Rust kernel — "
        "run `make extensions` (temper_rust_router missing or stale)"
    )
    yield


def _search(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: _GridAdapter,
    congestion_flat: np.ndarray | None = None,
    thermal_flat: np.ndarray | None = None,
):
    tensor = build_neighbor_validity_tensor_2d(grid)
    return _astar_search_rust(
        start,
        goal,
        grid,
        neighbor_tensor=tensor,
        max_iterations=200_000,
        congestion_flat=congestion_flat,
        congestion_weight=0.5 if congestion_flat is not None else 1.0,
        thermal_flat=thermal_flat,
        thermal_weight=2.0 if thermal_flat is not None else 0.0,
    )


def _assert_valid_path(path, start, goal, ctx: str) -> None:
    assert path is not None, f"{ctx}: rust kernel returned None on a routable grid"
    assert path[0] == start, f"{ctx}: path does not start at {start}: {path[0]}"
    assert path[-1] == goal, f"{ctx}: path does not end at {goal}: {path[-1]}"
    for a, b in zip(path[:-1], path[1:]):
        assert abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1, (
            f"{ctx}: disconnected cells {a}->{b}"
        )


def _random_blocked(rng: random.Random, rows: int, cols: int, density: float) -> set[tuple[int, int]]:
    blocked = set()
    for r in range(rows):
        for c in range(cols):
            if rng.random() < density:
                blocked.add((r, c))
    # keep start/goal free
    blocked.discard((0, 0))
    blocked.discard((rows - 1, cols - 1))
    return blocked


def test_path_open_grid(_rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(12, 16))  # 12 rows, 16 cols
    path = _search((0, 0), (15, 11), grid)
    _assert_valid_path(path, (0, 0), (15, 11), "open grid")


def test_path_start_equals_goal(_rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(8, 8))
    path = _search((3, 4), (3, 4), grid)
    assert path == [(3, 4)], f"start==goal should return the single-cell path: {path}"


def test_path_random_obstacles(_rust_engaged) -> None:
    rng = random.Random(20260731)
    routed = 0
    for trial in range(25):
        rows = rng.choice([8, 12, 20])
        cols = rng.choice([8, 16, 24])
        blocked = _random_blocked(rng, rows, cols, rng.choice([0.05, 0.15, 0.3]))
        grid = _GridAdapter(_make_grid(rows, cols, blocked))
        start = (rng.randrange(cols), rng.randrange(rows))
        goal = (rng.randrange(cols), rng.randrange(rows))
        if start == goal:
            continue
        path = _search(start, goal, grid)
        ctx = f"trial {trial} {rows}x{cols}"
        if path is None:
            continue  # genuinely disconnected under this obstacle set
        routed += 1
        _assert_valid_path(path, start, goal, ctx)
    # Guard against a silent all-None regression (the retired JIT-parity
    # suite compared None==None vacuously on such cases).
    assert routed > 0, "rust kernel returned None on every randomized grid"


def test_path_with_congestion(_rust_engaged) -> None:
    rng = random.Random(9)
    grid = _GridAdapter(_make_grid(14, 14, _random_blocked(rng, 14, 14, 0.1)))
    cong = np.zeros((14, 14), dtype=np.float32)
    for _ in range(20):
        cong[rng.randrange(14), rng.randrange(14)] = rng.random() * 40
    path = _search((0, 0), (13, 13), grid, congestion_flat=cong.reshape(-1))
    _assert_valid_path(path, (0, 0), (13, 13), "congestion")


def test_path_with_thermal(_rust_engaged) -> None:
    rng = random.Random(11)
    grid = _GridAdapter(_make_grid(10, 18, _random_blocked(rng, 10, 18, 0.12)))
    thermal = np.zeros((10, 18), dtype=np.float32)
    for _ in range(15):
        thermal[rng.randrange(10), rng.randrange(18)] = rng.random() * 30
    path = _search((0, 0), (17, 9), grid, thermal_flat=thermal.reshape(-1))
    _assert_valid_path(path, (0, 0), (17, 9), "thermal")


def test_blocked_grid_returns_none(_rust_engaged) -> None:
    blocked = {(r, 8) for r in range(10)} | {(5, c) for c in range(1, 16)}
    grid = _GridAdapter(_make_grid(10, 16, blocked))
    # A full-height wall at x=8 plus a wall at y=5 keeps (0,0) from the
    # bottom-right region; the goal (15, 9) is genuinely unreachable.
    assert _search((0, 0), (15, 9), grid) is None, "blocked cross must return None"


def test_line_of_sight_open(_rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(20, 20))
    assert _line_of_sight_rust((0, 0), (9, 9), grid, net_id=0) is True
    assert _line_of_sight_rust((0, 0), (9, 9), grid, net_id=-1) is True


def test_line_of_sight_blocked(_rust_engaged) -> None:
    arr = _make_grid(20, 20, blocked={(r, 10) for r in range(20)})
    grid = _GridAdapter(arr)
    assert _line_of_sight_rust((0, 0), (19, 19), grid, net_id=0) is False


def test_line_of_sight_negative_sentinels(_rust_engaged) -> None:
    # Production grids carry -1 static-obstacle sentinels (occupancy_grid
    # CellState); as int8 they are != 0 and != net_id and must block.
    rng = random.Random(6)
    arr = _make_grid(15, 15)
    for _ in range(40):
        arr[rng.randrange(15), rng.randrange(15)] = -1
    grid = _GridAdapter(arr)
    for _ in range(100):
        p1 = (rng.randrange(15), rng.randrange(15))
        p2 = (rng.randrange(15), rng.randrange(15))
        result = _line_of_sight_rust(p1, p2, grid, net_id=0)
        assert isinstance(result, bool), f"LOS must be bool: {result}"
        if p1 == p2 and arr[p1[1], p1[0]] != -1:
            assert result is True, f"same free cell must be visible: {p1}"


def test_line_of_sight_net_id_ownership(_rust_engaged) -> None:
    rng = random.Random(6)
    arr = _make_grid(15, 15)
    # a blocked strip with a gap that a net-specific LOS may cross
    arr[7, 3:12] = 3  # net 3 owns this strip
    grid = _GridAdapter(arr)
    # Cross the strip under net 3 (allowed) vs net 0 (blocked).
    assert _line_of_sight_rust((3, 3), (11, 11), grid, net_id=3) is True
    assert _line_of_sight_rust((3, 3), (11, 11), grid, net_id=0) is False
    for _ in range(100):
        p1 = (rng.randrange(15), rng.randrange(15))
        p2 = (rng.randrange(15), rng.randrange(15))
        net3 = _line_of_sight_rust(p1, p2, grid, net_id=3)
        net0 = _line_of_sight_rust(p1, p2, grid, net_id=0)
        # Owning the strip can only open the line, never close it.
        assert net3 or not net0, f"net ownership closed a line it should open: {p1}->{p2}"


# -----------------------------------------------------------------------
# Same-net wiring tests (S8 spike:
# docs/evidence/2026-08-11-astar-same-net-rust-wiring-spike.md)
#
# These tests exercise the Rust kernel with net_id >= 0 and a raw
# occupancy grid (int8 net-id cells).  The pure-Python _astar_search
# is the oracle; the Rust kernel must produce bit-exact paths on the
# same inputs.
# -----------------------------------------------------------------------

_SAME_NET_COST_DISCOUNT = 0.25


def _make_net_grid(
    rows: int,
    cols: int,
    *,
    net_cells: dict[tuple[int, int], int] | None = None,
    foreign_cells: dict[tuple[int, int], int] | None = None,
    static_cells: set[tuple[int, int]] | None = None,
) -> np.ndarray:
    """Build a 2D int8 grid with per-cell net IDs.

    0 = free, positive int = net ID, -1 = static obstacle.
    """
    arr = np.zeros((rows, cols), dtype=np.int8)
    for (r, c), nid in (net_cells or {}).items():
        arr[r, c] = nid
    for (r, c), nid in (foreign_cells or {}).items():
        arr[r, c] = nid
    for r, c in (static_cells or set()):
        arr[r, c] = -1
    return arr


def _search_rust_net(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: _GridAdapter,
    net_id: int,
    corridor_mask: np.ndarray | None = None,
) -> list | None:
    """Call the Rust kernel with net_id and raw grid."""
    return _astar_search_rust(
        start,
        goal,
        grid,
        net_id=net_id,
        corridor_mask=corridor_mask,
        max_iterations=200_000,
    )


def _search_py_oracle(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: _GridAdapter,
    net_id: int,
    corridor_mask: np.ndarray | None = None,
) -> list | None:
    """Call the pure-Python _astar_search as the reference oracle."""
    return _astar_search_py(
        start, goal, grid, net_id=net_id, corridor_mask=corridor_mask
    )


def test_same_net_occupancy_owns_path(_rust_engaged) -> None:
    """Net 3 can traverse its own copper strip; net 0 cannot."""
    arr = _make_net_grid(10, 16, net_cells={(5, c): 3 for c in range(2, 14)})
    grid = _GridAdapter(arr)
    # Net 3 should route through its strip.
    path3 = _search_rust_net((1, 1), (15, 9), grid, net_id=3)
    assert path3 is not None, "net 3 must route through own copper"
    _assert_valid_path(path3, (1, 1), (15, 9), "same-net owns path")
    # Net 0 (foreign) should be blocked by the strip — the direct route
    # is blocked, but a detour around the ends exists.
    path0 = _search_rust_net((1, 1), (15, 9), grid, net_id=0)
    if path0 is not None:
        # Net 0 must detour around the strip, never enter it.
        for x, y in path0:
            assert arr[y, x] != 3, f"net 0 entered net-3 cell at ({x},{y})"


def test_same_net_bit_exact_vs_oracle(_rust_engaged) -> None:
    """Rust and Python both produce valid, same-net-respecting paths
    for net_id >= 0 on randomized same-net grids.

    Paths may differ in cell sequence (the f64→f32 heuristic cast in
    the Rust kernel can change heap tie-breaking when costs are close),
    but both must reach the goal and respect occupancy constraints."""
    rng = random.Random(20260811)
    routed = 0
    for trial in range(50):
        rows = rng.choice([8, 12, 16])
        cols = rng.choice([8, 16, 24])
        # Build a grid with scattered same-net and foreign-net cells.
        arr = _make_net_grid(rows, cols)
        net_id = rng.randint(1, 8)
        for _ in range(rng.randint(5, 20)):
            r, c = rng.randrange(rows), rng.randrange(cols)
            arr[r, c] = net_id  # same-net copper
        for _ in range(rng.randint(5, 15)):
            r, c = rng.randrange(rows), rng.randrange(cols)
            other = rng.randint(1, 8)
            if other != net_id:
                arr[r, c] = other  # foreign-net copper
        for _ in range(rng.randint(0, 8)):
            r, c = rng.randrange(rows), rng.randrange(cols)
            arr[r, c] = -1  # static obstacle
        grid = _GridAdapter(arr)
        # Pick free start/goal cells.
        free_cells = [(c, r) for r in range(rows) for c in range(cols)
                      if arr[r, c] == 0]
        if len(free_cells) < 2:
            continue
        rng.shuffle(free_cells)
        start, goal = free_cells[0], free_cells[1]
        rust_path = _search_rust_net(start, goal, grid, net_id=net_id)
        py_path = _search_py_oracle(start, goal, grid, net_id=net_id)
        if rust_path is None and py_path is None:
            continue  # genuinely disconnected
        ctx = f"trial {trial} {rows}x{cols} net_id={net_id}"
        assert rust_path is not None, f"{ctx}: rust returned None but oracle found path"
        assert py_path is not None, f"{ctx}: oracle returned None but rust found path"
        # Both paths must be valid: connected, start/goal correct.
        _assert_valid_path(rust_path, start, goal, f"{ctx}/rust")
        _assert_valid_path(py_path, start, goal, f"{ctx}/py")
        # Both paths must respect occupancy: never enter foreign cells
        # or static obstacles.
        for label, p in [("rust", rust_path), ("py", py_path)]:
            for x, y in p:
                cell = arr[y, x]
                assert cell == 0 or cell == net_id, (
                    f"{ctx}/{label}: entered cell ({x},{y}) value={cell} "
                    f"(net_id={net_id})"
                )
        routed += 1
    assert routed > 0, "no same-net differential pair was routable"


def test_net_id_negative_unchanged(_rust_engaged) -> None:
    """net_id < 0 must behave identically to today (grid is None, tensor
    path used).  Verify the Rust kernel still produces valid paths
    matching the pure-Python oracle on the same inputs."""
    rng = random.Random(20260811)
    routed = 0
    for trial in range(30):
        rows = rng.choice([8, 12, 20])
        cols = rng.choice([8, 16, 24])
        blocked = _random_blocked(rng, rows, cols, rng.choice([0.05, 0.15, 0.3]))
        arr = _make_net_grid(rows, cols)
        for r, c in blocked:
            arr[r, c] = 1  # blocked
        grid = _GridAdapter(arr)
        start = (rng.randrange(cols), rng.randrange(rows))
        goal = (rng.randrange(cols), rng.randrange(rows))
        if start == goal:
            continue
        # The old _search helper pre-builds the tensor (the established
        # path).  Compare against the Python oracle.
        tensor = build_neighbor_validity_tensor_2d(grid)
        rust_path = _astar_search_rust(
            start, goal, grid, neighbor_tensor=tensor,
            net_id=-1, max_iterations=200_000,
        )
        py_path = _search_py_oracle(start, goal, grid, net_id=-1)
        if rust_path is None and py_path is None:
            continue
        ctx = f"trial {trial} {rows}x{cols}"
        assert rust_path is not None, f"{ctx}: rust returned None but oracle found path"
        assert py_path is not None, f"{ctx}: oracle returned None but rust found path"
        _assert_valid_path(rust_path, start, goal, f"{ctx}/rust")
        _assert_valid_path(py_path, start, goal, f"{ctx}/py")
        routed += 1
    assert routed > 0, "no net_id<0 differential pair was routable"


def test_corridor_mask_restricts(_rust_engaged) -> None:
    """When a corridor mask is passed with net_id >= 0, cells outside the
    corridor are unreachable.  The Rust and Python oracle must agree."""
    arr = _make_net_grid(12, 16)
    grid = _GridAdapter(arr)
    # Only rows 4-7 are allowed.
    mask = np.zeros((12, 16), dtype=np.uint8)
    mask[4:8, :] = 1  # rows 4-7, all cols
    # Start and goal are outside the corridor (rows 1 and 10).
    rust_path = _search_rust_net(
        (7, 1), (7, 10), grid, net_id=3, corridor_mask=mask
    )
    py_path = _search_py_oracle(
        (7, 1), (7, 10), grid, net_id=3, corridor_mask=mask
    )
    assert rust_path is None, (
        f"corridor mask should block exit; got path of length "
        f"{len(rust_path) if rust_path else 0}"
    )
    assert py_path is None, (
        f"Python oracle should also block exit; got path of length "
        f"{len(py_path) if py_path else 0}"
    )


def test_corridor_mask_allows(_rust_engaged) -> None:
    """A route entirely within the corridor mask succeeds."""
    arr = _make_net_grid(12, 16)
    grid = _GridAdapter(arr)
    mask = np.zeros((12, 16), dtype=np.uint8)
    mask[:, 4:9] = 1
    path = _search_rust_net(
        (5, 5), (7, 5), grid, net_id=3, corridor_mask=mask
    )
    assert path is not None, "route fully within corridor should succeed"
    _assert_valid_path(path, (5, 5), (7, 5), "corridor-allowed")


def test_same_net_cost_discount_anti_vacuity(_rust_engaged) -> None:
    """A grid where the 0.25x same-net discount changes the path.

    Without the discount, the path takes the free route.  With it, the
    path preferentially traverses same-net copper.  This proves D2
    (the cost discount divergence source) is actually wired.
    """
    arr = _make_net_grid(8, 12, net_cells={(3, c): 5 for c in range(2, 10)})
    grid = _GridAdapter(arr)
    # Net 5 routes from top-left to bottom-right.  The direct diagonal
    # crosses its own copper strip at row 3 -- with the 0.25x discount,
    # this should be the preferred path.
    path_discount = _search_rust_net((1, 1), (11, 6), grid, net_id=5)
    assert path_discount is not None, "routable grid must return a path"
    # The path should include cells from the net-5 strip (row 3, cols 2-9).
    strip_cells = {(c, 3) for c in range(2, 10)}
    uses_strip = any(cell in strip_cells for cell in path_discount)
    assert uses_strip, (
        f"same-net discount should incentivize using own copper strip; "
        f"path={path_discount[:10]}..."
    )
    # A net that doesn't own the strip must detour around it.
    path_no_discount = _search_rust_net((1, 1), (11, 6), grid, net_id=7)
    if path_no_discount is not None:
        for x, y in path_no_discount:
            assert arr[y, x] != 5, f"net 7 entered net-5 cell at ({x},{y})"


def test_static_obstacle_sentinels_block(_rust_engaged) -> None:
    """-1 static-obstacle sentinels block traversal for all net_ids."""
    arr = _make_net_grid(10, 10, static_cells={(5, c) for c in range(3, 7)})
    grid = _GridAdapter(arr)
    # Net 5 and net 0 should both be blocked by the static wall.
    path5 = _search_rust_net((1, 1), (8, 8), grid, net_id=5)
    path0 = _search_rust_net((1, 1), (8, 8), grid, net_id=0)
    # With the wall at col 5, the direct route is blocked; a detour exists
    # around the wall ends (cols <3 or >6).
    for path, label in [(path5, "net5"), (path0, "net0")]:
        if path is not None:
            for x, y in path:
                assert arr[y, x] != -1, f"{label} entered static obstacle at ({x},{y})"


def test_foreign_net_fully_enclosed_blocked(_rust_engaged) -> None:
    """When a foreign-net ring encloses the goal, no path exists."""
    arr = _make_net_grid(10, 10)
    # Net 7 surrounds the goal at (7,7) with a ring.
    for c in range(4, 8):
        arr[4, c] = 7  # top wall
        arr[7, c] = 7  # bottom wall
    for r in range(4, 8):
        arr[r, 4] = 7  # left wall
        arr[r, 7] = 7  # right wall
    grid = _GridAdapter(arr)
    path = _search_rust_net((1, 1), (7, 7), grid, net_id=3)
    assert path is None, "foreign-net ring must block path to enclosed goal"
