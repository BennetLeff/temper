"""Property-based tests for the Rust-backed constraint-model kernels
(``temper_placer/router_v6/constraint_model.py``, delegating to
``temper-design-bundle``'s ``constraint_model.rs``).

Six non-vacuous properties over randomized fixtures, exercised through the
production shim functions:

- P1 ``_point_to_segment_distance`` is non-negative and bounded by the
  endpoint distances (the clamped projection is never farther than either
  endpoint)
- P2 ``_point_to_segment_distance`` is exactly ``0.0`` for a point on a
  power-of-two-length axis-aligned segment (integer-on-power-of-two
  coordinates make every intermediate exact)
- P3 ``_pin_span`` is exactly permutation-invariant (the max over the same
  multiset of pair distances is the same value)
- P4 ``_dist_min_edge_to_pins`` is exactly the min of the per-pin
  point-to-segment distances (and ``inf`` for an empty pin list)
- P5 ``_is_candidate_edge`` returns True for an edge through a pin and False
  for an edge 500 mm beyond any reachable margin
- P6 ``canonical_channel_edges`` emits unique, orientation-canonicalised,
  key-sorted edge ids whose id strings encode their own row's quantised keys

Metamorphic relations (G5), exactness claims stated per relation:

- M1 uniform power-of-two scaling invariance of ``_point_to_segment_distance``
  (exact: every intermediate is a power-of-two-scaled twin of the unscaled
  one, so all roundings carry the same mantissa; translation was rejected for
  this role because adding an offset perturbs the projection's mantissa)
- M2 endpoint-swap invariance of ``_point_to_segment_distance`` (tight
  tolerance: the clamped projection's rounding can differ in the last ulp)
- M3 translation invariance of ``_pin_span`` (exact, integer + 2^k)
- M4 ``_is_candidate_edge`` is monotone non-decreasing in ``k_factor`` for a
  power-of-two doubling (exact: the ``k*span`` product scales exactly and the
  builtin-``max`` margin is monotone)
- M5 ``canonical_channel_edges`` is insertion-order independent when all
  quantised keys are distinct (the emitted sequence is a property of the
  geometry, not the construction — the module docstring's claim)

Every property carries a ``test_pN_fails_for_<mutant>`` companion proving a
degenerate kernel violates it (G4 vacuity guard).
"""

from __future__ import annotations

import math
import random

import hypothesis.strategies as st
import networkx as nx
import pytest
from hypothesis import HealthCheck, given, settings

from temper_placer.router_v6 import constraint_model as cm

_FINITE = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
_POINT = st.tuples(_FINITE, _FINITE)
_POINT_INT = st.tuples(st.integers(min_value=-40, max_value=40), st.integers(min_value=-40, max_value=40))

# The composite graph strategies' smallest natural input (>=1 edge, each
# drawing two 2-float points) trips hypothesis's large-base-example health
# check; the fixture is intentionally structured, not a shrinkability failure.
_LARGE_FIXTURE = [HealthCheck.large_base_example]


@st.composite
def nonempty_edge_graph(draw):
    """A list of >=1 distinct-node edges (as raw coordinate pairs)."""
    n = draw(st.integers(min_value=1, max_value=6))
    edges = []
    for _ in range(n):
        u = draw(_POINT)
        v = draw(_POINT)
        while v == u:
            v = draw(_POINT)
        edges.append((u, v))
    return edges


# ---------------------------------------------------------------------------
# P1 — point-to-segment bounded by the endpoint distances
# ---------------------------------------------------------------------------


@given(_POINT, _POINT, _POINT)
@settings(max_examples=200, deadline=60000)
def test_p1_point_to_segment_bounded_by_endpoints(p, a, b) -> None:
    d = cm._point_to_segment_distance(*p, *a, *b)
    assert d >= 0.0
    da = cm._point_to_segment_distance(*p, *a, *a)
    db = cm._point_to_segment_distance(*p, *b, *b)
    abx, aby = b[0] - a[0], b[1] - a[1]
    len_sq = abx * abx + aby * aby
    if len_sq == 0.0:
        # the degenerate arm returns the distance to `a`
        assert d == da
    else:
        scale = max(1.0, abs(p[0]), abs(p[1]), abs(a[0]), abs(a[1]), abs(b[0]), abs(b[1]))
        # clamped projection is never farther than either endpoint in exact
        # arithmetic; the projection rounding can add ~1 ulp of scale
        assert d <= (1.0 + 1e-9) * min(da, db) + 1e-12 * scale


# ---------------------------------------------------------------------------
# P2 — point on a power-of-two segment is exactly 0.0
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=1, max_value=4),
    st.integers(min_value=0, max_value=16),
)
@settings(max_examples=200, deadline=60000)
def test_p2_point_on_power_of_two_segment_is_exactly_zero(k, i) -> None:
    n = float(2**k)
    x = float(i % (n + 1))
    assert cm._point_to_segment_distance(x, 0.0, 0.0, 0.0, n, 0.0) == 0.0
    assert cm._point_to_segment_distance(0.0, x, 0.0, 0.0, 0.0, n) == 0.0


# ---------------------------------------------------------------------------
# P3 — pin span is exactly permutation-invariant
# ---------------------------------------------------------------------------


@given(st.lists(_POINT, min_size=0, max_size=8))
@settings(max_examples=200, deadline=60000)
def test_p3_pin_span_permutation_invariant(pins) -> None:
    rng = random.Random(1234)
    shuffled = list(pins)
    rng.shuffle(shuffled)
    assert cm._pin_span(pins) == cm._pin_span(shuffled)


# ---------------------------------------------------------------------------
# P4 — dist_min_edge_to_pins is exactly the min of per-pin distances
# ---------------------------------------------------------------------------


@given(_POINT, _POINT, st.lists(_POINT, min_size=0, max_size=6))
@settings(max_examples=200, deadline=60000)
def test_p4_dist_min_is_min_of_per_pin_distances(a, b, pins) -> None:
    got = cm._dist_min_edge_to_pins(*a, *b, pins)
    if not pins:
        assert got == math.inf
    else:
        per_pin = [cm._point_to_segment_distance(px, py, *a, *b) for px, py in pins]
        assert got == min(per_pin)


# ---------------------------------------------------------------------------
# P5 — candidate predicate: edge through a pin is candidate, far edge is not
# ---------------------------------------------------------------------------


@given(st.lists(_POINT, min_size=1, max_size=6))
@settings(max_examples=200, deadline=60000)
def test_p5_candidate_arms(pins) -> None:
    p0 = pins[0]
    on = ((p0[0] - 3.0, p0[1]), (p0[0] + 3.0, p0[1]))
    assert cm._is_candidate_edge(pins, on[0][0], on[0][1], on[1][0], on[1][1]) is True
    far = ((p0[0], p0[1] + 500.0), (p0[0] + 1.0, p0[1] + 500.0))
    assert cm._is_candidate_edge(pins, far[0][0], far[0][1], far[1][0], far[1][1]) is False


# ---------------------------------------------------------------------------
# P6 — canonical_channel_edges ids are unique, canonicalised, key-sorted
# ---------------------------------------------------------------------------


@given(nonempty_edge_graph())
@settings(max_examples=200, deadline=60000, suppress_health_check=_LARGE_FIXTURE)
def test_p6_edge_ids_canonical_sorted_unique(edges) -> None:
    g = nx.Graph()
    for u, v in edges:
        g.add_edge(u, v)
    rows = list(cm.canonical_channel_edges(g, "F.Cu"))
    assert rows
    ids = [eid for eid, _u, _v in rows]
    assert len(set(ids)) == len(ids)
    keys = []
    for eid, u, v in rows:
        ku = cm._edge_endpoint_key(u)
        kv = cm._edge_endpoint_key(v)
        assert ku <= kv, f"not canonicalised: {ku} > {kv}"
        assert eid == f"F.Cu_E{len(keys)}_{ku}_{kv}", f"id does not encode its row: {eid}"
        keys.append((ku, kv))
    assert keys == sorted(keys), "rows not emitted in quantised-key order"


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


@given(_POINT_INT, _POINT_INT, _POINT_INT, st.integers(min_value=1, max_value=20))
@settings(max_examples=200, deadline=60000)
def test_m1_point_to_segment_scaling_invariant(p, a, b, shift_exp) -> None:
    """Exact: uniform power-of-two scaling leaves every intermediate a scaled
    twin of the unscaled one (same mantissa, shifted exponent), so all
    roundings — including half-ulp ties — carry the same mantissa and
    ``d(2^k * x) == 2^k * d(x)`` bit-for-bit."""
    scale = 2.0**shift_exp
    p = (float(p[0]), float(p[1]))
    a = (float(a[0]), float(a[1]))
    b = (float(b[0]), float(b[1]))
    d0 = cm._point_to_segment_distance(*p, *a, *b)
    d1 = cm._point_to_segment_distance(
        p[0] * scale, p[1] * scale, a[0] * scale, a[1] * scale, b[0] * scale, b[1] * scale
    )
    assert d1 == d0 * scale


@given(_POINT, _POINT, _POINT)
@settings(max_examples=200, deadline=60000)
def test_m2_point_to_segment_endpoint_swap(p, a, b) -> None:
    """Tight tolerance: the clamped projection can round differently in the
    last ulp after the endpoint swap, so the bound is 1e-9 relative."""
    d0 = cm._point_to_segment_distance(*p, *a, *b)
    d1 = cm._point_to_segment_distance(*p, *b, *a)
    scale = max(1.0, abs(d0), abs(d1))
    assert abs(d0 - d1) <= 1e-9 * scale + 1e-12


@given(st.lists(_POINT_INT, min_size=0, max_size=6), st.integers(min_value=1, max_value=20))
@settings(max_examples=200, deadline=60000)
def test_m3_pin_span_translation_invariant(pins, shift_exp) -> None:
    """Exact: integer coords + power-of-two offset (pair differences cancel)."""
    shift = 2.0**shift_exp
    pins = [(float(x), float(y)) for x, y in pins]
    d0 = cm._pin_span(pins)
    d1 = cm._pin_span([(x + shift, y + shift) for x, y in pins])
    assert d0 == d1


@given(st.lists(_POINT, min_size=1, max_size=5), _POINT, _POINT, st.integers(min_value=1, max_value=4))
@settings(max_examples=200, deadline=60000)
def test_m4_candidate_monotone_in_k_factor(pins, a, b, k_exp) -> None:
    """Exact: doubling k_factor by a power of two scales ``k*span`` exactly,
    and the builtin-``max`` margin is monotone, so candidate(k1) must imply
    candidate(2^k * k1)."""
    k1 = 2.0
    if not cm._is_candidate_edge(pins, *a, *b, k1):
        return
    k2 = k1 * (2.0**k_exp)
    assert cm._is_candidate_edge(pins, *a, *b, k2)


@given(nonempty_edge_graph())
@settings(max_examples=200, deadline=60000, suppress_health_check=_LARGE_FIXTURE)
def test_m5_canonical_edges_insertion_order_independent(edges) -> None:
    """Exact: with distinct quantised keys the emitted id sequence depends
    only on the geometry, not on graph construction order."""
    a, b = nx.Graph(), nx.Graph()
    for u, v in edges:
        a.add_edge(u, v)
    for u, v in reversed(edges):
        b.add_edge(u, v)
    got_a = list(cm.canonical_channel_edges(a, "F.Cu"))
    got_b = list(cm.canonical_channel_edges(b, "F.Cu"))
    assert [e for e, _u, _v in got_a] == [e for e, _u, _v in got_b]


# ---------------------------------------------------------------------------
# Vacuity guards (G4): every property fails against a degenerate kernel
# ---------------------------------------------------------------------------

_MUTABLE_NAMES = (
    "_point_to_segment_distance",
    "_pin_span",
    "_dist_min_edge_to_pins",
    "_is_candidate_edge",
    "canonical_channel_edges",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(cm, name) for name in _MUTABLE_NAMES}
    yield
    for name, fn in saved.items():
        setattr(cm, name, fn)


def test_p1_fails_for_negative_constant_distance(_restore_kernels) -> None:
    cm._point_to_segment_distance = lambda *_a: -1.0
    with pytest.raises(AssertionError):
        test_p1_point_to_segment_bounded_by_endpoints.hypothesis.inner_test(
            (0.0, 0.0), (10.0, 0.0), (10.0, 10.0)
        )


def test_p2_fails_for_constant_one_mutant(_restore_kernels) -> None:
    """A kernel that never returns 0.0 violates the exact-on-segment claim."""
    cm._point_to_segment_distance = lambda *_a: 1.0
    with pytest.raises(AssertionError):
        test_p2_point_on_power_of_two_segment_is_exactly_zero.hypothesis.inner_test(1, 0)


def test_p3_fails_for_order_dependent_mutant(_restore_kernels) -> None:
    """A kernel that reads only the first and last pins violates permutation
    invariance (the fixture's first/last differ from its extremes)."""
    cm._pin_span = lambda pins: (
        cm._point_to_segment_distance(pins[0][0], pins[0][1], pins[-1][0], pins[-1][1], pins[-1][0], pins[-1][1])
        if len(pins) >= 2
        else 0.0
    )
    with pytest.raises(AssertionError):
        test_p3_pin_span_permutation_invariant.hypothesis.inner_test(
            [(0.0, 0.0), (3.0, 4.0), (5.0, 5.0)]
        )


def test_p4_fails_for_last_pin_only_mutant(_restore_kernels) -> None:
    """A kernel returning only the LAST pin's distance is not the min when the
    last pin is not the closest."""
    real = cm._point_to_segment_distance

    def last_only_mutant(edge_ax, edge_ay, edge_bx, edge_by, pins):
        if not pins:
            return math.inf
        px, py = pins[-1]
        return real(px, py, edge_ax, edge_ay, edge_bx, edge_by)

    cm._dist_min_edge_to_pins = last_only_mutant
    with pytest.raises(AssertionError):
        test_p4_dist_min_is_min_of_per_pin_distances.hypothesis.inner_test(
            (0.0, 0.0), (10.0, 0.0), [(5.0, 3.0), (100.0, 100.0), (200.0, 200.0)]
        )


def test_p5_fails_for_constant_true_mutant(_restore_kernels) -> None:
    cm._is_candidate_edge = lambda *_a, **_k: True
    with pytest.raises(AssertionError):
        test_p5_candidate_arms.hypothesis.inner_test([(0.0, 0.0)])


def test_p5b_fails_for_constant_false_mutant(_restore_kernels) -> None:
    cm._is_candidate_edge = lambda *_a, **_k: False
    with pytest.raises(AssertionError):
        test_p5_candidate_arms.hypothesis.inner_test([(0.0, 0.0)])


def test_p6_fails_for_unsorted_mutant(_restore_kernels) -> None:
    """A kernel that emits edges in insertion order without canonicalisation
    violates orientation + key-order claims."""
    cm.canonical_channel_edges = lambda graph, layer: (
        (f"{layer}_E{i}_{cm._edge_endpoint_key(u)}_{cm._edge_endpoint_key(v)}", u, v)
        for i, (u, v) in enumerate(graph.edges)
    )
    with pytest.raises(AssertionError):
        test_p6_edge_ids_canonical_sorted_unique.hypothesis.inner_test(
            [((10.0, 0.0), (0.0, 0.0)), ((0.0, 10.0), (10.0, 10.0))]
        )
