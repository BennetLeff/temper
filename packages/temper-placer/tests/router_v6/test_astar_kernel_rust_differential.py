"""Rust A* kernel path tests (cleanup C1).

The Rust kernel (``temper-rust-router``) is the sole A* backend since
the Numba fallback was removed on 2026-07-31.  The numba-vs-rust
comparison tests were retired with the Numba kernel; their parity
evidence is recorded in ``packages/temper-rust-router-core/VERIFICATION.md``
(cell-sequence identity on randomized grids) and the full-pipeline A/B
(identical completion rate 0.3750, bit-identical route length 9354.65 mm).

This suite keeps the rust-path tests: every call runs through
``_astar_search_numba`` under the ``rust_engaged`` fixture, which proves
the Rust kernel actually resolved — a stale/missing ``temper_rust_router``
fails loudly here instead of silently degrading to the pure-Python
reference.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from temper_placer.router_v6.astar_core_numba import (
    _astar_search_numba,
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
    return _astar_search_numba(
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


def test_path_open_grid(__rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(12, 16))  # 12 rows, 16 cols
    path = _search((0, 0), (15, 11), grid)
    _assert_valid_path(path, (0, 0), (15, 11), "open grid")


def test_path_start_equals_goal(__rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(8, 8))
    path = _search((3, 4), (3, 4), grid)
    assert path == [(3, 4)], f"start==goal should return the single-cell path: {path}"


def test_path_random_obstacles(__rust_engaged) -> None:
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
    # Guard against a silent all-None regression (the retired numba-parity
    # suite compared None==None vacuously on such cases).
    assert routed > 0, "rust kernel returned None on every randomized grid"


def test_path_with_congestion(__rust_engaged) -> None:
    rng = random.Random(9)
    grid = _GridAdapter(_make_grid(14, 14, _random_blocked(rng, 14, 14, 0.1)))
    cong = np.zeros((14, 14), dtype=np.float32)
    for _ in range(20):
        cong[rng.randrange(14), rng.randrange(14)] = rng.random() * 40
    path = _search((0, 0), (13, 13), grid, congestion_flat=cong.reshape(-1))
    _assert_valid_path(path, (0, 0), (13, 13), "congestion")


def test_path_with_thermal(__rust_engaged) -> None:
    rng = random.Random(11)
    grid = _GridAdapter(_make_grid(10, 18, _random_blocked(rng, 10, 18, 0.12)))
    thermal = np.zeros((10, 18), dtype=np.float32)
    for _ in range(15):
        thermal[rng.randrange(10), rng.randrange(18)] = rng.random() * 30
    path = _search((0, 0), (17, 9), grid, thermal_flat=thermal.reshape(-1))
    _assert_valid_path(path, (0, 0), (17, 9), "thermal")


def test_blocked_grid_returns_none(__rust_engaged) -> None:
    blocked = {(r, 8) for r in range(10)} | {(5, c) for c in range(1, 16)}
    grid = _GridAdapter(_make_grid(10, 16, blocked))
    # A full-height wall at x=8 plus a wall at y=5 keeps (0,0) from the
    # bottom-right region; the goal (15, 9) is genuinely unreachable.
    assert _search((0, 0), (15, 9), grid) is None, "blocked cross must return None"


def test_line_of_sight_open(__rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(20, 20))
    assert _line_of_sight_rust((0, 0), (9, 9), grid, net_id=0) is True
    assert _line_of_sight_rust((0, 0), (9, 9), grid, net_id=-1) is True


def test_line_of_sight_blocked(__rust_engaged) -> None:
    arr = _make_grid(20, 20, blocked={(r, 10) for r in range(20)})
    grid = _GridAdapter(arr)
    assert _line_of_sight_rust((0, 0), (19, 19), grid, net_id=0) is False


def test_line_of_sight_negative_sentinels(__rust_engaged) -> None:
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


def test_line_of_sight_net_id_ownership(__rust_engaged) -> None:
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
