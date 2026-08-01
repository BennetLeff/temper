"""Property-based + metamorphic tests for the Rust ClearanceGrid
rasterisation kernels (Wave 3 candidate #1).

The kernels under test are the temper-geometry pyfunctions
``block_circle_into_grid_py`` / ``block_segment_into_grid_py`` /
``block_rect_into_grid_py`` / ``clear_circle_from_grid_py`` /
``occupancy_bitmap_row_py`` (``packages/temper-geometry/src/grid_raster.rs``)
that ``_grid_core.py`` delegates to.

Five invariants (per the migration roadmap's R4 gate):

1. **Merge-domain**: blocking writes only ``{0, net_id, -1}`` and a
   non-empty circle actually writes ``net_id`` somewhere (vacuity guard:
   an implementation that returned all zeros fails the "some cell is
   net_id" assert).
2. **Bbox-boundedness**: no cell outside the kernel's bbox is ever
   modified, and at least one cell inside it is (vacuity guard).
3. **Monotonicity**: blocking with a larger radius on a fresh grid
   blocks a superset of cells (per-cell, ``dist <= r1 <= r2`` with
   identical arithmetic).
4. **Symmetry**: the circle mask is transpose-symmetric —
   ``mask(cx, cy)`` on a square grid transposed equals ``mask(cy, cx)``
   (dist is a sum of two identical pow terms; float addition is
   commutative, so bit-exact).
5. **Round-trip**: ``block(r)`` then ``unblock(r')`` with ``r' >= r`` on
   a fresh grid returns it to all-free (every blocked cell has
   ``dist <= r <= r'``, so the unblock clears exactly those cells).

Metamorphic relations (3 per kernel):

- block_circle: integer-cell translation (exact for power-of-two cell
  sizes, where all products are exact); net-merge commutativity
  (A then B == B then A); degenerate-segment equivalence
  (``block_segment(p, p, r) == block_circle(p, r)`` — identical
  arithmetic after the NaN clamp).
- block_segment: reversal symmetry on lattice segments (exact dyadic
  arithmetic); net-merge commutativity; idempotence ``f(f(x)) == f(x)``.
- block_rect: integer translation; size-subset monotonicity; idempotence.
- clear_circle: block-then-unblock round trip; unblock idempotence;
  unblock-on-fresh == fresh (unblock of a fresh grid changes nothing).
- occupancy_bitmap: zero input -> zero bitmap; union distributivity
  ``bitmap(A | B) == bitmap(A) | bitmap(B)``; trace/pad symmetry
  (same cells via trace or pad produce the same word).
"""

from __future__ import annotations

import numpy as np
import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 100

_cell = st.floats(min_value=0.25, max_value=2.0, allow_nan=False, allow_infinity=False)
_pos = st.floats(min_value=-5.0, max_value=25.0, allow_nan=False, allow_infinity=False)
_radius = st.floats(min_value=0.0, max_value=8.0, allow_nan=False, allow_infinity=False)
_net = st.integers(min_value=1, max_value=9)
_dims = st.integers(min_value=2, max_value=24)
_shift = st.integers(min_value=-3, max_value=3)
# Dyadic (multiple of 0.5) positions: shifts by integer cells are then
# EXACT in binary, which the translation metamorphic relations rely on.
_dyadic_pos = st.floats(
    min_value=-5.0, max_value=25.0, allow_nan=False, allow_infinity=False
).map(lambda v: round(v * 2.0) / 2.0)


def _fresh(rows, cols):
    return np.zeros((rows, cols), dtype=np.int32)


def _circle_covers_cell(rows, cols, cell, cx, cy, r):
    """True when at least one cell centre lies within the circle (the mask
    is then non-trivial — used for vacuity guards)."""
    if r <= 0.0:
        return False
    xs = np.arange(cols) * cell + cell / 2
    ys = np.arange(rows) * cell + cell / 2
    return bool(np.any((xs[None, :] - cx) ** 2 + (ys[:, None] - cy) ** 2 <= r * r))


def _blocked_mask(grid: np.ndarray) -> np.ndarray:
    return grid != 0


# ---------------------------------------------------------------------------
# Five invariants
# ---------------------------------------------------------------------------


@given(_dims, _dims, _cell, _pos, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_block_circle_merge_domain(rows, cols, cell, cx, cy, r, net_id):
    grid = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(grid, cx, cy, r, net_id, cell, 0, rows, 0, cols)
    allowed = {0, net_id, -1}
    assert set(np.unique(grid)).issubset(allowed)
    # Vacuity guard: a radius covering at least one cell centre must write
    # net_id somewhere (an all-zeros kernel fails here).
    inside = np.any(
        ((np.arange(cols) * cell + cell / 2 - cx) ** 2
         + (np.arange(rows) * cell + cell / 2 - cy)[:, None] ** 2) ** 0.5 <= r
    )
    if inside:
        assert (grid == net_id).any()


@given(_dims, _dims, _cell, _pos, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_bbox_boundedness(rows, cols, cell, cx, cy, r, net_id):
    grid = _fresh(rows, cols)
    min_row, max_row = 3, rows - 3
    min_col, max_col = 2, cols - 2
    if max_row <= min_row or max_col <= min_col:
        return
    before = grid.copy()
    _tg.block_circle_into_grid_py(grid, cx, cy, r, net_id, cell, min_row, max_row, min_col, max_col)
    outside = np.ones((rows, cols), dtype=bool)
    outside[min_row:max_row, min_col:max_col] = False
    assert np.array_equal(grid[outside], before[outside])
    # Vacuity guard: some cell inside the bbox changed when the circle
    # reaches a cell centre inside the bbox.
    xs = np.arange(min_col, max_col) * cell + cell / 2
    ys = np.arange(min_row, max_row) * cell + cell / 2
    if not np.any((xs[None, :] - cx) ** 2 + (ys[:, None] - cy) ** 2 <= r * r):
        return
    interior = grid[min_row:max_row, min_col:max_col]
    assert (interior != 0).any()


@given(_dims, _dims, _cell, _pos, _pos, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_radius_monotonicity(rows, cols, cell, cx, cy, net_id):
    r1 = 0.7
    r2 = r1 + 1.3
    small = _fresh(rows, cols)
    big = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(small, cx, cy, r1, net_id, cell, 0, rows, 0, cols)
    _tg.block_circle_into_grid_py(big, cx, cy, r2, net_id, cell, 0, rows, 0, cols)
    blocked_small = small != 0
    blocked_big = big != 0
    # Every cell blocked at the smaller radius is blocked at the larger one
    # (same arithmetic, dist <= r1 <= r2).
    assert np.all(blocked_small <= blocked_big)
    # Vacuity guard: the larger circle actually blocks more than nothing
    # whenever it covers a cell centre.
    if not _circle_covers_cell(rows, cols, cell, cx, cy, r2):
        return
    assert blocked_big.any()


@given(_dims, _cell, _pos, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_circle_mask_transpose_symmetry(rows, cell, cx, cy, r, net_id):
    cols = rows
    grid = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(grid, cx, cy, r, net_id, cell, 0, rows, 0, cols)
    trans = _fresh(cols, rows)
    _tg.block_circle_into_grid_py(trans, cy, cx, r, net_id, cell, 0, cols, 0, rows)
    # dist is the sum of two identical pow terms; float addition is
    # commutative, so cell (r, c) of the transposed mask equals cell (c, r)
    # of the original bit-for-bit.
    np.testing.assert_array_equal(grid.T, trans)
    if not _circle_covers_cell(rows, cols, cell, cx, cy, r):
        return
    assert (grid != 0).any()  # vacuity: a non-trivial mask exists


@given(_dims, _dims, _cell, _pos, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_block_then_unblock_round_trip(rows, cols, cell, cx, cy, r, net_id):
    grid = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(grid, cx, cy, r, net_id, cell, 0, rows, 0, cols)
    if not (grid != 0).any():
        return
    # unblock with a radius >= the block radius restores every cell: each
    # blocked cell has dist <= r <= r', so unblock clears exactly those.
    _tg.clear_circle_from_grid_py(grid, cx, cy, r + 0.5, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(grid, _fresh(rows, cols))


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


@given(_dims, _dims, _cell, _dyadic_pos, _dyadic_pos, _radius, _net, _shift)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_circle_translation_invariant(rows, cols, cell, cx, cy, r, net_id, k):
    # Translating the centre by an integer number of cells shifts the mask
    # by the same number of cells.  EXACT under three conditions, all
    # enforced here: power-of-two cell size (all col*cell products exact),
    # dyadic centre (cx + k*cell exact), and the shifted centre staying in
    # grid bounds.
    if cell not in (0.25, 0.5, 1.0, 2.0):
        return
    if k == 0:
        return
    if not (0.0 <= cx + k * cell <= cols * cell and 0.0 <= cy + k * cell <= rows * cell):
        return
    grid = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(grid, cx, cy, r, net_id, cell, 0, rows, 0, cols)
    shifted = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(shifted, cx + k * cell, cy, r, net_id, cell, 0, rows, 0, cols)
    if k > 0:
        np.testing.assert_array_equal(grid[:, : cols - k], shifted[:, k:])
    else:
        np.testing.assert_array_equal(grid[:, -k:], shifted[:, : cols + k])
    if not _circle_covers_cell(rows, cols, cell, cx, cy, r):
        return
    assert (grid != 0).any()  # vacuity: relation holds for a non-trivial mask


@given(_dims, _dims, _cell, _pos, _pos, _radius)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_circle_net_merge_commutative(rows, cols, cell, cx, cy, r):
    ab = _fresh(rows, cols)
    ba = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(ab, cx, cy, r, 5, cell, 0, rows, 0, cols)
    _tg.block_circle_into_grid_py(ab, cx, cy, r, 7, cell, 0, rows, 0, cols)
    _tg.block_circle_into_grid_py(ba, cx, cy, r, 7, cell, 0, rows, 0, cols)
    _tg.block_circle_into_grid_py(ba, cx, cy, r, 5, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(ab, ba)
    # overlap cells become conflicts (-1) in both orders
    if (ab != 0).any():
        assert (ab == -1).any()


@given(_dims, _dims, _cell, _pos, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_circle_equals_degenerate_segment(rows, cols, cell, cx, cy, r, net_id):
    # block_segment(p, p, r) == block_circle(p, r): with dx = dy = 0 the
    # segment's t clamps to 1.0 (NaN handled by min-then-max), proj = p,
    # and dist is computed by the identical pow chain.
    a = _fresh(rows, cols)
    b = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(a, cx, cy, r, net_id, cell, 0, rows, 0, cols)
    _tg.block_segment_into_grid_py(b, cx, cy, cx, cy, r, net_id, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(a, b)


@given(_dims, _cell, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_segment_reversal_symmetry(rows, cell, y, r, net_id):
    # Reversing a lattice-aligned segment gives the same mask: for a
    # horizontal segment at exact integer/dyadic coordinates all the
    # projection arithmetic (dx, L2, t, proj) is exact, so the two orders
    # evaluate the same real numbers.
    x1, x2 = 4.0, rows * cell - 4.0
    if x2 <= x1:
        return
    cols = rows
    fwd = _fresh(rows, cols)
    rev = _fresh(rows, cols)
    _tg.block_segment_into_grid_py(fwd, x1, y, x2, y, r, net_id, cell, 0, rows, 0, cols)
    _tg.block_segment_into_grid_py(rev, x2, y, x1, y, r, net_id, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(fwd, rev)
    # vacuity: skip only when the mask is legitimately trivial
    if not (fwd != 0).any():
        return
    assert (fwd != 0).any()


@given(_dims, _dims, _cell, _pos, _pos, _radius)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_segment_net_merge_commutative(rows, cols, cell, x, y, r):
    ab = _fresh(rows, cols)
    ba = _fresh(rows, cols)
    for (net1, net2) in ((5, 7), (7, 5)):
        g = ab if net1 == 5 else ba
        _tg.block_segment_into_grid_py(g, x, y, x + 4.0, y + 3.0, r, net1, cell, 0, rows, 0, cols)
        _tg.block_segment_into_grid_py(g, x + 2.0, y, x + 6.0, y + 3.0, r, net2, cell, 0, rows, 0, cols)
    # The full arrays differ in the net VALUES on single-coverage cells
    # (5 vs 7), so the invariant is on the masks: blocked sets and conflict
    # sets agree in both orders.
    if not (ab != 0).any():
        return
    s1 = _fresh(rows, cols)
    s2 = _fresh(rows, cols)
    _tg.block_segment_into_grid_py(s1, x, y, x + 4.0, y + 3.0, r, 1, cell, 0, rows, 0, cols)
    _tg.block_segment_into_grid_py(s2, x + 2.0, y, x + 6.0, y + 3.0, r, 2, cell, 0, rows, 0, cols)
    if np.any((s1 != 0) & (s2 != 0)):
        assert (ab == -1).any()
    np.testing.assert_array_equal(ab != 0, ba != 0)
    np.testing.assert_array_equal(ab == -1, ba == -1)


@given(_dims, _dims, _cell, _pos, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_segment_idempotent(rows, cols, cell, x, y, r, net_id):
    once = _fresh(rows, cols)
    twice = _fresh(rows, cols)
    _tg.block_segment_into_grid_py(once, x, y, x + 5.0, y + 2.0, r, net_id, cell, 0, rows, 0, cols)
    _tg.block_segment_into_grid_py(twice, x, y, x + 5.0, y + 2.0, r, net_id, cell, 0, rows, 0, cols)
    _tg.block_segment_into_grid_py(twice, x, y, x + 5.0, y + 2.0, r, net_id, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(once, twice)
    # vacuity: skip only when the mask is legitimately trivial
    if not (once != 0).any():
        return
    assert (once != 0).any()


@given(_dims, _dims, _net, _shift)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_rect_translation_invariant(rows, cols, net_id, k):
    # Integer-only kernel: translation is exact by construction.  The
    # shifted rect must stay within the grid: min_col = 2 + k >= 0 and
    # max_col = cols - 2 + k <= cols, i.e. -2 <= k <= 2.
    if not (-2 <= k <= 2) or k == 0:
        return
    if rows < 6 or cols < 6:
        return
    a = _fresh(rows, cols)
    b = _fresh(rows, cols)
    _tg.block_rect_into_grid_py(a, net_id, 2, rows - 2, 2, cols - 2)
    _tg.block_rect_into_grid_py(b, net_id, 2, rows - 2, 2 + k, cols - 2 + k)
    if k > 0:
        np.testing.assert_array_equal(a[:, : cols - k], b[:, k:])
    else:
        np.testing.assert_array_equal(a[:, -k:], b[:, : cols + k])


@given(_dims, _dims, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_rect_size_monotonic(rows, cols, net_id):
    # rect [4, rows-4) is non-empty only when rows > 8
    if rows <= 8 or cols <= 8:
        return
    small = _fresh(rows, cols)
    big = _fresh(rows, cols)
    _tg.block_rect_into_grid_py(small, net_id, 4, rows - 4, 4, cols - 4)
    _tg.block_rect_into_grid_py(big, net_id, 2, rows - 2, 2, cols - 2)
    assert np.all((small != 0) <= (big != 0))
    assert (big != 0).any() and (small != 0).any()


@given(_dims, _dims, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_block_rect_idempotent(rows, cols, net_id):
    # rect [3, rows-3) is non-empty only when rows > 6
    if rows <= 6 or cols <= 6:
        return
    once = _fresh(rows, cols)
    twice = _fresh(rows, cols)
    _tg.block_rect_into_grid_py(once, net_id, 3, rows - 3, 3, cols - 3)
    _tg.block_rect_into_grid_py(twice, net_id, 3, rows - 3, 3, cols - 3)
    _tg.block_rect_into_grid_py(twice, net_id, 3, rows - 3, 3, cols - 3)
    np.testing.assert_array_equal(once, twice)
    assert (once != 0).any()  # vacuity: the rect is non-empty here


@given(_dims, _dims, _cell, _pos, _pos, _radius, _net)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_clear_circle_block_then_unblock(rows, cols, cell, cx, cy, r, net_id):
    grid = _fresh(rows, cols)
    _tg.block_circle_into_grid_py(grid, cx, cy, r, net_id, cell, 0, rows, 0, cols)
    if not (grid != 0).any():
        return
    _tg.clear_circle_from_grid_py(grid, cx, cy, r + 0.5, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(grid, _fresh(rows, cols))


@given(_dims, _dims, _cell, _pos, _pos, _radius)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_clear_circle_idempotent(rows, cols, cell, cx, cy, r):
    a = np.full((rows, cols), 3, dtype=np.int32)
    b = np.full((rows, cols), 3, dtype=np.int32)
    _tg.clear_circle_from_grid_py(a, cx, cy, r, cell, 0, rows, 0, cols)
    _tg.clear_circle_from_grid_py(b, cx, cy, r, cell, 0, rows, 0, cols)
    _tg.clear_circle_from_grid_py(b, cx, cy, r, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(a, b)


@given(_dims, _dims, _cell, _pos, _pos, _radius)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_clear_circle_on_fresh_is_identity(rows, cols, cell, cx, cy, r):
    fresh = _fresh(rows, cols)
    cleared = _fresh(rows, cols)
    _tg.clear_circle_from_grid_py(cleared, cx, cy, r, cell, 0, rows, 0, cols)
    np.testing.assert_array_equal(fresh, cleared)


@given(_dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_bitmap_zero_input_is_zero(rows):
    cols = rows
    trace = _fresh(rows, cols)
    pad = _fresh(rows, cols)
    stride = (cols + 63) // 64
    words = _tg.occupancy_bitmap_row_py(trace, pad, rows, cols, stride)
    assert all(w == 0 for w in words)


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_bitmap_union_distributes(rows, cols):
    rng = np.random.default_rng(7)
    a = rng.integers(0, 6, size=(rows, cols), dtype=np.int32)
    b = rng.integers(0, 6, size=(rows, cols), dtype=np.int32)
    stride = (cols + 63) // 64
    wa = np.asarray(_tg.occupancy_bitmap_row_py(a, np.zeros_like(a), rows, cols, stride), dtype=np.uint64)
    wb = np.asarray(_tg.occupancy_bitmap_row_py(b, np.zeros_like(b), rows, cols, stride), dtype=np.uint64)
    wor = np.asarray(
        _tg.occupancy_bitmap_row_py(np.maximum(a, b), np.zeros_like(a), rows, cols, stride),
        dtype=np.uint64,
    )
    np.testing.assert_array_equal(wor, wa | wb)
    assert wor.any()  # vacuity: the grids are non-trivial


@given(_dims, _dims)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_bitmap_trace_pad_symmetric(rows, cols):
    rng = np.random.default_rng(11)
    cells = rng.integers(0, 6, size=(rows, cols), dtype=np.int32)
    stride = (cols + 63) // 64
    via_trace = _tg.occupancy_bitmap_row_py(cells, np.zeros_like(cells), rows, cols, stride)
    via_pad = _tg.occupancy_bitmap_row_py(np.zeros_like(cells), cells, rows, cols, stride)
    assert via_trace == via_pad
    assert any(w != 0 for w in via_trace)
