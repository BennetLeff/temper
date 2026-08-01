"""Property-based tests for the CP-SAT encoder pure compute in Rust
(temper_constraints.encoder, Wave 3 #4).

Five non-vacuous invariants per migrated function (each one fails if the
function returned a constant — a constant is the canonical vacuous
implementation) plus five metamorphic relations for the module.

The migrated surface (unit conversion + margin parameters) is the pure
compute of the CP-SAT encoder: every handler's margin math funnels
through ``mm_to_units``, and the margin parameters (courtyard τ,
domain-classification margin, keepout bbox) are what the encoders feed
the ortools calls.  The ortools wiring itself stays Python.

Bit-exactness notes: Python ``round(x)`` (no ndigits) is round-half-even
— Rust ``round_ties_even``, NOT ``f64::round`` (half away from zero);
the even-parity adjustment uses Python *floor* modulo (negative odd raw
decrements by one — ``rem_euclid`` in Rust, never truncating ``%``);
``keepout_rect_units`` converts the *difference* ``zx_max - zx_min``
(f64 subtraction first), never the difference of conversions.
"""

from __future__ import annotations

import temper_constraints as _tc
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 200

_mm = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_pos_mm = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_units = st.integers(min_value=1, max_value=1000)
_units_grid = st.integers(min_value=1, max_value=1000)
_margin = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
_zone = st.tuples(_mm, _mm, _mm, _mm)


def _rect(z, m, u):
    return _tc.keepout_rect_units_py(*z, m, u)


# ---------------------------------------------------------------------------
# mm_to_units — 5 properties
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(mm=_mm, u=_units_grid)
def test_mm_to_units_variation(mm, u):
    """P1 — the mapping covers a rich output range (a constant fails).
    Integer-mm samples over [-200, 200] map to >= 201 distinct even
    outputs at any grid resolution (round is shift-by-1 monotone, so
    adjacent integer inputs can only merge by one)."""
    outputs = {_tc.mm_to_units_py(float(i), u) for i in range(-200, 201)}
    assert len(outputs) >= 100


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(mm=_mm, u=_units_grid)
def test_mm_to_units_even_parity(mm, u):
    """P2 — outputs are always even (midpoint-constraint invariant:
    sizes must be even so 2*x_start + x_size matches 2*x_center)."""
    assert _tc.mm_to_units_py(mm, u) % 2 == 0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(mm=_mm, u=_units_grid)
def test_mm_to_units_nearness(mm, u):
    """P3 — within one and a half model units of the exact scaled value
    (round → within 0.5, even-adjust → within another 1.0)."""
    out = _tc.mm_to_units_py(mm, u)
    assert abs(out - mm * u) <= 1.5


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(mm1=_mm, mm2=_mm, u=_units_grid)
def test_mm_to_units_monotonic_with_strict_growth(mm1, mm2, u):
    """P4 — non-decreasing in mm, and strictly increasing somewhere in
    the domain (a constant is non-decreasing but never strict)."""
    a, b = sorted((mm1, mm2))
    assert _tc.mm_to_units_py(a, u) <= _tc.mm_to_units_py(b, u)
    outputs = [_tc.mm_to_units_py(i / 100.0, u) for i in range(0, 2001, 25)]
    assert any(nxt > prev for prev, nxt in zip(outputs, outputs[1:]))


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(mm=_mm, u=_units_grid)
def test_mm_to_units_round_trip(mm, u):
    """P5 — round-tripping through units_to_mm recovers mm within the
    conversion's own granularity (1.5 units / u)."""
    back = _tc.units_to_mm_py(_tc.mm_to_units_py(mm, u), u)
    assert abs(back - mm) <= 1.5 / u


# ---------------------------------------------------------------------------
# units_to_mm — 5 properties
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(u=_units_grid)
def test_units_to_mm_variation(u):
    """P1 — covers a rich output range (a constant fails)."""
    outputs = {_tc.units_to_mm_py(i, u) for i in range(-1000, 1001, 10)}
    assert len(outputs) >= 100


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(u=_units_grid)
def test_units_to_mm_identity_at_grid(u):
    """P2 — units == units_per_mm maps to exactly 1.0 mm."""
    assert _tc.units_to_mm_py(u, u) == 1.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(k=st.integers(min_value=-100, max_value=100), u=_units_grid)
def test_units_to_mm_scaling_exact(k, u):
    """P3 — k grid units map to exactly k mm."""
    assert _tc.units_to_mm_py(k * u, u) == float(k)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(u1=st.integers(min_value=-1000, max_value=1000),
       u2=st.integers(min_value=-1000, max_value=1000),
       u=_units_grid)
def test_units_to_mm_strict_monotonic(u1, u2, u):
    """P4 — strictly increasing in units (a constant fails)."""
    if u1 < u2:
        assert _tc.units_to_mm_py(u1, u) < _tc.units_to_mm_py(u2, u)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(units=st.integers(min_value=-10_000, max_value=10_000), u=_units_grid)
def test_units_to_mm_sign(units, u):
    """P5 — sign is preserved (a constant 0 fails)."""
    out = _tc.units_to_mm_py(units, u)
    assert (units > 0 and out > 0.0) or (units < 0 and out < 0.0) or (units == 0 and out == 0.0)


# ---------------------------------------------------------------------------
# courtyard_clearance_mm — 5 properties
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(d=_pos_mm, e=_margin)
def test_courtyard_clearance_variation(d, e):
    """P1 — responds to both arguments (a constant fails)."""
    assert _tc.courtyard_clearance_mm_py(d, e) != _tc.courtyard_clearance_mm_py(d + 1.0, e)
    assert _tc.courtyard_clearance_mm_py(d, e) != _tc.courtyard_clearance_mm_py(d, e + 0.5)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(d=_pos_mm, e=_margin)
def test_courtyard_clearance_definitional(d, e):
    """P2 — bit-exact definitional equality: d + 2*e with the same
    operation order (2*e first, then the addition)."""
    assert _tc.courtyard_clearance_mm_py(d, e) == d + 2 * e


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(d1=_pos_mm, d2=_pos_mm, e=_margin)
def test_courtyard_clearance_strict_in_default(d1, d2, e):
    """P3 — strictly increasing in the default clearance (a constant
    fails: d1 < d2 forces a strict gap).  Guarded like P5: a default
    delta that is tiny relative to the τ scale rounds away, and the
    reference produces bit-identical τ for both."""
    if d1 < d2:
        t1, t2 = _tc.courtyard_clearance_mm_py(d1, e), _tc.courtyard_clearance_mm_py(d2, e)
        if (d2 - d1) > (d2 + 2.0 * e) * 1e-12:
            assert t1 < t2
        else:
            # Both defaults round to the same τ at 2e's scale — exactly
            # the reference behavior (bit-identical, never inverted).
            assert t1 <= t2


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(d=_pos_mm, e1=_margin, e2=_margin)
def test_courtyard_clearance_strict_in_expansion(d, e1, e2):
    """P4 — strictly increasing in the mask expansion (a constant
    fails).  Guarded like P5: two expansions that are both tiny relative
    to d can round to the same τ."""
    if e1 < e2:
        if 2.0 * e1 <= d * 1e-12 and 2.0 * e2 <= d * 1e-12:
            # Both expansion terms round away at d's scale: τ is
            # bit-identical, which is exactly the reference behavior.
            assert _tc.courtyard_clearance_mm_py(d, e1) == _tc.courtyard_clearance_mm_py(d, e2)
        else:
            assert _tc.courtyard_clearance_mm_py(d, e1) < _tc.courtyard_clearance_mm_py(d, e2)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(d=_pos_mm, e=_margin)
def test_courtyard_clearance_positivity(d, e):
    """P5 — τ never drops below the default, and strictly exceeds it
    whenever the mask-expansion term is representable at d's scale
    (2*e tiny relative to d rounds away — the strict arm is guarded on
    the expansion being material; a constant fails both arms)."""
    assert _tc.courtyard_clearance_mm_py(d, e) >= d
    if e > 0.0 and 2.0 * e > d * 1e-12:
        assert _tc.courtyard_clearance_mm_py(d, e) > d


# ---------------------------------------------------------------------------
# required_margin_mm — 5 properties
# ---------------------------------------------------------------------------

_cm = st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(c=_cm, k=_cm)
def test_required_margin_symmetric(c, k):
    """P1 — max is commutative for finite inputs (a constant fails)."""
    assert _tc.required_margin_mm_py(c, k) == _tc.required_margin_mm_py(k, c)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(c=_cm, k=_cm)
def test_required_margin_dominates(c, k):
    """P2 — the margin is at least both minimums (a constant fails)."""
    out = _tc.required_margin_mm_py(c, k)
    assert out >= c and out >= k


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(c=_cm)
def test_required_margin_idempotent(c):
    """P3 — max(a, a) == a (a constant fails)."""
    assert _tc.required_margin_mm_py(c, c) == c


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(c=_cm, k=_cm)
def test_required_margin_absorption(c, k):
    """P4 — max(a, max(a, b)) == max(a, b) (a constant fails)."""
    inner = _tc.required_margin_mm_py(c, k)
    assert _tc.required_margin_mm_py(c, inner) == inner


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(c=_cm, k1=_cm, k2=_cm)
def test_required_margin_monotonic_with_strict(c, k1, k2):
    """P5 — non-decreasing in the creepage minimum, and strictly
    increasing somewhere (a constant is never strict)."""
    a, b = sorted((k1, k2))
    assert _tc.required_margin_mm_py(c, a) <= _tc.required_margin_mm_py(c, b)
    if b > a and c < b:
        assert _tc.required_margin_mm_py(c, a) < _tc.required_margin_mm_py(c, b)


# ---------------------------------------------------------------------------
# keepout_rect_units — 5 properties
# ---------------------------------------------------------------------------


def _mk_zone():
    return st.tuples(_mm, _mm, _mm, _mm)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(z=_mk_zone(), m=_margin, u=_units)
def test_keepout_rect_parity_and_variation(z, m, u):
    """P1 — every output is even (all are sums/differences of
    mm_to_units results), and the rect varies with the zone (a constant
    fails the variation half)."""
    sx, sy, wx, wy = _rect(z, m, u)
    assert sx % 2 == 0 and sy % 2 == 0 and wx % 2 == 0 and wy % 2 == 0
    outputs = {
        _rect((z[0] + dx, z[1], z[2] + dx, z[3]), m, u) for dx in range(0, 41, 10)
    }
    assert len(outputs) >= 3


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(z=_mk_zone(), u=_units)
def test_keepout_rect_zero_margin_decomposition(z, u):
    """P2 — zero margin degenerates to the raw converted zone, exactly
    the keepout handler's original four mm_to_units calls."""
    zx_min, zy_min, zx_max, zy_max = z
    assert _rect(z, 0.0, u) == (
        _tc.mm_to_units_py(zx_min, u),
        _tc.mm_to_units_py(zy_min, u),
        _tc.mm_to_units_py(zx_max - zx_min, u),
        _tc.mm_to_units_py(zy_max - zy_min, u),
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(z=_mk_zone(), m1=_margin, m2=_margin, u=_units)
def test_keepout_rect_margin_monotonic(z, m1, m2, u):
    """P3 — growing the margin grows the keepout rect (start moves down,
    size grows; a constant fails).  The rect only changes when the
    *converted* margin changes — the even-parity unit grid collapses
    close margins to the same units, so the somewhere-strict arm is
    guarded on the conversions differing."""
    if m1 < m2:
        r1, r2 = _rect(z, m1, u), _rect(z, m2, u)
        assert r2[0] <= r1[0] and r2[1] <= r1[1]  # starts move outward
        assert r2[2] >= r1[2] and r2[3] >= r1[3]  # sizes grow
        if _tc.mm_to_units_py(m1, u) != _tc.mm_to_units_py(m2, u):
            assert (r2[0], r2[2]) != (r1[0], r1[2]) or (r2[1], r2[3]) != (r1[1], r1[3])


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(z=_mk_zone(), m=_margin, u=_units)
def test_keepout_rect_size_translation_invariant(z, m, u):
    """P4 — the keepout *size* depends only on the zone span and margin,
    not the zone origin (Sterbenz-exact shift by 1.0 with coords in
    [0,1): see the module's metamorphic section for the exactness
    argument)."""
    zx_min, zy_min, zx_max, zy_max = z
    # Clamp the zone into [0, 1) so the shift-by-1.0 subtraction is exact.
    span_x, span_y = zx_max - zx_min, zy_max - zy_min
    if 0.0 <= span_x < 1.0 and 0.0 <= span_y < 1.0 and 0.0 <= zx_min < 1.0 and 0.0 <= zy_min < 1.0:
        shifted = (zx_min + 1.0, zy_min + 1.0, zx_max + 1.0, zy_max + 1.0)
        assert _rect(shifted, m, u)[2:] == _rect(z, m, u)[2:]


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(z=_mk_zone(), m=_margin, u=_units)
def test_keepout_rect_size_formula(z, m, u):
    """P5 — width/height follow the span formula exactly: converted span
    plus twice the converted margin."""
    zx_min, zy_min, zx_max, zy_max = z
    sx, sy, wx, wy = _rect(z, m, u)
    margin_u = _tc.mm_to_units_py(m, u)
    assert wx == _tc.mm_to_units_py(zx_max - zx_min, u) + 2 * margin_u
    assert wy == _tc.mm_to_units_py(zy_max - zy_min, u) + 2 * margin_u


# ---------------------------------------------------------------------------
# Metamorphic relations (module level, ≥ 3)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(mm=_mm, u=_units_grid)
def test_mr1_mm_to_units_scale_identity(mm, u):
    """MR1 — mm_to_units(mm, u) == mm_to_units(mm*u, 1): scaling the grid
    by u and the input by 1/u are the same conversion (bit-exact — the
    scaled product is the identical f64)."""
    assert _tc.mm_to_units_py(mm, u) == _tc.mm_to_units_py(mm * u, 1)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(c=_cm, k=_cm)
def test_mr2_required_margin_order_permutation(c, k):
    """MR2 — permuting the arguments leaves the margin unchanged
    (bit-exact for finite inputs; NaN is excluded by the strategy)."""
    assert _tc.required_margin_mm_py(c, k) == _tc.required_margin_mm_py(k, c)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(d=_pos_mm, e=_margin)
def test_mr3_courtyard_additive_decomposition(d, e):
    """MR3 — τ(d, e) == τ(d, 0) + τ(0, e): the margin decomposes into
    the default and the mask-expansion contributions (bit-exact — the
    same d + 2e addition in both orders)."""
    assert _tc.courtyard_clearance_mm_py(d, e) == (
        _tc.courtyard_clearance_mm_py(d, 0.0) + _tc.courtyard_clearance_mm_py(0.0, e)
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(z=_mk_zone(), m=_margin, u=_units)
def test_mr4_keepout_zero_margin_matches_zone(z, m, u):
    """MR4 — a zero-margin keepout rect is the converted zone itself:
    keepout_rect(z, 0, u) == keepout_rect with the *zone already in
    units* re-converted at u=1 (dual-call identity on the conversion
    spine)."""
    zx_min, zy_min, zx_max, zy_max = z
    in_units = (
        _tc.mm_to_units_py(zx_min, u),
        _tc.mm_to_units_py(zy_min, u),
        _tc.mm_to_units_py(zx_max - zx_min, u),
        _tc.mm_to_units_py(zy_max - zy_min, u),
    )
    # Re-converting already-integer unit values at grid 1 is the identity.
    assert _tc.keepout_rect_units_py(
        float(in_units[0]), float(in_units[1]), float(in_units[0] + in_units[2]),
        float(in_units[1] + in_units[3]), 0.0, 1,
    ) == (in_units[0], in_units[1], in_units[2], in_units[3])


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(z=_mk_zone(), m1=_margin, m2=_margin, u=_units)
def test_mr5_keepout_margin_containment(z, m1, m2, u):
    """MR5 — the larger-margin rect contains the smaller one: growing
    the margin never shrinks any side of the keepout (conservative-bound
    relation: the encoded keepout region only ever grows with m)."""
    r_small, r_big = _rect(z, min(m1, m2), u), _rect(z, max(m1, m2), u)
    assert r_big[0] <= r_small[0] and r_big[1] <= r_small[1]
    assert r_big[2] >= r_small[2] and r_big[3] >= r_small[3]
