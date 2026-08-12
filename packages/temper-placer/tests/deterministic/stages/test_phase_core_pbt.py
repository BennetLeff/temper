"""Property-based tests for the migrated _phase_core compute.

Wave 4, Phase 5, final leaves. Properties exercise the migrated
``temper_design_bundle_python.deterministic_phase`` kernels
(``footprint_radius_py`` / ``reserve_slots_py`` / ``distance_py``) that the
delegation shim ``deterministic/stages/_phase_core.py`` calls; bit-identical
parity against the pinned pre-migration Python is asserted separately by
``test_phase_core_rust_differential.py``.

Six properties (R1c):

- P1. Footprint-radius shape: with bounds present the radius is >= 1.0
  (``sqrt(...) >= 0``, so ``/2 + 1 >= 1``).
- P2. No-bounds fallback: ``footprint_radius(None, s) == s / 2``.
- P3. Monotonicity in bounds magnitude: enlarging both dimensions (by
  non-negative deltas) does not decrease the radius.
- P4. Reservation subset: every reserved slot is a member of the input list
  and the result never exceeds the input length.
- P5. Distance non-negativity and self-distance zero.
- P6. Determinism: repeated calls agree bit-for-bit.

Three metamorphic relations (R1d):

- MR1. Distance symmetry: ``distance(a, b) == distance(b, a)`` (bit-exact --
  the squared differences negate and ``pow`` is even in the exponent).
- MR2. Footprint-radius axis swap: ``footprint_radius((w, h)) ==
  footprint_radius((h, w))`` (bit-exact -- addition is commutative).
- MR3. Reservation radius monotonicity: enlarging the radius returns a
  superset.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_DP = _tdb.deterministic_phase
RS_FOOTPRINT = _DP.footprint_radius_py
RS_RESERVE = _DP.reserve_slots_py
RS_DISTANCE = _DP.distance_py

_COORD = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False, allow_subnormal=False
)
_POS = st.tuples(_COORD, _COORD)
_NONNEG = st.floats(
    min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False, allow_subnormal=False
)
_SPACING = st.floats(
    min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False, allow_subnormal=False
)
_RADIUS = st.floats(
    min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False, allow_subnormal=False
)


@given(_POS, _SPACING)
@settings(max_examples=200, deadline=None)
def test_p1_footprint_shape(bounds, spacing):
    assert RS_FOOTPRINT(bounds, spacing) >= 1.0


@given(_SPACING)
@settings(max_examples=200, deadline=None)
def test_p2_no_bounds_fallback(spacing):
    assert RS_FOOTPRINT(None, spacing) == spacing / 2.0


@given(_NONNEG, _NONNEG, _NONNEG, _NONNEG, _SPACING)
@settings(max_examples=200, deadline=None)
def test_p3_footprint_monotone(w, h, dw, dh, spacing):
    base = RS_FOOTPRINT((w, h), spacing)
    grown = RS_FOOTPRINT((w + dw, h + dh), spacing)
    assert grown >= base


@given(_POS, _RADIUS, st.lists(_POS, max_size=40))
@settings(max_examples=200, deadline=None)
def test_p4_reserve_subset(center, radius, slots):
    out = RS_RESERVE(center, radius, slots)
    assert len(out) <= len(slots)
    assert set(out) <= set(slots)


@given(_POS, _POS)
@settings(max_examples=200, deadline=None)
def test_p5_distance_non_negative_and_self_zero(p, q):
    assert RS_DISTANCE(p, q) >= 0.0
    assert RS_DISTANCE(p, p) == 0.0


@given(_POS, _SPACING, _POS, _POS, st.lists(_POS, max_size=30))
@settings(max_examples=200, deadline=None)
def test_p6_determinism(bounds, spacing, p, q, slots):
    assert RS_FOOTPRINT(bounds, spacing) == RS_FOOTPRINT(bounds, spacing)
    assert RS_DISTANCE(p, q) == RS_DISTANCE(p, q)
    r = 5.0
    assert RS_RESERVE(p, r, slots) == RS_RESERVE(p, r, slots)


@given(_POS, _POS)
@settings(max_examples=200, deadline=None)
def test_mr1_distance_symmetry(p, q):
    assert RS_DISTANCE(p, q) == RS_DISTANCE(q, p)


@given(_POS, _SPACING)
@settings(max_examples=200, deadline=None)
def test_mr2_footprint_axis_swap(bounds, spacing):
    w, h = bounds
    assert RS_FOOTPRINT((w, h), spacing) == RS_FOOTPRINT((h, w), spacing)


@given(_POS, _RADIUS, _RADIUS, st.lists(_POS, max_size=40))
@settings(max_examples=200, deadline=None)
def test_mr3_reserve_radius_monotone(center, r1, r2, slots):
    lo = RS_RESERVE(center, min(r1, r2), slots)
    hi = RS_RESERVE(center, max(r1, r2), slots)
    assert set(lo) <= set(hi)
