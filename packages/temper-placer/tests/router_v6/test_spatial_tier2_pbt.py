"""Property-based and metamorphic tests for the Wave-4 spatial-tier-2
Rust kernels (bottleneck_analysis, layer_capacity, connectivity,
obstacle_map circle-buffer).

G4 verification unit = this whole cluster (one pinned oracle corpus in
``test_spatial_tier2_rust_differential.py``).  Module-to-property map:

- P1, P2        -> ``bottleneck_analysis`` kernels (utilization
                   arithmetic; severity monotonicity in capacity)
- P3            -> ``layer_capacity`` estimate kernel
- P4            -> ``connectivity`` kernel (partition == from-first-
                   principles circle-pad contact closure)
- P5            -> ``connectivity`` kernel (monotonicity under copper
                   addition)
- P6            -> ``obstacle_map`` circle-buffer kernel (ring geometry)

``routing_space`` is JUSTIFIED-KEEP in this unit (GEOS difference/area,
see the differential suite's module docstring); it has no Rust kernel for
a property to reach.

Reachability (G4 condition 2): each property's generators are checked by
a mutation test at the bottom (`test_pN_fails_for_<mutant>`) proving a
degenerate kernel violates the property — a property that cannot fail is
not counted.

Metamorphic relations (G5, >= 3 per migrated module), in the
"Metamorphic relations" section:

bottleneck_analysis:
  M1 severity scale invariance under an exact power-of-two capacity/demand
     scaling (exact: integer ratio preserved, f64 division of exact
     operands)
  M2 permutation invariance of the layer-dict order (exact: the bottleneck
     list mirrors dict order)
  M3 zero-demand edge (exact: utilization 0.0 / severity NONE for positive
     capacity)

layer_capacity:
  M1 common power-of-two scaling of (avg_channel_width, min_trace_width,
     min_clearance) leaves the estimate unchanged (exact: scaling by 2 is
     exact and commutes with IEEE rounding)
  M2 zero-pitch edge (exact: estimate 0 for min_trace_width ==
     min_clearance == 0)
  M3 monotone non-decreasing in free_cells (exact: truncation is monotone)

connectivity:
  M1 pad-component partition invariant under input permutation (exact)
  M2 layer-index shift invariance (exact: membership/intersection are
     index-agnostic)
  M3 duplicate-copper idempotence: adding a copy of an existing via/track
     does not change the partition (exact)

obstacle_map:
  M1 empty-ring invariance under translation for radius <= 0 (exact)
  M2 vertex-count / closure invariant: ring(cx, cy, r, q) has exactly
     4q+1 coordinates for r > 0 (exact)
  M3 cardinal-point placement: vertices 0/8/16/24 of the q=8 ring land
     exactly on the axes through the center (exact, sinCosSnap)
  M4 start-point identity: ring[0] == (cx + r, cy) (exact)
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from temper_placer.router_v6 import bottleneck_analysis as ba
from temper_placer.router_v6 import connectivity as conn
from temper_placer.router_v6 import layer_capacity as lc
from temper_placer.router_v6 import obstacle_map as om
from temper_placer.router_v6.bottleneck_analysis import BottleneckSeverity
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    CopperVia,
    CopperZone,
    PadIdentity,
    verify_net_connectivity,
)
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.layer_capacity import LayerCapacity
from temper_placer.router_v6.routing_demand import RoutingDemand

_SEVERITY_RANK = {
    BottleneckSeverity.NONE: 0,
    BottleneckSeverity.LOW: 1,
    BottleneckSeverity.MEDIUM: 2,
    BottleneckSeverity.HIGH: 3,
    BottleneckSeverity.CRITICAL: 4,
}


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


@st.composite
def capacities_and_demand(draw):
    """A layer-capacity dict (1-4 layers, insertion-ordered) and a demand."""
    n_layers = draw(st.integers(min_value=1, max_value=4))
    caps = {}
    for i in range(n_layers):
        caps[f"L{i}"] = LayerCapacity(
            layer_name=f"L{i}",
            total_cells=10000,
            free_cells=draw(st.integers(0, 10000)),
            blocked_cells=draw(st.integers(0, 10000)),
            min_channel_width=draw(st.floats(0.0, 2.0, allow_nan=False)),
            avg_channel_width=draw(st.floats(0.0, 10.0, allow_nan=False)),
            estimated_traces=draw(st.integers(0, 200)),
        )
    demand = RoutingDemand(
        total_nets=draw(st.integers(0, 300)),
        routable_nets=draw(st.integers(0, 300)),
        total_pins=0,
        signal_nets=0,
        power_nets=0,
        diff_pair_nets=0,
        avg_pins_per_net=0.0,
        max_pins_per_net=0,
    )
    return caps, demand


@st.composite
def grid_and_widths(draw):
    free = draw(st.integers(0, 4000))
    return (
        free,
        draw(st.floats(0.0, 20.0, allow_nan=False)),
        # Bounded away from denormals: trace_pitch stays >= 0.01 so
        # avg/trace_pitch is finite and the reference's int() never hits
        # OverflowError (the reference raises on int(inf) too).
        draw(st.floats(0.01, 1.0, allow_nan=False)),
        draw(st.floats(0.01, 1.0, allow_nan=False)),
    )


def _pad(rng, net, idx, x=None, y=None):
    return CopperPad(
        identity=PadIdentity(
            component_ref=f"C{idx}", pad=f"P{idx}", net=net,
            x=float(idx), y=float(idx % 5), layers=(0,),
        ),
        center=Point(x if x is not None else rng.uniform(-5, 5),
                     y if y is not None else rng.uniform(-5, 5)),
        shape=rng.choice(["circle", "rect"]),
        size=(rng.choice([0.5, 1.0, 1.5]), rng.choice([0.5, 1.0, 1.5])),
        rotation=float(rng.choice([0, 30, 45, 90])),
    )


@st.composite
def connectivity_inputs(draw):
    rng = random.Random(draw(st.integers(0, 2**31 - 1)))
    net = f"N{draw(st.integers(0, 1000))}"
    pads = [_pad(rng, net, i) for i in range(draw(st.integers(1, 4)))]
    tracks = [
        CopperTrack(
            start=Point(rng.uniform(-5, 5), rng.uniform(-5, 5)),
            end=Point(rng.uniform(-5, 5), rng.uniform(-5, 5)),
            layer=rng.choice([0, 1]),
            width=rng.choice([0.2, 0.5, 1.0]),
            net=net,
        )
        for _ in range(draw(st.integers(0, 4)))
    ]
    vias = [
        CopperVia(
            center=Point(rng.uniform(-5, 5), rng.uniform(-5, 5)),
            layers=frozenset(rng.choice([(0,), (1,), (0, 1)])),
            diameter=rng.choice([0.4, 0.6, 1.0]),
            net=net,
        )
        for _ in range(draw(st.integers(0, 3)))
    ]
    zones = [
        CopperZone(
            polygon=Polygon(
                [(rng.uniform(-4, 0), rng.uniform(-4, 0)),
                 (rng.uniform(0, 4), rng.uniform(-4, 0)),
                 (rng.uniform(0, 4), rng.uniform(0, 4)),
                 (rng.uniform(-4, 0), rng.uniform(0, 4))]
            ),
            layer=rng.choice([0, 1]),
            net=net,
        )
        for _ in range(draw(st.integers(0, 2)))
    ]
    return pads, tracks, vias, zones


def _pad_partition(result):
    """Frozenset of frozensets of pad identities — order-free partition."""
    return frozenset(frozenset(c.pads) for c in result.components)


# ---------------------------------------------------------------------------
# P1 — bottleneck utilization arithmetic
# ---------------------------------------------------------------------------


@given(capacities_and_demand())
@settings(max_examples=100, deadline=60000)
def test_p1_utilization_arithmetic(caps_and_demand):
    caps, demand = caps_and_demand
    analysis = ba.identify_bottlenecks(caps, demand)
    num_layers = len(caps)
    demand_per_layer = demand.routable_nets // num_layers if num_layers else 0
    assert analysis.total_demand == demand.routable_nets
    assert analysis.total_capacity == sum(c.estimated_traces for c in caps.values())
    for name, bn in zip(caps.keys(), analysis.bottlenecks):
        cap = caps[name].estimated_traces
        if cap > 0:
            assert bn.utilization == demand_per_layer / cap
            assert bn.utilization.hex() == (demand_per_layer / cap).hex()
        else:
            assert bn.utilization == float("inf")
        assert bn.demand == demand_per_layer
        assert bn.capacity == cap


# ---------------------------------------------------------------------------
# P2 — bottleneck severity monotonic in capacity
# ---------------------------------------------------------------------------


@given(capacities_and_demand())
@settings(max_examples=100, deadline=60000)
def test_p2_severity_monotonic_in_capacity(caps_and_demand):
    caps, demand = caps_and_demand
    # Raise one layer's capacity and check its severity never worsens.
    name = next(iter(caps))
    cap = caps[name].estimated_traces
    analysis_lo = ba.identify_bottlenecks(caps, demand)
    severity_lo = next(bn.severity for bn in analysis_lo.bottlenecks if bn.layer_name == name)

    caps_hi = dict(caps)
    caps_hi[name] = LayerCapacity(
        layer_name=name, total_cells=10000, free_cells=0, blocked_cells=0,
        min_channel_width=0.0, avg_channel_width=0.0,
        estimated_traces=cap + 25,
    )
    analysis_hi = ba.identify_bottlenecks(caps_hi, demand)
    severity_hi = next(bn.severity for bn in analysis_hi.bottlenecks if bn.layer_name == name)
    assert _SEVERITY_RANK[severity_hi] <= _SEVERITY_RANK[severity_lo]
    # Cross-module consistency: severity == the classify kernel on the same
    # scalars.
    bn = next(bn for bn in analysis_hi.bottlenecks if bn.layer_name == name)
    assert bn.severity == ba._classify_severity(bn.capacity, bn.demand)


# ---------------------------------------------------------------------------
# P3 — layer_capacity estimate monotone in free cells and channel width
# ---------------------------------------------------------------------------


@given(grid_and_widths())
@settings(max_examples=100, deadline=60000)
def test_p3_estimate_monotonic_with_free_cells_and_width(gw):
    free, avg, tw, cl = gw
    grid = _grid_stub("F.Cu", free)
    widths = _widths_stub(avg)
    lo_free = lc.calculate_layer_capacity(grid, widths, tw, cl)
    hi_grid = _grid_stub("F.Cu", free + 500)
    hi_free = lc.calculate_layer_capacity(hi_grid, widths, tw, cl)
    assert hi_free.estimated_traces >= lo_free.estimated_traces

    lo_w = lc.calculate_layer_capacity(grid, _widths_stub(avg), tw, cl)
    hi_w = lc.calculate_layer_capacity(grid, _widths_stub(avg + 5.0), tw, cl)
    assert hi_w.estimated_traces >= lo_w.estimated_traces
    assert lo_free.estimated_traces >= 0


def _grid_stub(layer_name, free):
    return __import__("types", fromlist=["SimpleNamespace"]).SimpleNamespace(
        layer_name=layer_name,
        width_cells=50,
        height_cells=50,
        free_cell_count=free,
        blocked_cell_count=2500 - free,
    )


def _widths_stub(avg):
    return __import__("types", fromlist=["SimpleNamespace"]).SimpleNamespace(
        min_width=0.5, avg_width=avg
    )


# ---------------------------------------------------------------------------
# P4 — connectivity partition matches the circle-pad contact closure
# ---------------------------------------------------------------------------


def _circle_contact_partition(pads):
    """Reference transitive closure over circle pads only: two pads are in
    the same component when either center lies inside the other's contact
    circle (``local_x² + local_y² <= (w/2)² + TOL``, radius == 0).  This is
    a from-first-principles recomputation of the kernel's own circle-pad
    rule, independent of the Rust predicates."""
    n = len(pads)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = pads[i], pads[j]
            if not (a.layers & b.layers):
                continue
            for (px, py, q) in ((a.center.x, a.center.y, b), (b.center.x, b.center.y, a)):
                local_x, local_y = px - q.center.x, py - q.center.y
                half = q.size[0] / 2.0
                if local_x * local_x + local_y * local_y <= half * half + conn.CONTACT_TOLERANCE_MM:
                    union(i, j)
                    break
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(pads[i].identity)
    return frozenset(frozenset(g) for g in groups.values())


@st.composite
def circle_pad_inputs(draw):
    """Nets of 1-5 circle pads only (no tracks/vias/zones), so the closure
    above fully determines the expected partition."""
    rng = random.Random(draw(st.integers(0, 2**31 - 1)))
    net = f"N{draw(st.integers(0, 1000))}"
    pads = []
    for i in range(draw(st.integers(2, 5))):
        pads.append(CopperPad(
            identity=PadIdentity(f"C{i}", f"P{i}", net, float(i), 0.0, (0,)),
            center=Point(rng.uniform(-3, 3), rng.uniform(-3, 3)),
            shape="circle",
            size=(rng.choice([0.5, 1.0, 1.5]), 1.0),
            rotation=0.0,
        ))
    return pads


@given(circle_pad_inputs())
@settings(max_examples=100, deadline=60000)
def test_p4_partition_matches_circle_contact_closure(pads):
    result = verify_net_connectivity(pads, [], [])
    assert _pad_partition(result) == _circle_contact_partition(pads)
    # The kernel's pad count accounting is consistent with the closure.
    assert result.total_required_pad_count == len(pads)


# ---------------------------------------------------------------------------
# P5 — connectivity monotone under copper addition
# ---------------------------------------------------------------------------


@given(connectivity_inputs())
@settings(max_examples=100, deadline=60000)
def test_p5_components_monotone_under_copper_addition(cin):
    pads, tracks, vias, zones = cin
    base = verify_net_connectivity(pads, tracks, vias, zones)
    extra_track = CopperTrack(
        start=Point(-0.1, -0.1), end=Point(0.1, 0.1), layer=0, width=1.0, net=base.net or "N"
    )
    grown = verify_net_connectivity(pads, tracks + [extra_track], vias, zones)
    # Adding copper can only merge components, never split them.
    assert len(grown.components) <= len(base.components)
    assert grown.connected_pad_count >= base.connected_pad_count


def test_p5_bridge_track_strictly_merges_two_components():
    """A single bridge track between two separated pads merges exactly one
    pair of components: 2 -> 1."""
    pads = [_single_pad(0.0, 0.0, 0), _single_pad(4.0, 4.0, 1)]
    base = verify_net_connectivity(pads, [], [])
    assert len(base.components) == 2
    bridge = CopperTrack(start=Point(0.0, 0.0), end=Point(4.0, 4.0), layer=0, width=1.0, net="N")
    grown = verify_net_connectivity(pads, [bridge], [])
    assert len(grown.components) == 1
    assert grown.disposition == conn.NetDisposition.ROUTED


# ---------------------------------------------------------------------------
# P6 — obstacle_map circle-buffer ring geometry
# ---------------------------------------------------------------------------


@given(st.floats(-50, 50, allow_nan=False), st.floats(-50, 50, allow_nan=False),
       st.floats(1e-3, 20, allow_nan=False))
@settings(max_examples=100, deadline=60000)
def test_p6_ring_vertices_lie_on_the_circle(cx, cy, r):
    ring = om._circle_buffer_ring(cx, cy, r, 8)
    assert len(ring) == 33  # 32 distinct + closure
    assert ring[0] == ring[-1]
    for vx, vy in ring:
        dist_sq = (vx - cx) * (vx - cx) + (vy - cy) * (vy - cy)
        assert abs(dist_sq - r * r) <= 1e-9 * max(r * r, 1.0), (cx, cy, r, vx, vy, dist_sq)


# ---------------------------------------------------------------------------
# Non-vacuity: each property fails against a mutated (degenerate) kernel
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    orig = {
        "ba_identify": ba._tg.identify_bottlenecks_py,
        "ba_classify": ba._tg.classify_severity_py,
        "lc_estimate": lc._tg.estimate_traces_py,
        "conn_components": conn._tg.connectivity_components_py,
        "om_ring": om._tg.circle_buffer_ring_py,
    }
    yield
    ba._tg.identify_bottlenecks_py = orig["ba_identify"]
    ba._tg.classify_severity_py = orig["ba_classify"]
    lc._tg.estimate_traces_py = orig["lc_estimate"]
    conn._tg.connectivity_components_py = orig["conn_components"]
    om._tg.circle_buffer_ring_py = orig["om_ring"]


def _plain_caps_demand():
    caps = {
        "L0": LayerCapacity("L0", 10000, 8000, 2000, 1.0, 5.0, 50),
        "L1": LayerCapacity("L1", 10000, 8000, 2000, 1.0, 5.0, 100),
    }
    dem = RoutingDemand(100, 80, 0, 0, 0, 0, 0.0, 0)
    return caps, dem


def test_p1_fails_for_zero_utilization_kernel(_restore_kernels) -> None:
    ba._tg.identify_bottlenecks_py = lambda traces, total_demand: (
        sum(traces), total_demand // len(traces) if traces else 0, [0.0] * len(traces),
        ["none"] * len(traces),
    )
    with pytest.raises(AssertionError):
        test_p1_utilization_arithmetic.hypothesis.inner_test(_plain_caps_demand())


def test_p2_fails_for_constant_critical_kernel(_restore_kernels) -> None:
    ba._tg.identify_bottlenecks_py = lambda traces, total_demand: (
        sum(traces), total_demand // len(traces) if traces else 0,
        [0.0] * len(traces), ["critical"] * len(traces),
    )
    with pytest.raises(AssertionError):
        test_p2_severity_monotonic_in_capacity.hypothesis.inner_test(_plain_caps_demand())


def test_p3_fails_for_decreasing_estimate_kernel(_restore_kernels) -> None:
    lc._tg.estimate_traces_py = lambda free_cells, *a, **k: -free_cells  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p3_estimate_monotonic_with_free_cells_and_width.hypothesis.inner_test(
            (2000, 2.0, 0.127, 0.127)
        )


def test_p4_fails_for_constant_singleton_components(_restore_kernels) -> None:
    """A kernel that never joins pads (always one component per pad)
    violates the closure property as soon as two pads touch."""

    def singletons(pads, *a, **k):
        return [[i] for i in range(len(pads) // 5)]

    conn._tg.connectivity_components_py = singletons
    with pytest.raises(AssertionError):
        test_p4_partition_matches_circle_contact_closure.hypothesis.inner_test(
            [_single_pad(0.0, 0.0, 0), _single_pad(0.5, 0.0, 1)]
        )


def test_p5_fails_for_track_count_increasing_components(_restore_kernels) -> None:
    """A kernel whose component count grows with the track count violates
    the copper-addition monotonicity."""

    def grows_with_tracks(pads, pad_shapes, pad_layers, tracks, track_layers, vias, via_layers,
                          zone_pairs, total_items):
        n_pads = len(pads) // 5
        extra = len(tracks) // 5
        return [[i] for i in range(n_pads)] + [[] for _ in range(extra)]

    conn._tg.connectivity_components_py = grows_with_tracks
    with pytest.raises(AssertionError):
        test_p5_components_monotone_under_copper_addition.hypothesis.inner_test(
            (
                [_single_pad(0.0, 0.0, 0), _single_pad(4.0, 4.0, 1)],
                [],
                [],
                [],
            )
        )


def test_p6_fails_for_square_ring_kernel(_restore_kernels) -> None:
    om._tg.circle_buffer_ring_py = lambda cx, cy, r, q: (  # noqa: ARG005
        [(cx + r, cy), (cx, cy - r), (cx - r, cy), (cx, cy + r), (cx + r, cy)]
        if r > 0
        else []
    )
    with pytest.raises(AssertionError):
        test_p6_ring_vertices_lie_on_the_circle.hypothesis.inner_test(0.0, 0.0, 1.0)


def _single_pad(x, y, idx=0):
    return CopperPad(
        identity=PadIdentity("C1", f"P{idx}", "N", x, y, (0,)),
        center=Point(x, y),
        shape="circle",
        size=(1.0, 1.0),
        rotation=0.0,
    )


# sanity: the production kernels are NOT degenerate (the properties
# genuinely exercise them)
def test_properties_reach_discriminating_inputs() -> None:
    caps, dem = _plain_caps_demand()
    analysis = ba.identify_bottlenecks(caps, dem)
    assert any(bn.utilization > 0.0 for bn in analysis.bottlenecks)

    pads = [_single_pad(0.0, 0.0, 0), _single_pad(0.5, 0.0, 1)]
    assert len(verify_net_connectivity(pads, [], []).components) == 1

    ring = om._circle_buffer_ring(0.0, 0.0, 1.0, 8)
    assert len(ring) == 33


# ---------------------------------------------------------------------------
# Metamorphic relations (G5, >= 3 per module)
# ---------------------------------------------------------------------------


class TestBottleneckMetamorphic:
    @given(st.integers(0, 100), st.integers(0, 100))
    @settings(max_examples=50, deadline=60000)
    def test_m1_severity_scale_invariance(self, cap, demand):
        # M1: doubling both operands preserves the severity (exact: 2*cap /
        # 2*demand rounds identically to cap / demand).
        assert ba._classify_severity(2 * cap, 2 * demand) == ba._classify_severity(cap, demand)

    def test_m2_permutation_invariance(self):
        # M2: reordering the layer dict permutes the bottleneck list the
        # same way, with unchanged per-layer values.
        caps_a = {
            "A": LayerCapacity("A", 1, 1, 0, 0.0, 0.0, 10),
            "B": LayerCapacity("B", 1, 1, 0, 0.0, 0.0, 50),
            "C": LayerCapacity("C", 1, 1, 0, 0.0, 0.0, 100),
        }
        caps_b = {k: caps_a[k] for k in ("C", "A", "B")}
        dem = RoutingDemand(30, 30, 0, 0, 0, 0, 0.0, 0)
        a = ba.identify_bottlenecks(caps_a, dem)
        b = ba.identify_bottlenecks(caps_b, dem)
        assert [bn.layer_name for bn in a.bottlenecks] == ["A", "B", "C"]
        assert [bn.layer_name for bn in b.bottlenecks] == ["C", "A", "B"]
        values_a = {bn.layer_name: (bn.capacity, bn.demand, bn.utilization, bn.severity)
                    for bn in a.bottlenecks}
        values_b = {bn.layer_name: (bn.capacity, bn.demand, bn.utilization, bn.severity)
                    for bn in b.bottlenecks}
        assert values_a == values_b

    def test_m3_zero_demand_edge(self):
        dem = RoutingDemand(0, 0, 0, 0, 0, 0, 0.0, 0)
        caps = {
            "A": LayerCapacity("A", 1, 1, 0, 0.0, 0.0, 10),
            "B": LayerCapacity("B", 1, 1, 0, 0.0, 0.0, 0),
        }
        analysis = ba.identify_bottlenecks(caps, dem)
        assert analysis.total_demand == 0
        for bn in analysis.bottlenecks:
            assert bn.demand == 0
            if bn.capacity > 0:
                assert bn.utilization == 0.0
                assert bn.severity == BottleneckSeverity.NONE
            else:
                assert bn.severity == BottleneckSeverity.NONE  # demand 0 -> NONE


class TestLayerCapacityMetamorphic:
    @given(st.integers(1, 5000), st.floats(0.01, 20, allow_nan=False),
           st.floats(0.01, 1, allow_nan=False), st.floats(0.01, 1, allow_nan=False))
    @settings(max_examples=50, deadline=60000)
    def test_m1_power_of_two_scale_invariance(self, free, avg, tw, cl):
        grid = _grid_stub("F.Cu", free)
        a = lc.calculate_layer_capacity(grid, _widths_stub(avg), tw, cl)
        b = lc.calculate_layer_capacity(grid, _widths_stub(2.0 * avg), 2.0 * tw, 2.0 * cl)
        assert a.estimated_traces == b.estimated_traces

    def test_m2_zero_pitch_edge(self):
        grid = _grid_stub("F.Cu", 500)
        for avg in (0.5, 5.0, 20.0):
            cap = lc.calculate_layer_capacity(grid, _widths_stub(avg), min_trace_width=0.0,
                                              min_clearance=0.0)
            assert cap.estimated_traces == 0

    def test_m3_monotone_in_free_cells(self):
        widths = _widths_stub(5.0)
        low = lc.calculate_layer_capacity(_grid_stub("F.Cu", 100), widths, 0.127, 0.127)
        high = lc.calculate_layer_capacity(_grid_stub("F.Cu", 900), widths, 0.127, 0.127)
        assert low.estimated_traces <= high.estimated_traces


class TestConnectivityMetamorphic:
    @given(connectivity_inputs())
    @settings(max_examples=50, deadline=60000)
    def test_m1_partition_invariant_under_permutation(self, cin):
        pads, tracks, vias, zones = cin
        base = verify_net_connectivity(pads, tracks, vias, zones)
        rng = random.Random(7)
        shuffled = list(pads)
        rng.shuffle(shuffled)
        reordered = verify_net_connectivity(shuffled, list(reversed(tracks)), vias, zones)
        assert _pad_partition(base) == _pad_partition(reordered)

    def test_m2_layer_shift_invariance(self):
        # All layers shifted by +1: membership/intersection are
        # index-agnostic, so the partition is unchanged.
        pads = [_single_pad(0.0, 0.0, 0), _single_pad(0.5, 0.0, 1)]
        tracks = [CopperTrack(Point(0, 0), Point(1, 1), layer=0, width=1.0, net="N")]
        # shift the layer of everything by 1
        pads_s = [
            CopperPad(
                PadIdentity(p.identity.component_ref, p.identity.pad, p.identity.net,
                            p.identity.x, p.identity.y, (1,)),
                p.center, p.shape, p.size, p.rotation,
            )
            for p in pads
        ]
        tracks_s = [CopperTrack(t.start, t.end, layer=1, width=t.width, net=t.net)
                    for t in tracks]
        base = verify_net_connectivity(pads, tracks, [])
        shifted_res = verify_net_connectivity(pads_s, tracks_s, [])
        # Compare the grouping structure, not the identity (PadIdentity
        # carries the layer, which necessarily changed).
        def structure(result):
            return frozenset(frozenset(p.pad for p in comp.pads) for comp in result.components)

        assert structure(base) == structure(shifted_res)
        assert len(base.components) == 1

    def test_m3_duplicate_copper_idempotence(self):
        pads = [_single_pad(0.0, 0.0, 0), _single_pad(0.9, 0.0, 1)]
        # Both pads connect through the via at (0.45, 0): pad contact radius
        # 0.5 + via radius 0.3 = 0.8 >= 0.45.
        via = CopperVia(Point(0.45, 0.0), frozenset((0,)), 0.6, "N")
        base = verify_net_connectivity(pads, [], [via])
        assert len(base.components) == 1
        grown = verify_net_connectivity(pads, [], [via, via])
        assert _pad_partition(base) == _pad_partition(grown)


class TestObstacleMapMetamorphic:
    def test_m1_empty_ring_invariant_under_translation(self):
        for r in (0.0, -0.0, -1.5):
            assert om._circle_buffer_ring(1.0, 2.0, r, 8) == []
            assert om._circle_buffer_ring(100.0, -40.0, r, 8) == []

    @given(st.integers(1, 16), st.floats(1e-3, 20, allow_nan=False))
    @settings(max_examples=50, deadline=60000)
    def test_m2_vertex_count_and_closure(self, q, r):
        ring = om._circle_buffer_ring(3.0, -2.0, r, q)
        assert len(ring) == 4 * q + 1
        assert ring[0] == ring[-1]

    def test_m3_cardinal_points(self):
        ring = om._circle_buffer_ring(1.5, -2.25, 0.3, 8)
        assert ring[0] == (1.8, -2.25)
        assert ring[8] == (1.5, -2.55)
        assert ring[16] == (1.2, -2.25)
        assert ring[24] == (1.5, -1.95)

    def test_m4_start_point_identity(self):
        ring = om._circle_buffer_ring(-10.0, 20.0, 1.7, 8)
        assert ring[0] == (-8.3, 20.0)
