"""
Wave 4 PR-A — 4D Bit Tensor for DRC-Neighbor Validity

Verifies the pre-baked neighbor-validity tensor from the
closure-rate rollout plan.

R9: A 4D boolean tensor (rows, cols, 8) is built once at A* pass
    start.  The inner loop's neighbor-validity check becomes a
    single bit read instead of an inlined bounds + numpy +
    occupancy check.  Compounding effect: U6 (Numba-JIT A*)
    reads this same tensor as a flat numpy array, multiplying
    the speedup of both.
"""
from __future__ import annotations

import numpy as np
import pytest

from temper_placer.router_v6.neighbor_validity import (
    DIRS_8,
    build_neighbor_validity_tensor_2d,
    is_valid_2d,
)


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> np.ndarray:
    """Build a 2D occupancy grid: 0 = free, 1 = blocked.

    ``blocked`` is a set of (row, col) tuples; the test passes them
    in that ordering to keep tests readable.
    """
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in (blocked or set()):
        if 0 <= r < rows and 0 <= c < cols:
            arr[r, c] = 1
    return arr


class _GridAdapter:
    """Minimal adapter matching OccupancyGrid's .grid / .width_cells /
    .height_cells interface, so the tensor builder doesn't need a
    full OccupancyGrid to test against.
    """

    def __init__(self, arr: np.ndarray) -> None:
        self.grid = arr
        self.height_cells, self.width_cells = arr.shape


def test_tensor_shape_matches_grid_dimensions():
    """Tensor shape is (rows, cols, 8) for the input grid."""
    arr = _make_grid(5, 7)
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)
    assert tensor.shape == (5, 7, 8)
    assert tensor.dtype == np.bool_


def test_tensor_marks_interior_directions_free_in_empty_grid():
    """An empty 4x4 grid has all 8 directions free from interior cells.

    Corner cells always have OOB moves (they only have 3 valid
    directions: E, SE, S for the top-left corner of an empty grid),
    so we don't assert tensor.all() — we assert the interior cells.
    """
    arr = _make_grid(4, 4)
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)
    # Interior (1, 1), (1, 2), (2, 1), (2, 2): every direction in-bounds and free
    for r, c in [(1, 1), (1, 2), (2, 1), (2, 2)]:
        for d in range(8):
            assert tensor[r, c, d], f"Interior ({r},{c}) should be free in dir {d}"


def test_tensor_marks_oob_directions_invalid():
    """Moves that land out-of-bounds from a corner cell are False;
    interior cells have all 8 directions free.

    For a 4x4 grid, the top-left corner (0, 0):
    - W (4), NW (5), N (6), SW (3) all OOB — must be False
    - E (0), SE (1), S (2) all in-bounds and free — must be True
    """
    arr = _make_grid(4, 4)
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)
    # Corner (0, 0): W=4, NW=5, N=6, SW=3 should be False
    assert not tensor[0, 0, 4]  # W
    assert not tensor[0, 0, 5]  # NW
    assert not tensor[0, 0, 6]  # N
    assert not tensor[0, 0, 3]  # SW
    # E=0, SE=1, S=2 land in-bounds and free
    assert tensor[0, 0, 0], "(0,0) E -> (0,1) should be True"
    assert tensor[0, 0, 1], "(0,0) SE -> (1,1) should be True"
    assert tensor[0, 0, 2], "(0,0) S -> (1,0) should be True"


def test_tensor_marks_blocked_neighbors_invalid():
    """A blocked cell makes every direction that lands on it False.

    With a 4x4 grid and a single block at (row=1, col=1):
    - (0, 0) moving SE (dir 1) lands on (1, 1) — must be False
    - (0, 0) moving E (dir 0) lands on (0, 1) — still free
    - (0, 2) moving SW (dir 3) lands on (1, 1) — must be False
    """
    arr = _make_grid(4, 4, blocked={(1, 1)})
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)
    assert not tensor[0, 0, 1], "(0,0) SE -> (1,1) blocked; should be False"
    assert tensor[0, 0, 0], "(0,0) E -> (0,1) free; should be True"
    assert not tensor[0, 2, 3], "(0,2) SW -> (1,1) blocked; should be False"


def test_tensor_does_not_mark_src_oob_as_valid():
    """Building a tensor doesn't produce True entries for moves that
    originate outside the grid (the tensor's first dimension is
    bounded; OOB source cells are not in the array).
    """
    arr = _make_grid(4, 4)
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)
    rows, cols, _ = tensor.shape
    assert rows == 4 and cols == 4
    # The tensor only covers (0..3, 0..3).  OOB reads (handled by
    # is_valid_2d) return False.  Confirm is_valid_2d boundary.
    assert not is_valid_2d(tensor, -1, 0, 0)
    assert not is_valid_2d(tensor, 0, -1, 0)
    assert not is_valid_2d(tensor, 4, 0, 0)
    assert not is_valid_2d(tensor, 0, 4, 0)


def test_dirs_8_matches_eight_connected_orthogonal_and_diagonal():
    """DIRS_8 has 8 entries, all 8-connected (king's-move) directions."""
    assert len(DIRS_8) == 8
    for dx, dy in DIRS_8:
        assert dx in (-1, 0, 1)
        assert dy in (-1, 0, 1)
        assert (dx, dy) != (0, 0)


def test_astar_uses_tensor_when_passed():
    """When ``neighbor_tensor`` is supplied, the inner loop reads
    from it; the A* result is identical to the inlined-check path.

    Smoke test: build a small grid, build the tensor, run A* with
    the tensor and without, confirm the path is the same.
    """
    from temper_placer.router_v6.astar_core import _astar_search

    arr = _make_grid(10, 10, blocked={(5, 5), (5, 6), (6, 5)})
    grid = _GridAdapter(arr)
    tensor = build_neighbor_validity_tensor_2d(grid)
    start = (0, 0)
    goal = (9, 9)
    path_with = _astar_search(start, goal, grid, neighbor_tensor=tensor)
    path_without = _astar_search(start, goal, grid, neighbor_tensor=None)
    assert path_with == path_without, (
        f"A* with tensor {path_with} != A* without tensor {path_without}"
    )
