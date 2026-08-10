"""Property-based tests for the Wave-4 core graph/geometry cluster.

Verification unit (G4 cluster rule): the seven migrated modules of the
``core_graph_cluster`` unit (graph.py, hypergraph.py, pin_geometry.py,
power_topology.py, topology.py, courtyard.py, geometry_types.py) are ONE
unit behind this shared property corpus. ``community.py`` and
``loop_ownership.py`` are JUSTIFIED-KEEP (no migrated kernel; see
VERIFICATION.md) and are not part of this unit.

Every property below is vacuity-guarded by a mutation test
(``test_pN_fails_for_<mutant>``) that swaps the corresponding
``temper_geometry`` kernel for a degenerate implementation and re-runs the
property via ``hypothesis.inner_test``, asserting it FAILS — so none of the
properties is satisfied by a trivial kernel.

Reachability: each property drives the module's PUBLIC shim entry point,
which delegates to the named Rust kernel — the generated inputs genuinely
execute the kernel under test (reachability is by construction of the shim
delegation; the differential suite additionally pins the kernels bit-for-bit
against the pre-migration oracle).

Module-to-property map (cross-referenced with
test_core_graph_cluster_rust_differential.py):
  graph.py:            P1 (clique coverage + order), P2 (batch offsets),
                       MR1 (net-list permutation), MR2 (component relabel),
                       MR3 (batch associativity)
  hypergraph.py:       P3 (row-sum identity), MR4 (triplet-order invariance,
                       tolerance), MR5 (single-triplet basis), MR6 (transpose
                       degrees)
  pin_geometry.py:     P4 (R(-theta) quadrant law), MR7 (zero-rotation
                       translation), MR8 (90-degree quarter-turn), MR9
                       (rotation additivity)
  power_topology.py:   P5 (band lattice + monotonicity), MR10 (1oz
                       consistency), MR11 (monotone non-decreasing),
                       MR12 (threshold lattice exact)
  topology.py:         P6 (valid partition), MR13 (edge-order invariance),
                       MR14 (component permutation), MR15 (merge monotonicity)
  courtyard.py:        P7 (translation exactness), MR16 (rotation
                       composition), MR17 (double-rotation negation),
                       MR18 (area preservation)
  geometry_types.py:   P8 (distance/radius laws), MR19 (distance symmetry),
                       MR20 (radius symmetry), MR21 (distance scale)

Exactness claims are stated per relation: "exact" means every f64 bit is
asserted equal (via `==`; sign-of-zero counts as equal); relations with a
stated tolerance use the oracle's own band and say so.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.courtyard import Courtyard
from temper_placer.core.geometry_types import Pad, Point
from temper_placer.core.graph import batch_graphs, netlist_to_graph
from temper_placer.core.hypergraph import Coo
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.pin_geometry import pin_world_position_at
from temper_placer.core.power_topology import (
    IPC2221Rule,
    PowerDeliveryStrategy,
    PowerRailSpec,
)
from temper_placer.core.topology import TopologicalGraph

# ---------------------------------------------------------------------------
# Kernel registry for the vacuity guards: swapping one of these for a mutant
# and re-running the property must FAIL it.
# ---------------------------------------------------------------------------

_KERNEL_NAMES = (
    "graph_clique_expand_py",
    "graph_batch_concat_py",
    "hypergraph_coo_matvec_py",
    "normalize_rotation_index_py",
    "pin_world_position_kernel_py",
    "power_required_trace_width_py",
    "power_trace_width_py",
    "power_delivery_strategy_py",
    "topology_connected_components_py",
    "courtyard_global_points_py",
    "point_distance_py",
    "track_midpoint_py",
    "pad_radius_py",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_tg, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_tg, name, fn)


# ---------------------------------------------------------------------------
# Shared generators
# ---------------------------------------------------------------------------


@st.composite
def netlist_strategy(draw):
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = random.Random(seed)
    n_components = draw(st.integers(min_value=0, max_value=8))
    n_nets = draw(st.integers(min_value=0, max_value=8))
    comps = []
    for i in range(n_components):
        c = Component(
            ref=f"C{i}",
            footprint="0603",
            bounds=(draw(st.floats(min_value=0.5, max_value=8.0, allow_nan=False, allow_infinity=False)),
                    draw(st.floats(min_value=0.5, max_value=8.0, allow_nan=False, allow_infinity=False))),
        )
        c.fixed = rng.random() < 0.3
        c.pins.extend([None] * draw(st.integers(min_value=0, max_value=10)))
        comps.append(c)
    nets = []
    for i in range(n_nets):
        k = draw(st.integers(min_value=0, max_value=6))
        chosen = rng.sample([c.ref for c in comps], k=min(k, n_components)) if comps else []
        pins = [(r, f"P{j}") for j, r in enumerate(chosen)]
        nets.append(
            Net(
                name=f"N{i}",
                pins=pins,
                weight=draw(st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False)),
            )
        )
    return Netlist(components=comps, nets=nets)


@st.composite
def coo_strategy(draw):
    n_rows = draw(st.integers(min_value=1, max_value=6))
    n_cols = draw(st.integers(min_value=1, max_value=6))
    nnz = draw(st.integers(min_value=0, max_value=12))
    row = np.array([draw(st.integers(min_value=0, max_value=n_rows - 1)) for _ in range(nnz)], dtype=np.int64)
    col = np.array([draw(st.integers(min_value=0, max_value=n_cols - 1)) for _ in range(nnz)], dtype=np.int64)
    data = np.array(
        [draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)) for _ in range(nnz)],
        dtype=np.float64,
    )
    return Coo(row=row, col=col, data=data, shape=(n_rows, n_cols))


@st.composite
def pin_geometry_case(draw):
    px = draw(st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    py = draw(st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    rotation_idx = draw(st.integers(min_value=0, max_value=3))
    return px, py, rotation_idx


@st.composite
def polygon_strategy(draw):
    """A guaranteed-valid convex polygon: a regular n-gon with small angle
    jitter (< half the inter-vertex gap) and per-vertex radius jitter, so
    shapely never normalizes/merges its ring and no two vertices (including
    the first/last) are close enough to collapse under a translation."""
    n = draw(st.integers(min_value=4, max_value=8))
    gap = 2.0 * math.pi / n  # >= pi/2 for n <= 8
    radii = [draw(st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)) for _ in range(n)]
    jitter = [draw(st.floats(min_value=0.0, max_value=gap / 3.0, allow_nan=False, allow_infinity=False)) for _ in range(n)]
    points = []
    for i in range(n):
        a = gap * i + jitter[i]
        points.append((radii[i] * math.cos(a), radii[i] * math.sin(a)))
    return points


# ---------------------------------------------------------------------------
# P1 — graph.py: clique expansion covers every pair, in order, with the
# net's weight (reaches graph_clique_expand_py)
# ---------------------------------------------------------------------------


def _expected_clique_pairs(netlist):
    comp_refs = {c.ref: i for i, c in enumerate(netlist.components)}
    pairs = []
    weights = []
    for net in netlist.nets:
        indices = list({comp_refs[p[0]] for p in net.pins if p[0] in comp_refs})
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                pairs.append((indices[i], indices[j]))
                weights.append(net.weight)
    return pairs, weights


@given(netlist_strategy())
@settings(max_examples=100, deadline=60000)
def test_p1_clique_expansion_exact_and_ordered(netlist):
    got = netlist_to_graph(netlist)
    pairs, weights = _expected_clique_pairs(netlist)
    assert got.edges.shape == (len(pairs), 2)
    for (u, v), (eu, ev) in zip(pairs, got.edges):
        assert (u, v) == (int(eu), int(ev))
    for w, gw in zip(weights, got.edge_weights):
        assert w == float(gw)


def test_p1_fails_for_empty_clique_mutant(_restore_kernels):
    """A kernel emitting no pairs violates the pair-coverage count."""
    _tg.graph_clique_expand_py = lambda *_a, **_k: ([], [], [])
    with pytest.raises(AssertionError):
        test_p1_clique_expansion_exact_and_ordered.hypothesis.inner_test(_some_netlist())


def _some_netlist():
    comps = [Component(ref=f"C{i}", footprint="0603", bounds=(1.0, 2.0)) for i in range(4)]
    for c in comps:
        c.pins.extend([None, None])
    nets = [Net(name="N0", pins=[(c.ref, "1") for c in comps], weight=1.5)]
    return Netlist(components=comps, nets=nets)


# ---------------------------------------------------------------------------
# P2 — graph.py: batch offsets shift later graphs by the cumulative node
# count, first graph's edges unchanged (reaches graph_batch_concat_py)
# ---------------------------------------------------------------------------


@given(netlist_strategy())
@settings(max_examples=60, deadline=60000)
def test_p2_batch_offsets_correct(netlist):
    extra = _some_netlist()
    ga = netlist_to_graph(netlist)
    gb = netlist_to_graph(extra)
    batched = batch_graphs([ga, gb])
    assert batched.nodes.shape[0] == ga.nodes.shape[0] + gb.nodes.shape[0]
    assert np.array_equal(batched.nodes[: ga.nodes.shape[0]], ga.nodes)
    assert np.array_equal(batched.nodes[ga.nodes.shape[0] :], gb.nodes)
    # second graph's edges shifted by the first graph's node count
    offset = ga.nodes.shape[0]
    expected_b = gb.edges + offset
    assert batched.edges.shape == (ga.edges.shape[0] + gb.edges.shape[0], 2)
    assert np.array_equal(batched.edges[: ga.edges.shape[0]], ga.edges)
    assert np.array_equal(batched.edges[ga.edges.shape[0] :], expected_b)


def test_p2_fails_for_no_offset_mutant(_restore_kernels):
    """A kernel that concatenates WITHOUT shifting breaks the offset law."""

    def no_shift(nf, ef, wf):
        out_e = []
        for flat in ef:
            out_e.extend(flat)
        out_n = [v for flat in nf for v in flat]
        out_w = [v for flat in wf for v in flat]
        return out_n, out_e, out_w

    _tg.graph_batch_concat_py = no_shift
    with pytest.raises(AssertionError):
        test_p2_batch_offsets_correct.hypothesis.inner_test(_some_netlist())


# ---------------------------------------------------------------------------
# P3 — hypergraph.py: Coo @ ones == independent per-row accumulation in
# triplet order (reaches hypergraph_coo_matvec_py)
# ---------------------------------------------------------------------------


def _independent_row_sums(coo):
    acc = {}
    for r, c, d in zip(coo.row, coo.col, coo.data):
        del c  # value-independent scatter-add; the row index selects the bin
        acc[int(r)] = acc.get(int(r), 0.0) + float(d) * 1.0
    n = coo.shape[0]
    return [acc.get(i, 0.0) for i in range(n)]


@given(coo_strategy())
@settings(max_examples=100, deadline=60000)
def test_p3_coo_matvec_equals_row_sums(coo):
    ones = np.ones(coo.shape[1], dtype=np.float64)
    got = coo @ ones
    want = _independent_row_sums(coo)
    assert len(got) == coo.shape[0]
    for g, w in zip(got, want):
        assert g == w


def test_p3_fails_for_zero_matvec_mutant(_restore_kernels):
    """A matvec returning all zeros breaks the row-sum identity."""
    _tg.hypergraph_coo_matvec_py = lambda *_a, **_k: [0.0] * 4
    coo = Coo(
        row=np.array([0, 1], dtype=np.int64),
        col=np.array([0, 1], dtype=np.int64),
        data=np.array([2.0, 3.0], dtype=np.float64),
        shape=(2, 2),
    )
    with pytest.raises(AssertionError):
        test_p3_coo_matvec_equals_row_sums.hypothesis.inner_test(coo)


# ---------------------------------------------------------------------------
# P4 — pin_geometry.py: R(-theta) quadrant law (tight tolerance, the
# oracle's cos(pi/2) ~ 6e-17 band), zero rotation exact (reaches
# pin_world_position_kernel_py)
# ---------------------------------------------------------------------------


@given(pin_geometry_case())
@settings(max_examples=100, deadline=60000)
def test_p4_quadrant_rotation_law(case):
    px, py, rotation_idx = case
    comp = Component(ref="T", footprint="0603", bounds=(1.0, 1.0))
    comp.initial_position = (0.0, 0.0)
    comp.initial_rotation = rotation_idx
    comp.initial_side = 0
    pin = _PointPin((px, py))
    got = pin_world_position_at(pin, comp)
    # Closed-form R(-theta) at exact quadrant angles: 0:(x,y), 1:(y,-x),
    # 2:(-x,-y), 3:(-y,x). The kernel computes cos/sin of (idx*pi/2); the
    # near-axis cos/sin terms are O(1e-16) of the coordinates, so the law
    # holds to a stated tight tolerance, and EXACTLY at rotation 0.
    expected = [(px, py), (py, -px), (-px, -py), (-py, px)][rotation_idx]
    tol = 1e-12 * (1.0 + abs(px) + abs(py))
    assert abs(got[0] - expected[0]) <= tol
    assert abs(got[1] - expected[1]) <= tol
    if rotation_idx == 0:
        assert got == expected


def test_p4_fails_for_sign_flip_mutant(_restore_kernels):
    """An R(+theta) (sign-flipped) kernel breaks the law at 90/270 deg."""
    from math import cos, sin

    def r_plus(px, py, side, theta, cx, cy):
        c, s = cos(theta), sin(theta)
        mx = -px if side == 1 else px
        return (cx + mx * c - py * s, cy + mx * s + py * c)

    _tg.pin_world_position_kernel_py = r_plus
    comp = Component(ref="T", footprint="0603", bounds=(1.0, 1.0))
    comp.initial_position = (0.0, 0.0)
    comp.initial_rotation = 1
    comp.initial_side = 0
    with pytest.raises(AssertionError):
        test_p4_quadrant_rotation_law.hypothesis.inner_test((3.0, -2.0, 1))


# ---------------------------------------------------------------------------
# P5 — power_topology.py: delivery-strategy band lattice + trace-width
# monotonicity (reaches power_delivery_strategy_py, power_trace_width_py,
# power_required_trace_width_py)
# ---------------------------------------------------------------------------


@given(st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100, deadline=60000)
def test_p5_band_lattice_and_monotonicity(current):
    rail = PowerRailSpec(
        net_name="+X", max_current_a=current, voltage_v=1.0,
        source_component="S", sink_components=(),
    )
    strategy = rail.delivery_strategy()
    if current >= 3.0:
        assert strategy is PowerDeliveryStrategy.PLANE
    elif current >= 1.0:
        assert strategy is PowerDeliveryStrategy.WIDE_TRACE
    else:
        assert strategy is PowerDeliveryStrategy.STANDARD_TRACE

    # trace width strictly grows with current, at a safely-spread pair
    low = PowerRailSpec(
        net_name="+A", max_current_a=1.0, voltage_v=1.0,
        source_component="S", sink_components=(),
    )
    high = PowerRailSpec(
        net_name="+B", max_current_a=4.0, voltage_v=1.0,
        source_component="S", sink_components=(),
    )
    assert IPC2221Rule().trace_width(high) > IPC2221Rule().trace_width(low)
    assert high.required_trace_width() > low.required_trace_width()


def test_p5_fails_for_constant_strategy_mutant(_restore_kernels):
    """A strategy kernel returning a constant breaks the band lattice."""
    _tg.power_delivery_strategy_py = lambda *_a, **_k: 2
    with pytest.raises(AssertionError):
        test_p5_band_lattice_and_monotonicity.hypothesis.inner_test(5.0)


# ---------------------------------------------------------------------------
# P6 — topology.py: get_clusters yields a valid partition and co-clusters
# every adjacency edge's endpoints (reaches topology_connected_components_py)
# ---------------------------------------------------------------------------


@st.composite
def topological_graph_strategy(draw):
    graph = TopologicalGraph()
    n_nodes = draw(st.integers(min_value=0, max_value=8))
    for i in range(n_nodes):
        graph.add_node(f"N{i}")
    n_edges = draw(st.integers(min_value=0, max_value=10))
    for _ in range(n_edges):
        if n_nodes < 2:
            break
        a, b = draw(st.sampled_from(graph.nodes)), draw(st.sampled_from(graph.nodes))
        graph.add_adjacency(a, b, draw(st.floats(min_value=0.1, max_value=5.0)))
    return graph


@given(topological_graph_strategy())
@settings(max_examples=100, deadline=60000)
def test_p6_clusters_form_valid_partition(graph):
    clusters = graph.get_clusters()
    node_sets = [set(c) for c in clusters]
    # every node appears in exactly one cluster
    all_nodes = [n for s in node_sets for n in s]
    assert len(all_nodes) == len(set(all_nodes)) == len(graph.nodes)
    # each adjacency edge's endpoints are co-clustered
    for a, b, _ in graph.adjacency_edges:
        assert any(a in s and b in s for s in node_sets)


def test_p6_fails_for_empty_partition_mutant(_restore_kernels):
    """A kernel returning no clusters breaks the partition law."""
    _tg.topology_connected_components_py = lambda *_a, **_k: []
    g = TopologicalGraph()
    g.add_adjacency("A", "B", 1.0)
    with pytest.raises(AssertionError):
        test_p6_clusters_form_valid_partition.hypothesis.inner_test(g)


# ---------------------------------------------------------------------------
# P7 — courtyard.py: translating the component position translates every
# vertex EXACTLY (base position 0.0 makes the kernel's translate step and
# the shim-side addition the same expression) (reaches
# courtyard_global_points_py)
# ---------------------------------------------------------------------------


@given(polygon_strategy(), st.integers(min_value=0, max_value=3),
    st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100, deadline=60000)
def test_p7_translation_is_exact(points, rotation_idx, dx, dy):
    c = Courtyard(component_ref="U1", points=points)
    base = list(c.get_global_polygon(0.0, 0.0, rotation_idx).exterior.coords)
    moved = list(c.get_global_polygon(dx, dy, rotation_idx).exterior.coords)
    assert len(base) == len(moved)
    for (bx, by), (mx, my) in zip(base, moved):
        assert mx == bx + dx
        assert my == by + dy


def test_p7_fails_for_ignored_position_mutant(_restore_kernels):
    """A kernel that ignores the component position breaks translation."""
    original = _tg.courtyard_global_points_py

    def no_translate(pts, rotation_idx, x, y):
        return original(pts, rotation_idx, 0.0, 0.0)

    _tg.courtyard_global_points_py = no_translate
    with pytest.raises(AssertionError):
        test_p7_translation_is_exact.hypothesis.inner_test(
            [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], 0, 3.0, 4.0
        )


# ---------------------------------------------------------------------------
# P8 — geometry_types.py: distance/radius laws (reaches point_distance_py,
# pad_radius_py)
# ---------------------------------------------------------------------------


@given(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
       st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
       # radii >= 1e-3 keep pow(pow(w,2)+pow(h,2), 0.5) out of the denormal
       # band (B8), where the host libm's pow can legitimately return 0.0
       # and break the geometric bound — that is an underflow, not a kernel bug.
       st.floats(min_value=1e-3, max_value=10.0, allow_nan=False, allow_infinity=False),
       st.floats(min_value=1e-3, max_value=10.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100, deadline=60000)
def test_p8_distance_and_radius_laws(x, y, w, h):
    a = Point(x, y)
    assert a.distance_to(a) == 0.0
    assert a.distance_to(Point(0.0, 0.0)) >= 0.0
    pad = Pad(center=Point(0.0, 0.0), shape="rect", size=(w, h), net="N", layer=1)
    # the bound is the R2 proof: the circumscribing radius never under-reports
    assert pad.radius >= max(w, h) / 2.0


def test_p8_fails_for_constant_distance_mutant(_restore_kernels):
    """A distance kernel returning a constant breaks d(a, a) == 0.0."""
    _tg.point_distance_py = lambda *_a, **_k: 1.0
    with pytest.raises(AssertionError):
        test_p8_distance_and_radius_laws.hypothesis.inner_test(1.0, 2.0, 3.0, 4.0)


def test_p8_fails_for_underreporting_radius_mutant(_restore_kernels):
    """A radius kernel returning max(w,h)/2 - epsilon breaks the bound."""
    _tg.pad_radius_py = lambda w, h, *_a: max(w, h) / 2.0 - 0.1
    with pytest.raises(AssertionError):
        test_p8_distance_and_radius_laws.hypothesis.inner_test(1.0, 2.0, 3.0, 4.0)


# ============================================================================
# Metamorphic relations (G5) — >= 3 per migrated module
# ============================================================================

_FLOAT = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)


# ---- graph.py ---------------------------------------------------------------


@given(netlist_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr1_net_permutation_exact(netlist):
    """Permuting the net list permutes the edge blocks accordingly (exact)."""
    perm = list(reversed(netlist.nets))
    original = netlist_to_graph(netlist)
    permuted = netlist_to_graph(Netlist(components=netlist.components, nets=perm))
    # block spans per net, in original edge order
    comp_refs = {c.ref: i for i, c in enumerate(netlist.components)}
    blocks = []
    idx = 0
    for net in netlist.nets:
        indices = list({comp_refs[p[0]] for p in net.pins if p[0] in comp_refs})
        k = len(indices) * (len(indices) - 1) // 2
        blocks.append((idx, idx + k))
        idx += k
    # reverse the block order (nets reversed) and reorder the edge arrays
    edge_rows = [original.edges[s:e] for s, e in reversed(blocks)]
    weight_rows = [original.edge_weights[s:e] for s, e in reversed(blocks)]
    if edge_rows:
        got_edges = np.concatenate(edge_rows, axis=0)
        got_weights = np.concatenate(weight_rows, axis=0)
    else:
        got_edges = original.edges[:0]
        got_weights = original.edge_weights[:0]
    assert np.array_equal(got_edges, permuted.edges)
    assert np.array_equal(got_weights, permuted.edge_weights)


@given(netlist_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr2_component_relabel_exact(netlist):
    """Relabeling components via a bijection preserves connectivity up to
    the relabel: the ref-pair set maps identically (exact)."""
    relabel_map = {c.ref: f"Z{i}" for i, c in enumerate(netlist.components)}
    comps2 = []
    for c in netlist.components:
        c2 = Component(ref=relabel_map[c.ref], footprint=c.footprint, bounds=(c.width, c.height))
        c2.pins.extend([None] * len(c.pins))
        comps2.append(c2)
    nets2 = [
        Net(name=n.name, pins=[(relabel_map[p[0]], p[1]) for p in n.pins], weight=n.weight)
        for n in netlist.nets
    ]
    got = netlist_to_graph(netlist)
    want = netlist_to_graph(Netlist(components=comps2, nets=nets2))
    refs = [c.ref for c in netlist.components]
    refs2 = [c.ref for c in comps2]
    got_pairs = {frozenset((refs[u], refs[v])) for u, v in got.edges}
    want_pairs = {frozenset((refs2[u], refs2[v])) for u, v in want.edges}
    expected = {frozenset((relabel_map[a], relabel_map[b])) for a, b in got_pairs}
    assert expected == want_pairs


@given(netlist_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr3_batch_associativity_exact(netlist):
    """batching [a, b, c] equals batching [[a, b], c] and [a, [b, c]] (exact)."""
    a = netlist_to_graph(netlist)
    b = netlist_to_graph(_some_netlist())
    c = netlist_to_graph(_some_netlist())
    left = batch_graphs([batch_graphs([a, b]), c])
    right = batch_graphs([a, batch_graphs([b, c])])
    direct = batch_graphs([a, b, c])
    for g1, g2 in ((left, direct), (right, direct)):
        assert np.array_equal(g1.nodes, g2.nodes)
        assert np.array_equal(g1.edges, g2.edges)
        assert np.array_equal(g1.edge_weights, g2.edge_weights)


# ---- hypergraph.py -----------------------------------------------------------


@given(coo_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr4_triplet_order_invariance_tolerance(coo):
    """Permuting the triplets leaves the matvec result unchanged within the
    oracle's own band. NOT exact: FP addition is order-dependent (the
    scatter-add sums in triplet order, and a permutation can move the last
    ulp — the mathematically order-invariant sum is not bit-invariant).
    The band is 1 ulp of the largest magnitude term."""
    ones = np.ones(coo.shape[1], dtype=np.float64)
    baseline = coo @ ones
    perm = list(range(len(coo.data)))
    random.Random(7).shuffle(perm)
    shuffled = Coo(
        row=coo.row[perm],
        col=coo.col[perm],
        data=coo.data[perm],
        shape=coo.shape,
    )
    got = shuffled @ ones
    scale = max(1.0, float(np.max(np.abs(baseline))) if len(baseline) else 1.0)
    assert np.all(np.abs(got - baseline) <= 1e-12 * scale)


def test_mr4_fails_for_order_dependent_mutant(_restore_kernels):
    """A matvec whose accumulation depends on triplet POSITION breaks the
    order-invariance relation (Random(7) permutes 3 elements non-trivially,
    so the shuffled and baseline orders genuinely differ)."""
    def order_dependent(row, col, data, n_rows, other):
        n = max(n_rows, (int(row.max()) + 1) if len(row) else 0)
        result = [0.0] * n
        for i in range(len(data)):
            result[row[i]] += data[i] * other[col[i]] * (i + 1)
        return result

    _tg.hypergraph_coo_matvec_py = order_dependent
    coo = Coo(
        row=np.array([0, 0, 0], dtype=np.int64),
        col=np.array([0, 0, 0], dtype=np.int64),
        data=np.array([1.0, 2.0, 4.0], dtype=np.float64),
        shape=(1, 1),
    )
    with pytest.raises(AssertionError):
        test_mr4_triplet_order_invariance_tolerance.hypothesis.inner_test(coo)


@given(st.integers(min_value=0, max_value=4), st.integers(min_value=0, max_value=4),
       st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=60000)
def test_mr5_single_triplet_basis_exact(r, c, d):
    """A single triplet times the basis vector yields exactly d at r, 0 elsewhere."""
    n_rows, n_cols = 5, 5
    coo = Coo(
        row=np.array([r], dtype=np.int64),
        col=np.array([c], dtype=np.int64),
        data=np.array([d], dtype=np.float64),
        shape=(n_rows, n_cols),
    )
    e = np.zeros(n_cols, dtype=np.float64)
    e[c] = 1.0
    got = coo @ e
    assert len(got) == n_rows
    for i, v in enumerate(got):
        if i == r:
            assert v == d
        else:
            assert v == 0.0


@given(coo_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr6_transpose_degrees_exact(coo):
    """coo @ ones gives node degrees; coo.T @ ones gives hyperedge degrees;
    both equal their independent per-row/col sums (exact)."""
    ones_cols = np.ones(coo.shape[1], dtype=np.float64)
    ones_rows = np.ones(coo.shape[0], dtype=np.float64)
    node_deg = coo @ ones_cols
    edge_deg = coo.T @ ones_rows
    for i in range(coo.shape[0]):
        assert node_deg[i] == _independent_row_sums(coo)[i]
    transposed = Coo(row=coo.col, col=coo.row, data=coo.data, shape=(coo.shape[1], coo.shape[0]))
    for j in range(coo.shape[1]):
        assert edge_deg[j] == _independent_row_sums(transposed)[j]


# ---- pin_geometry.py ---------------------------------------------------------


@given(pin_geometry_case())
@settings(max_examples=50, deadline=60000)
def test_mr7_zero_rotation_is_translation_exact(case):
    """At rotation 0, side 0: world position is the pure translation (exact)."""
    px, py, _ = case
    comp = Component(ref="T", footprint="0603", bounds=(1.0, 1.0))
    comp.initial_position = (3.0, -2.0)
    comp.initial_rotation = 0
    comp.initial_side = 0
    pin = _PointPin((px, py))
    got = pin_world_position_at(pin, comp)
    assert got == (3.0 + px, -2.0 + py)


@given(pin_geometry_case())
@settings(max_examples=50, deadline=60000)
def test_mr8_quarter_turn_law(case):
    """At rotation index 1 the position follows the (py, -px) quarter turn
    within the oracle's own cos(pi/2)~6e-17 band (tight tolerance)."""
    px, py, _ = case
    comp = Component(ref="T", footprint="0603", bounds=(1.0, 1.0))
    comp.initial_position = (0.0, 0.0)
    comp.initial_rotation = 1
    comp.initial_side = 0
    got = pin_world_position_at(_PointPin((px, py)), comp)
    tol = 1e-12 * (1.0 + abs(px) + abs(py))
    assert abs(got[0] - py) <= tol
    assert abs(got[1] + px) <= tol


@given(pin_geometry_case())
@settings(max_examples=50, deadline=60000)
def test_mr9_rotation_additivity(case):
    """rotating by index a then index b equals rotating by (a+b) mod 4
    (tight tolerance; the composition of libm quadrant cos/sin carries
    1-ulp terms through, so the law is bounded, not bit-exact)."""
    px, py, _ = case
    for a in (0, 1, 2, 3):
        for b in (0, 1, 2, 3):
            comp1 = Component(ref="T", footprint="0603", bounds=(1.0, 1.0))
            comp1.initial_position = (0.0, 0.0)
            comp1.initial_rotation = (a + b) % 4
            comp1.initial_side = 0
            direct = pin_world_position_at(_PointPin((px, py)), comp1)
            # compose: apply rotation a, then rotation b to the resulting point
            comp2 = Component(ref="T", footprint="0603", bounds=(1.0, 1.0))
            comp2.initial_position = (0.0, 0.0)
            comp2.initial_rotation = a
            comp2.initial_side = 0
            mid = pin_world_position_at(_PointPin((px, py)), comp2)
            comp3 = Component(ref="T", footprint="0603", bounds=(1.0, 1.0))
            comp3.initial_position = (0.0, 0.0)
            comp3.initial_rotation = b
            comp3.initial_side = 0
            composed = pin_world_position_at(_PointPin(mid), comp3)
            tol = 1e-9 * (1.0 + abs(px) + abs(py))
            assert abs(direct[0] - composed[0]) <= tol
            assert abs(direct[1] - composed[1]) <= tol


# ---- power_topology.py -------------------------------------------------------


@given(st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=60000)
def test_mr10_one_oz_consistency_exact(current):
    """IPC2221Rule(1.0) trace_width equals the rail's required_trace_width
    — the same expression, so bit-exact."""
    rail = PowerRailSpec(
        net_name="+X", max_current_a=current, voltage_v=1.0,
        source_component="S", sink_components=(),
    )
    assert IPC2221Rule(copper_weight_oz=1.0).trace_width(rail) == rail.required_trace_width()


@given(st.integers(min_value=0, max_value=40))
@settings(max_examples=50, deadline=60000)
def test_mr11_trace_width_monotone_non_decreasing(base):
    """trace_width and required_trace_width are non-decreasing in current
    (exact: comparisons, no arithmetic)."""
    i1, i2 = float(base), float(base + 1)
    r1 = PowerRailSpec(net_name="A", max_current_a=i1, voltage_v=1.0, source_component="S", sink_components=())
    r2 = PowerRailSpec(net_name="B", max_current_a=i2, voltage_v=1.0, source_component="S", sink_components=())
    assert r1.required_trace_width() <= r2.required_trace_width()
    assert IPC2221Rule(copper_weight_oz=2.0).trace_width(r1) <= IPC2221Rule(copper_weight_oz=2.0).trace_width(r2)


@given(st.floats(min_value=-5.0, max_value=10.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=60000)
def test_mr12_threshold_lattice_exact(current):
    """delivery_strategy follows the exact <1 / [1,3) / >=3 bands (exact)."""
    rail = PowerRailSpec(net_name="+X", max_current_a=current, voltage_v=1.0, source_component="S", sink_components=())
    s = rail.delivery_strategy()
    if current < 1.0:
        assert s is PowerDeliveryStrategy.STANDARD_TRACE
    elif current < 3.0:
        assert s is PowerDeliveryStrategy.WIDE_TRACE
    else:
        assert s is PowerDeliveryStrategy.PLANE


# ---- topology.py -------------------------------------------------------------


@given(topological_graph_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr13_edge_order_invariance_exact(graph):
    """Rebuilding the same adjacency edges in shuffled order leaves the
    partition AND the first-appearance group order unchanged (exact)."""
    if not graph.adjacency_edges:
        return
    baseline = graph.get_clusters()
    shuffled = TopologicalGraph()
    for n in graph.nodes:
        shuffled.add_node(n)
    for a, b, d in list(reversed(graph.adjacency_edges)):
        shuffled.add_adjacency(a, b, d)
    assert shuffled.get_clusters() == baseline


@given(topological_graph_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr14_component_permutation_exact(graph):
    """Permuting node insertion order permutes the cluster groups
    consistently; the multiset of clusters is invariant (exact)."""
    baseline = graph.get_clusters()
    baseline_multiset = {frozenset(c) for c in baseline}
    permuted = TopologicalGraph()
    for n in list(reversed(graph.nodes)):
        permuted.add_node(n)
    for a, b, d in graph.adjacency_edges:
        permuted.add_adjacency(a, b, d)
    got = permuted.get_clusters()
    assert {frozenset(c) for c in got} == baseline_multiset


@given(topological_graph_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr15_merge_monotonicity_exact(graph):
    """Adding an edge can only merge clusters — never split — so the number
    of clusters is non-increasing and every new cluster is a superset of a
    pre-existing one (exact: set inclusion)."""
    if not graph.nodes:
        return
    before = graph.get_clusters()
    before_sets = [set(c) for c in before]
    grown = TopologicalGraph()
    for n in graph.nodes:
        grown.add_node(n)
    for a, b, d in graph.adjacency_edges:
        grown.add_adjacency(a, b, d)
    if len(graph.nodes) >= 2:
        grown.add_adjacency(graph.nodes[0], graph.nodes[-1], 1.0)
    after = [set(c) for c in grown.get_clusters()]
    assert len(after) <= len(before)
    for s in before_sets:
        assert any(s <= t for t in after)


# ---- courtyard.py ------------------------------------------------------------


@given(polygon_strategy(), st.integers(min_value=0, max_value=3), st.integers(min_value=0, max_value=3))
@settings(max_examples=50, deadline=60000)
def test_mr16_rotation_composition_exact(points, a, b):
    """Rotating by a then b equals rotating by (a+b) mod 4 — EXACT: at
    quadrant angles shapely's cosp/sinp zeroing makes every rotation an
    exact (permutation + negation) map."""
    c = Courtyard(component_ref="U1", points=points)
    direct = list(c.get_global_polygon(0.0, 0.0, (a + b) % 4).exterior.coords)
    first = list(c.get_global_polygon(0.0, 0.0, a).exterior.coords)
    c2 = Courtyard(component_ref="U1", points=first)
    composed = list(c2.get_global_polygon(0.0, 0.0, b).exterior.coords)
    assert len(direct) == len(composed)
    for (dx_, dy_), (cx_, cy_) in zip(direct, composed):
        assert dx_ == cx_
        assert dy_ == cy_


@given(polygon_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr17_double_rotation_is_negation_exact(points):
    """Rotation by 2 quadrants (180 deg) maps every local vertex to its
    exact negation (cos(pi) = -1 exactly, sin zeroed by shapely). Compare
    against the rotation-0 (identity) polygon so the closing ring vertex
    is present on both sides."""
    c = Courtyard(component_ref="U1", points=points)
    identity = list(c.get_global_polygon(0.0, 0.0, 0).exterior.coords)
    twice = list(c.get_global_polygon(0.0, 0.0, 2).exterior.coords)
    assert len(identity) == len(twice)
    for (x, y), (gx, gy) in zip(identity, twice):
        assert gx == -x
        assert gy == -y


@given(polygon_strategy(), st.integers(min_value=0, max_value=3))
@settings(max_examples=50, deadline=60000)
def test_mr18_area_preservation_shoelace_exact(points, rotation_idx):
    """Polygon area (vertex shoelace) is invariant under any quadrant
    rotation — EXACT: the cross-product terms are invariant under the
    (x,y)->(y,-x) / negation maps, so the shoelace sum is bit-identical."""
    c = Courtyard(component_ref="U1", points=points)
    rotated = list(c.get_global_polygon(0.0, 0.0, rotation_idx).exterior.coords)

    def shoelace(coords):
        acc = 0.0
        for i in range(len(coords) - 1):
            x0, y0 = coords[i]
            x1, y1 = coords[i + 1]
            acc += x0 * y1 - x1 * y0
        return acc

    assert shoelace(rotated) == shoelace(points + [points[0]])


# ---- geometry_types.py -------------------------------------------------------


@given(_FLOAT, _FLOAT, _FLOAT, _FLOAT)
@settings(max_examples=50, deadline=60000)
def test_mr19_distance_symmetry_exact(x1, y1, x2, y2):
    a = Point(x1, y1)
    b = Point(x2, y2)
    assert a.distance_to(b) == b.distance_to(a)


@given(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
       st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=60000)
def test_mr20_radius_symmetry_exact(w, h):
    assert Pad(center=Point(0, 0), shape="rect", size=(w, h), net="N", layer=1).radius == \
        Pad(center=Point(0, 0), shape="rect", size=(h, w), net="N", layer=1).radius


@given(_FLOAT, _FLOAT, _FLOAT, _FLOAT)
@settings(max_examples=50, deadline=60000)
def test_mr21_distance_scale_tolerance(x1, y1, x2, y2):
    """distance(k*p1, k*p2) == k * distance(p1, p2) within the oracle's own
    band (power-of-two k keeps the relative error at the 1-ulp level; the
    Dekker vector_norm is not exactly homogeneous)."""
    k = 4.0
    a = Point(x1, y1)
    b = Point(x2, y2)
    d = a.distance_to(b)
    scaled = Point(k * x1, k * y1).distance_to(Point(k * x2, k * y2))
    tol = 1e-12 * (1.0 + abs(d))
    assert abs(scaled - k * d) <= tol


# ---------------------------------------------------------------------------
# Small pin duck-type for the pin_geometry properties
# ---------------------------------------------------------------------------


class _PointPin:
    def __init__(self, position):
        self.position = position


# sanity: the mutant fixtures genuinely discriminate (the input classes are
# not trivially degenerate for the properties they guard)
def test_mr1_fixture_not_trivially_symmetric():
    netlist = _some_netlist()
    pairs, _ = _expected_clique_pairs(netlist)
    assert len(pairs) == 6  # C(4, 2) — a non-degenerate clique


def test_mr17_fixture_is_not_zero_area():
    pts = [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)]
    c = Courtyard(component_ref="U1", points=pts)
    twice = list(c.get_global_polygon(0.0, 0.0, 2).exterior.coords)
    assert all(gx == -x and gy == -y for (x, y), (gx, gy) in zip(pts, twice))
