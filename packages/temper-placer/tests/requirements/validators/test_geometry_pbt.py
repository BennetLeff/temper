"""Property-based tests for the Rust-backed geometry kernels
(``temper_placer/requirements/validators/_geometry.py``, delegating to
``temper-geometry``'s ``geometry_kernels.rs``).

Six non-vacuous properties over randomized finite-coordinate fixtures, all
exercised through the production shim functions:

- P1 ``_distance`` is non-negative and exactly symmetric
- P2 ``_point_to_segment_distance`` is bounded by both endpoint distances
- P3 ``_segment_to_segment_distance`` is exactly the 4-candidate min when
  the segments do not intersect, and exactly 0.0 when they do
- P4 ``_point_to_polyline_distance`` is exactly the per-segment minimum
- P5 ``_polyline_min_distance`` is exactly the per-segment-pair minimum and
  0.0 iff the polylines cross
- P6 ``_point_to_polyline_distance`` is monotone non-increasing when a
  far-away point is appended (absorption)

Metamorphic relations (G5), exactness claims stated per relation:

- M1 translation invariance of ``_distance`` / ``_point_to_segment_distance``
  / ``_polyline_length`` (exact: integer coordinates + power-of-two offset)
- M2 ``_rects_overlap`` commutativity (exact boolean)
- M3 segment reversal of ``_point_to_segment_distance`` (tight tolerance:
  the clamped projection's rounding can differ in the last ulp)
- M4 ``_point_in_rect`` translation invariance (exact, integer + 2^k)
- M5 ``_rects_overlap`` translation invariance (exact, integer + 2^k)

Every property carries a ``test_pN_fails_for_<mutant>`` companion proving a
degenerate (constant / position-deleted) kernel violates it (G4 vacuity
guard).
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.requirements.validators import _geometry as geom

_FINITE = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
_POINT = st.tuples(_FINITE, _FINITE)
_RECT = st.tuples(_FINITE, _FINITE, _FINITE, _FINITE)


@st.composite
def polyline(draw):
    n = draw(st.integers(min_value=1, max_value=6))
    return [draw(_POINT) for _ in range(n)]


@st.composite
def two_polylines(draw):
    return draw(polyline()), draw(polyline())


# ---------------------------------------------------------------------------
# P1 — distance: non-negative and exactly symmetric
# ---------------------------------------------------------------------------


@given(_POINT, _POINT)
@settings(max_examples=200, deadline=60000)
def test_p1_distance_nonnegative_and_symmetric(a, b) -> None:
    d_ab = geom._distance(a, b)
    d_ba = geom._distance(b, a)
    assert d_ab >= 0.0
    assert d_ab == d_ba  # negation is exact in IEEE; both use vector_norm


# ---------------------------------------------------------------------------
# P2 — point-to-segment distance bounded by the endpoint distances
# ---------------------------------------------------------------------------

# Coordinates in a comparable-magnitude band: the reference's own projection
# arithmetic can lose catastrophic precision when a segment endpoint is
# subnormal next to a unit-scale one (the computed closest point can land a
# hair off the true segment), so P2's bound is stated for this domain.
_COORD = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
).filter(lambda x: abs(x) >= 1e-3 or x == 0.0)
_POINT_BOUNDED = st.tuples(_COORD, _COORD)


@given(_POINT_BOUNDED, _POINT_BOUNDED, _POINT_BOUNDED)
@settings(max_examples=200, deadline=60000)
def test_p2_point_to_segment_bounded_by_endpoints(p, a, b) -> None:
    d = geom._point_to_segment_distance(p, a, b)
    da = geom._distance(p, a)
    db = geom._distance(p, b)
    abx, aby = b[0] - a[0], b[1] - a[1]
    len2 = abx * abx + aby * aby
    if len2 < 1e-12:
        # the reference's degenerate arm returns the distance to `a`
        # regardless of where p actually lies (pinned bit-exactly by the
        # differential suite) -- pin it here exactly, no bound applies
        assert d == da
    else:
        # the clamped projection is never farther than either endpoint in
        # exact arithmetic; the reference's own projection rounding can add
        # ~1 ulp of the coordinate scale, so the band is a relative 1e-9
        # plus an absolute 1e-12 * scale floor (still ~1e5 ulps too tight
        # to mask a genuinely wrong kernel)
        scale = max(1.0, abs(p[0]), abs(p[1]), abs(a[0]), abs(a[1]), abs(b[0]), abs(b[1]))
        assert d <= (1.0 + 1e-9) * min(da, db) + 1e-12 * scale


# ---------------------------------------------------------------------------
# P3 — segment-to-segment distance: 0 iff intersecting, else the exact min
# ---------------------------------------------------------------------------


@given(_POINT, _POINT, _POINT, _POINT)
@settings(max_examples=200, deadline=60000)
def test_p3_segment_to_segment_is_candidate_min(a, b, c, d) -> None:
    dist = geom._segment_to_segment_distance(a, b, c, d)
    if geom._segments_intersect(a, b, c, d):
        assert dist == 0.0
    else:
        candidates = (
            geom._point_to_segment_distance(a, c, d),
            geom._point_to_segment_distance(b, c, d),
            geom._point_to_segment_distance(c, a, b),
            geom._point_to_segment_distance(d, a, b),
        )
        assert dist == min(candidates)


# ---------------------------------------------------------------------------
# P4 — point-to-polyline distance: exact per-segment minimum
# ---------------------------------------------------------------------------


@given(_POINT, polyline())
@settings(max_examples=200, deadline=60000)
def test_p4_point_to_polyline_is_segment_min(p, poly) -> None:
    d = geom._point_to_polyline_distance(p, poly)
    if not poly:
        assert d == math.inf
    elif len(poly) == 1:
        assert d == geom._distance(p, poly[0])
    else:
        per_segment = [
            geom._point_to_segment_distance(p, poly[i], poly[i + 1])
            for i in range(len(poly) - 1)
        ]
        assert d == min(per_segment)


# ---------------------------------------------------------------------------
# P5 — polyline-min distance: exact per-pair minimum, 0 iff crossing
# ---------------------------------------------------------------------------


@given(two_polylines())
@settings(max_examples=200, deadline=60000)
def test_p5_polyline_min_is_pair_min(pair) -> None:
    poly1, poly2 = pair
    d = geom._polyline_min_distance(poly1, poly2)
    if not poly1 or not poly2:
        assert d == math.inf
    elif geom._polylines_intersect(poly1, poly2):
        assert d == 0.0
    elif len(poly1) == 1:
        assert d == geom._point_to_polyline_distance(poly1[0], poly2)
    elif len(poly2) == 1:
        assert d == geom._point_to_polyline_distance(poly2[0], poly1)
    else:
        per_pair = [
            geom._segment_to_segment_distance(poly1[i], poly1[i + 1], poly2[j], poly2[j + 1])
            for i in range(len(poly1) - 1)
            for j in range(len(poly2) - 1)
        ]
        assert d == min(per_pair)


# ---------------------------------------------------------------------------
# P6 — absorption: appending a far-away point cannot increase the
# point-to-polyline distance
# ---------------------------------------------------------------------------


@given(_POINT, polyline())
@settings(max_examples=200, deadline=60000)
def test_p6_appending_point_is_monotone(p, poly) -> None:
    d_before = geom._point_to_polyline_distance(p, poly)
    if not poly:
        return
    # a point ~1e6 away from the current nearest distance cannot reduce it
    far = (p[0] + 1e6, p[1] + 1e6)
    d_after = geom._point_to_polyline_distance(p, [*poly, far])
    assert d_after <= d_before + 1e-9


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


def _shift(points, offset):
    return [(x + offset, y + offset) for x, y in points]


@given(st.integers(min_value=-40, max_value=40), st.integers(min_value=-40, max_value=40))
@settings(max_examples=200, deadline=60000)
def test_m1_translation_invariance_integer_coords(ix, iy) -> None:
    """Exact: integer coordinates translated by a power-of-two offset keep
    every difference bit-identical, so distances and lengths are unchanged
    bit-for-bit."""
    offset = 2.0**20
    a = (float(ix), float(iy))
    b = (float(ix + 7), float(iy - 13))
    p = (float(ix - 3), float(iy + 11))
    seg = [(float(ix), float(iy)), (float(ix + 9), float(iy - 5))]

    a_s, b_s, p_s = _shift([a, b, p], offset)
    seg_s = _shift(seg, offset)
    assert geom._distance(a, b) == geom._distance(a_s, b_s)
    assert geom._point_to_segment_distance(p, a, b) == geom._point_to_segment_distance(
        p_s, seg_s[0], seg_s[1]
    )
    assert geom._polyline_length([a, b, p]) == geom._polyline_length(_shift([a, b, p], offset))


@given(_RECT, _RECT)
@settings(max_examples=200, deadline=60000)
def test_m2_rects_overlap_commutative(r1, r2) -> None:
    """Exact boolean: overlap is symmetric."""
    assert geom._rects_overlap(r1, r2) == geom._rects_overlap(r2, r1)


@given(_POINT, _POINT, _POINT)
@settings(max_examples=200, deadline=60000)
def test_m3_segment_reversal_within_tolerance(p, a, b) -> None:
    """Tight tolerance on the PROJECTION arm only: reversing the segment
    mirrors the projection parameter, whose rounding can differ from
    ``1 - t`` in the last ulp.  (The degenerate arm is deliberately not
    covered: for ``len2 < 1e-12`` the reference returns the distance to
    ``a``, so reversal swaps which endpoint is measured — a pinned quirk,
    not a symmetry.)"""
    abx, aby = b[0] - a[0], b[1] - a[1]
    if abx * abx + aby * aby < 1e-12:
        return
    d1 = geom._point_to_segment_distance(p, a, b)
    d2 = geom._point_to_segment_distance(p, b, a)
    scale = max(1.0, abs(d1), abs(d2))
    assert abs(d1 - d2) <= 1e-9 * scale


@given(st.integers(min_value=-40, max_value=40), st.integers(min_value=-40, max_value=40))
@settings(max_examples=200, deadline=60000)
def test_m4_point_in_rect_translation_invariant(ix, iy) -> None:
    """Exact (integer coords + power-of-two offset): membership is unchanged."""
    offset = 2.0**20
    rect = (float(ix), float(iy), 5.0, 7.0)
    pt = (float(ix + 1), float(iy + 2))
    assert geom._point_in_rect(pt, rect) == geom._point_in_rect(
        _shift([pt], offset)[0], _shift([(rect[0], rect[1])], offset)[0] + rect[2:]
    )


@given(st.integers(min_value=-40, max_value=40), st.integers(min_value=-40, max_value=40), st.integers(min_value=-40, max_value=40), st.integers(min_value=-40, max_value=40))
@settings(max_examples=200, deadline=60000)
def test_m5_rects_overlap_translation_invariant(ix1, iy1, ix2, iy2) -> None:
    """Exact (integer coords + power-of-two offset): overlap is unchanged."""
    offset = 2.0**20
    r1 = (float(ix1), float(iy1), 4.0, 6.0)
    r2 = (float(ix2), float(iy2), 4.0, 6.0)
    shift_rect = lambda r: _shift([(r[0], r[1])], offset)[0] + r[2:]  # noqa: E731
    assert geom._rects_overlap(r1, r2) == geom._rects_overlap(shift_rect(r1), shift_rect(r2))


# ---------------------------------------------------------------------------
# Vacuity guards (G4): every property fails against a degenerate kernel
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    saved = {
        name: getattr(geom, name)
        for name in (
            "_distance",
            "_point_to_segment_distance",
            "_segment_to_segment_distance",
            "_point_to_polyline_distance",
            "_polyline_min_distance",
            "_polylines_intersect",
        )
    }
    yield
    for name, fn in saved.items():
        setattr(geom, name, fn)


def test_p1_fails_for_negative_constant_distance(_restore_kernels) -> None:
    geom._distance = lambda a, b: -1.0
    with pytest.raises(AssertionError):
        test_p1_distance_nonnegative_and_symmetric.hypothesis.inner_test((0.0, 0.0), (3.0, 4.0))


def test_p2_fails_for_constant_zero_distance(_restore_kernels) -> None:
    geom._point_to_segment_distance = lambda p, a, b: 0.0
    # P2 compares the point-to-segment distance against endpoint distances;
    # a constant 0.0 trivially satisfies it, so use a constant FAR above
    # both endpoints as the discriminating mutant instead.
    def far_mutant(p, a, b):
        return geom._distance(p, a) + geom._distance(p, b) + 1e9

    geom._point_to_segment_distance = far_mutant
    with pytest.raises(AssertionError):
        test_p2_point_to_segment_bounded_by_endpoints.hypothesis.inner_test(
            (0.0, 0.0), (10.0, 0.0), (10.0, 10.0)
        )


def test_p3_fails_for_candidate_min_mutant(_restore_kernels) -> None:
    """A kernel returning the FIRST candidate (not the min) when the
    segments do not intersect violates the exact-min property.  The
    fixture's first candidate (20.0) is not the minimum (10.0)."""
    real_pts = geom._point_to_segment_distance

    def first_candidate_mutant(a, b, c, d):
        if geom._segments_intersect(a, b, c, d):
            return 0.0
        return real_pts(a, c, d)

    geom._segment_to_segment_distance = first_candidate_mutant
    with pytest.raises(AssertionError):
        test_p3_segment_to_segment_is_candidate_min.hypothesis.inner_test(
            (0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)
        )


def test_p4_fails_for_constant_inf_mutant(_restore_kernels) -> None:
    geom._point_to_polyline_distance = lambda p, poly: math.inf
    with pytest.raises(AssertionError):
        test_p4_point_to_polyline_is_segment_min.hypothesis.inner_test(
            (1.0, 1.0), [(0.0, 0.0), (10.0, 10.0)]
        )


def test_p5_fails_for_constant_inf_mutant(_restore_kernels) -> None:
    geom._polyline_min_distance = lambda p1, p2: math.inf
    with pytest.raises(AssertionError):
        test_p5_polyline_min_is_pair_min.hypothesis.inner_test(
            ([(0.0, 0.0), (1.0, 1.0)], [(2.0, 2.0), (3.0, 3.0)])
        )


def test_p6_fails_for_increasing_mutant(_restore_kernels) -> None:
    """A kernel that returns the MAX of the per-segment distances (instead
    of the min) violates the absorption monotonicity: appending a far-away
    point strictly increases the max."""
    real_pts = geom._point_to_segment_distance

    def max_mutant(p, poly):
        if len(poly) < 2:
            return 0.0
        return max(real_pts(p, poly[i], poly[i + 1]) for i in range(len(poly) - 1))

    geom._point_to_polyline_distance = max_mutant
    with pytest.raises(AssertionError):
        test_p6_appending_point_is_monotone.hypothesis.inner_test((0.0, 0.0), [(0.0, 0.0), (1.0, 0.0)])
