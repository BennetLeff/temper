"""Property-based tests for the migrated REQ-SAFE-01 clearance geometry
(Wave 3 slice 3).

Five invariants (per the migration roadmap's gate):

P1. Non-negativity: the pad-pair distance is always >= 0.0 (bit-exact).
P2. Symmetry: dist(A, B) == dist(B, A) (within 1 ulp -- the final
    ``max(gap - ra - rb, 0.0)`` subtracts the corner radii in pad order,
    so the two directions can differ by exactly 1 ulp; this is the
    ORACLE's behaviour and is preserved, not "fixed").
P3. Rotation periodicity: rotating both pads around the world origin by
    2*pi preserves the distance (closeness -- 2*pi is not representable).
P4. Boundedness: dist(pad_a, pad_b) <= dist(origins) + reach_a + reach_b
    -- the true copper gap can never exceed the centre distance plus both
    pads' extents (this is the safety direction: the reported figure is
    never an over-estimate).
P5. Monotonicity: growing a pad (widening or lengthening it) can never
    increase the distance to a fixed other pad (bigger copper is closer
    or equal).

The properties exercise the wrapper (``temper_placer.core.pad_geometry.
pad_pair_distance``), the consumer surface the clearance/creepage
validator sees.
"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.pad_geometry import pad_pair_distance

MAX_EXAMPLES = 150

_dim = st.floats(min_value=0.05, max_value=12.0, allow_nan=False, allow_infinity=False)
_pos = st.floats(min_value=-40.0, max_value=40.0, allow_nan=False, allow_infinity=False)
_angle = st.floats(
    min_value=-8 * math.pi, max_value=8 * math.pi, allow_nan=False, allow_infinity=False
)
_shape = st.sampled_from(["circle", "oval", "rect", "roundrect", "thru_hole"])
_ratio = st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False)

_pad = st.tuples(_dim, _dim, _shape, _pos, _pos, _angle, _ratio)


@given(_pad, _pad)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_distance_non_negative(pad_a, pad_b):
    d = pad_pair_distance(pad_a, pad_b)
    assert d >= 0.0
    assert not math.isnan(d)


@given(_pad, _pad)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_distance_symmetric(pad_a, pad_b):
    d_ab = pad_pair_distance(pad_a, pad_b)
    d_ba = pad_pair_distance(pad_b, pad_a)
    assert d_ab == d_ba or abs(d_ab - d_ba) <= 1e-12 * max(1.0, d_ab)


@given(_pad, _pad)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_distance_2pi_rotation_periodic(pad_a, pad_b):
    """Rotating both pads around the world origin by 2*pi is a rigid
    isometry: the distance is preserved up to f64 rounding (2*pi is not
    representable, so the rotated coordinates carry ulp-level noise)."""
    d0 = pad_pair_distance(pad_a, pad_b)
    d1 = pad_pair_distance(_world_rotate(pad_a, 2 * math.pi), _world_rotate(pad_b, 2 * math.pi))
    assert d1 == d0 or abs(d1 - d0) <= 1e-9 * max(1.0, d0)


def _world_rotate(pad, delta):
    w, h, s, cx, cy, rot, rr = pad
    c, sn = math.cos(delta), math.sin(delta)
    return (w, h, s, c * cx - sn * cy, sn * cx + c * cy, rot + delta, rr)


def _bounding_radius(width, height, shape, ratio):
    """The oracle half-extent -> circumscribing-radius chain (matches the
    pre-migration pure-Python pad_bounding_radius)."""
    norm = "circle" if shape == "thru_hole" else shape
    if norm == "circle":
        r = max(width, height) / 2.0
    elif norm == "oval":
        r = min(width, height) / 2.0
    elif norm == "roundrect":
        r = ratio * min(width, height)
    else:
        r = 0.0
    hw = max(width / 2.0 - r, 0.0)
    hh = max(height / 2.0 - r, 0.0)
    return math.hypot(hw, hh) + r


@given(_pad, _pad)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_distance_bounded_by_centre_plus_extents(pad_a, pad_b):
    """The true copper gap is never larger than the pad-centre distance
    plus both pads' full extents -- the safety direction (never an
    over-estimate)."""
    d = pad_pair_distance(pad_a, pad_b)
    wa, ha, sa, cxa, cya, _, rra = pad_a
    wb, hb, sb, cxb, cyb, _, rrb = pad_b
    centre = math.dist((cxa, cya), (cxb, cyb))
    bound = centre + _bounding_radius(wa, ha, sa, rra) + _bounding_radius(wb, hb, sb, rrb)
    assert d <= bound + 1e-9


@given(_pad, _pad, st.floats(min_value=1.01, max_value=4.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_distance_monotonic_in_pad_width(pad_a, pad_b, growth):
    """Widening pad_a can only bring it closer to pad_b, never push it
    further away (bigger copper is closer or equal)."""
    d_small = pad_pair_distance(pad_a, pad_b)
    grown = (pad_a[0] * growth, pad_a[1], pad_a[2], pad_a[3], pad_a[4], pad_a[5], pad_a[6])
    d_big = pad_pair_distance(grown, pad_b)
    assert d_big <= d_small + 1e-9


@given(_pad, _pad, st.floats(min_value=1.01, max_value=4.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_distance_monotonic_in_pad_height(pad_a, pad_b, growth):
    """Lengthening pad_a can only bring it closer to pad_b, never push it
    further away (bigger copper is closer or equal)."""
    d_small = pad_pair_distance(pad_a, pad_b)
    grown = (pad_a[0], pad_a[1] * growth, pad_a[2], pad_a[3], pad_a[4], pad_a[5], pad_a[6])
    d_big = pad_pair_distance(grown, pad_b)
    assert d_big <= d_small + 1e-9
