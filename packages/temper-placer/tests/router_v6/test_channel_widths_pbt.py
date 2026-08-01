"""Property-based tests for the batched EDT width lookup.

Five invariants (per the migration roadmap's PBT discipline):

1. Widths are non-negative
2. Widths are bounded by the grid diagonal (2 * max EDT distance)
3. Widths are scale-invariant: scaling coordinates, bounds, and cell
   size by the same factor leaves the grid indices (and widths) unchanged
4. Widths are symmetric under coordinate swap for a symmetric grid
5. Widths are monotonic non-decreasing in the interior mask: growing
   the mask cannot shrink any width

The properties exercise the wrapper
(``temper_placer.router_v6.channel_widths``), the consumer surface the
router sees.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.channel_widths import _edt_width_lookup_batch

MAX_EXAMPLES = 100

_dim = st.integers(4, 40)
_coord = st.floats(min_value=-2.0, max_value=42.0, allow_nan=False, allow_infinity=False)
_scale = st.floats(min_value=0.25, max_value=4.0, allow_nan=False, allow_infinity=False)


def _corridor_grid(h: int, w: int, interior_frac: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Vertical corridor: columns 0..interior_cols-1 are interior (True),
    the rest are wall (False). EDT = horizontal distance to the nearest
    wall column — a genuine nonzero distance field inside the corridor."""
    interior_cols = max(1, int(w * interior_frac))
    mask = np.zeros((h, w), dtype=bool)
    mask[:, :interior_cols] = True
    cols = np.arange(w, dtype=np.float64).reshape(1, -1)
    edt = np.maximum(0.0, interior_cols - cols)
    edt = np.broadcast_to(edt, (h, w)).copy()
    return edt, mask


@given(_dim, _dim, st.lists(_coord, min_size=1, max_size=30), st.lists(_coord, min_size=1, max_size=30))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_widths_non_negative(h: int, w: int, xs: list[float], ys: list[float]) -> None:
    edt, mask = _corridor_grid(h, w)
    widths = _edt_width_lookup_batch(
        np.asarray(xs), np.asarray(ys), edt, mask, (0.0, 0.0, float(w), float(h)), 1.0
    )
    assert (widths >= 0.0).all()


@given(_dim, _dim, st.lists(_coord, min_size=1, max_size=30), st.lists(_coord, min_size=1, max_size=30))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_widths_bounded_by_grid_diagonal(h: int, w: int, xs: list[float], ys: list[float]) -> None:
    edt, mask = _corridor_grid(h, w)
    widths = _edt_width_lookup_batch(
        np.asarray(xs), np.asarray(ys), edt, mask, (0.0, 0.0, float(w), float(h)), 1.0
    )
    max_edt = np.hypot(h - 1, w - 1)
    assert (widths <= 2.0 * max_edt + 1e-9).all()


@given(_dim, _dim, st.lists(st.integers(0, 19).map(lambda i: float(i) + 0.37), min_size=1, max_size=20), _scale)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_widths_scale_invariant(h: int, w: int, coords: list[float], k: float) -> None:
    edt, mask = _corridor_grid(h, w)
    xs = np.asarray(coords)
    ys = np.asarray(coords)
    base = _edt_width_lookup_batch(xs, ys, edt, mask, (0.0, 0.0, float(w), float(h)), 1.0)
    # width = 2*d*cell_size, so scaling cell_size by k scales widths by k.
    # Coordinates are fixed fractions off cell edges: (x*k - min*k)/k != x
    # in f64, so a half-ulp shift at a cell boundary would flip the floor
    # and jump the interpolation — boundary-safe coords keep the grid
    # indices stable and the relation exact to f64 rounding.
    scaled = _edt_width_lookup_batch(
        xs * k, ys * k, edt, mask, (0.0, 0.0, float(w) * k, float(h) * k), k
    )
    np.testing.assert_allclose(scaled, k * base, rtol=1e-9, atol=1e-12)


@given(_dim, st.lists(_coord, min_size=1, max_size=20))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_widths_symmetric_in_square_corridor(n: int, coords: list[float]) -> None:
    # A swap-symmetric, nonzero field: distance to the nearest grid edge
    # of a square (symmetric under (x, y) swap by construction).
    rows = np.arange(n, dtype=np.float64).reshape(-1, 1)
    cols = np.arange(n, dtype=np.float64).reshape(1, -1)
    edt = np.minimum(np.minimum(rows, n - 1 - rows), np.minimum(cols, n - 1 - cols))
    mask = np.ones((n, n), dtype=bool)
    xs = np.asarray(coords)
    ys = np.asarray(coords)[::-1]
    bounds = (0.0, 0.0, float(n), float(n))
    a = _edt_width_lookup_batch(xs, ys, edt, mask, bounds, 1.0)
    b = _edt_width_lookup_batch(ys, xs, edt, mask, bounds, 1.0)
    # Mathematically identical (bilinear weights swap with the field's
    # symmetry), but the two evaluation orders round differently in f64 —
    # assert closeness, not bit equality. (Bit-exactness of the lookup
    # itself is pinned by the differential suite.)
    np.testing.assert_allclose(a, b, rtol=1e-12, atol=1e-12)


@given(_dim, _dim, st.lists(_coord, min_size=1, max_size=20), st.lists(_coord, min_size=1, max_size=20))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_widths_monotonic_in_mask(h: int, w: int, xs: list[float], ys: list[float]) -> None:
    narrow_edt, narrow_mask = _corridor_grid(h, w, interior_frac=0.3)
    wide_edt, wide_mask = _corridor_grid(h, w, interior_frac=0.7)
    bounds = (0.0, 0.0, float(w), float(h))
    narrow = _edt_width_lookup_batch(np.asarray(xs), np.asarray(ys), narrow_edt, narrow_mask, bounds, 1.0)
    wide = _edt_width_lookup_batch(np.asarray(xs), np.asarray(ys), wide_edt, wide_mask, bounds, 1.0)
    assert (wide >= narrow - 1e-9).all()
