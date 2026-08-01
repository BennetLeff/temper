"""Differential tests: ClearanceGrid rasterisation kernels, Rust vs oracle.

Wave 3 candidate #1: the pure rasterisation compute of
``temper_placer/deterministic/stages/_grid_core.py`` moved to the
``temper-geometry`` crate (``packages/temper-geometry/src/grid_raster.rs``)
as in-place ``PyBuffer<i32>`` kernels.  The pre-migration implementations
(the numba ``_block_circle_numba`` / ``_block_segment_numba`` loops and the
pure-Python ``block_rect`` / ``unblock_circle`` / ``occupancy_bitmap``
loops) are pinned here VERBATIM as oracles.

The kernels mutate an int32 grid in place through numpy's buffer
protocol, exactly like the numba originals; the Python methods in
``_grid_core.py`` keep their public API and delegate.  The bbox
computation (``min_row``/``max_row``/``min_col``/``max_col``) is part of
the orchestration and stays Python; the loop over the bbox is the Rust
compute.  The end-to-end tests below pin bbox + kernel + net-id
resolution together through the public methods.

Bit-exactness notes:
- ``x ** 2`` in the Python reference is libm ``pow(x, 2.0)`` (CPython's
  float_pow), NOT ``x * x``; ``x ** 0.5`` is libm ``pow(x, 0.5)``, not
  ``sqrt``.  The Rust kernels resolve ``pow`` via ``dlsym`` so they call
  the exact same libm the reference uses.
- Everything else is plain f64 left-to-right arithmetic, preserved
  op-for-op.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import temper_geometry as _tg

from temper_placer.deterministic.stages._grid_core import ClearanceGrid

# ---------------------------------------------------------------------------
# Oracles: the pre-migration implementations, verbatim
# ---------------------------------------------------------------------------


def _oracle_block_circle(
    target_grid, cx, cy, total_radius, net_id, cell_size_mm, min_row, max_row, min_col, max_col
):
    """The pre-migration _block_circle_numba body, verbatim (pure Python)."""
    for row in range(min_row, max_row):
        for col in range(min_col, max_col):
            cell_x = col * cell_size_mm + cell_size_mm / 2
            cell_y = row * cell_size_mm + cell_size_mm / 2
            dist = ((cell_x - cx) ** 2 + (cell_y - cy) ** 2) ** 0.5
            if dist <= total_radius:
                curr = target_grid[row, col]
                if curr == 0:
                    target_grid[row, col] = net_id
                elif curr != net_id:
                    target_grid[row, col] = -1  # Multiple nets/Conflict


def _oracle_block_segment(
    target_grid,
    x1,
    y1,
    x2,
    y2,
    total_radius,
    net_id,
    cell_size_mm,
    min_row,
    max_row,
    min_col,
    max_col,
):
    """The pre-migration _block_segment_numba body, verbatim (pure Python)."""
    dx = x2 - x1
    dy = y2 - y1
    L2 = dx * dx + dy * dy

    for row in range(min_row, max_row):
        for col in range(min_col, max_col):
            cell_x = col * cell_size_mm + cell_size_mm / 2
            cell_y = row * cell_size_mm + cell_size_mm / 2

            # Projection of point (cell_x, cell_y) onto segment
            t = ((cell_x - x1) * dx + (cell_y - y1) * dy) / L2
            t = max(0.0, min(1.0, t))

            proj_x = x1 + t * dx
            proj_y = y1 + t * dy

            dist = ((cell_x - proj_x) ** 2 + (cell_y - proj_y) ** 2) ** 0.5
            if dist <= total_radius:
                curr = target_grid[row, col]
                if curr == 0:
                    target_grid[row, col] = net_id
                elif curr != net_id:
                    target_grid[row, col] = -1  # Multiple nets/Conflict


def _oracle_block_rect(target_grid, net_id, min_row, max_row, min_col, max_col):
    """The pre-migration block_rect inner loop, verbatim."""
    for row in range(min_row, max_row):
        for col in range(min_col, max_col):
            curr = target_grid[row, col]
            if curr == 0:
                target_grid[row, col] = net_id
            elif curr != net_id:
                target_grid[row, col] = -1  # Multiple nets/conflict


def _oracle_clear_circle(
    target_grid, cx, cy, radius_mm, cell_size_mm, min_row, max_row, min_col, max_col
):
    """The pre-migration unblock_circle inner loop, verbatim (one grid)."""
    for row in range(min_row, max_row):
        for col in range(min_col, max_col):
            cell_x = col * cell_size_mm + cell_size_mm / 2
            cell_y = row * cell_size_mm + cell_size_mm / 2
            dist = ((cell_x - cx) ** 2 + (cell_y - cy) ** 2) ** 0.5
            if dist <= radius_mm:
                target_grid[row, col] = 0


def _oracle_occupancy_bitmap_row(trace, pad, rows, cols, stride):
    """The pre-migration occupancy_bitmap inner loop, verbatim (one layer)."""
    bitmap = np.zeros((rows, stride), dtype=np.uint64)
    for row in range(rows):
        for word in range(stride):
            start_col = word * 64
            end_col = min(start_col + 64, cols)
            word_val = np.uint64(0)
            for col in range(start_col, end_col):
                t_val = int(trace[row, col])
                p_val = int(pad[row, col])
                if t_val != 0 or p_val != 0:
                    word_val |= np.uint64(1) << np.uint64(col - start_col)
            bitmap[row, word] = word_val
    return bitmap


# ---------------------------------------------------------------------------
# Kernel-level differential: randomized inputs
# ---------------------------------------------------------------------------

_CELL_SIZES = [0.25, 0.5, 1.0, 2.0]


def _random_bbox(rng, rows, cols):
    """Random clamped bbox within the grid (mirrors the Python clamp math)."""
    min_col = rng.randrange(0, cols)
    max_col = rng.randrange(min_col, cols + 1)
    min_row = rng.randrange(0, rows)
    max_row = rng.randrange(min_row, rows + 1)
    return min_row, max_row, min_col, max_col


def _fresh_grid(rng, rows, cols):
    """Fresh int32 grid, possibly pre-populated with nets/conflicts/obstacles."""
    grid = np.zeros((rows, cols), dtype=np.int32)
    for r in range(rows):
        for c in range(cols):
            v = rng.random()
            if v < 0.35:
                grid[r, c] = rng.choice([-2, -1, 1, 2, 3, 5, 7])
            elif v < 0.45:
                grid[r, c] = 0
    return grid


def test_block_circle_matches_oracle_on_random_inputs():
    rng = random.Random(20260731)
    for _ in range(500):
        rows = rng.randrange(1, 25)
        cols = rng.randrange(1, 25)
        cell = rng.choice(_CELL_SIZES)
        grid = _fresh_grid(rng, rows, cols)
        ref = grid.copy()
        min_row, max_row, min_col, max_col = _random_bbox(rng, rows, cols)
        # centers allowed outside the bbox (boundary conditions)
        cx = rng.uniform(-5.0, cols * cell + 5.0)
        cy = rng.uniform(-5.0, rows * cell + 5.0)
        total_radius = rng.uniform(0.0, 8.0)
        net_id = int(rng.choice([1, 2, 3, -2]))

        _tg.block_circle_into_grid_py(
            grid, cx, cy, total_radius, net_id, cell, min_row, max_row, min_col, max_col
        )
        _oracle_block_circle(
            ref, cx, cy, total_radius, net_id, cell, min_row, max_row, min_col, max_col
        )
        np.testing.assert_array_equal(grid, ref)


def test_block_segment_matches_oracle_on_random_inputs():
    rng = random.Random(991)
    for _ in range(500):
        rows = rng.randrange(1, 20)
        cols = rng.randrange(1, 20)
        cell = rng.choice(_CELL_SIZES)
        grid = _fresh_grid(rng, rows, cols)
        ref = grid.copy()
        min_row, max_row, min_col, max_col = _random_bbox(rng, rows, cols)
        x1 = rng.uniform(-8.0, cols * cell + 8.0)
        y1 = rng.uniform(-8.0, rows * cell + 8.0)
        x2 = rng.uniform(-8.0, cols * cell + 8.0)
        y2 = rng.uniform(-8.0, rows * cell + 8.0)
        total_radius = rng.uniform(0.0, 6.0)
        net_id = int(rng.choice([1, 2, 3, -2]))

        _tg.block_segment_into_grid_py(
            grid, x1, y1, x2, y2, total_radius, net_id, cell, min_row, max_row, min_col, max_col
        )
        _oracle_block_segment(
            ref, x1, y1, x2, y2, total_radius, net_id, cell, min_row, max_row, min_col, max_col
        )
        np.testing.assert_array_equal(grid, ref)


def test_block_rect_matches_oracle_on_random_inputs():
    rng = random.Random(4242)
    for _ in range(500):
        rows = rng.randrange(1, 25)
        cols = rng.randrange(1, 25)
        grid = _fresh_grid(rng, rows, cols)
        ref = grid.copy()
        min_row, max_row, min_col, max_col = _random_bbox(rng, rows, cols)
        net_id = int(rng.choice([1, 2, 3, -2]))

        _tg.block_rect_into_grid_py(grid, net_id, min_row, max_row, min_col, max_col)
        _oracle_block_rect(ref, net_id, min_row, max_row, min_col, max_col)
        np.testing.assert_array_equal(grid, ref)


def test_clear_circle_matches_oracle_on_random_inputs():
    rng = random.Random(777)
    for _ in range(500):
        rows = rng.randrange(1, 25)
        cols = rng.randrange(1, 25)
        cell = rng.choice(_CELL_SIZES)
        grid = _fresh_grid(rng, rows, cols)
        ref = grid.copy()
        min_row, max_row, min_col, max_col = _random_bbox(rng, rows, cols)
        cx = rng.uniform(-5.0, cols * cell + 5.0)
        cy = rng.uniform(-5.0, rows * cell + 5.0)
        radius_mm = rng.uniform(0.0, 8.0)

        _tg.clear_circle_from_grid_py(
            grid, cx, cy, radius_mm, cell, min_row, max_row, min_col, max_col
        )
        _oracle_clear_circle(ref, cx, cy, radius_mm, cell, min_row, max_row, min_col, max_col)
        np.testing.assert_array_equal(grid, ref)


def test_occupancy_bitmap_row_matches_oracle_on_random_inputs():
    rng = random.Random(31337)
    for _ in range(500):
        rows = rng.randrange(1, 20)
        cols = rng.randrange(1, 40)
        trace = _fresh_grid(rng, rows, cols)
        pad = _fresh_grid(rng, rows, cols)
        stride = (cols + 63) // 64
        rust = np.asarray(
            _tg.occupancy_bitmap_row_py(trace, pad, rows, cols, stride), dtype=np.uint64
        ).reshape((rows, stride))
        oracle = _oracle_occupancy_bitmap_row(trace, pad, rows, cols, stride)
        np.testing.assert_array_equal(rust, oracle)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_kernels_handle_empty_and_single_cell_grids():
    for rows, cols in [(1, 1), (0, 1), (1, 0), (0, 0)]:
        grid = np.zeros((rows, cols), dtype=np.int32)
        _tg.block_circle_into_grid_py(grid, 0.5, 0.5, 1.0, 1, 1.0, 0, rows, 0, cols)
        _tg.block_segment_into_grid_py(grid, 0.0, 0.0, 1.0, 1.0, 0.5, 1, 1.0, 0, rows, 0, cols)
        _tg.block_rect_into_grid_py(grid, 1, 0, rows, 0, cols)
        _tg.clear_circle_from_grid_py(grid, 0.5, 0.5, 1.0, 1.0, 0, rows, 0, cols)
        assert grid.shape == (rows, cols)


def test_kernels_with_empty_bbox_change_nothing():
    grid = _fresh_grid(random.Random(1), 10, 10)
    ref = grid.copy()
    _tg.block_circle_into_grid_py(grid, 5.0, 5.0, 3.0, 7, 1.0, 3, 3, 3, 3)  # empty bbox
    np.testing.assert_array_equal(grid, ref)
    _tg.block_segment_into_grid_py(grid, 0.0, 0.0, 5.0, 5.0, 1.0, 7, 1.0, 2, 2, 2, 2)
    np.testing.assert_array_equal(grid, ref)


def test_segment_with_zero_length_uses_circle_semantics():
    # L2 == 0 in the kernel: t = (0)/(0) = nan.  The pure-Python oracle
    # raises ZeroDivisionError here (CPython float division), but the numba
    # kernel -- the production implementation this kernel replaces -- does
    # not: it computes t = nan, and min/max treat NaN by returning the
    # non-NaN operand, so min(1.0, nan) = 1.0 and t clamps to 1.0, giving
    # proj = (x1, y1) and a circle of radius total_radius around the
    # endpoint.  The Rust kernel reproduces the numba semantics exactly.
    # (The ClearanceGrid._block_segment method itself early-returns on
    # L2 == 0, so this path is never reached from production.)
    rows = cols = 15
    grid = np.zeros((rows, cols), dtype=np.int32)
    _tg.block_segment_into_grid_py(grid, 5.0, 5.0, 5.0, 5.0, 2.0, 7, 1.0, 0, rows, 0, cols)
    assert grid[5, 5] == 7  # centre (5.5, 5.5), dist 0.707 <= 2
    assert grid[5, 4] == 7  # centre (4.5, 5.5), dist 0.707 <= 2
    assert grid[2, 5] == 0  # centre (2.5, 5.5), dist 2.55 > 2


def test_circle_boundary_exact_radius_blocks():
    # A cell centre exactly on the radius boundary must be blocked (<=).
    grid = np.zeros((9, 9), dtype=np.int32)
    cell = 1.0
    # centre at (4.5, 4.5) is cell (4, 4)'s centre; radius 1.0 hits the
    # centres of the 4 orthogonal neighbours at exactly distance 1.0.
    _tg.block_circle_into_grid_py(grid, 4.5, 4.5, 1.0, 3, cell, 0, 9, 0, 9)
    assert grid[4, 4] == 3
    assert grid[4, 3] == 3 and grid[4, 5] == 3 and grid[3, 4] == 3 and grid[5, 4] == 3
    assert grid[3, 3] == 0  # diagonal is sqrt(2) away


# ---------------------------------------------------------------------------
# End-to-end: public ClearanceGrid methods vs oracle (bbox + kernel + net-id)
# ---------------------------------------------------------------------------


def _reference_block_circle(grid, center, radius_mm, clearance_mm, cell_size, net_id):
    total_radius = radius_mm + clearance_mm
    cx, cy = center
    min_col = max(0, int((cx - total_radius) / cell_size))
    max_col = min(grid.shape[1], int((cx + total_radius) / cell_size) + 1)
    min_row = max(0, int((cy - total_radius) / cell_size))
    max_row = min(grid.shape[0], int((cy + total_radius) / cell_size) + 1)
    _oracle_block_circle(grid, cx, cy, total_radius, net_id, cell_size, min_row, max_row, min_col, max_col)


def _reference_block_rect(grid, center, size, clearance_mm, cell_size, net_id):
    cx, cy = center
    half_w, half_h = size[0] / 2.0 + clearance_mm, size[1] / 2.0 + clearance_mm
    min_col = max(0, int((cx - half_w) / cell_size))
    max_col = min(grid.shape[1], int((cx + half_w) / cell_size) + 1)
    min_row = max(0, int((cy - half_h) / cell_size))
    max_row = min(grid.shape[0], int((cy + half_h) / cell_size) + 1)
    _oracle_block_rect(grid, net_id, min_row, max_row, min_col, max_col)


def _reference_unblock_circle(grid, center, radius_mm, cell_size):
    cx, cy = center
    min_col = max(0, int((cx - radius_mm) / cell_size))
    max_col = min(grid.shape[1], int((cx + radius_mm) / cell_size) + 1)
    min_row = max(0, int((cy - radius_mm) / cell_size))
    max_row = min(grid.shape[0], int((cy + radius_mm) / cell_size) + 1)
    _oracle_clear_circle(grid, cx, cy, radius_mm, cell_size, min_row, max_row, min_col, max_col)


@pytest.mark.parametrize("seed", range(25))
def test_block_circle_method_matches_oracle_end_to_end(seed):
    rng = random.Random(seed * 101 + 5)
    w, h, cell, layers = 20.0, 16.0, rng.choice(_CELL_SIZES), 2
    prod = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    ref = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    for _ in range(4):
        center = (rng.uniform(0, w), rng.uniform(0, h))
        radius = rng.uniform(0.1, 4.0)
        clearance = rng.uniform(0.0, 2.0)
        layer = rng.randrange(layers)
        net_name = rng.choice(["", "NET_A", "NET_B", None])
        prod.block_circle(center, radius, clearance, layer=layer, net_name=net_name)
        net_id = ref.get_net_id(net_name) if net_name else -2
        ref_grid = ref._pad_net_ids[layer]
        _reference_block_circle(ref_grid, center, radius, clearance, cell, net_id)
        np.testing.assert_array_equal(prod._pad_net_ids[layer], ref._pad_net_ids[layer])
        np.testing.assert_array_equal(prod._trace_net_ids[layer], ref._trace_net_ids[layer])


@pytest.mark.parametrize("seed", range(25))
def test_block_rect_method_matches_oracle_end_to_end(seed):
    rng = random.Random(seed * 7 + 1)
    w, h, cell, layers = 20.0, 20.0, rng.choice(_CELL_SIZES), 2
    prod = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    ref = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    for _ in range(4):
        center = (rng.uniform(0, w), rng.uniform(0, h))
        size = (rng.uniform(0.5, 6.0), rng.uniform(0.5, 6.0))
        clearance = rng.uniform(0.0, 1.5)
        layer = rng.randrange(layers)
        is_obstacle = rng.random() < 0.5
        net_name = rng.choice(["", "NET_A", None])
        prod.block_rect(center, size, clearance, layer=layer, net_name=net_name, is_obstacle=is_obstacle)
        if is_obstacle:
            net_id = -2
        elif net_name:
            net_id = ref.get_net_id(net_name)
        else:
            net_id = -2
        _reference_block_rect(ref._trace_net_ids[layer], center, size, clearance, cell, net_id)
        np.testing.assert_array_equal(prod._trace_net_ids[layer], ref._trace_net_ids[layer])


@pytest.mark.parametrize("seed", range(15))
def test_unblock_circle_method_matches_oracle_end_to_end(seed):
    rng = random.Random(seed * 13 + 3)
    w, h, cell, layers = 20.0, 16.0, rng.choice(_CELL_SIZES), 2
    prod = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    ref = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    # Pre-block both with the same circles so unblock has something to clear
    for _ in range(3):
        center = (rng.uniform(2, w - 2), rng.uniform(2, h - 2))
        radius = rng.uniform(0.5, 3.0)
        layer = rng.randrange(layers)
        prod.block_circle(center, radius, 0.5, layer=layer)
        net_id = -2
        _reference_block_circle(ref._pad_net_ids[layer], center, radius, 0.5, cell, net_id)
    for layer in range(layers):
        np.testing.assert_array_equal(prod._pad_net_ids[layer], ref._pad_net_ids[layer])
    # Now unblock on one layer
    for _ in range(3):
        center = (rng.uniform(2, w - 2), rng.uniform(2, h - 2))
        radius = rng.uniform(0.5, 3.0)
        layer = rng.randrange(layers)
        prod.unblock_circle(center, radius, layer=layer)
        _reference_unblock_circle(ref._trace_net_ids[layer], center, radius, cell)
        _reference_unblock_circle(ref._pad_net_ids[layer], center, radius, cell)
    for layer in range(layers):
        np.testing.assert_array_equal(prod._trace_net_ids[layer], ref._trace_net_ids[layer])
        np.testing.assert_array_equal(prod._pad_net_ids[layer], ref._pad_net_ids[layer])


@pytest.mark.parametrize("seed", range(15))
def test_occupancy_bitmap_matches_oracle_end_to_end(seed):
    rng = random.Random(seed * 29 + 9)
    w, h, cell, layers = 20.0, 12.0, rng.choice([0.5, 1.0]), 2
    prod = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    ref = ClearanceGrid(width_mm=w, height_mm=h, cell_size_mm=cell, layer_count=layers)
    for _ in range(5):
        center = (rng.uniform(1, w - 1), rng.uniform(1, h - 1))
        radius = rng.uniform(0.3, 2.0)
        layer = rng.randrange(layers)
        prod.block_circle(center, radius, 0.2, layer=layer)
        net_id = -2
        _reference_block_circle(ref._pad_net_ids[layer], center, radius, 0.2, cell, net_id)
    prod_bitmap = prod.occupancy_bitmap
    ref_bitmap = np.stack(
        [
            _oracle_occupancy_bitmap_row(
                ref._trace_net_ids[layer], ref._pad_net_ids[layer], ref.rows, ref.cols, (ref.cols + 63) // 64
            )
            for layer in range(layers)
        ],
        axis=0,
    )
    assert prod_bitmap.shape == ref_bitmap.shape
    np.testing.assert_array_equal(prod_bitmap, ref_bitmap)
    assert prod.bitmap_row_stride == (ref.cols + 63) // 64
