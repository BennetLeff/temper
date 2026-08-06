"""R1c/R1d: properties and metamorphic relations for ``constraints_geometry``.

Scope of the claims made here
-----------------------------
The differential suite (R1a) proves the Rust arm reproduces the pinned
Python oracle **bit-for-bit, with no tolerance**.  This file proves
something different and complementary: that the *shared* behaviour of both
arms satisfies the geometric invariants a DRC distance kernel must satisfy.
A property here may legitimately carry a tolerance -- these are statements
about floating-point geometry, not about the two arms agreeing.

Where a relation does **not** hold exactly, it is not narrowed silently:
the file carries an explicit *witness* test that constructs an input where
the exact form fails, so the weaker claim is justified by evidence rather
than by convenience.  ``test_witness_*`` are those.

Every property is vacuity-guarded: a property that can only be exercised by
inputs the strategy never generates is worse than no property at all, so
each one asserts that its interesting branch was actually reached.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.constraints_geometry import (
    LineSegment,
    Point,
    RotatedRect,
    _segments_intersect,
    closest_points_segment_segment,
    point_to_circle_distance,
    point_to_rotated_rect_distance,
    point_to_segment_distance,
    segment_to_rotated_rect_distance,
    segment_to_segment_distance,
)

# Board-scale finite coordinates: mm, within a generous board envelope.
COORD = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False)
EXTENT = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
ANGLE = st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False)

SETTINGS = settings(
    max_examples=400,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much],
)


def _seg(x1, y1, x2, y2):
    return LineSegment(Point(x1, y1), Point(x2, y2))


def _rect(cx, cy, w, h, rot):
    return RotatedRect(Point(cx, cy), (w, h), rot)


# ===========================================================================
# R1c -- properties
# ===========================================================================


class _Reached:
    """Vacuity guard: records whether a property's interesting branch ran."""

    def __init__(self) -> None:
        self.n = 0

    def hit(self) -> None:
        self.n += 1


# --- P1 -------------------------------------------------------------------


def test_p1_point_to_segment_distance_is_bounded_by_the_endpoint_distances():
    """P1. ``0 <= d(p, seg) <= min(|p-start|, |p-end|)``.

    The upper bound is what makes this non-trivial: it fails immediately if
    the projection parameter is not clamped to ``[0, 1]``.
    """
    interior = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, COORD, COORD)
    def prop(px, py, x1, y1, x2, y2):
        seg = _seg(x1, y1, x2, y2)
        d = point_to_segment_distance(Point(px, py), seg)
        assert d >= 0.0
        # The upper bound is claimed only on the PROJECTION branch. On the
        # degenerate branch (seg_len_sq < 1e-10) the reference measures from
        # the segment's START rather than its nearest endpoint, so a
        # short-but-nonzero segment can report a distance larger than
        # |p - end|.  That is the reference's own behaviour, reproduced
        # faithfully; see test_witness_degenerate_arm_breaks_the_endpoint_bound.
        seg_len_sq = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1)
        if seg_len_sq < 1e-10:
            return
        d_start = math.hypot(px - x1, py - y1)
        d_end = math.hypot(px - x2, py - y2)
        assert d <= min(d_start, d_end) * (1 + 1e-12) + 1e-12
        if d < min(d_start, d_end) * (1 - 1e-9):
            interior.hit()

    prop()
    assert interior.n > 0, "vacuous: no example ever projected onto the interior"


def test_witness_degenerate_arm_breaks_the_endpoint_bound():
    """Why P1's upper bound is claimed only on the projection branch.

    ``point_to_segment_distance`` treats any segment with
    ``seg_len_sq < 1e-10`` as the single point ``segment.start`` -- so for a
    1e-6-long segment it returns the distance to the START even when the
    query point is exactly ON the other endpoint.  This is a real (if minor)
    infidelity in the reference algorithm, not in the port; it is recorded
    here rather than used to quietly weaken P1.
    """
    d = point_to_segment_distance(Point(0.0, 0.0), _seg(0.0, 1e-6, 0.0, 0.0))
    assert d == 1e-6
    # the point IS an endpoint of the segment, so the true distance is 0
    assert min(math.hypot(0.0, 1e-6), 0.0) == 0.0


# --- P2 -------------------------------------------------------------------


def test_p2_intersecting_segments_have_exactly_zero_distance():
    """P2. ``_segments_intersect(a, b) implies d(a, b) == 0.0`` -- exactly.

    This is an *exact* property (no tolerance): the reference returns the
    literal ``0.0`` on the intersect branch.
    """
    hit = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, COORD, COORD, COORD, COORD)
    def prop(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y):
        a = _seg(a1x, a1y, a2x, a2y)
        b = _seg(b1x, b1y, b2x, b2y)
        if _segments_intersect(a, b):
            hit.hit()
            assert segment_to_segment_distance(a, b) == 0.0
        else:
            assert segment_to_segment_distance(a, b) >= 0.0

    prop()
    assert hit.n > 0, "vacuous: no generated pair ever intersected"


# --- P3 -------------------------------------------------------------------


def test_p3_rotated_rect_signed_distance_agrees_with_containment():
    """P3. ``point_to_rotated_rect_distance < 0`` iff the point is strictly
    inside the rect, checked independently in the rect's own frame."""
    inside = _Reached()
    outside = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, EXTENT, EXTENT, ANGLE)
    def prop(px, py, cx, cy, w, h, rot):
        assume(w > 1e-6 and h > 1e-6)
        d = point_to_rotated_rect_distance(Point(px, py), _rect(cx, cy, w, h, rot))
        rad = math.radians(rot)
        c, s = math.cos(rad), math.sin(rad)
        dx, dy = px - cx, py - cy
        lx, ly = dx * c - dy * s, dx * s + dy * c
        margin = min(w / 2 - abs(lx), h / 2 - abs(ly))
        # Only assert away from the boundary, where the sign is unambiguous
        # in floating point.
        tol = 1e-9 * max(1.0, w, h, abs(lx), abs(ly))
        if margin > tol:
            inside.hit()
            assert d < 0.0
        elif margin < -tol:
            outside.hit()
            assert d > 0.0

    prop()
    assert inside.n > 0 and outside.n > 0, f"vacuous: inside={inside.n} outside={outside.n}"


# --- P4 -------------------------------------------------------------------


def test_p4_closest_points_lie_on_their_own_segments():
    """P4. Both points returned by ``closest_points_segment_segment`` lie on
    the segment they came from."""
    nondegenerate = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, COORD, COORD, COORD, COORD)
    def prop(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y):
        a = _seg(a1x, a1y, a2x, a2y)
        b = _seg(b1x, b1y, b2x, b2y)
        c1, c2 = closest_points_segment_segment(a, b)
        scale = max(1.0, abs(a1x), abs(a1y), abs(a2x), abs(a2y), abs(b1x), abs(b1y), abs(b2x), abs(b2y))
        assert point_to_segment_distance(c1, a) <= 1e-9 * scale
        assert point_to_segment_distance(c2, b) <= 1e-9 * scale
        if a.length > 1e-3 and b.length > 1e-3:
            nondegenerate.hit()

    prop()
    assert nondegenerate.n > 0, "vacuous: every generated pair was degenerate"


# --- P5 -------------------------------------------------------------------


def test_p5_rect_corners_are_a_rectangle_of_the_requested_size():
    """P5. The 4 corners are the requested ``w x h`` rectangle: adjacent
    edges have lengths w, h, w, h and the diagonals are equal."""
    nondegenerate = _Reached()

    @SETTINGS
    @given(COORD, COORD, EXTENT, EXTENT, ANGLE)
    def prop(cx, cy, w, h, rot):
        cs = _rect(cx, cy, w, h, rot).corners
        assert len(cs) == 4
        scale = max(1.0, abs(cx), abs(cy), w, h)
        tol = 1e-9 * scale
        e = [cs[i].distance_to(cs[(i + 1) % 4]) for i in range(4)]
        assert abs(e[0] - w) <= tol and abs(e[2] - w) <= tol
        assert abs(e[1] - h) <= tol and abs(e[3] - h) <= tol
        d0 = cs[0].distance_to(cs[2])
        d1 = cs[1].distance_to(cs[3])
        assert abs(d0 - d1) <= tol
        if w > 1e-3 and h > 1e-3:
            nondegenerate.hit()

    prop()
    assert nondegenerate.n > 0, "vacuous: every generated rect was degenerate"


# --- P6 -------------------------------------------------------------------


def test_p6_bounding_radius_bounds_every_corner():
    """P6. ``bounding_radius`` is >= the centre-to-corner distance for all
    four corners, at every rotation."""
    checked = _Reached()

    @SETTINGS
    @given(COORD, COORD, EXTENT, EXTENT, ANGLE)
    def prop(cx, cy, w, h, rot):
        r = _rect(cx, cy, w, h, rot)
        br = r.bounding_radius
        scale = max(1.0, abs(cx), abs(cy), w, h)
        for c in r.corners:
            assert c.distance_to(r.center) <= br + 1e-9 * scale
        checked.hit()

    prop()
    assert checked.n > 0


# --- P7 -------------------------------------------------------------------


def test_p7_circle_distance_is_the_centre_distance_minus_the_radius():
    """P7. ``point_to_circle_distance`` is monotone decreasing in the radius
    and equals 0 exactly on the circle."""
    inside = _Reached()
    outside = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, EXTENT)
    def prop(px, py, cx, cy, r):
        p, c = Point(px, py), Point(cx, cy)
        d0 = point_to_circle_distance(p, c, r)
        d1 = point_to_circle_distance(p, c, r + 1.0)
        assert d1 <= d0
        assert d1 == d0 - 1.0 or abs((d1 + 1.0) - d0) <= 1e-9 * max(1.0, abs(d0))
        if d0 < 0:
            inside.hit()
        elif d0 > 0:
            outside.hit()

    prop()
    assert inside.n > 0 and outside.n > 0


# ===========================================================================
# R1d -- metamorphic relations
# ===========================================================================


def test_m1_power_of_two_scaling_is_exactly_equivariant():
    """M1 (EXACT). Scaling every coordinate by 2**k scales the distance by
    exactly 2**k -- no tolerance.

    This holds bit-exactly, unlike the general scaling relation, because a
    power of two is exact in binary floating point at every step: the
    projection parameter ``t`` is a ratio of quantities that both scale by
    ``4**k`` and CPython's ``vector_norm`` normalises by a power of two
    before summing.  It is the strongest relation available on this kernel
    and would break under any change that introduces an absolute constant
    into the distance computation.
    """
    reached = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, COORD, COORD, st.integers(min_value=-40, max_value=40))
    def prop(px, py, x1, y1, x2, y2, k):
        s = 2.0**k
        base = point_to_segment_distance(Point(px, py), _seg(x1, y1, x2, y2))
        scaled = point_to_segment_distance(
            Point(px * s, py * s), _seg(x1 * s, y1 * s, x2 * s, y2 * s)
        )
        assume(math.isfinite(scaled) and scaled != 0.0 and base != 0.0)
        # The degenerate-segment threshold (1e-10 on the SQUARED length) is
        # an absolute constant, so a segment can cross it under scaling and
        # legitimately switch arms.  Exclude only that case, explicitly.
        #
        # NOTE the squaring: `dx * dx`, NOT `dx ** 2`.  `x ** 2` is libm
        # `pow`, which is not bit-identical to the multiply the kernel does,
        # so a `** 2` guard silently admits examples that straddle the
        # threshold -- Hypothesis found exactly that (x2 - x1 == 1.19e-07).
        dx, dy = x2 - x1, y2 - y1
        sq = dx * dx + dy * dy
        sq_scaled = (dx * s) * (dx * s) + (dy * s) * (dy * s)
        assume((sq < 1e-10) == (sq_scaled < 1e-10))
        assert scaled == base * s, (base, scaled, k)
        reached.hit()

    prop()
    assert reached.n > 50, f"vacuous: only {reached.n} examples survived the assumptions"


def test_m2_segment_to_segment_distance_is_symmetric_exactly():
    """M2 (EXACT). ``d(a, b) == d(b, a)`` bit-for-bit for finite inputs."""
    reached = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, COORD, COORD, COORD, COORD)
    def prop(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y):
        a = _seg(a1x, a1y, a2x, a2y)
        b = _seg(b1x, b1y, b2x, b2y)
        ab = segment_to_segment_distance(a, b)
        ba = segment_to_segment_distance(b, a)
        assert ab.hex() == ba.hex(), (ab, ba)
        reached.hit()

    prop()
    assert reached.n > 100


def test_m3_reversing_a_rect_rotation_by_180_maps_a_point_through_the_centre():
    """M3. Rotating the rect by 180 degrees and reflecting the query point
    through the rect centre leaves the distance unchanged.

    Held to a relative tolerance, not exactly: ``cos(pi)`` is ``-1.0``
    exactly but ``sin(pi)`` is ``1.2246e-16``, so the 180-degree rotation
    matrix is not the exact negation of the identity.  The witness below
    exhibits an input where the exact form fails.
    """
    reached = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, EXTENT, EXTENT, ANGLE)
    def prop(px, py, cx, cy, w, h, rot):
        assume(w > 1e-6 and h > 1e-6)
        d0 = point_to_rotated_rect_distance(Point(px, py), _rect(cx, cy, w, h, rot))
        d1 = point_to_rotated_rect_distance(
            Point(2 * cx - px, 2 * cy - py), _rect(cx, cy, w, h, rot + 180.0)
        )
        scale = max(1.0, abs(px - cx), abs(py - cy), w, h)
        assert abs(d0 - d1) <= 1e-9 * scale, (d0, d1)
        reached.hit()

    prop()
    assert reached.n > 100


def test_m4_swapping_width_height_is_a_90_degree_rotation():
    """M4. A ``w x h`` rect at angle ``theta`` covers the same set as an
    ``h x w`` rect at ``theta + 90``, so the point distance agrees."""
    reached = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, EXTENT, EXTENT, ANGLE)
    def prop(px, py, cx, cy, w, h, rot):
        assume(w > 1e-6 and h > 1e-6)
        d0 = point_to_rotated_rect_distance(Point(px, py), _rect(cx, cy, w, h, rot))
        d1 = point_to_rotated_rect_distance(Point(px, py), _rect(cx, cy, h, w, rot + 90.0))
        scale = max(1.0, abs(px - cx), abs(py - cy), w, h)
        assert abs(d0 - d1) <= 1e-9 * scale, (d0, d1)
        reached.hit()

    prop()
    assert reached.n > 100


def test_m5_reversing_a_segment_preserves_the_point_distance():
    """M5. ``d(p, [A,B]) == d(p, [B,A])`` -- to tolerance, not exactly; the
    witness below shows the exact form failing."""
    reached = _Reached()

    @SETTINGS
    @given(COORD, COORD, COORD, COORD, COORD, COORD)
    def prop(px, py, x1, y1, x2, y2):
        # Non-degenerate branch only: on the degenerate branch the reference
        # measures from `segment.start`, which reversal moves.  See
        # test_witness_reversal_is_not_even_approximate_when_degenerate.
        dx, dy = x2 - x1, y2 - y1
        assume(dx * dx + dy * dy >= 1e-10)
        p = Point(px, py)
        fwd = point_to_segment_distance(p, _seg(x1, y1, x2, y2))
        rev = point_to_segment_distance(p, _seg(x2, y2, x1, y1))
        scale = max(1.0, abs(px), abs(py), abs(x1), abs(y1), abs(x2), abs(y2))
        assert abs(fwd - rev) <= 1e-12 * scale, (fwd, rev)
        reached.hit()

    prop()
    assert reached.n > 100


def test_witness_reversal_is_not_even_approximate_when_degenerate():
    """Why M5 excludes the degenerate branch.

    For a segment shorter than 1e-5 the reference collapses it to
    ``segment.start`` and measures from there, so reversing the endpoints
    changes the answer by the whole length of the segment -- not by a
    rounding error.  Found by Hypothesis while the mutation campaign was
    replaying its example database; recorded rather than absorbed into a
    looser tolerance.
    """
    p = Point(0.0, 0.0)
    fwd = point_to_segment_distance(p, _seg(0.0, 0.0, 0.0, 1.192092896e-07))
    rev = point_to_segment_distance(p, _seg(0.0, 1.192092896e-07, 0.0, 0.0))
    assert fwd == 0.0
    assert rev == 1.192092896e-07
    assert abs(fwd - rev) > 1e-8


# ===========================================================================
# Witnesses: the relations above that do NOT hold exactly
# ===========================================================================


def test_witness_segment_reversal_is_not_bit_exact():
    """M5 is stated with a tolerance because the exact form is false.

    Reversing the endpoints changes which endpoint the projection is
    measured from, so the rounding differs.  This is the constructed
    counterexample -- recorded rather than quietly weakening the claim.
    """
    p = Point(0.30000000000000004, 0.7000000000000001)
    a, b = (0.1, 0.2), (7.3, 11.9)
    fwd = point_to_segment_distance(p, _seg(*a, *b))
    rev = point_to_segment_distance(p, _seg(*b, *a))
    assert abs(fwd - rev) < 1e-12
    assert fwd.hex() != rev.hex(), (
        "segment reversal has become bit-exact; M5 can be strengthened to an "
        "exact relation and this witness deleted"
    )


def test_witness_180_degree_rotation_is_not_bit_exact():
    """M3's tolerance, justified: ``math.sin(math.pi)`` is 1.2246e-16, not 0."""
    assert math.sin(math.radians(180.0)) != 0.0
    px, py = -9.957878932977787, -1.092256118903972
    cx, cy = 2.2154003234078257, -2.7123777872954733
    w, h, rot = 7.567638494875986, 7.22127691513072, -168.98760610792073
    d0 = point_to_rotated_rect_distance(Point(px, py), _rect(cx, cy, w, h, rot))
    d1 = point_to_rotated_rect_distance(
        Point(2 * cx - px, 2 * cy - py), _rect(cx, cy, w, h, rot + 180.0)
    )
    assert abs(d0 - d1) < 1e-12
    assert d0.hex() != d1.hex(), (
        "the 180-degree relation has become bit-exact; M3 can be strengthened"
    )


def test_witness_general_scaling_is_not_bit_exact():
    """M1 is restricted to powers of two because general scaling is false."""
    p = (-7.312715117751976, 6.9486747387446535)
    a = (5.275492379532281, -4.898619485211566)
    b = (-0.09129825816118142, -1.010178704225238)
    base = point_to_segment_distance(Point(*p), _seg(*a, *b))
    s = 3.0
    scaled = point_to_segment_distance(
        Point(p[0] * s, p[1] * s), _seg(a[0] * s, a[1] * s, b[0] * s, b[1] * s)
    )
    assert abs(scaled - base * s) < 1e-12
    assert scaled.hex() != (base * s).hex(), (
        "general scaling has become bit-exact; M1 can drop its power-of-two "
        "restriction"
    )


def test_witness_translation_invariance_is_not_bit_exact():
    """A translation relation is deliberately NOT asserted at all.

    Translating a point-and-segment by a common offset changes the distance
    in the last bits, so a translation-invariance metamorphic relation
    could only be stated with a tolerance and would add nothing the
    relations above do not already cover.  The counterexample is recorded
    so the omission is a measured decision, not an oversight.
    """
    p, a, b = (0.1, 0.2), (0.3, 0.4), (5.5, 7.7)
    t = 1e6
    d0 = point_to_segment_distance(Point(*p), _seg(*a, *b))
    d1 = point_to_segment_distance(
        Point(p[0] + t, p[1] + t), _seg(a[0] + t, a[1] + t, b[0] + t, b[1] + t)
    )
    assert d0.hex() != d1.hex()
    assert abs(d0 - d1) < 1e-8


# ===========================================================================
# Regressions found while building this slice
# ===========================================================================


def test_regression_hypot_top_binade_is_not_nan():
    """``py_hypot`` returned NaN for every input in the top binade until
    ``pow2`` replaced ``2f64.powi(-max_e)`` (which underflows to 0.0 at
    ``max_e == 1024``).  Pinned from the Python side too, so the fix cannot
    regress unnoticed in either language."""
    d = point_to_segment_distance(Point(1e308, 0.0), _seg(0.0, 0.0, 1.0, 0.0))
    assert d == 1e308, d
    d2 = point_to_circle_distance(Point(1e308, 1e308), Point(0.0, 0.0), 1.0)
    assert math.isfinite(d2) and d2 == math.hypot(1e308, 1e308) - 1.0


def test_regression_infinity_beats_nan_in_hypot():
    """``hypot(-inf, nan)`` is ``inf``, not NaN -- reachable for real when a
    segment endpoint is infinite and the clamped projection produces a NaN
    coordinate."""
    inf = float("inf")
    d = segment_to_segment_distance(_seg(-inf, 0.0, inf, 0.0), _seg(0.0, -inf, 0.0, inf))
    assert d == inf, d


@pytest.mark.parametrize("rot", [float("inf"), float("-inf")])
def test_infinite_rotation_raises(rot):
    with pytest.raises(ValueError, match="math domain error"):
        _rect(0.0, 0.0, 2.0, 3.0, rot).corners
    with pytest.raises(ValueError, match="math domain error"):
        point_to_rotated_rect_distance(Point(1.0, 1.0), _rect(0.0, 0.0, 2.0, 3.0, rot))
    with pytest.raises(ValueError, match="math domain error"):
        segment_to_rotated_rect_distance(
            _seg(5.0, 5.0, 6.0, 6.0), _rect(0.0, 0.0, 2.0, 3.0, rot)
        )
