"""Property-based tests for the Rust ``temper-geometry.bundle_analyzer``
GEOS-seam kernels (hull + buffer + STRtree-contains replacement).

Five non-vacuous properties over randomized pad sets / footprints (each
checked against the module's Rust-backed entry points):

- P1 hull contains its pads (every pad inside-or-on the hull ring)
- P2 buffer offset exactness (every buffer ring point is at distance
  ~median-m from some hull vertex)
- P3 dilation soundness (pads strictly inside the buffer; the buffer
  reaches no farther than m beyond the hull ring)
- P4 contains-predicate parity with shapely ``Polygon(ring).contains``
  per midpoint (the region equality itself is pinned by the differential
  suite; this pins the predicate on the ring)
- P5 hull convexity (every consecutive triple turns CW — no reflex vertex)

Non-vacuity: every property has a mutation test at the bottom proving a
mutated kernel violates it — the properties are not satisfied by
degenerate implementations.

Metamorphic relations (exactness claim per relation):

- M1 midpoint-array permutation equivariance (exact: the predicate is a
  pure function of the region, and permuting rows permutes the indices)
- M2 pad-input-order permutation -> identical hull vertex set (exact: the
  GEOS hull is set-deterministic)
- M3 ring reversal/orientation -> identical covered index set (exact:
  the point-in-convex-polygon test is orientation-agnostic)
- M4 duplicate pads -> identical hull vertex set (exact: extractUnique)
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, Polygon

from temper_placer.router_v6 import bundle_analyzer as ba

_TG = ba._tg

PAD_STRATEGY = st.lists(
    st.tuples(
        # width=32 restricts the exponent range to float32's, so |dx| >= ~1.4e-45
        # and `dx*dx` can never underflow f64.  At f64-underflow separations
        # (|dx| < ~1e-162) the GEOS offset curve itself produces NaN/inf
        # offsets that the noding pipeline silently drops; that regime is
        # outside the transcription's validity (see bundle_analyzer.rs's
        # module doc) and outside any real pad configuration.
        st.floats(min_value=-50.0, max_value=50.0, width=32, allow_nan=False, allow_infinity=False),
        st.floats(min_value=-50.0, max_value=50.0, width=32, allow_nan=False, allow_infinity=False),
    ),
    min_size=3,
    max_size=8,
)
M_STRATEGY = st.floats(min_value=0.05, max_value=10.0, allow_nan=False, allow_infinity=False)


def _ring_point_set(ring) -> frozenset[tuple[float, float]]:
    return frozenset(ring[:-1])


def _point_poly_dist(p, ring) -> float:
    best = float("inf")
    for i in range(len(ring) - 1):
        a, b = ring[i], ring[i + 1]
        vx, vy = b[0] - a[0], b[1] - a[1]
        denom = vx * vx + vy * vy
        if denom == 0.0:
            continue
        wx, wy = p[0] - a[0], p[1] - a[1]
        t = (vx * wx + vy * wy) / denom
        t = max(0.0, min(1.0, t))
        d = ((a[0] + t * vx - p[0]) ** 2 + (a[1] + t * vy - p[1]) ** 2) ** 0.5
        best = min(best, d)
    return best


# ---------------------------------------------------------------------------
# P1 — hull contains its pads
# ---------------------------------------------------------------------------


@given(PAD_STRATEGY, M_STRATEGY)
@settings(max_examples=100, deadline=60000)
def test_p1_hull_contains_all_pads(pads, m):
    ring = _TG.convex_hull_ring_py(pads)
    if not ring:
        # collinear/degenerate pad set -> no polygon; nothing to contain
        return
    hull = Polygon(ring)
    for pad in pads:
        assert hull.covers(Point(pad)), f"pad {pad} outside hull {ring}"


# ---------------------------------------------------------------------------
# P2 — buffer offset exactness (every buffer point at distance ~m from a hull vertex)
# ---------------------------------------------------------------------------


@given(PAD_STRATEGY, M_STRATEGY)
@settings(max_examples=100, deadline=60000)
def test_p2_buffer_points_offset_hull_vertices_by_m(pads, m):
    ring = _TG.convex_hull_ring_py(pads)
    if not ring:
        return
    buf = _TG.hull_buffer_ring_py(ring, m)
    verts = ring[:-1]
    for p in buf[:-1]:
        md = min(((p[0] - v[0]) ** 2 + (p[1] - v[1]) ** 2) ** 0.5 for v in verts)
        assert m - 1e-6 <= md <= m + 1e-6, f"buffer point {p} not at distance m={m}"


# ---------------------------------------------------------------------------
# P3 — dilation soundness
# ---------------------------------------------------------------------------


@given(PAD_STRATEGY, M_STRATEGY)
@settings(max_examples=100, deadline=60000)
def test_p3_dilation_soundness(pads, m):
    ring = _TG.convex_hull_ring_py(pads)
    if not ring:
        return
    buf = _TG.hull_buffer_ring_py(ring, m)
    poly = Polygon(buf)
    hull_poly = Polygon(ring)
    # (a) pads strictly inside the buffer
    for pad in pads:
        assert poly.contains(Point(pad)), f"pad {pad} not strictly inside buffer"
    # (b) the buffer reaches no farther than m beyond the hull ring: any
    # buffer point is either inside the hull or within m + eps of the ring.
    for p in buf[:-1]:
        assert hull_poly.contains(Point(p)) or _point_poly_dist(p, ring) <= m + 1e-6, (
            f"buffer point {p} beyond m-offset of hull"
        )


# ---------------------------------------------------------------------------
# P4 — contains-predicate parity with shapely on the ring
# ---------------------------------------------------------------------------


@st.composite
def ring_with_midpoints(draw):
    pads = draw(PAD_STRATEGY)
    m = draw(M_STRATEGY)
    n = draw(st.integers(min_value=1, max_value=30))
    pts = [
        (
            draw(st.floats(min_value=-60.0, max_value=60.0, width=32, allow_nan=False, allow_infinity=False)),
            draw(st.floats(min_value=-60.0, max_value=60.0, width=32, allow_nan=False, allow_infinity=False)),
        )
        for _ in range(n)
    ]
    return pads, m, pts


@given(ring_with_midpoints())
@settings(max_examples=100, deadline=60000)
def test_p4_covered_indices_match_shapely_contains(case):
    pads, m, pts = case
    ring = _TG.convex_hull_ring_py(pads)
    if not ring:
        return
    buf = _TG.hull_buffer_ring_py(ring, m)
    poly = Polygon(buf)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    idx = _TG.covered_edge_indices_py(buf, xs, ys)
    expect = [i for i, p in enumerate(pts) if poly.contains(Point(p))]
    assert list(idx) == expect, f"covered mismatch ring={buf} pts={pts}"


# ---------------------------------------------------------------------------
# P5 — hull convexity (all CW turns)
# ---------------------------------------------------------------------------


@given(PAD_STRATEGY)
@settings(max_examples=100, deadline=60000)
def test_p5_hull_is_convex_cw(pads):
    ring = _TG.convex_hull_ring_py(pads)
    if not ring:
        return
    for i in range(len(ring) - 2):
        (ax, ay), (bx, by), (cx, cy) = ring[i], ring[i + 1], ring[i + 2]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        assert cross < 1e-9, f"reflex/CW-violating turn at vertex {ring[i+1]}"


# ---------------------------------------------------------------------------
# Metamorphic relations (all exact)
# ---------------------------------------------------------------------------


@given(PAD_STRATEGY, M_STRATEGY, st.integers(min_value=1, max_value=2**31 - 1))
@settings(max_examples=50, deadline=60000)
def test_m1_midpoint_permutation_equivariance(pads, m, seed):
    rng = random.Random(seed)
    ring = _TG.convex_hull_ring_py(pads)
    if not ring:
        return
    buf = _TG.hull_buffer_ring_py(ring, m)
    n = rng.randint(5, 25)
    xs = [rng.uniform(-60, 60) for _ in range(n)]
    ys = [rng.uniform(-60, 60) for _ in range(n)]
    perm = list(range(n))
    rng.shuffle(perm)
    base = set(_TG.covered_edge_indices_py(buf, xs, ys))
    perm_xs = [xs[i] for i in perm]
    perm_ys = [ys[i] for i in perm]
    perm_idx = set(_TG.covered_edge_indices_py(buf, perm_xs, perm_ys))
    # the point at original index j sits at new position perm.index(j)
    assert {perm.index(j) for j in base} == perm_idx, "permutation equivariance violated"


@given(PAD_STRATEGY, st.integers(min_value=1, max_value=2**31 - 1))
@settings(max_examples=50, deadline=60000)
def test_m2_pad_order_permutation_identical_hull(pads, seed):
    rng = random.Random(seed)
    shuffled = list(pads)
    rng.shuffle(shuffled)
    assert _ring_point_set(_TG.convex_hull_ring_py(pads)) == _ring_point_set(
        _TG.convex_hull_ring_py(shuffled)
    )


@given(PAD_STRATEGY, M_STRATEGY, st.integers(min_value=1, max_value=2**31 - 1))
@settings(max_examples=50, deadline=60000)
def test_m3_ring_reversal_identical_coverage(pads, m, seed):
    rng = random.Random(seed)
    ring = _TG.convex_hull_ring_py(pads)
    if not ring:
        return
    buf = _TG.hull_buffer_ring_py(ring, m)
    xs = [rng.uniform(-60, 60) for _ in range(20)]
    ys = [rng.uniform(-60, 60) for _ in range(20)]
    base = _TG.covered_edge_indices_py(buf, xs, ys)
    rev = [buf[0]] + list(reversed(buf[1:-1])) + [buf[0]]
    assert _TG.covered_edge_indices_py(rev, xs, ys) == base, "ring orientation changed coverage"


@given(PAD_STRATEGY)
@settings(max_examples=50, deadline=60000)
def test_m4_duplicate_pads_identical_hull(pads):
    dupes = list(pads) + [pads[0], pads[len(pads) // 2]]
    assert _ring_point_set(_TG.convex_hull_ring_py(pads)) == _ring_point_set(
        _TG.convex_hull_ring_py(dupes)
    )


# ---------------------------------------------------------------------------
# Vacuity guards — a mutated kernel must violate its property
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    orig_hull = _TG.convex_hull_ring_py
    orig_buf = _TG.hull_buffer_ring_py
    orig_cov = _TG.covered_edge_indices_py
    yield
    _TG.convex_hull_ring_py = orig_hull
    _TG.hull_buffer_ring_py = orig_buf
    _TG.covered_edge_indices_py = orig_cov


def _nondegenerate_pads():
    # 4 corners + interior: a genuinely discriminating input class.
    return [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 10.0),
        (0.0, 10.0),
        (5.0, 5.0),
    ]


def test_p1_fails_for_wrong_hull(_restore_kernels):
    """A mutant hull that does not contain the pads violates P1 (an empty
    ring would trip the property's degenerate-input early return instead,
    which is not an assertion)."""
    _TG.convex_hull_ring_py = lambda _pads: [(100.0, 100.0), (101.0, 100.0), (101.0, 101.0), (100.0, 101.0), (100.0, 100.0)]
    with pytest.raises(AssertionError):
        test_p1_hull_contains_all_pads.hypothesis.inner_test(_nondegenerate_pads(), 1.0)


def test_p2_fails_for_identity_buffer(_restore_kernels):
    """A mutant buffer returning the hull unchanged has points at distance 0,
    not m — P2 rejects it."""
    _TG.hull_buffer_ring_py = lambda ring, _m: list(ring)
    with pytest.raises(AssertionError):
        test_p2_buffer_points_offset_hull_vertices_by_m.hypothesis.inner_test(
            _nondegenerate_pads(), 1.0
        )


def test_p3_fails_for_shrunken_buffer(_restore_kernels):
    """A mutant buffer returning a tiny square contains no pads — P3(a) rejects it."""

    def tiny(_ring, _m):
        return [(0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1), (0.0, 0.0)]

    _TG.hull_buffer_ring_py = tiny
    with pytest.raises(AssertionError):
        test_p3_dilation_soundness.hypothesis.inner_test(_nondegenerate_pads(), 1.0)


def test_p4_fails_for_all_indices(_restore_kernels):
    """A mutant coverage kernel returning every index includes outside points —
    P4 (shapely parity) rejects it."""
    _TG.covered_edge_indices_py = lambda _ring, xs, _ys: list(range(len(xs)))
    case = (_nondegenerate_pads(), 1.0, [(20.0, 20.0), (5.0, 5.0)])
    with pytest.raises(AssertionError):
        test_p4_covered_indices_match_shapely_contains.hypothesis.inner_test(case)


def test_p5_fails_for_reversed_ring(_restore_kernels):
    """A mutant hull returning a CCW (reversed) ring has reflex turns — P5 rejects it."""
    orig = _TG.convex_hull_ring_py

    def reversed_ring(pads):
        ring = orig(pads)
        return [ring[0]] + list(reversed(ring[1:-1])) + [ring[0]] if ring else []

    # guard: the mutant must actually differ from the real hull for this input
    assert orig(_nondegenerate_pads()) != reversed_ring(
        _nondegenerate_pads()
    ), "mutant equals the real hull — vacuous"
    _TG.convex_hull_ring_py = reversed_ring
    with pytest.raises(AssertionError):
        test_p5_hull_is_convex_cw.hypothesis.inner_test(_nondegenerate_pads())
