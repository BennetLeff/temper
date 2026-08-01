"""Regression test for the _grid_core.py hot-loop kernels.

History: this file originally guarded the njit fallback shim in
``_grid_core.py`` (see docs/solutions/dependency-issues/
njit-fallback-shim-discards-function-on-bare-decorator-2026-07-17.md):
when numba failed to import, the fallback ``def njit(...)`` had to keep the
bare-``@njit``-decorated block kernels callable.

Wave 3 candidate #1 replaced those numba kernels with Rust pyfunctions in
temper-geometry (``grid_raster.rs``) and removed the numba import from
``_grid_core.py`` entirely — the module's perf-critical rasterisation no
longer depends on numba at all (numba's cold import was the documented
cost).  This test keeps guarding the same invariant the old one did — the
hot-loop kernels are callable with real arguments and block the right
cells — now against the Rust-backed delegation path, plus a guard that
``_grid_core`` no longer pulls numba in on import.
"""

import sys

import numpy as np

from temper_placer.deterministic.stages import _grid_core
from temper_placer.deterministic.stages._grid_core import ClearanceGrid


def test_grid_core_does_not_import_numba():
    """The cold-start win: importing _grid_core must not load numba."""
    assert "numba" not in sys.modules or "numba" not in _grid_core.__dict__


def test_block_circle_is_callable_and_blocks():
    grid = ClearanceGrid(width_mm=20, height_mm=20, cell_size_mm=1.0, layer_count=2)
    grid.block_circle(center=(5.0, 5.0), radius_mm=1.5, clearance_mm=0.5, layer=0)
    assert (grid._pad_net_ids[0] == -2).any(), "expected at least one cell inside the circle to be blocked"
    row, col = grid._mm_to_cell(5.0, 5.0)
    assert grid._pad_net_ids[0][row, col] == -2


def test_block_trace_is_callable_and_blocks():
    grid = ClearanceGrid(width_mm=20, height_mm=20, cell_size_mm=1.0, layer_count=2)
    grid.block_trace([(2.0, 10.0), (12.0, 10.0)], width_mm=1.0, clearance_mm=0.0, layer=0)
    assert (grid._trace_net_ids[0] == -2).any(), "expected at least one cell along the trace to be blocked"


def test_block_rect_and_unblock_circle_are_callable():
    grid = ClearanceGrid(width_mm=20, height_mm=20, cell_size_mm=1.0, layer_count=2)
    grid.block_rect(center=(5.0, 5.0), size=(2.0, 2.0), clearance_mm=0.0, layer=0)
    assert grid.blocked_count_on_layer(0) > 0
    grid.unblock_circle(center=(5.0, 5.0), radius_mm=3.0, layer=0)
    assert grid.blocked_count_on_layer(0) == 0


def test_occupancy_bitmap_is_callable():
    grid = ClearanceGrid(width_mm=20, height_mm=20, cell_size_mm=0.5, layer_count=2)
    grid.block_circle(center=(5.0, 5.0), radius_mm=1.0, clearance_mm=0.2, layer=1)
    bitmap = grid.occupancy_bitmap
    assert bitmap.shape == (2, grid.rows, (grid.cols + 63) // 64)
    assert bitmap.dtype == np.uint64
    assert bitmap[1].any(), "expected the blocked layer to have non-zero words"
