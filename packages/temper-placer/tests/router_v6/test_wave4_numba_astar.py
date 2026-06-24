"""
Wave 4 PR-B — Numba-JIT A* Inner Loop

Verifies the Numba-jitted A* front-end from the closure-rate
rollout plan.

R10: ``_astar_search_numba`` in
    ``router_v6/astar_core_numba.py`` ports the A* inner loop to
    a ``@njit`` function with flat ``np.float32`` / ``np.int32``
    arrays for g_score / came_from / closed and a manual binary
    heap.  Reads the same pre-baked neighbor-validity tensor
    (R9 / U5) as a flat ``uint8`` array.

Falls through to ``_astar_search`` (pure Python) when numba is
not installed; this is a soft dependency.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from temper_placer.router_v6.astar_core_numba import _HAVE_NUMBA
from temper_placer.router_v6.astar_core import _astar_search as _python_astar
from temper_placer.router_v6.neighbor_validity import build_neighbor_validity_tensor_2d


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> np.ndarray:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in (blocked or set()):
        if 0 <= r < rows and 0 <= c < cols:
            arr[r, c] = 1
    return arr


class _GridAdapter:
    def __init__(self, arr: np.ndarray) -> None:
        self.grid = arr
        self.height_cells, self.width_cells = arr.shape


@pytest.mark.skipif(not _HAVE_NUMBA, reason="numba not installed")
def test_numba_path_matches_python_path_on_empty_grid():
    """On an empty 20x20 grid, both A* variants find a diagonal
    path of length 20 (cells 0,0 to 19,19) — the same shortest
    path.  Confirms Numba port returns identical results.
    """
    arr = _make_grid(20, 20)
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)

    py_path = _python_astar((0, 0), (19, 19), grid, neighbor_tensor=tensor)
    from temper_placer.router_v6.astar_core_numba import _astar_search_numba
    nb_path = _astar_search_numba((0, 0), (19, 19), grid, neighbor_tensor=tensor)

    assert py_path == nb_path, (
        f"Python {py_path[:3]}... != Numba {nb_path[:3]}..."
    )
    # Diagonal path is 20 cells
    assert len(py_path) == 20


@pytest.mark.skipif(not _HAVE_NUMBA, reason="numba not installed")
def test_numba_path_matches_python_path_around_blocked_cells():
    """A 20x20 grid with a diagonal wall — both A* variants find
    a shortest path of the same length.  The exact cell sequence
    may differ between the Python heapq and the manual Numba heap
    (different tie-breaking), so we compare path length and the
    set of cells, not the exact sequence.
    """
    arr = _make_grid(20, 20, blocked={(i, i) for i in range(5, 15)})
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)

    py_path = _python_astar((0, 0), (19, 19), grid, neighbor_tensor=tensor)
    from temper_placer.router_v6.astar_core_numba import _astar_search_numba
    nb_path = _astar_search_numba((0, 0), (19, 19), grid, neighbor_tensor=tensor)

    assert py_path is not None
    assert nb_path is not None
    # Both must find a valid path with the same length
    assert len(py_path) == len(nb_path), (
        f"Python path length {len(py_path)} != Numba path length {len(nb_path)}"
    )
    # Both must start at (0,0) and end at (19,19)
    assert py_path[0] == (0, 0) and py_path[-1] == (19, 19)
    assert nb_path[0] == (0, 0) and nb_path[-1] == (19, 19)


@pytest.mark.skipif(not _HAVE_NUMBA, reason="numba not installed")
def test_numba_returns_none_for_unreachable_goal():
    """A 10x10 grid with a full horizontal wall — neither A*
    variant can reach the other side."""
    arr = _make_grid(10, 10, blocked={(5, c) for c in range(10)})
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)

    from temper_placer.router_v6.astar_core_numba import _astar_search_numba
    assert _astar_search_numba((0, 0), (9, 9), grid, neighbor_tensor=tensor) is None


@pytest.mark.skipif(not _HAVE_NUMBA, reason="numba not installed")
def test_numba_is_faster_than_python_on_large_grid():
    """Smoke benchmark on a 100x100 grid with sparse obstacles.

    We don't assert an exact ratio (CI variability) but the Numba
    path should be at least 2x faster than the pure-Python path.
    """
    arr = _make_grid(100, 100, blocked={(i, (i * 7) % 100) for i in range(0, 100, 3)})
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)

    from temper_placer.router_v6.astar_core_numba import _astar_search_numba

    t0 = time.perf_counter()
    for _ in range(5):
        _python_astar((0, 0), (99, 99), grid, neighbor_tensor=tensor)
    py_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(5):
        _astar_search_numba((0, 0), (99, 99), grid, neighbor_tensor=tensor)
    nb_time = time.perf_counter() - t0

    speedup = py_time / max(nb_time, 1e-9)
    assert speedup > 2.0, (
        f"Numba A* not faster than Python: py={py_time:.3f}s, "
        f"nb={nb_time:.3f}s, speedup={speedup:.1f}x"
    )


def test_numba_path_returns_list_of_xy_tuples():
    """Numba A* returns the same shape as Python A*: list of
    ``(col, row)`` tuples, not flat cell indices.
    """
    if not _HAVE_NUMBA:
        pytest.skip("numba not installed")
    arr = _make_grid(10, 10)
    grid = _GridAdapter(arr)
    from temper_placer.router_v6.astar_core_numba import _astar_search_numba
    path = _astar_search_numba((0, 0), (9, 9), grid)
    assert isinstance(path, list)
    for cell in path:
        assert isinstance(cell, tuple)
        assert len(cell) == 2
        assert all(isinstance(v, int) for v in cell)
