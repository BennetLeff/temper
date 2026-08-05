"""Property-based + metamorphic tests for the migrated grid_utils compute.

Wave 4, Phase 5, first slice (deterministic leaf stages). These properties
exercise the migrated ``temper_geometry.snap_to_grid`` /
``temper_geometry.add_endpoint_nudge`` (the delegation shim
``deterministic/geometry/grid_utils.py`` calls them); bit-identical parity
against the pinned pre-migration Python is asserted separately by
``test_grid_utils_rust_differential.py``.

Five hypothesis properties (R1c, all non-vacuously guarded):

- P1. Idempotence: re-snapping a snapped point is a fixed point
  (bit-exact — the second snap's division result is already integral).
- P2. Half-cell bound: every snapped coordinate is within ``grid_size/2``
  of the input (round-half-even is a nearest-integer rule).
- P3. Power-of-two scale invariance: scaling a point and the grid size by
  the same power of two scales the snap by it, bit-exactly
  (``2^n * x`` is an exact float scaling, and the division
  ``(2^n x) / (2^n g)`` has the same exact ratio as ``x / g``, so the
  correctly-rounded quotient — and hence the round — is unchanged).
- P4. On-grid identity: an exact integer multiple of the grid size snaps
  to itself, bit-exactly.
- P5. Zero fixed point: ``snap_to_grid((0, 0)) == (0, 0)`` exactly, and
  the empty path is returned by ``add_endpoint_nudge`` unchanged.

Three metamorphic relations (R1d):

- MR1. Per-axis independence: snapping ``(x, y)`` equals the snap of
  ``x`` and ``y`` computed independently (the tuple carries no cross-axis
  state).
- MR2. Reflection: ``snap(-p) == -snap(p)`` (numeric equality; ties round
  to even so ``-0.0`` vs ``0.0`` may differ in sign bit — the honest
  bound, checked with ``==``).
- MR3. Nudge order preservation: for a non-empty path, the result contains
  the original path as a contiguous subsequence, with at most one
  coordinate appended before and one after.
"""

from __future__ import annotations

import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

_GRID = st.floats(min_value=1e-3, max_value=4.0, allow_nan=False, allow_infinity=False)
_POS = st.tuples(
    st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
)


@given(_POS, _GRID)
@settings(max_examples=300, deadline=None)
def test_p1_snap_idempotent(pos, gs):
    once = _tg.snap_to_grid(pos[0], pos[1], gs)
    twice = _tg.snap_to_grid(once[0], once[1], gs)
    assert once == twice
    assert once[0].hex() == twice[0].hex() and once[1].hex() == twice[1].hex()


@given(_POS, _GRID)
@settings(max_examples=300, deadline=None)
def test_p2_half_cell_bound(pos, gs):
    sx, sy = _tg.snap_to_grid(pos[0], pos[1], gs)
    assert abs(sx - pos[0]) <= gs / 2 + 1e-12
    assert abs(sy - pos[1]) <= gs / 2 + 1e-12


@given(_POS, _GRID, st.integers(min_value=-8, max_value=8))
@settings(max_examples=200, deadline=None)
def test_p3_pow2_scale_invariance(pos, gs, n):
    k = 2.0**n
    sx, sy = _tg.snap_to_grid(pos[0], pos[1], gs)
    kx, ky = _tg.snap_to_grid(k * pos[0], k * pos[1], k * gs)
    assert kx.hex() == (k * sx).hex()
    assert ky.hex() == (k * sy).hex()


@given(st.integers(min_value=-50, max_value=50), _GRID)
@settings(max_examples=200, deadline=None)
def test_p4_ongrid_identity(i, gs):
    v = i * gs
    sx, sy = _tg.snap_to_grid(v, v, gs)
    assert sx.hex() == v.hex()
    assert sy.hex() == v.hex()


@given(_GRID)
@settings(max_examples=100, deadline=None)
def test_p5_zero_fixed_point(gs):
    assert _tg.snap_to_grid(0.0, 0.0, gs) == (0.0, 0.0)
    # Empty path vacuity guard.
    assert list(_tg.add_endpoint_nudge([], 1.0, 2.0, 3.0, 4.0)) == []


@given(_POS, _GRID)
@settings(max_examples=200, deadline=None)
def test_mr1_axis_independence(pos, gs):
    both = _tg.snap_to_grid(pos[0], pos[1], gs)
    x_only = _tg.snap_to_grid(pos[0], 0.0, gs)
    y_only = _tg.snap_to_grid(0.0, pos[1], gs)
    assert both[0].hex() == x_only[0].hex()
    assert both[1].hex() == y_only[1].hex()


@given(_POS, _GRID)
@settings(max_examples=200, deadline=None)
def test_mr2_reflection(pos, gs):
    sx, sy = _tg.snap_to_grid(pos[0], pos[1], gs)
    rx, ry = _tg.snap_to_grid(-pos[0], -pos[1], gs)
    # Numeric equality; sign-of-zero may differ (round-half-even ties).
    assert rx == -sx and ry == -sy


@given(
    st.lists(
        st.tuples(
            st.floats(min_value=-50.0, max_value=50.0),
            st.floats(min_value=-50.0, max_value=50.0),
        ),
        min_size=1,
        max_size=6,
    ),
    _POS,
    _POS,
)
@settings(max_examples=150, deadline=None)
def test_mr3_nudge_order_preservation(path, start, end):
    flat = [x for p in path for x in p]
    result = list(_tg.add_endpoint_nudge(flat, start[0], start[1], end[0], end[1]))
    pts = [tuple(result[i : i + 2]) for i in range(0, len(result), 2)]
    # The original path appears as a contiguous subsequence.
    for i in range(len(pts) - len(path) + 1):
        if pts[i : i + len(path)] == path:
            break
    else:
        raise AssertionError(f"path {path} not a contiguous subsequence of {pts}")
    # At most one coordinate appended before and one after.
    assert len(pts) - len(path) <= 2
