"""Metamorphic relations for the Phase E batch E4 channel-operations
orchestration (temper-orchestration ``channel_mapping`` module, exercised
through the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E4. G5: >= 3
invariant relations per module family, each with a discriminating companion
that asserts the relation does not hold vacuously.

- MR1  two-pad expansion idempotence: expanding an already-expanded 2-pad
       path is a no-op — ``expand(expand(path, pads), pads) ==
       expand(path, pads)`` (a corrected path is already correct, so the
       zero-cost identity mapping is chosen). Companion: a wrong-endpoint
       path is genuinely changed by the first expansion.
- MR2  pad-order endpoint closure + interior preservation: for a 2-pad net,
       ``expand(path, [b, a])`` and ``expand(path, [a, b])`` both land on
       the two true pads as endpoints and never touch the interior waypoints
       (the identity/swap decision only ever reorders the endpoint PAIR).
       Companion: an exact-displacement tie where each arm prefers its own
       identity pairing, so the two arms genuinely pick DIFFERENT endpoint
       orders (the tie-break is live, not vacuous).
- MR3  all-pad-tree waypoint permutation invariance: permuting the ``pads``
       list leaves the output waypoints unchanged (the append order comes
       from the set-based ``_nearest_terminal_order`` + ``min(missing)``).
       Companion: unsorted pads where ``sorted != input`` and the waypoints
       equal the deterministic order. (The ``total_length`` field is NOT
       invariant — it sums the pad-INPUT-order ``missing`` list; that wart is
       pinned in the differential, not here.)
- MR4  channel-width edge min is an upper bound: for every edge,
       ``edge_widths[(u, v)] <= min(node_widths[u], node_widths[v])`` (the
       edge min includes both endpoints). Companion: a wide gap with a narrow
       middle where the edge width dips strictly below both endpoints.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings
from shapely.geometry import box

from temper_placer.router_v6.channel_mapping import (
    ChannelPath,
    expand_channel_path_terminals,
)
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton, SkeletonGraph
from temper_placer.router_v6.channel_widths import compute_channel_widths
from temper_placer.router_v6.routing_space import RoutingSpace

_SETTINGS = settings(max_examples=60, deadline=8000, suppress_health_check=[])

_POINT = st.tuples(
    st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False),
)


def _path(waypoints):
    return ChannelPath(
        net_name="NET",
        channel_sequence=[f"c{i}" for i in range(len(waypoints))],
        waypoints=list(waypoints),
        total_length=1.0,
    )


# ---------------------------------------------------------------------------
# MR1 — two-pad expansion idempotence
# ---------------------------------------------------------------------------


@given(_POINT, _POINT, st.tuples(_POINT, _POINT))
@_SETTINGS
def test_mr1_two_pad_expansion_idempotent(first, last, pad_pair):
    path = _path([first, last])
    pads = list(pad_pair)
    once = expand_channel_path_terminals(path, pads)
    twice = expand_channel_path_terminals(once, pads)
    assert once.waypoints == twice.waypoints
    assert once.total_length == twice.total_length


def test_mr1_companion_correction_is_live():
    path = _path([(0.0, 0.0), (99.0, 99.0)])
    pads = [(0.0, 0.0), (10.0, 0.0)]
    once = expand_channel_path_terminals(path, pads)
    assert once.waypoints != path.waypoints  # the first expansion really corrects
    assert once.waypoints[0] == (0.0, 0.0)
    assert once.waypoints[-1] == (10.0, 0.0)
    # and the second is an identity
    twice = expand_channel_path_terminals(once, pads)
    assert once.waypoints == twice.waypoints


# ---------------------------------------------------------------------------
# MR2 — pad-order mirror symmetry
# ---------------------------------------------------------------------------


@given(_POINT, _POINT, _POINT, _POINT)
@_SETTINGS
def test_mr2_pad_swap_endpoint_closure(first, last, a, b):
    path = _path([first, last])
    ab = expand_channel_path_terminals(path, [a, b])
    ba = expand_channel_path_terminals(path, [b, a])
    # interiors are never touched by either arm
    assert ab.waypoints[1:-1] == ba.waypoints[1:-1]
    assert ab.waypoints[1:-1] == list(path.waypoints[1:-1])
    # both arms land on exactly the two true pads as endpoints
    assert {ab.waypoints[0], ab.waypoints[-1]} == {a, b}
    assert {ba.waypoints[0], ba.waypoints[-1]} == {a, b}


def test_mr2_companion_tie_break_is_live():
    path = _path([(0.0, 0.0), (4.0, 0.0)])
    a = (2.0, -1.0)
    b = (2.0, 1.0)

    def d(p, q):
        return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5

    # exact displacement tie: dist(first,a)+dist(last,b) == dist(first,b)+dist(last,a)
    ident = d((0.0, 0.0), a) + d((4.0, 0.0), b)
    swap = d((0.0, 0.0), b) + d((4.0, 0.0), a)
    assert ident == swap
    ab = expand_channel_path_terminals(path, [a, b])
    ba = expand_channel_path_terminals(path, [b, a])
    # the tie-break is identity-preferring, so each arm picks its OWN
    # identity pairing — the endpoint orders genuinely differ, and mirror.
    assert ab.waypoints[0] == a and ab.waypoints[-1] == b
    assert ba.waypoints[0] == b and ba.waypoints[-1] == a
    assert ab.waypoints[0] == ba.waypoints[-1]


# ---------------------------------------------------------------------------
# MR3 — all-pad-tree waypoint permutation invariance
# ---------------------------------------------------------------------------


@given(_POINT, st.lists(_POINT, min_size=3, max_size=6))
@_SETTINGS
def test_mr3_all_pad_tree_waypoints_permutation_invariant(first, pads):
    path = _path([first])
    permuted = pads[:]
    import random

    rng = random.Random(42)
    rng.shuffle(permuted)
    a = expand_channel_path_terminals(path, pads, enable_all_pad_tree=True)
    b = expand_channel_path_terminals(path, permuted, enable_all_pad_tree=True)
    assert a.waypoints == b.waypoints


def test_mr3_companion_deterministic_append_order():
    path = _path([(0.0, 0.0)])
    pads = [(3.0, 3.0), (1.0, 1.0), (2.0, 2.0)]
    out = expand_channel_path_terminals(path, pads, enable_all_pad_tree=True)
    # Greedy Manhattan-nearest ordering from (0,0): (1,1) then (2,2) then (3,3).
    assert out.waypoints == [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
    # and a different input order gives the same appended sequence
    out2 = expand_channel_path_terminals(
        path, list(reversed(pads)), enable_all_pad_tree=True
    )
    assert out2.waypoints == out.waypoints


# ---------------------------------------------------------------------------
# MR4 — channel-width edge min is an upper bound
# ---------------------------------------------------------------------------


def _rs():
    return RoutingSpace(
        layer_name="F.Cu",
        available_area=box(0, 0, 30, 10),
        total_area=300.0,
        obstacle_area=0.0,
        routing_area=300.0,
    )


@given(
    st.lists(
        st.tuples(
            st.floats(min_value=0.5, max_value=29.5, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0.5, max_value=9.5, allow_nan=False, allow_infinity=False),
        ),
        min_size=2,
        max_size=7,
    )
)
@_SETTINGS
def test_mr4_edge_width_bounded_by_endpoints(nodes):
    g = SkeletonGraph()
    for n in nodes:
        g.add_node(n, pos=n)
    for i in range(len(nodes) - 1):
        g.add_edge(nodes[i], nodes[i + 1], weight=1.0)
    sk = ChannelSkeleton(g, "F.Cu", 0.0)
    cw = compute_channel_widths(_rs(), sk, sample_distance=1.0)
    for (u, v), w in cw.edge_widths.items():
        assert float(w) <= float(cw.node_widths[u])
        assert float(w) <= float(cw.node_widths[v])


def test_mr4_companion_edge_dips_below_endpoints():
    # A 28 mm edge through a polygon whose middle is pinched by a notch: the
    # midpoint samples land on the notch boundary (mask False -> width 0),
    # so the edge min must dip strictly below both endpoint widths — proving
    # the interior samples participate in the min.
    from shapely.geometry import Polygon

    poly = Polygon(
        [(0, 0), (30, 0), (30, 10), (20, 10), (20, 5), (10, 5), (10, 10), (0, 10)]
    )
    rs = RoutingSpace(
        layer_name="F.Cu",
        available_area=poly,
        total_area=poly.area,
        obstacle_area=0.0,
        routing_area=poly.area,
    )
    g = SkeletonGraph()
    for n in [(1.0, 5.0), (29.0, 5.0)]:
        g.add_node(n, pos=n)
    g.add_edge((1.0, 5.0), (29.0, 5.0), weight=1.0)
    sk = ChannelSkeleton(g, "F.Cu", 0.0)
    cw = compute_channel_widths(rs, sk, sample_distance=1.0)
    (u, v), w = next(iter(cw.edge_widths.items()))
    assert float(w) < float(cw.node_widths[u])
    assert float(w) < float(cw.node_widths[v])
