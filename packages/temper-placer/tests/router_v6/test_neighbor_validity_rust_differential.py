"""Differential: the Rust neighbour-validity kernel vs the pinned Python oracle.

``temper_placer/router_v6/neighbor_validity.py`` now delegates
``build_neighbor_validity_tensor_2d`` to
``temper_geometry.build_neighbor_validity_tensor_2d_py``
(``packages/temper-geometry/src/neighbor_validity.rs``).  The pre-migration
numpy implementation is pinned verbatim at
``tests/router_v6/_neighbor_validity_py_oracle.py`` and is the reference
here.

The comparison is BIT-EXACT (``array_equal`` on ``bool_`` arrays), and the
grid shapes exercised include the production board's own
(2380 x 1680 F.Cu / B.Cu) and (595 x 420 coarse) grids -- the two the router
actually builds, per a captured production route.  Synthetic shapes cover
the degenerate cases real routes never produce (1-wide, 1-tall, empty), and
randomised occupancy covers the border/interior split the Rust kernel makes
for speed.

Why the border matters: the oracle ``np.zeros``-initialises and then fills
only the sub-rectangle of source cells whose destination is in bounds, so
every out-of-bounds move stays False by omission.  The Rust kernel writes
into an ``np.empty`` buffer and must therefore assign those entries
EXPLICITLY.  A kernel that skipped them would read as correct on any
zero-initialised buffer and wrong in production; the border-heavy cases
below are what separate the two.
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.router_v6.neighbor_validity import (
    DIRS_8,
    build_neighbor_validity_tensor_2d,
)

from ._neighbor_validity_py_oracle import (
    DIRS_8 as ORACLE_DIRS_8,
)
from ._neighbor_validity_py_oracle import (
    build_neighbor_validity_tensor_2d as oracle_build,
)


class _FakeGrid:
    """Minimal stand-in exposing exactly what the function reads."""

    def __init__(self, arr: np.ndarray) -> None:
        self.grid = arr
        self.height_cells = arr.shape[0]
        self.width_cells = arr.shape[1]


def _rng_grid(rows: int, cols: int, seed: int, occupied_frac: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    arr = np.zeros((rows, cols), dtype=np.int8)
    occ = rng.random((rows, cols)) < occupied_frac
    # Mix real net ids and the -1 static-obstacle sentinel: both are
    # "occupied" (grid != 0) and the port must not treat them differently.
    ids = rng.integers(1, 100, size=(rows, cols)).astype(np.int8)
    arr[occ] = ids[occ]
    sentinel = rng.random((rows, cols)) < occupied_frac / 3.0
    arr[sentinel] = -1
    return arr


def test_direction_table_matches_oracle() -> None:
    """The port is only meaningful if the direction encoding is unchanged."""
    assert DIRS_8 == ORACLE_DIRS_8


@pytest.mark.parametrize(
    "rows,cols",
    [
        (1, 1),
        (1, 5),
        (5, 1),
        (2, 2),
        (3, 3),
        (4, 7),
        (17, 13),
        (64, 64),
        (595, 420),  # the production board's real COARSE grid
    ],
)
@pytest.mark.parametrize("occupied_frac", [0.0, 0.35, 1.0])
def test_matches_oracle_without_mask(rows: int, cols: int, occupied_frac: float) -> None:
    arr = _rng_grid(rows, cols, seed=rows * 1000 + cols, occupied_frac=occupied_frac)
    got = build_neighbor_validity_tensor_2d(_FakeGrid(arr))
    want = oracle_build(_FakeGrid(arr))
    assert got.dtype == want.dtype == np.bool_
    assert got.shape == want.shape == (rows, cols, 8)
    assert np.array_equal(got, want)


@pytest.mark.parametrize(
    "rows,cols",
    [(1, 1), (3, 3), (4, 7), (17, 13), (64, 64), (595, 420)],
)
@pytest.mark.parametrize("corridor_frac", [0.0, 0.5, 1.0])
def test_matches_oracle_with_corridor_mask(
    rows: int, cols: int, corridor_frac: float
) -> None:
    arr = _rng_grid(rows, cols, seed=rows * 31 + cols, occupied_frac=0.3)
    rng = np.random.default_rng(rows * 7919 + cols)
    mask = rng.random((rows, cols)) < corridor_frac
    got = build_neighbor_validity_tensor_2d(_FakeGrid(arr), corridor_mask=mask)
    want = oracle_build(_FakeGrid(arr), corridor_mask=mask)
    assert np.array_equal(got, want)


def test_border_entries_are_written_not_inherited() -> None:
    """The Rust kernel fills an ``np.empty`` buffer; out-of-bounds moves must
    be assigned False rather than left as whatever the allocator returned.

    Detecting a *stale-buffer* bug needs the allocation to be dirty. Doing a
    large alloc/free first makes numpy hand back recycled, non-zero memory
    with high probability, so a kernel that skipped the border would show up
    here as a mismatch against the all-False border the oracle produces.
    """
    rows, cols = 96, 96
    dirty = np.full((rows, cols, 8), 0xFF, dtype=np.uint8)
    del dirty
    arr = np.zeros((rows, cols), dtype=np.int8)  # everything free
    got = build_neighbor_validity_tensor_2d(_FakeGrid(arr))
    want = oracle_build(_FakeGrid(arr))
    assert np.array_equal(got, want)
    # Corner (0,0) on a wholly-free grid: only E, SE, S are in bounds.
    assert list(got[0, 0]) == [True, True, True, False, False, False, False, False]
    # Opposite corner: only W, NW, N.
    assert list(got[rows - 1, cols - 1]) == [
        False, False, False, False, True, True, True, False,
    ]


@pytest.mark.slow
def test_matches_oracle_on_production_fine_grid() -> None:
    """The real F.Cu/B.Cu routing grid this board actually builds.

    2380 x 1680 x 8 = 32.0 MB per tensor, so this is marked slow and kept to
    one occupancy pattern plus one corridor-masked pattern.
    """
    rows, cols = 2380, 1680
    arr = _rng_grid(rows, cols, seed=20260818, occupied_frac=0.77)
    assert np.array_equal(
        build_neighbor_validity_tensor_2d(_FakeGrid(arr)),
        oracle_build(_FakeGrid(arr)),
    )
    rng = np.random.default_rng(4242)
    mask = rng.random((rows, cols)) < 0.08  # corridors are narrow
    assert np.array_equal(
        build_neighbor_validity_tensor_2d(_FakeGrid(arr), corridor_mask=mask),
        oracle_build(_FakeGrid(arr), corridor_mask=mask),
    )
