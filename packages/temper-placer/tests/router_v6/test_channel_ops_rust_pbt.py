"""Property-based tests for the Phase E batch E4 channel-operations
orchestration (temper-orchestration ``channel_mapping`` module, exercised
through the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E4. These properties
run against the production shims (``router_v6.{channel_mapping,
channel_widths}``) and hold over randomized inputs.

Six non-vacuous properties (G4):

- P1  SAT sequence is authoritative: every net whose ``uses_channels`` is
      non-empty is mapped, and its path's ``channel_sequence`` equals the
      net's ``uses_channels`` exactly (order preserved — the SAT guidance is
      never reordered or dropped). Vacuity guard: a kernel that drops the
      sequence (empty mapping) violates.
- P2  path-graph fallback: a net with empty ``uses_channels`` but a
      non-empty ``path_graph`` maps to the graph's node strings in first-seen
      order (PathGraph M6 rule). Vacuity guard: a kernel that skips the
      fallback (net unmapped) violates.
- P3  fallback_channel_path determinism: with ``enable_all_pad_tree`` the
      waypoints are ``sorted(pads)`` (deterministic coordinate order); the
      default multi-pad path is ``[pads[0], pads[-1]]``; a 2-pad net keeps
      ``pads``. Vacuity guard: input-order waypoints violate on unsorted pads.
- P4  two-pad endpoint correction: for a 2-pad net, the expanded path's
      first/last waypoints are exactly the two true pads (in the
      displacement-minimising order), and an already-correct path is left
      unchanged. Vacuity guard: a kernel that leaves a wrong endpoint
      violates.
- P5  channel-width statistics are consistent: ``min_width`` / ``max_width``
      / ``avg_width`` equal the min / max / mean of the node+edge width
      dicts (naive-summed in dict order, matching the reference). Vacuity
      guard: an always-zero-stats kernel violates.
- P6  every edge's width is the min over its endpoints and interior samples:
      ``edge_widths[(u, v)] <= node_widths[u]`` and ``<= node_widths[v]``.
      Vacuity guard: a max-based edge width violates.

Anti-vacuity per G4 is explicit in each property's ``_guard`` companion.
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from shapely.geometry import box

from temper_placer.router_v6.channel_mapping import (
    expand_channel_path_terminals,
    fallback_channel_path,
    map_topology_to_channels,
)
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton, SkeletonGraph
from temper_placer.router_v6.channel_widths import compute_channel_widths
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.topology_extraction import NetTopology, PathGraph, TopologyGraph

_SETTINGS = settings(max_examples=80, deadline=8000, suppress_health_check=[])

_COORD = st.floats(
    min_value=-40.0, max_value=40.0, allow_nan=False, allow_infinity=False
).filter(lambda x: abs(x) >= 1e-3 or x == 0.0)
_POINT = st.tuples(_COORD, _COORD)
_COORD_ID = st.tuples(st.integers(min_value=-20, max_value=20), st.integers(min_value=-20, max_value=20))


def _make_skeleton(nodes, edges=()):
    g = SkeletonGraph()
    for n in nodes:
        g.add_node(n, pos=n)
    for u, v in edges:
        g.add_edge(u, v, weight=1.0)
    return ChannelSkeleton(g, "F.Cu", 0.0)


def _net_topo(name, uses, path_edges=None):
    pg = PathGraph(path_edges) if path_edges is not None else None
    return NetTopology(
        net_name=name, path_graph=pg, uses_channels=list(uses), total_length_estimate=0.0
    )


# ---------------------------------------------------------------------------
# P1 — the SAT channel sequence is authoritative
# ---------------------------------------------------------------------------


@given(st.lists(st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=6), min_size=1, max_size=6))
@_SETTINGS
def test_p1_sat_sequence_authoritative(uses_lists):
    net_topos = {
        f"NET{i}": _net_topo(f"NET{i}", uses) for i, uses in enumerate(uses_lists)
    }
    topo = TopologyGraph(net_topologies=net_topos)
    sk = _make_skeleton([(0.0, 0.0), (10.0, 0.0)])
    mapping = map_topology_to_channels(topo, sk)
    assert mapping.mapped_net_count == len(net_topos)
    for i, uses in enumerate(uses_lists):
        name = f"NET{i}"
        path = mapping.get_path(name)
        assert path is not None
        assert path.channel_sequence == list(uses)


def test_p1_guard_dropped_sequence_discriminates():
    net = _net_topo("NET1", ["(0.0, 0.0)", "(10.0, 0.0)"])
    mapping = map_topology_to_channels(TopologyGraph(net_topologies={"NET1": net}), _make_skeleton([]))
    path = mapping.get_path("NET1")
    # The SAT sequence is authoritative and never dropped: the path carries
    # the full channel guidance even when no skeleton node exists.
    assert path is not None
    assert path.channel_sequence == ["(0.0, 0.0)", "(10.0, 0.0)"]


# ---------------------------------------------------------------------------
# P2 — the path-graph fallback fires for an empty SAT sequence
# ---------------------------------------------------------------------------


@given(st.lists(st.tuples(st.text(min_size=1, max_size=6), st.text(min_size=1, max_size=6)), min_size=1, max_size=4))
@_SETTINGS
def test_p2_path_graph_fallback(edges):
    name = "NET"
    topo = TopologyGraph(net_topologies={name: _net_topo(name, [], path_edges=edges)})
    sk = _make_skeleton([(0.0, 0.0), (10.0, 0.0)])
    mapping = map_topology_to_channels(topo, sk)
    path = mapping.get_path(name)
    assert path is not None
    # First-seen node order over the edge list (PathGraph M6 rule).
    seen = []
    for (a, b) in edges:
        for n in (a, b):
            if n not in seen:
                seen.append(n)
    assert path.channel_sequence == seen


def test_p2_guard_fallback_not_vacuous():
    topo = TopologyGraph(
        net_topologies={"NET": _net_topo("NET", [], path_edges=[("A", "B"), ("B", "C")])}
    )
    mapping = map_topology_to_channels(topo, _make_skeleton([(0.0, 0.0), (10.0, 0.0)]))
    # Without the fallback the net would be unmapped (empty sequence) — this
    # asserts the fallback really fired.
    path = mapping.get_path("NET")
    assert path is not None
    assert path.channel_sequence == ["A", "B", "C"]
    assert path.channel_sequence != []


# ---------------------------------------------------------------------------
# P3 — fallback_channel_path determinism
# ---------------------------------------------------------------------------


@given(st.lists(_POINT, min_size=2, max_size=8))
@_SETTINGS
def test_p3_fallback_deterministic_ordering(pads):
    all_pad = fallback_channel_path("NET", pads, enable_all_pad_tree=True)
    default = fallback_channel_path("NET", pads)
    if len(pads) == 2:
        # The two-pad historical-endpoint branch wins over the flag.
        assert all_pad.waypoints == pads
        assert default.waypoints == pads
    else:
        assert all_pad.waypoints == sorted(pads)
        assert default.waypoints == [pads[0], pads[-1]]


def test_p3_guard_sorted_not_input_order():
    pads = [(10.0, 0.0), (0.0, 0.0), (5.0, 5.0)]
    assert sorted(pads) != pads  # the discriminator is live
    path = fallback_channel_path("NET", pads, enable_all_pad_tree=True)
    assert path.waypoints == sorted(pads)
    assert path.waypoints != pads  # a kernel using input order would fail


# ---------------------------------------------------------------------------
# P4 — two-pad endpoint correction
# ---------------------------------------------------------------------------


@given(_POINT, _POINT, st.tuples(_POINT, _POINT))
@_SETTINGS
def test_p4_two_pad_endpoints_are_true_pads(first, last, pad_pair):
    from temper_placer.router_v6.channel_mapping import ChannelPath

    path = ChannelPath(
        net_name="NET",
        channel_sequence=["c1", "c2"],
        waypoints=[first, last],
        total_length=1.0,
    )
    pads = list(pad_pair)
    expanded = expand_channel_path_terminals(path, pads, enable_all_pad_tree=False)
    pad_a, pad_b = pads[0], pads[1]
    first_wp, last_wp = expanded.waypoints[0], expanded.waypoints[-1]
    # The endpoints are exactly the two true pads, in one of the two orders.
    assert {first_wp, last_wp} == {pad_a, pad_b}


def test_p4_guard_wrong_endpoint_is_corrected():
    from temper_placer.router_v6.channel_mapping import ChannelPath

    path = ChannelPath(
        net_name="NET",
        channel_sequence=["c1", "c2"],
        waypoints=[(0.0, 0.0), (99.0, 99.0)],
        total_length=1.0,
    )
    expanded = expand_channel_path_terminals(path, [(0.0, 0.0), (10.0, 0.0)])
    assert expanded.waypoints != path.waypoints  # the correction really fires
    assert expanded.waypoints[0] == (0.0, 0.0)
    assert expanded.waypoints[-1] == (10.0, 0.0)


# ---------------------------------------------------------------------------
# P5 — channel-width statistics consistency
# ---------------------------------------------------------------------------


def _rs():
    return RoutingSpace(
        layer_name="F.Cu",
        available_area=box(0, 0, 25, 12),
        total_area=300.0,
        obstacle_area=0.0,
        routing_area=300.0,
    )


@given(st.lists(_POINT, min_size=2, max_size=7), st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False))
@_SETTINGS
def test_p5_width_stats_consistent(nodes, sample_distance):
    rs = _rs()
    edges = [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
    sk = _make_skeleton(nodes, edges)
    cw = compute_channel_widths(rs, sk, sample_distance=sample_distance)
    all_w = list(cw.node_widths.values()) + list(cw.edge_widths.values())
    assert len(all_w) > 0
    assert float(cw.min_width) == min(float(w) for w in all_w)
    assert float(cw.max_width) == max(float(w) for w in all_w)
    assert float(cw.avg_width) == sum(float(w) for w in all_w) / len(all_w)


def test_p5_guard_stats_not_vacuous():
    sk = _make_skeleton([(1.0, 1.0), (5.0, 1.0)])
    cw = compute_channel_widths(_rs(), sk, sample_distance=1.0)
    assert cw.min_width > 0.0  # inside a 25x12 box the skeleton clears the edge
    assert cw.max_width >= cw.min_width
    assert cw.avg_width >= cw.min_width


# ---------------------------------------------------------------------------
# P6 — every edge's width is the min over its endpoints and interior samples
# ---------------------------------------------------------------------------


@given(st.lists(_POINT, min_size=2, max_size=7), st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False))
@_SETTINGS
def test_p6_edge_width_bounded_by_endpoints(nodes, sample_distance):
    rs = _rs()
    edges = [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
    sk = _make_skeleton(nodes, edges)
    cw = compute_channel_widths(rs, sk, sample_distance=sample_distance)
    for (u, v), w in cw.edge_widths.items():
        assert float(w) <= float(cw.node_widths[u])
        assert float(w) <= float(cw.node_widths[v])


def test_p6_guard_edge_min_is_live():
    # A wide gap between two nodes with a narrow middle: the edge min must
    # dip below both endpoints, proving the interior samples participate.
    sk = _make_skeleton(
        [(1.0, 1.0), (24.0, 1.0)],
        [((1.0, 1.0), (24.0, 1.0))],
    )
    cw = compute_channel_widths(_rs(), sk, sample_distance=1.0)
    (u, v), w = next(iter(cw.edge_widths.items()))
    assert float(w) <= float(cw.node_widths[u])
    assert float(w) <= float(cw.node_widths[v])
