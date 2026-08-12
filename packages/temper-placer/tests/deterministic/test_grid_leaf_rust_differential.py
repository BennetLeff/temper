"""Differential tests: D3 clearance-grid residual leaf kernels, Rust vs oracle.

The three pieces of `ClearanceGrid` / `_grid_stage` leaf compute that were
STILL Python after the rasterisation kernels moved to
``temper-geometry/src/grid_raster.rs``:

- ``blocked_count`` / ``blocked_count_on_layer`` (the ``np.sum(arr != 0)``
  reductions) -> ``count_blocked_cells_py``;
- ``is_available``'s per-sample cell read -> ``grid_cell_available_py``;
- the EXP-13 exclusion-zone ``if curr == 0 or curr == net_id: arr[row, col] = -2``
  write loop -> ``block_exclusion_zone_into_grid_py``.

The kernels live in ``packages/temper-geometry/src/grid_leaf.rs``; the
pre-migration implementations are pinned VERBATIM here as the oracles (the
same G1 discipline as ``test_grid_core_rust_differential.py``).  Each kernel
is compared bit-exactly (``int32`` cells; the only float is the ``x / cell``
coordinate truncation, which is ``int()`` in both arms) on randomized
pre-populated inputs plus the public ``ClearanceGrid`` methods end-to-end.
"""

from __future__ import annotations

import random

import numpy as np
import temper_geometry as _tg

from temper_placer.deterministic.stages._grid_core import ClearanceGrid

# ---------------------------------------------------------------------------
# Oracles: the pre-migration implementations, verbatim
# ---------------------------------------------------------------------------


def _oracle_blocked_count_on_layer(trace, pad):
    """`blocked_count_on_layer`'s reduction, verbatim."""
    return int(np.sum(trace != 0) + np.sum(pad != 0))


def _oracle_is_available(trace, pad, rows, cols, cell_size, x_mm, y_mm, net_id):
    """`is_available`'s body after the layer bounds check, verbatim."""
    col = int(x_mm / cell_size)
    row = int(y_mm / cell_size)
    if 0 <= row < rows and 0 <= col < cols:
        t_id = trace[row, col]
        if t_id != 0 and t_id != net_id:
            return False
        p_id = pad[row, col]
        return not (p_id != 0 and p_id != net_id)
    return False


def _oracle_exclusion_zone(target_grid, net_id, min_row, max_row, min_col, max_col):
    """The EXP-13 exclusion-zone write loop, verbatim."""
    for row in range(min_row, max_row):
        for col in range(min_col, max_col):
            curr = target_grid[row, col]
            if curr == 0 or curr == net_id:
                target_grid[row, col] = -2


# ---------------------------------------------------------------------------
# Corpus builders
# ---------------------------------------------------------------------------


def _fresh_grid(rng, rows, cols):
    """Fresh int32 grid pre-populated with nets/conflicts/obstacles/free."""
    grid = np.zeros((rows, cols), dtype=np.int32)
    for r in range(rows):
        for c in range(cols):
            v = rng.random()
            if v < 0.5:
                grid[r, c] = rng.choice([-2, -1, 0, 1, 2, 3, 5, 7, 9])
            elif v < 0.6:
                grid[r, c] = 0
    return grid


# ---------------------------------------------------------------------------
# Kernel-level differential: randomized inputs
# ---------------------------------------------------------------------------

_CELL_SIZES = [0.25, 0.5, 1.0, 2.0]


def test_count_blocked_cells_matches_oracle_on_random_inputs():
    rng = random.Random(20260812)
    for _ in range(500):
        rows = rng.randrange(1, 25)
        cols = rng.randrange(1, 25)
        trace = _fresh_grid(rng, rows, cols)
        pad = _fresh_grid(rng, rows, cols)
        rust = _tg.count_blocked_cells_py(trace, pad)
        oracle = _oracle_blocked_count_on_layer(trace, pad)
        assert rust == oracle, f"count mismatch: {rust} != {oracle}"


def test_count_blocked_cells_empty_is_zero():
    assert _tg.count_blocked_cells_py(np.zeros((3, 3), np.int32), np.zeros((3, 3), np.int32)) == 0
    assert _tg.count_blocked_cells_py(np.zeros((1, 1), np.int32), np.zeros((1, 1), np.int32)) == 0


def test_grid_cell_available_matches_oracle_on_random_inputs():
    rng = random.Random(77121)
    for _ in range(2000):
        rows = rng.randrange(1, 25)
        cols = rng.randrange(1, 25)
        cell = rng.choice(_CELL_SIZES)
        trace = _fresh_grid(rng, rows, cols)
        pad = _fresh_grid(rng, rows, cols)
        # Coordinates both inside and outside the grid (boundary conditions).
        x = rng.uniform(-3.0, cols * cell + 3.0)
        y = rng.uniform(-3.0, rows * cell + 3.0)
        net_id = rng.choice([None, 1, 2, 3, 7, 9])
        rust = _tg.grid_cell_available_py(trace, pad, rows, cols, cell, x, y, net_id)
        oracle = _oracle_is_available(trace, pad, rows, cols, cell, x, y, net_id)
        assert rust == oracle, (
            f"availability mismatch at ({x}, {y}) net={net_id}: {rust} != {oracle}"
        )


def test_grid_cell_available_truncation_toward_zero():
    """Negative coords truncate toward zero (Python `int()`), not floor."""
    trace = np.zeros((5, 5), np.int32)
    pad = np.zeros((5, 5), np.int32)
    # -0.5 / 1.0 -> col 0 (in bounds), so (row 2, col 0) is free.
    assert _tg.grid_cell_available_py(trace, pad, 5, 5, 1.0, -0.5, 2.5, None) is True
    # -1.5 / 1.0 -> col -1 -> out of bounds -> blocked.
    assert _tg.grid_cell_available_py(trace, pad, 5, 5, 1.0, -1.5, 2.5, None) is False


def test_block_exclusion_zone_matches_oracle_on_random_inputs():
    rng = random.Random(424242)
    for _ in range(500):
        rows = rng.randrange(1, 25)
        cols = rng.randrange(1, 25)
        grid = _fresh_grid(rng, rows, cols)
        ref = grid.copy()
        min_col = rng.randrange(0, cols)
        max_col = rng.randrange(min_col, cols + 1)
        min_row = rng.randrange(0, rows)
        max_row = rng.randrange(min_row, rows + 1)
        net_id = int(rng.choice([1, 2, 3, 7]))

        _tg.block_exclusion_zone_into_grid_py(grid, net_id, min_row, max_row, min_col, max_col)
        _oracle_exclusion_zone(ref, net_id, min_row, max_row, min_col, max_col)
        np.testing.assert_array_equal(grid, ref)


def test_block_exclusion_zone_empty_bbox_changes_nothing():
    grid = _fresh_grid(random.Random(9), 10, 10)
    ref = grid.copy()
    _tg.block_exclusion_zone_into_grid_py(grid, 5, 3, 3, 3, 3)  # empty bbox
    np.testing.assert_array_equal(grid, ref)


# ---------------------------------------------------------------------------
# End-to-end: public ClearanceGrid methods vs the verbatim oracle
# ---------------------------------------------------------------------------


def test_blocked_count_methods_match_oracle_end_to_end():
    rng = random.Random(1122)
    w, h, cell, layers = 20.0, 16.0, rng.choice(_CELL_SIZES), 2
    grid = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    for _ in range(6):
        center = (rng.uniform(0, w), rng.uniform(0, h))
        radius = rng.uniform(0.2, 4.0)
        grid.block_circle(center, radius, 0.2, layer=rng.randrange(layers))
    for layer in range(layers):
        oracle = _oracle_blocked_count_on_layer(
            grid._trace_net_ids[layer], grid._pad_net_ids[layer]
        )
        assert grid.blocked_count_on_layer(layer) == oracle
    total_oracle = sum(
        _oracle_blocked_count_on_layer(grid._trace_net_ids[ly], grid._pad_net_ids[ly])
        for ly in range(layers)
    )
    assert grid.blocked_count == total_oracle


def test_is_available_method_matches_oracle_end_to_end():
    rng = random.Random(3344)
    w, h, cell, layers = 20.0, 16.0, rng.choice(_CELL_SIZES), 2
    grid = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    for _ in range(4):
        center = (rng.uniform(0, w), rng.uniform(0, h))
        grid.block_circle(center, rng.uniform(0.2, 3.0), 0.2, layer=rng.randrange(layers))
    for _ in range(200):
        layer = rng.randrange(layers)
        x = rng.uniform(-2.0, w + 2.0)
        y = rng.uniform(-2.0, h + 2.0)
        net_name = rng.choice(["", "NET_A", "NET_B", None])
        net_id = grid.get_net_id(net_name) if net_name else None
        oracle = _oracle_is_available(
            grid._trace_net_ids[layer], grid._pad_net_ids[layer],
            grid.rows, grid.cols, cell, x, y, net_id,
        )
        assert grid.is_available(x, y, layer=layer, net_name=net_name) == oracle
