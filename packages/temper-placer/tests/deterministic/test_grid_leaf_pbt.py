"""Property-based + metamorphic tests for the D3 residual leaf kernels.

The kernels under test are the temper-geometry pyfunctions
``count_blocked_cells_py`` / ``grid_cell_available_py`` /
``block_exclusion_zone_into_grid_py`` (``packages/temper-geometry/src/
grid_leaf.rs``) that ``_grid_core.py`` and ``grid_stage.rs`` delegate to.

Six invariants (each with a vacuity guard — a degenerate stand-in that must
trip the same body):

1. **P1 count-is-nonzero-cells**: the blocked count equals the number of
   non-zero cells across both arrays.
2. **P2 count-grows-by-one-on-block**: writing a non-zero id into a free
   cell increases the count by exactly one.
3. **P3 own-net transparency**: a cell holding net id N is available to N,
   blocked to any other id, and blocked to no-net.
4. **P4 no-net availability is exactly zero-cells**: with ``net_id=None`` a
   cell is available iff both its trace and pad ids are zero (in bounds).
5. **P5 exclusion-zone conservative write domain**: the kernel only ever
   writes ``-2`` (never clears a cell, never writes a conflict ``-1``), so
   it can only over-block, never under-block.
6. **P6 exclusion-zone idempotence**: applying the kernel twice equals
   applying it once.

Metamorphic relations:

- MR1: count is symmetric under trace/pad swap.
- MR2: count is translation-invariant (same number of blocked cells, shifted).
- MR3: exclusion-zone write is translation-equivariant (shifted bbox blocks
  the shifted cells).
- MR4: exclusion-zone never turns a non-zero cell into zero (the creepage
  conservatism guarantee).

These are the R24-adjacent conservatism properties: the fence's availability
assertion (P3/P4) and the exclusion zone's over-blocking guarantee (P5/MR4)
never under-state blockage.
"""

from __future__ import annotations

import numpy as np
import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 100

_dims = st.integers(min_value=2, max_value=24)


# ---------------------------------------------------------------------------
# P1 / P2 — count_blocked_cells
# ---------------------------------------------------------------------------


def _body_p1(impl, trace, pad):
    got = impl(trace, pad)
    assert got == int(np.count_nonzero(trace) + np.count_nonzero(pad))


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_count_is_nonzero_cells(rows, cols):
    trace = np.array(
        np.random.default_rng(rows * 1000 + cols).integers(-2, 10, size=(rows, cols)), dtype=np.int32
    )
    pad = np.array(
        np.random.default_rng(rows * 2000 + cols).integers(-2, 10, size=(rows, cols)), dtype=np.int32
    )
    _body_p1(_tg.count_blocked_cells_py, trace, pad)


def test_p1_fails_for_undercount_mutant():
    def mutant(trace, pad):
        return _tg.count_blocked_cells_py(trace, pad) - 1

    import pytest

    trace = np.array([[0, 5, 0]], dtype=np.int32)
    pad = np.array([[0, 0, 0]], dtype=np.int32)
    with pytest.raises(AssertionError):
        _body_p1(mutant, trace, pad)


def _body_p2(impl, rows, cols):
    trace = np.zeros((rows, cols), dtype=np.int32)
    pad = np.zeros((rows, cols), dtype=np.int32)
    before = impl(trace, pad)
    assert before == 0
    trace[rows // 2, cols // 2] = 3
    assert impl(trace, pad) == before + 1


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_count_grows_by_one_on_block(rows, cols):
    _body_p2(_tg.count_blocked_cells_py, rows, cols)


def test_p2_fails_for_constant_zero_mutant():
    def mutant(trace, pad):
        return 0

    import pytest

    with pytest.raises(AssertionError):
        _body_p2(mutant, 5, 5)


# ---------------------------------------------------------------------------
# P3 / P4 — grid_cell_available
# ---------------------------------------------------------------------------


def _body_p3(impl, rows, cols):
    cell = 1.0
    trace = np.zeros((rows, cols), dtype=np.int32)
    pad = np.zeros((rows, cols), dtype=np.int32)
    r, c = rows // 2, cols // 2
    trace[r, c] = 3
    x = c * cell + cell / 2
    y = r * cell + cell / 2
    assert impl(trace, pad, rows, cols, cell, x, y, 3) is True
    assert impl(trace, pad, rows, cols, cell, x, y, 7) is False
    assert impl(trace, pad, rows, cols, cell, x, y, None) is False


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_own_net_transparency(rows, cols):
    _body_p3(_tg.grid_cell_available_py, rows, cols)


def test_p3_fails_for_inverted_mutant():
    def mutant(trace, pad, rows, cols, cell, x, y, net_id):
        return not _tg.grid_cell_available_py(trace, pad, rows, cols, cell, x, y, net_id)

    import pytest

    with pytest.raises(AssertionError):
        _body_p3(mutant, 7, 7)


def _body_p4(impl, rows, cols):
    cell = 0.5
    trace = np.zeros((rows, cols), dtype=np.int32)
    pad = np.zeros((rows, cols), dtype=np.int32)
    r, c = rows // 2, cols // 2
    x = c * cell + cell / 2
    y = r * cell + cell / 2
    # both zero -> available
    assert impl(trace, pad, rows, cols, cell, x, y, None) is True
    # pad blocked -> unavailable
    pad[r, c] = 5
    assert impl(trace, pad, rows, cols, cell, x, y, None) is False
    pad[r, c] = 0
    # trace blocked -> unavailable
    trace[r, c] = -2
    assert impl(trace, pad, rows, cols, cell, x, y, None) is False


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_no_net_availability_is_zero_cells(rows, cols):
    _body_p4(_tg.grid_cell_available_py, rows, cols)


def test_p4_fails_for_always_true_mutant():
    def mutant(trace, pad, rows, cols, cell, x, y, net_id):
        return True

    import pytest

    with pytest.raises(AssertionError):
        _body_p4(mutant, 7, 7)


# ---------------------------------------------------------------------------
# P5 / P6 — block_exclusion_zone
# ---------------------------------------------------------------------------


def _body_p5(impl, grid):
    rows, cols = grid.shape
    net_id = 5
    min_row, max_row = rows // 4, (3 * rows) // 4
    min_col, max_col = cols // 4, (3 * cols) // 4
    before = grid.copy()
    impl(grid, net_id, min_row, max_row, min_col, max_col)
    for r in range(rows):
        for c in range(cols):
            pre = int(before[r, c])
            post = int(grid[r, c])
            in_bbox = min_row <= r < max_row and min_col <= c < max_col
            if not in_bbox:
                assert post == pre, "cell outside bbox changed"
                continue
            # The kernel only ever writes -2, never -1 or 0 or another net.
            assert post in (pre, -2), f"cell ({r},{c}) {pre} -> {post} is not pre/-2"
            if pre == 0 or pre == net_id:
                assert post == -2, f"cell ({r},{c}) {pre} should be blocked to -2, got {post}"


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_exclusion_zone_conservative_write_domain(rows, cols):
    rng = np.random.default_rng(rows * 3000 + cols)
    grid = rng.integers(-2, 10, size=(rows, cols)).astype(np.int32)
    _body_p5(_tg.block_exclusion_zone_into_grid_py, grid)


def test_p5_fails_for_conflict_writing_mutant():
    def mutant(grid, net_id, min_row, max_row, min_col, max_col):
        _tg.block_exclusion_zone_into_grid_py(grid, net_id, min_row, max_row, min_col, max_col)
        grid[min_row, min_col] = -1  # write a conflict instead of -2

    import pytest

    grid = np.zeros((8, 8), dtype=np.int32)  # deterministic: (2,2) is free
    with pytest.raises(AssertionError):
        _body_p5(mutant, grid)


def _body_p6(impl, rows, cols):
    rng = np.random.default_rng(rows * 4000 + cols)
    grid = rng.integers(-2, 10, size=(rows, cols)).astype(np.int32)
    once = grid.copy()
    impl(once, 3, 0, rows, 0, cols)
    twice = once.copy()
    impl(twice, 3, 0, rows, 0, cols)
    np.testing.assert_array_equal(once, twice)


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p6_exclusion_zone_idempotent(rows, cols):
    _body_p6(_tg.block_exclusion_zone_into_grid_py, rows, cols)


def test_p6_fails_for_nonidempotent_mutant():
    def mutant(grid, net_id, min_row, max_row, min_col, max_col):
        grid[0, 0] += 1  # a genuinely non-idempotent perturbation
        return _tg.block_exclusion_zone_into_grid_py(
            grid, net_id, min_row, max_row, min_col, max_col
        )

    import pytest

    with pytest.raises(AssertionError):
        _body_p6(mutant, 8, 8)


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_count_trace_pad_symmetric(rows, cols):
    rng = np.random.default_rng(rows * 5000 + cols)
    a = rng.integers(-2, 10, size=(rows, cols)).astype(np.int32)
    b = rng.integers(-2, 10, size=(rows, cols)).astype(np.int32)
    assert _tg.count_blocked_cells_py(a, b) == _tg.count_blocked_cells_py(b, a)


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_count_translation_invariant(rows, cols):
    rng = np.random.default_rng(rows * 6000 + cols)
    grid = rng.integers(-2, 10, size=(rows, cols)).astype(np.int32)
    shifted = np.roll(np.roll(grid, 1, axis=0), 1, axis=1)
    assert _tg.count_blocked_cells_py(grid, np.zeros_like(grid)) == _tg.count_blocked_cells_py(
        shifted, np.zeros_like(shifted)
    )


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_exclusion_zone_translation_equivariant(rows, cols):
    rng = np.random.default_rng(rows * 7000 + cols)
    grid = rng.integers(-2, 10, size=(rows, cols)).astype(np.int32)
    if rows < 6 or cols < 6:
        return
    dr, dc = 1, 1
    # Translate the INPUT grid for the second application, then compare the
    # two blocked outputs under the same translation (the write condition
    # `pre == 0 or pre == net_id` is value-dependent, so equivalence holds
    # only when the input values move together with the bbox).
    g1 = grid.copy()
    g2 = np.roll(np.roll(grid, dr, axis=0), dc, axis=1)
    _tg.block_exclusion_zone_into_grid_py(g1, 5, 2, rows - 1, 2, cols - 1)
    _tg.block_exclusion_zone_into_grid_py(g2, 5, 2 + dr, rows - 1 + dr, 2 + dc, cols - 1 + dc)
    np.testing.assert_array_equal(g2, np.roll(np.roll(g1, dr, axis=0), dc, axis=1))


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_exclusion_zone_never_clears(rows, cols):
    rng = np.random.default_rng(rows * 8000 + cols)
    grid = rng.integers(-2, 10, size=(rows, cols)).astype(np.int32)
    before = grid.copy()
    _tg.block_exclusion_zone_into_grid_py(grid, 5, 0, rows, 0, cols)
    assert np.all((grid != 0) | (before == 0)), "exclusion zone cleared a non-zero cell"
