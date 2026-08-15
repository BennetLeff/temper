"""Differential tests: ``router_v6/constraint_model.py`` compute kernels vs
the pre-migration pure-Python reference (Wave 4).

The five compute kernels migrated to ``packages/temper-design-bundle/src/
constraint_model.rs`` are pinned bit-exactly against a VERBATIM copy of the
pre-migration implementations (the ``_oracle_*`` block below, copied from the
module as committed on ``main`` before this migration):

- ``_edge_endpoint_key`` — 6-decimal-quantised ``(x, y)`` string identity
- ``canonical_channel_edges`` — quantised-key-sorted edge-identity generator
- ``_point_to_segment_distance`` — clamped projection with the canonical
  temper-geometry hypot contract (issue #987: the Wave-4 ``sqrt`` copy this
  oracle used to mirror was deleted; the oracle below was re-pinned to the
  canonical contract in the same commit)
- ``_pin_span`` — max pairwise ``sqrt(pow + pow)`` distance
- ``_dist_min_edge_to_pins`` — min over pins (empty -> ``inf``)
- ``_is_candidate_edge`` — ``dist_min <= max(k * span, m_min)`` predicate

Bit-exactness classes exercised (``docs/wave4-discipline-contract.md`` §2):

- **B3** (banker's rounding): Python ``round(c, 6)`` followed by ``:6f`` is
  byte-identical to a single ``{:.6}`` format of ``c`` — verified on this host
  over 200k adversarial samples including near-tie values (exact 6-decimal
  ties are unreachable for binary floats: a tie needs a ``5^6`` factor that
  no ``2^k`` denominator has), so the Rust ``format!("{:.6}")`` is the oracle.
- **B7** (arithmetic order / ``**`` is libm ``pow``): ``_pin_span``'s
  ``(xi - xj) ** 2`` is CPython ``float_pow`` = libm ``pow(x, 2.0)``, NOT
  ``x * x`` — measured 152/200k random samples apart on this host.
- **B1** (host-runtime libm via ``dlsym``): ``math.sqrt`` = host ``sqrt``,
  ``**`` = host ``pow`` (``crate::host_math``).
- **B5** (builtin ``max`` keeps the first argument): ``_is_candidate_edge``'s
  ``max(k_factor * span, m_min)`` -> ``py_max``.

Determinism notes for ``canonical_channel_edges``: the quantised-key sort is
stable in both Python (Timsort) and Rust (``sort_by``), so the only
insertion-order dependence left is the tie-break for two DISTINCT edges that
quantise to identical endpoint keys — preserved exactly because the shim
extracts ``list(graph.edges)`` in the same order the oracle iterates them.
That tie-break case is pinned below by ``test_quantise_collision_tie_break``.
"""

from __future__ import annotations

import math
import random

import tests.graph_fixtures as nx
import pytest

from temper_placer.router_v6 import constraint_model as cm

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the module AS COMMITTED on main
# before the Wave 4 migration; do not edit — they are the reference).  Only
# the ``_oracle_`` name prefix and the internal references to oracle names
# differ from the committed file.
# ---------------------------------------------------------------------------

_ORACLE_EDGE_COORD_DECIMALS = 6


def _oracle_edge_endpoint_key(node) -> str:
    return (
        "("
        + ", ".join(f"{round(float(c), _ORACLE_EDGE_COORD_DECIMALS):.6f}" for c in node)
        + ")"
    )


def _oracle_canonical_channel_edges(graph, layer_name: str):
    rows = []
    for u, v in graph.edges:
        ku, kv = _oracle_edge_endpoint_key(u), _oracle_edge_endpoint_key(v)
        if kv < ku:
            u, v, ku, kv = v, u, kv, ku
        rows.append((ku, kv, u, v))
    rows.sort(key=lambda r: (r[0], r[1]))
    for i, (ku, kv, u, v) in enumerate(rows):
        yield f"{layer_name}_E{i}_{ku}_{kv}", u, v


def _oracle_point_to_segment_distance(
    px: float,
    py: float,
    seg_ax: float,
    seg_ay: float,
    seg_bx: float,
    seg_by: float,
) -> float:
    # Re-pinned 2026-08-11 (issue #987) to the canonical temper-geometry
    # contract (creepage_check): the Wave-4 sqrt/if-elif-else copy this
    # oracle used to mirror was deleted. CPython math.hypot == the Rust
    # py_hypot Dekker double-double; denom==0 OR non-finite triggers the
    # degenerate arm; builtin min/max clamp NaN t to 1.0. ≤1-ulp,
    # decision-immune on real inputs (docs/evidence/2026-08-11-...execution.md).
    dx = seg_bx - seg_ax
    dy = seg_by - seg_ay
    denom = dx * dx + dy * dy

    if denom == 0.0 or not math.isfinite(denom):
        return math.hypot(px - seg_ax, py - seg_ay)

    t = ((px - seg_ax) * dx + (py - seg_ay) * dy) / denom
    t = max(0.0, min(1.0, t))

    proj_x = seg_ax + t * dx
    proj_y = seg_ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _oracle_pin_span(pin_positions: list[tuple[float, float]]) -> float:
    if len(pin_positions) < 2:
        return 0.0
    max_d = 0.0
    for i in range(len(pin_positions)):
        xi, yi = pin_positions[i]
        for j in range(i + 1, len(pin_positions)):
            xj, yj = pin_positions[j]
            d = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2)
            if d > max_d:
                max_d = d
    return max_d


def _oracle_dist_min_edge_to_pins(
    edge_ax: float,
    edge_ay: float,
    edge_bx: float,
    edge_by: float,
    pin_positions: list[tuple[float, float]],
) -> float:
    if not pin_positions:
        return float("inf")
    best = float("inf")
    for px, py in pin_positions:
        d = _oracle_point_to_segment_distance(px, py, edge_ax, edge_ay, edge_bx, edge_by)
        if d < best:
            best = d
    return best


def _oracle_is_candidate_edge(
    pin_positions: list[tuple[float, float]],
    edge_ax: float,
    edge_ay: float,
    edge_bx: float,
    edge_by: float,
    k_factor: float = 2.0,  # _DEFAULT_PRUNE_K_FACTOR as committed
    m_min: float = 30.0,  # _DEFAULT_PRUNE_M_MIN as committed
) -> bool:
    span = _oracle_pin_span(pin_positions)
    margin = max(k_factor * span, m_min)
    dist = _oracle_dist_min_edge_to_pins(edge_ax, edge_ay, edge_bx, edge_by, pin_positions)
    return dist <= margin


# ---------------------------------------------------------------------------
# Oracle sanity: guards against a transcription slip in the ``_oracle_`` rename
# ---------------------------------------------------------------------------


def test_oracle_is_verbatim_semantics() -> None:
    assert _oracle_edge_endpoint_key((1.0, 2.0)) == "(1.000000, 2.000000)"
    assert _oracle_edge_endpoint_key((-0.0, -1e-7)) == "(-0.000000, -0.000000)"
    assert _oracle_point_to_segment_distance(5.0, 3.0, 0.0, 0.0, 10.0, 0.0) == 3.0
    assert _oracle_point_to_segment_distance(-5.0, 0.0, 0.0, 0.0, 10.0, 0.0) == 5.0
    assert _oracle_point_to_segment_distance(5.0, 0.0, 0.0, 0.0, 10.0, 0.0) == 0.0
    assert _oracle_point_to_segment_distance(3.0, 4.0, 0.0, 0.0, 0.0, 0.0) == 5.0
    assert _oracle_pin_span([]) == 0.0
    assert _oracle_pin_span([(5.0, 5.0)]) == 0.0
    assert _oracle_pin_span([(0.0, 0.0), (3.0, 4.0)]) == 5.0
    assert _oracle_pin_span([(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]) == math.sqrt(200.0)
    assert _oracle_dist_min_edge_to_pins(0.0, 0.0, 10.0, 0.0, []) == math.inf
    assert _oracle_dist_min_edge_to_pins(0.0, 0.0, 10.0, 0.0, [(5.0, 3.0)]) == 3.0
    assert _oracle_is_candidate_edge([(0.0, 0.0)], 0.0, 0.0, 10.0, 0.0) is True
    assert _oracle_is_candidate_edge([(0.0, 0.0)], 500.0, 0.0, 510.0, 0.0) is False
    g = nx.Graph()
    g.add_edge((0.0, 0.0), (10.0, 0.0))
    g.add_edge((0.0, 10.0), (10.0, 10.0))
    got = list(_oracle_canonical_channel_edges(g, "F.Cu"))
    assert got[0][0] == "F.Cu_E0_(0.000000, 0.000000)_(10.000000, 0.000000)"
    assert got[1][0] == "F.Cu_E1_(0.000000, 10.000000)_(10.000000, 10.000000)"


# ---------------------------------------------------------------------------
# Bit-exact comparison helpers
# ---------------------------------------------------------------------------


def key(value):
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan", math.copysign(1.0, value))
        return ("float", value.hex())
    if isinstance(value, bool):
        return ("bool", value)
    return (type(value).__name__, value)


def assert_bits(got, expected, label: str) -> None:
    assert key(got) == key(expected), (
        f"{label}: rust={got!r} ({key(got)}) oracle={expected!r} ({key(expected)})"
    )


def rng_point(rng, lo=-10.0, hi=10.0):
    return (rng.uniform(lo, hi), rng.uniform(lo, hi))


def rng_pin_set(rng, n):
    return [rng_point(rng) for _ in range(n)]


# ---------------------------------------------------------------------------
# _edge_endpoint_key
# ---------------------------------------------------------------------------


class TestEdgeEndpointKey:
    @pytest.mark.parametrize(
        "node,expected",
        [
            ((1.0, 2.0), "(1.000000, 2.000000)"),
            ((-1.5, -2.25), "(-1.500000, -2.250000)"),
            ((0.0, 0.0), "(0.000000, 0.000000)"),
            ((-0.0, 0.0), "(-0.000000, 0.000000)"),
            ((1e-7, -1e-7), "(0.000000, -0.000000)"),
            ((0.9999995, 0.99999949), "(1.000000, 0.999999)"),
            ((1e12, 1e-12), "(1000000000000.000000, 0.000000)"),
        ],
    )
    def test_fixed(self, node, expected):
        assert cm._edge_endpoint_key(node) == expected

    @pytest.mark.parametrize("seed", range(40))
    def test_random(self, seed):
        rng = random.Random(seed)
        node = rng_point(rng, -1e4, 1e4)
        expected = _oracle_edge_endpoint_key(node)
        got = cm._edge_endpoint_key(node)
        assert got == expected, f"edge_endpoint_key {node}: {got!r} != {expected!r}"

    @pytest.mark.parametrize("seed", range(20))
    def test_adversarial_magnitudes_and_near_ties(self, seed):
        rng = random.Random(1000 + seed)
        node = (
            rng.choice([1e-7, -1e-7, 5e-7, -5e-7, 0.9999995, 0.0000005, 1e6, -1e6, 1e-12]),
            rng.choice([2.5e-6, -2.5e-6, 123456.789012, 0.0, -0.0, 1.23456789e-6]),
        )
        expected = _oracle_edge_endpoint_key(node)
        got = cm._edge_endpoint_key(node)
        assert got == expected, f"edge_endpoint_key {node}: {got!r} != {expected!r}"


# ---------------------------------------------------------------------------
# canonical_channel_edges
# ---------------------------------------------------------------------------


class TestCanonicalChannelEdges:
    def _build_graph(self, rng, n_nodes=8, n_edges=10):
        nodes = [rng_point(rng, -100.0, 100.0) for _ in range(n_nodes)]
        g = nx.Graph()
        for node in nodes:
            g.add_node(node)
        for _ in range(n_edges):
            u = nodes[rng.randrange(n_nodes)]
            v = nodes[rng.randrange(n_nodes)]
            if u != v:
                g.add_edge(u, v)
        return g

    def test_fixed_orientation_canonicalised(self):
        # Insert the "reversed" edge first; the oracle/shims must still
        # canonicalise to the lexicographically-smaller key first.
        g = nx.Graph()
        g.add_edge((10.0, 0.0), (0.0, 0.0))  # reversed relative to sorted order
        got = list(cm.canonical_channel_edges(g, "B.Cu"))
        expected = list(_oracle_canonical_channel_edges(g, "B.Cu"))
        assert len(got) == 1
        assert got[0][0] == "B.Cu_E0_(0.000000, 0.000000)_(10.000000, 0.000000)"
        assert got[0][1:] == expected[0][1:]
        assert got[0][1:] == ((0.0, 0.0), (10.0, 0.0))

    @pytest.mark.parametrize("seed", range(25))
    def test_random_graph_parity(self, seed):
        rng = random.Random(seed)
        g = self._build_graph(rng)
        expected = list(_oracle_canonical_channel_edges(g, "F.Cu"))
        got = list(cm.canonical_channel_edges(g, "F.Cu"))
        assert len(got) == len(expected)
        for i, ((eid_got, u_got, v_got), (eid_exp, u_exp, v_exp)) in enumerate(
            zip(got, expected)
        ):
            assert eid_got == eid_exp, f"edge {i}: {eid_got!r} != {eid_exp!r}"
            assert_bits(u_got, u_exp, f"edge {i} u")
            assert_bits(v_got, v_exp, f"edge {i} v")

    def test_quantise_collision_tie_break(self):
        """Two distinct edges whose endpoints quantise to IDENTICAL keys: the
        emitted index is the stable-sort tie-break, i.e. the graph's edge
        insertion order. The shim extracts ``list(graph.edges)`` in that same
        order, so the result is byte-identical to the oracle."""
        g = nx.Graph()
        g.add_edge((0.0, 0.0), (1.0, 0.0))
        g.add_edge((0.0000004, 0.0), (1.0, 0.0))  # round(0.0000004, 6) == 0.0
        expected = list(_oracle_canonical_channel_edges(g, "L1"))
        got = list(cm.canonical_channel_edges(g, "L1"))
        assert len(expected) == 2
        assert [e for e, _u, _v in got] == [e for e, _u, _v in expected]
        assert got[0][0] != got[1][0]

    def test_insertion_order_independent_for_distinct_keys(self):
        """With distinct quantised keys the emitted id sequence is a property
        of the geometry, not the construction order (the module docstring's
        claim)."""
        edges = [((0.0, 0.0), (10.0, 0.0)), ((5.0, 5.0), (5.0, 6.0)), ((0.0, 10.0), (10.0, 10.0))]
        a, b = nx.Graph(), nx.Graph()
        for e in edges:
            a.add_edge(*e)
        for e in reversed(edges):
            b.add_edge(*e)
        got_a = list(cm.canonical_channel_edges(a, "F.Cu"))
        got_b = list(cm.canonical_channel_edges(b, "F.Cu"))
        assert [e for e, _u, _v in got_a] == [e for e, _u, _v in got_b]


# ---------------------------------------------------------------------------
# _point_to_segment_distance
# ---------------------------------------------------------------------------


class TestPointToSegmentDistance:
    @pytest.mark.parametrize("seed", range(40))
    def test_random(self, seed):
        rng = random.Random(seed)
        p = rng_point(rng)
        a = rng_point(rng)
        b = rng_point(rng)
        expected = _oracle_point_to_segment_distance(*p, *a, *b)
        got = cm._point_to_segment_distance(*p, *a, *b)
        assert_bits(got, expected, f"point_to_segment {p} {a} {b}")

    @pytest.mark.parametrize("seed", range(15))
    def test_adversarial_magnitudes(self, seed):
        rng = random.Random(2000 + seed)
        p = (rng.choice([1e-6, 1e6, -1e6, 0.0, -0.0]), rng.choice([1e-6, 1e6, -1e6, 0.0]))
        a = (rng.choice([1e-6, 1e6, -1e6, 1e-12]), rng.choice([1e-6, 1e6, -1e6]))
        b = (rng.choice([1e-6, 1e6, -1e6, 3.0]), rng.choice([1e-6, 1e6, -1e6, 4.0]))
        expected = _oracle_point_to_segment_distance(*p, *a, *b)
        got = cm._point_to_segment_distance(*p, *a, *b)
        assert_bits(got, expected, f"point_to_segment {p} {a} {b}")

    def test_denormal_band(self):
        """B8: denormal-magnitude coords must not flush to zero (no fast-math)."""
        vals = [1e-308, -1e-308, 2.5e-309, -2.5e-309, 5e-324, 0.0, 1e-307]
        for px in vals:
            for py in vals[:3]:
                expected = _oracle_point_to_segment_distance(px, py, 1e-308, 0.0, 1e-307, 1e-308)
                got = cm._point_to_segment_distance(px, py, 1e-308, 0.0, 1e-307, 1e-308)
                assert_bits(got, expected, f"denormal ({px}, {py})")

    def test_degenerate_zero_length_segment(self):
        for seed in range(10):
            rng = random.Random(seed)
            p = rng_point(rng)
            a = rng_point(rng)
            expected = _oracle_point_to_segment_distance(*p, *a, *a)
            got = cm._point_to_segment_distance(*p, *a, *a)
            assert_bits(got, expected, f"degenerate {p} {a}")

    def test_nan_inf_parity(self):
        pairs = [
            (float("nan"), 1.0, 0.0, 0.0, 10.0, 0.0),
            (1.0, float("nan"), 0.0, 0.0, 10.0, 0.0),
            (float("inf"), 1.0, 0.0, 0.0, 10.0, 0.0),
            (float("-inf"), 1.0, 0.0, 0.0, 10.0, 0.0),
            (5.0, 3.0, 0.0, 0.0, float("inf"), 0.0),
            (5.0, 3.0, float("nan"), 0.0, 10.0, 0.0),
            (5.0, 3.0, 0.0, 0.0, float("nan"), 0.0),
            (float("inf"), float("nan"), 0.0, 0.0, 10.0, 0.0),
            (1e308, 1e308, 0.0, 0.0, 0.0, 0.0),
        ]
        for args in pairs:
            expected = _oracle_point_to_segment_distance(*args)
            got = cm._point_to_segment_distance(*args)
            assert_bits(got, expected, f"nan/inf {args}")


# ---------------------------------------------------------------------------
# _pin_span
# ---------------------------------------------------------------------------


class TestPinSpan:
    @pytest.mark.parametrize("seed", range(30))
    def test_random(self, seed):
        rng = random.Random(seed)
        pins = rng_pin_set(rng, rng.randint(0, 8))
        expected = _oracle_pin_span(pins)
        got = cm._pin_span(pins)
        assert_bits(got, expected, f"pin_span {pins}")

    def test_degenerate(self):
        assert cm._pin_span([]) == 0.0
        assert cm._pin_span([(5.0, 5.0)]) == 0.0
        assert cm._pin_span([(5.0, 5.0), (5.0, 5.0)]) == 0.0

    @pytest.mark.parametrize("seed", range(10))
    def test_permutation_invariance_bit_exact(self, seed):
        rng = random.Random(seed)
        pins = rng_pin_set(rng, rng.randint(2, 8))
        shuffled = list(pins)
        rng.shuffle(shuffled)
        assert cm._pin_span(pins) == cm._pin_span(shuffled)

    @pytest.mark.parametrize("seed", range(10))
    def test_adversarial_magnitudes(self, seed):
        rng = random.Random(3000 + seed)
        pins = [
            (rng.choice([1e6, -1e6, 1e-6, 0.0, 12345.678]), rng.choice([1e6, -1e6, 1e-6, 0.0]))
            for _ in range(rng.randint(2, 6))
        ]
        expected = _oracle_pin_span(pins)
        got = cm._pin_span(pins)
        assert_bits(got, expected, f"pin_span adv {pins}")


# ---------------------------------------------------------------------------
# _dist_min_edge_to_pins
# ---------------------------------------------------------------------------


class TestDistMinEdgeToPins:
    @pytest.mark.parametrize("seed", range(30))
    def test_random(self, seed):
        rng = random.Random(seed)
        a = rng_point(rng)
        b = rng_point(rng)
        pins = rng_pin_set(rng, rng.randint(0, 8))
        expected = _oracle_dist_min_edge_to_pins(*a, *b, pins)
        got = cm._dist_min_edge_to_pins(*a, *b, pins)
        assert_bits(got, expected, f"dist_min {a} {b} {pins}")

    def test_empty_returns_inf(self):
        assert cm._dist_min_edge_to_pins(0.0, 0.0, 10.0, 0.0, []) == math.inf

    def test_single_pin_equals_point_to_segment(self):
        rng = random.Random(9)
        a = rng_point(rng)
        b = rng_point(rng)
        p = rng_point(rng)
        assert cm._dist_min_edge_to_pins(*a, *b, [p]) == cm._point_to_segment_distance(*p, *a, *b)


# ---------------------------------------------------------------------------
# _is_candidate_edge
# ---------------------------------------------------------------------------


class TestIsCandidateEdge:
    @pytest.mark.parametrize("seed", range(30))
    def test_random(self, seed):
        rng = random.Random(seed)
        a = rng_point(rng)
        b = rng_point(rng)
        pins = rng_pin_set(rng, rng.randint(0, 6))
        kf = rng.choice([0.5, 1.0, 2.0, 3.5, 10.0])
        mm = rng.choice([1.0, 5.0, 30.0, 100.0])
        expected = _oracle_is_candidate_edge(pins, *a, *b, kf, mm)
        got = cm._is_candidate_edge(pins, *a, *b, kf, mm)
        assert got is expected, f"is_candidate {pins} {a} {b} k={kf} m={mm}"

    def test_empty_pins_never_candidate(self):
        assert cm._is_candidate_edge([], 0.0, 0.0, 10.0, 0.0) is False

    def test_defaults_match_oracle(self):
        rng = random.Random(11)
        a = rng_point(rng)
        b = rng_point(rng)
        pins = rng_pin_set(rng, 4)
        assert cm._is_candidate_edge(pins, *a, *b) == _oracle_is_candidate_edge(pins, *a, *b)
