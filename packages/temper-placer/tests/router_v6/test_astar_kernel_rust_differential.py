"""Differential tests: Rust A* kernel vs the Numba kernel.

Both backends must produce IDENTICAL path cell sequences on identical
inputs (the U5 acceptance, KTD7: cell-sequence equality; bit-identical
where float evaluation order is preserved).  The Numba kernel is the
reference; the Rust kernel is selected via TEMPER_ASTAR_BACKEND=rust
(the dispatch seam in astar_core_numba.py, roadmap KTD6).
"""

from __future__ import annotations

import os
import random

import numpy as np
import pytest

from temper_placer.router_v6.astar_core_numba import (
    _astar_search_numba,
    _line_of_sight_numba,
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
def rust_backend(monkeypatch):
    monkeypatch.setenv("TEMPER_ASTAR_BACKEND", "rust")
    yield


@pytest.fixture
def numba_backend(monkeypatch):
    monkeypatch.delenv("TEMPER_ASTAR_BACKEND", raising=False)
    yield


@pytest.fixture
def _rust_engaged(monkeypatch):
    """Set the rust backend AND assert it actually resolved (fails loudly
    instead of silently running numba on both sides when temper_rust_router
    is missing/stale). Leading underscore: the fixture is consumed purely
    for its side effect, so the parameter is intentionally unused in tests
    (vulture-clean)."""
    monkeypatch.setenv("TEMPER_ASTAR_BACKEND", "rust")
    from temper_placer.router_v6.astar_core_numba import _select_astar_backend

    assert _select_astar_backend() == "rust", (
        "TEMPER_ASTAR_BACKEND=rust did not resolve to the Rust kernel — "
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


def _assert_same_path(a, b, ctx: str) -> None:
    if a is None or b is None:
        assert a is None and b is None, f"{ctx}: one backend found a path, other did not"
        return
    assert a == b, f"{ctx}: path mismatch\nrust={a}\nnumba={b}"


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


def test_path_identity_open_grid(_rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(12, 16))
    os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
    numba_path = _search((0, 0), (11, 15), grid)
    os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
    rust_path = _search((0, 0), (11, 15), grid)
    _assert_same_path(rust_path, numba_path, "open grid")


def test_path_identity_start_equals_goal(_rust_engaged) -> None:
    grid = _GridAdapter(_make_grid(8, 8))
    os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
    numba_path = _search((3, 4), (3, 4), grid)
    os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
    rust_path = _search((3, 4), (3, 4), grid)
    _assert_same_path(rust_path, numba_path, "start == goal")


def test_path_identity_random_obstacles(_rust_engaged) -> None:
    rng = random.Random(20260731)
    for trial in range(25):
        rows = rng.choice([8, 12, 20])
        cols = rng.choice([8, 16, 24])
        blocked = _random_blocked(rng, rows, cols, rng.choice([0.05, 0.15, 0.3]))
        grid = _GridAdapter(_make_grid(rows, cols, blocked))
        start = (rng.randrange(cols), rng.randrange(rows))
        goal = (rng.randrange(cols), rng.randrange(rows))
        if start == goal:
            continue
        os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
        numba_path = _search(start, goal, grid)
        os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
        rust_path = _search(start, goal, grid)
        _assert_same_path(rust_path, numba_path, f"trial {trial} {rows}x{cols}")


def test_path_identity_with_congestion(_rust_engaged) -> None:
    rng = random.Random(9)
    grid = _GridAdapter(_make_grid(14, 14, _random_blocked(rng, 14, 14, 0.1)))
    cong = np.zeros((14, 14), dtype=np.float32)
    for _ in range(20):
        cong[rng.randrange(14), rng.randrange(14)] = rng.random() * 40
    os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
    numba_path = _search((0, 0), (13, 13), grid, congestion_flat=cong.reshape(-1))
    os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
    rust_path = _search((0, 0), (13, 13), grid, congestion_flat=cong.reshape(-1))
    _assert_same_path(rust_path, numba_path, "congestion")


def test_path_identity_with_thermal(_rust_engaged) -> None:
    rng = random.Random(11)
    grid = _GridAdapter(_make_grid(10, 18, _random_blocked(rng, 10, 18, 0.12)))
    thermal = np.zeros((10, 18), dtype=np.float32)
    for _ in range(15):
        thermal[rng.randrange(10), rng.randrange(18)] = rng.random() * 30
    os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
    numba_path = _search((0, 0), (9, 17), grid, thermal_flat=thermal.reshape(-1))
    os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
    rust_path = _search((0, 0), (9, 17), grid, thermal_flat=thermal.reshape(-1))
    _assert_same_path(rust_path, numba_path, "thermal")


def test_blocked_grid_both_return_none(_rust_engaged) -> None:
    blocked = {(r, 8) for r in range(10)} | {(5, c) for c in range(1, 16)}
    grid = _GridAdapter(_make_grid(10, 16, blocked))
    os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
    numba_path = _search((0, 0), (9, 15), grid)
    os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
    rust_path = _search((0, 0), (9, 15), grid)
    _assert_same_path(rust_path, numba_path, "blocked cross")


def test_line_of_sight_parity(_rust_engaged) -> None:
    rng = random.Random(5)
    grid = _GridAdapter(_make_grid(20, 20, _random_blocked(rng, 20, 20, 0.2)))
    for _ in range(200):
        p1 = (rng.randrange(20), rng.randrange(20))
        p2 = (rng.randrange(20), rng.randrange(20))
        os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
        n = _line_of_sight_numba(p1, p2, grid, net_id=0)
        os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
        r = _line_of_sight_numba(p1, p2, grid, net_id=0)
        assert r == n, f"LOS mismatch {p1}->{p2}: rust={r} numba={n}"


def test_line_of_sight_parity_with_negative_sentinels(_rust_engaged) -> None:
    # Production grids carry -1 static-obstacle sentinels (occupancy_grid
    # CellState); as uint8 they reinterpret to 0xFF (still != 0, != net_id)
    # and must behave identically in both kernels.
    rng = random.Random(6)
    arr = _make_grid(15, 15)
    for _ in range(40):
        arr[rng.randrange(15), rng.randrange(15)] = -1
    grid = _GridAdapter(arr)
    for _ in range(100):
        p1 = (rng.randrange(15), rng.randrange(15))
        p2 = (rng.randrange(15), rng.randrange(15))
        os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
        n = _line_of_sight_numba(p1, p2, grid, net_id=0)
        os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
        r = _line_of_sight_numba(p1, p2, grid, net_id=0)
        assert r == n, f"LOS sentinel mismatch {p1}->{p2}"


def test_line_of_sight_net_id_parity() -> None:
    rng = random.Random(6)
    arr = _make_grid(15, 15)
    # a blocked strip with a gap that a net-specific LOS may cross
    arr[7, 3:12] = 3  # net 3 owns this strip
    grid = _GridAdapter(arr)
    for _ in range(100):
        p1 = (rng.randrange(15), rng.randrange(15))
        p2 = (rng.randrange(15), rng.randrange(15))
        os.environ["TEMPER_ASTAR_BACKEND"] = "numba"
        n = _line_of_sight_numba(p1, p2, grid, net_id=3)
        os.environ["TEMPER_ASTAR_BACKEND"] = "rust"
        r = _line_of_sight_numba(p1, p2, grid, net_id=3)
        assert r == n, f"LOS net-id mismatch {p1}->{p2}"
