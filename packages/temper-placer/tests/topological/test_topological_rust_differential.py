"""R1a bit-identical differential: Rust-backed ``temper_placer.topological``
vs the verbatim pinned Python oracles (``_*_py_oracle.py``, origin/main
f57b52d51).

Every assertion compares through :func:`tests.topological._diffhelp.key`,
which renders floats via ``float.hex()`` and tags every non-float leaf with
its concrete ``type``. No tolerance is used anywhere in this file.

Three hazards this suite is specifically built to catch, all established
empirically before the port (see the crate VERIFICATION.md):

1. **CPython ``sum()`` is Neumaier-compensated** (3.12+). ``total_area`` in
   ``place_components_in_zone`` is a ``sum()`` over a generator, so a naive
   Rust accumulator diverges -- measurably from n=8 upward. The
   ``test_place_in_zone_total_area_*`` cases drive that boundary directly.
2. **Force accumulation is naive ``+=``** on a float64 numpy array, so the
   result depends on edge order. The Rust side consumes the caller's edge
   order rather than imposing one; ``test_force_*_edge_order_*`` pins that.
3. **Iteration order from ``set``/``dict``** is incidental and, for the zone
   solver, outcome-changing. Those cases feed an explicit candidate order to
   both sides.
"""

from __future__ import annotations

import math

import pytest

# The differential is only meaningful if the live package really is
# Rust-backed. Without this import it would compare Python against Python and
# pass vacuously, which is the exact failure mode the R1a gate exists to
# prevent -- so the extension is imported directly and collection fails loudly
# whenever the delegation is absent or has regressed.
import temper_placement_topology as _rust

import tests.topological._force_refinement_py_oracle as fr_oracle
import tests.topological._graph_py_oracle as graph_oracle
import tests.topological._initial_placement_py_oracle as ip_oracle
import tests.topological._propagation_py_oracle as prop_oracle
import tests.topological._zone_solver_py_oracle as zs_oracle
from temper_placer.core.board import Zone
from temper_placer.topological import (
    ConstraintPropagator,
    TopologicalGraph,
    ZoneSolver,
    apply_force_refinement,
    compute_adjacency_force,
    compute_boundary_force,
    compute_separation_force,
    identify_clusters,
    place_cluster,
    place_components_in_zone,
)
from tests.topological._diffhelp import assert_identical


def test_live_package_is_rust_backed():
    """Anti-vacuity guard for the whole file: every migrated entry point must
    resolve through the Rust extension. If any of these regressed to a pure
    Python body, the assertions below would still pass while measuring
    nothing."""
    import temper_placer.topological.force_refinement as fr
    import temper_placer.topological.graph as gr
    import temper_placer.topological.initial_placement as ip
    import temper_placer.topological.propagation as pp
    import temper_placer.topological.zone_solver as zs

    for mod in (fr, gr, ip, pp, zs):
        assert getattr(mod, "_rust", None) is _rust, (
            f"{mod.__name__} does not delegate to temper_placement_topology; "
            "the differential would be vacuous"
        )
    # and the extension really exposes the kernels, not just a stub module
    for fn in (
        "adjacency_cluster",
        "separation_conflicts",
        "propagate_bounds",
        "force_refine",
        "identify_clusters",
        "place_components_in_zone",
        "place_cluster",
        "zone_backtrack",
    ):
        assert callable(getattr(_rust, fn, None)), f"missing Rust kernel {fn}"


# ---------------------------------------------------------------------------
# graph construction helpers -- build the live and oracle graphs identically
# ---------------------------------------------------------------------------


def _build(cls, components, adjacencies, separations):
    g = cls()
    for ref in components:
        g.add_component(ref)
    for a, b, d, cid in adjacencies:
        g.add_adjacency(a, b, d, cid)
    for a, b, d, cid in separations:
        g.add_separation(a, b, d, cid)
    return g


def _pair(components, adjacencies=(), separations=()):
    """Return (live_graph, oracle_graph) built from the same spec."""
    return (
        _build(TopologicalGraph, components, adjacencies, separations),
        _build(graph_oracle.TopologicalGraph, components, adjacencies, separations),
    )


# A spread of graph shapes: empty, singleton, chain, star, cycle, disjoint,
# self-conflicting, and a dense clique.
GRAPH_CASES = {
    "singleton": (["A"], [], []),
    "pair_adjacent": (["A", "B"], [("A", "B", 5.0, "c1")], []),
    "chain3": (
        ["A", "B", "C"],
        [("A", "B", 5.0, "c1"), ("B", "C", 3.0, "c2")],
        [],
    ),
    "star4": (
        ["H", "A", "B", "C"],
        [("H", "A", 4.0, "c1"), ("H", "B", 6.0, "c2"), ("H", "C", 2.5, "c3")],
        [],
    ),
    "cycle4": (
        ["A", "B", "C", "D"],
        [
            ("A", "B", 5.0, "c1"),
            ("B", "C", 5.0, "c2"),
            ("C", "D", 5.0, "c3"),
            ("D", "A", 5.0, "c4"),
        ],
        [],
    ),
    "disjoint": (
        ["A", "B", "C", "D"],
        [("A", "B", 5.0, "c1"), ("C", "D", 7.0, "c2")],
        [],
    ),
    "conflict": (
        ["A", "B"],
        [("A", "B", 5.0, "c1")],
        [("A", "B", 10.0, "s1")],
    ),
    "conflict_multi": (
        ["A", "B", "C"],
        [("A", "B", 1.0, "c1"), ("B", "C", 2.0, "c2")],
        [("A", "B", 9.0, "s1"), ("B", "C", 8.0, "s2")],
    ),
    "sep_only": (["A", "B", "C"], [], [("A", "B", 12.0, "s1"), ("B", "C", 4.0, "s2")]),
    # Exactly-equal bounds: the conflict test is strict `<`, so an adjacency
    # ceiling equal to the separation floor is satisfiable and must NOT be
    # reported. Pins that boundary deterministically -- a `<=` would add a
    # spurious conflict here. (Mutation M15.)
    "conflict_equal_bounds": (
        ["A", "B"],
        [("A", "B", 7.0, "c1")],
        [("A", "B", 7.0, "s1")],
    ),
    # ...and one ulp apart on either side of that boundary.
    "conflict_one_ulp_under": (
        ["A", "B"],
        [("A", "B", 6.999999999999999, "c1")],
        [("A", "B", 7.0, "s1")],
    ),
    "conflict_one_ulp_over": (
        ["A", "B"],
        [("A", "B", 7.000000000000001, "c1")],
        [("A", "B", 7.0, "s1")],
    ),
    "clique4": (
        ["A", "B", "C", "D"],
        [
            ("A", "B", 3.0, "c1"),
            ("A", "C", 4.0, "c2"),
            ("A", "D", 5.0, "c3"),
            ("B", "C", 6.0, "c4"),
            ("B", "D", 7.0, "c5"),
            ("C", "D", 8.0, "c6"),
        ],
        [],
    ),
    "subnormal_distance": (
        ["A", "B"],
        [("A", "B", 5e-324, "c1")],
        [("A", "B", 1e-320, "s1")],
    ),
    "huge_distance": (["A", "B"], [("A", "B", 1e308, "c1")], []),
}


# ---------------------------------------------------------------------------
# graph.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GRAPH_CASES))
def test_adjacency_cluster_identical(name):
    comps, adj, sep = GRAPH_CASES[name]
    live, orc = _pair(comps, adj, sep)
    for seed in comps:
        assert_identical(
            live.get_adjacency_cluster(seed),
            orc.get_adjacency_cluster(seed),
            f"get_adjacency_cluster({seed!r}) [{name}]",
        )


@pytest.mark.parametrize("name", sorted(GRAPH_CASES))
def test_separation_conflicts_identical(name):
    comps, adj, sep = GRAPH_CASES[name]
    live, orc = _pair(comps, adj, sep)
    assert_identical(
        live.find_separation_conflicts(),
        orc.find_separation_conflicts(),
        f"find_separation_conflicts [{name}]",
    )


@pytest.mark.parametrize("name", sorted(GRAPH_CASES))
@pytest.mark.parametrize("etype", [None, "adjacent", "separated", "member_of"])
def test_get_neighbors_identical(name, etype):
    comps, adj, sep = GRAPH_CASES[name]
    live, orc = _pair(comps, adj, sep)
    for node in comps:
        assert_identical(
            live.get_neighbors(node, edge_type=etype),
            orc.get_neighbors(node, edge_type=etype),
            f"get_neighbors({node!r}, {etype!r}) [{name}]",
        )


def test_group_membership_identical():
    live, orc = _pair(["A", "B", "C"], [], [])
    live.add_group("grp", ["A", "B"])
    orc.add_group("grp", ["A", "B"])
    for node in ("A", "B", "C", "grp"):
        assert_identical(
            live.get_neighbors(node), orc.get_neighbors(node), f"group neighbors {node}"
        )
    assert_identical(
        live.find_separation_conflicts(),
        orc.find_separation_conflicts(),
        "group conflicts",
    )


def test_separation_conflict_ordering_follows_edge_insertion():
    """The conflict list order is the graph's edge order, which is incidental
    (insertion-derived). Both sides must report the *same* incidental order,
    not a sorted one -- sorting here would be an uncaught behaviour change."""
    spec = ["B", "A", "C"]
    adj = [("B", "A", 1.0, "c1"), ("C", "A", 2.0, "c2"), ("B", "C", 3.0, "c3")]
    sep = [("B", "A", 9.0, "s1"), ("C", "A", 9.0, "s2"), ("B", "C", 9.0, "s3")]
    live, orc = _pair(spec, adj, sep)
    got, want = live.find_separation_conflicts(), orc.find_separation_conflicts()
    assert_identical(got, want, "conflict ordering")
    assert len(want) > 1, "case must produce multiple conflicts to constrain order"


# ---------------------------------------------------------------------------
# propagation.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GRAPH_CASES))
@pytest.mark.parametrize("max_iterations", [0, 1, 2, 100])
def test_propagation_identical(name, max_iterations):
    comps, adj, sep = GRAPH_CASES[name]
    live, orc = _pair(comps, adj, sep)
    p_live = ConstraintPropagator(live)
    p_orc = prop_oracle.ConstraintPropagator(orc)

    assert_identical(
        p_live.propagate(max_iterations=max_iterations),
        p_orc.propagate(max_iterations=max_iterations),
        f"propagate feasible [{name}/{max_iterations}]",
    )
    for a in comps:
        for b in comps:
            ba, bb = p_live.get_bound(a, b), p_orc.get_bound(a, b)
            assert_identical(
                (ba.min_distance, ba.max_distance),
                (bb.min_distance, bb.max_distance),
                f"bound({a},{b}) [{name}/{max_iterations}]",
            )
    assert_identical(
        [(a, b, x.min_distance, x.max_distance) for a, b, x in p_live.get_infeasible_pairs()],
        [(a, b, x.min_distance, x.max_distance) for a, b, x in p_orc.get_infeasible_pairs()],
        f"infeasible pairs [{name}/{max_iterations}]",
    )


def test_distance_bound_tighten_identical():
    values = [0.0, -0.0, 1e-320, 5e-324, 0.1, 1.0, 1e308, math.inf, -math.inf]
    for v in values:
        live = ConstraintPropagator.__module__ and None  # sanity: import worked
        del live
        b_live = _DistanceBoundLive()
        b_orc = prop_oracle.DistanceBound()
        b_live.tighten_max(v)
        b_orc.tighten_max(v)
        b_live.tighten_min(v)
        b_orc.tighten_min(v)
        assert_identical(
            (b_live.min_distance, b_live.max_distance, b_live.is_feasible()),
            (b_orc.min_distance, b_orc.max_distance, b_orc.is_feasible()),
            f"DistanceBound tighten({v!r})",
        )


def _DistanceBoundLive():
    from temper_placer.topological import DistanceBound

    return DistanceBound()


# ---------------------------------------------------------------------------
# force_refinement.py -- the float-accumulation surface
# ---------------------------------------------------------------------------

FORCE_POSITIONS = [
    ("coincident", {"A": (1.0, 1.0), "B": (1.0, 1.0)}),
    ("near_coincident", {"A": (0.0, 0.0), "B": (1e-7, 0.0)}),
    ("at_epsilon", {"A": (0.0, 0.0), "B": (1e-6, 0.0)}),
    ("simple", {"A": (0.0, 0.0), "B": (10.0, 0.0)}),
    ("diagonal", {"A": (-3.25, 7.5), "B": (11.125, -2.75)}),
    ("negative", {"A": (-40.0, -40.0), "B": (-10.0, -25.0)}),
    ("irrational", {"A": (0.1, 0.2), "B": (0.3, 0.7)}),
]


@pytest.mark.parametrize("posname,positions", FORCE_POSITIONS, ids=lambda v: v if isinstance(v, str) else "")
@pytest.mark.parametrize("target", [0.0, 0.5, 5.0, 10.0, 1e6])
def test_compute_adjacency_force_identical(posname, positions, target):
    import numpy as np

    pa = np.array(positions["A"])
    pb = np.array(positions["B"])
    assert_identical(
        compute_adjacency_force(pa, pb, target),
        fr_oracle.compute_adjacency_force(pa.copy(), pb.copy(), target),
        f"compute_adjacency_force[{posname}/{target}]",
    )


@pytest.mark.parametrize("posname,positions", FORCE_POSITIONS, ids=lambda v: v if isinstance(v, str) else "")
@pytest.mark.parametrize("min_dist", [0.0, 0.5, 5.0, 10.0, 1e6])
def test_compute_separation_force_identical(posname, positions, min_dist):
    import numpy as np

    pa = np.array(positions["A"])
    pb = np.array(positions["B"])
    assert_identical(
        compute_separation_force(pa, pb, min_dist),
        fr_oracle.compute_separation_force(pa.copy(), pb.copy(), min_dist),
        f"compute_separation_force[{posname}/{min_dist}]",
    )


@pytest.mark.parametrize(
    "pos",
    [
        (0.0, 0.0),
        (-5.0, -5.0),
        (50.0, 50.0),
        (10.0, -3.0),
        (-0.0, 0.0),
        (1e-320, 1e-320),
    ],
)
def test_compute_boundary_force_identical(pos):
    import numpy as np

    zone = Zone(name="z", bounds=(0.0, 0.0, 20.0, 20.0))
    assert_identical(
        compute_boundary_force(np.array(pos), zone),
        fr_oracle.compute_boundary_force(np.array(pos), zone),
        f"compute_boundary_force[{pos}]",
    )


FORCE_GRAPHS = {
    "adjacent_pair": (["A", "B"], [("A", "B", 5.0, "c1")], []),
    "separated_pair": (["A", "B"], [], [("A", "B", 15.0, "s1")], ),
    "mixed": (
        ["A", "B", "C"],
        [("A", "B", 5.0, "c1"), ("B", "C", 4.0, "c2")],
        [("A", "C", 20.0, "s1")],
    ),
    "clique4": GRAPH_CASES["clique4"],
    "disjoint": GRAPH_CASES["disjoint"],
}


@pytest.mark.parametrize("gname", sorted(FORCE_GRAPHS))
@pytest.mark.parametrize("iterations", [0, 1, 2, 8, 17, 100])
@pytest.mark.parametrize("lr", [0.0, 0.1, 1.0])
def test_apply_force_refinement_identical(gname, iterations, lr):
    spec = FORCE_GRAPHS[gname]
    comps, adj, sep = spec[0], spec[1], spec[2]
    live, orc = _pair(comps, adj, sep)

    positions = {ref: (float(i) * 3.25 - 4.0, float(i) * -1.75 + 2.5) for i, ref in enumerate(comps)}
    zones = {"Z": Zone(name="Z", bounds=(-50.0, -50.0, 50.0, 50.0))}
    assignments = dict.fromkeys(comps, "Z")

    assert_identical(
        apply_force_refinement(
            positions=dict(positions), graph=live, zones=zones,
            zone_assignments=dict(assignments), iterations=iterations, learning_rate=lr,
        ),
        fr_oracle.apply_force_refinement(
            positions=dict(positions), graph=orc, zones=zones,
            zone_assignments=dict(assignments), iterations=iterations, learning_rate=lr,
        ),
        f"apply_force_refinement[{gname}/{iterations}/{lr}]",
    )


def test_apply_force_refinement_unzoned_default_bounds_identical():
    """Components with no matching zone fall back to the [-1000,1000] box."""
    live, orc = _pair(["A", "B"], [("A", "B", 5.0, "c1")], [])
    positions = {"A": (-2000.0, 3000.0), "B": (1500.0, -1200.0)}
    assert_identical(
        apply_force_refinement(dict(positions), live, {}, {}, iterations=25, learning_rate=0.1),
        fr_oracle.apply_force_refinement(dict(positions), orc, {}, {}, iterations=25, learning_rate=0.1),
        "force refinement with unmatched zones",
    )


def test_apply_force_refinement_empty_identical():
    live, orc = _pair([], [], [])
    assert_identical(
        apply_force_refinement({}, live, {}, {}),
        fr_oracle.apply_force_refinement({}, orc, {}, {}),
        "force refinement empty",
    )


def test_force_accumulation_order_is_preserved():
    """Naive ``+=`` accumulation is not associative, so a component touched by
    many edges has an order-dependent force. Rust must consume the caller's
    edge order, not a sorted one."""
    comps = ["H", "A", "B", "C", "D", "E", "F", "G", "I"]
    adj = [("H", n, 0.1 * (k + 1), f"c{k}") for k, n in enumerate(comps[1:])]
    live, orc = _pair(comps, adj, [])
    positions = {ref: (0.1 * i, 0.3 * i) for i, ref in enumerate(comps)}
    zones = {"Z": Zone(name="Z", bounds=(-1e3, -1e3, 1e3, 1e3))}
    assignments = dict.fromkeys(comps, "Z")
    assert_identical(
        apply_force_refinement(dict(positions), live, zones, dict(assignments), 40, 0.1),
        fr_oracle.apply_force_refinement(dict(positions), orc, zones, dict(assignments), 40, 0.1),
        "hub force accumulation order",
    )


# ---------------------------------------------------------------------------
# initial_placement.py
# ---------------------------------------------------------------------------

ZONE = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 80.0))


@pytest.mark.parametrize("n", [1, 2, 3, 5, 7, 8, 9, 11, 16])
def test_place_components_in_zone_identical(n):
    comps = [f"U{i}" for i in range(n)]
    sizes = {ref: (2.0 + 0.25 * i, 1.5 + 0.125 * i) for i, ref in enumerate(comps)}
    assert_identical(
        place_components_in_zone(ZONE, comps, sizes),
        ip_oracle.place_components_in_zone(ZONE, comps, sizes),
        f"place_components_in_zone[n={n}]",
    )


def test_place_components_in_zone_empty_identical():
    assert_identical(
        place_components_in_zone(ZONE, [], {}),
        ip_oracle.place_components_in_zone(ZONE, [], {}),
        "place_components_in_zone empty",
    )


@pytest.mark.parametrize("n", [8, 9, 12, 20, 33])
def test_place_in_zone_total_area_neumaier_boundary(n):
    """``total_area`` is a CPython ``sum()`` -- Neumaier-compensated since
    3.12 -- and diverges from naive accumulation from n=8 up. Sizes are chosen
    so the running total is not exactly representable."""
    comps = [f"U{i}" for i in range(n)]
    sizes = dict.fromkeys(comps, (0.1, 0.1))
    assert_identical(
        place_components_in_zone(ZONE, comps, sizes),
        ip_oracle.place_components_in_zone(ZONE, comps, sizes),
        f"neumaier total_area[n={n}]",
    )


def test_place_in_zone_neumaier_and_naive_straddle_the_packing_threshold():
    """The decisive Neumaier case: compensated and naive sums land on
    *opposite sides* of `total_area > zone_area * 0.8`.

    `total_area` is observable only through that branch -- the positions never
    read it -- so a differential that merely computes a slightly different sum
    proves nothing. Here 8 components of area 0.1 sum to `0x1.999999999999ap-1`
    compensated but `0x1.9999999999999p-1` naively, and the zone area is
    chosen so the threshold is *exactly* the naive value. The correct
    implementation raises PlacementError; a naive accumulator returns
    positions instead. (Mutation M1.)
    """
    zw = 0.9999999999999999  # one ulp below 1.0
    zone = Zone(name="Z", bounds=(0.0, 0.0, zw, 1.0))
    comps = [f"U{i}" for i in range(8)]
    sizes = dict.fromkeys(comps, (0.5, 0.2))  # 0.5*0.2 == 0.1 exactly

    got = _capture(lambda: place_components_in_zone(zone, comps, sizes))
    want = _capture(lambda: ip_oracle.place_components_in_zone(zone, comps, sizes))
    assert want[0] == "raised", "fixture must land on the raising side of the threshold"
    assert_identical(got, want, "Neumaier/naive threshold straddle")


def test_place_in_zone_packing_limit_is_exactly_eighty_percent():
    """Pin the 80% constant itself: this fill lands between 0.80 and 0.81 of
    the zone area, so the correct implementation raises while any loosened
    limit would not. (Mutation M12.)"""
    zone = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))
    comps = [f"U{i}" for i in range(100)]
    sizes = dict.fromkeys(comps, (10.0, 8.05))  # total 8050 of 10000

    got = _capture(lambda: place_components_in_zone(zone, comps, sizes))
    want = _capture(lambda: ip_oracle.place_components_in_zone(zone, comps, sizes))
    assert want[0] == "raised", "fixture must exceed the 80% limit"
    assert_identical(got, want, "80% packing limit")


def test_place_cluster_clamp_order_with_an_oversized_component():
    """`place_cluster` performs no size check, so a component wider than the
    zone drives the clamp into `lo > hi`, where `max(lo, min(x, hi))` and
    `min(hi, max(x, lo))` disagree -- the former pins to `lo`, the latter to
    `hi`. Pins the clamp nesting order. (Mutation M13.)"""
    zone = Zone(name="Z", bounds=(0.0, 0.0, 10.0, 10.0))
    live, orc = _pair(["A", "B"], [("A", "B", 4.0, "c1")], [])
    sizes = {"A": (40.0, 40.0), "B": (40.0, 40.0)}  # far wider than the zone

    assert_identical(
        place_cluster({"A", "B"}, zone, live, sizes, 0, 1),
        ip_oracle.place_cluster({"A", "B"}, zone, orc, sizes, 0, 1),
        "clamp order under an inverted clamp window",
    )


def test_place_cluster_with_nan_component_sizes():
    """A NaN size reaches the `max`/`min` folds, where CPython's semantics
    (NaN propagates from the left operand, is discarded from the right) differ
    from `f64::max`/`f64::min`, which always discard it. (Mutation M2.)"""
    zone = Zone(name="Z", bounds=(0.0, 0.0, 50.0, 50.0))
    live, orc = _pair(["A", "B", "C"], [("A", "B", 4.0, "c1")], [])
    sizes = {"A": (float("nan"), 2.0), "B": (3.0, float("nan")), "C": (2.0, 2.0)}

    assert_identical(
        place_cluster({"A", "B", "C"}, zone, live, sizes, 0, 1),
        ip_oracle.place_cluster({"A", "B", "C"}, zone, orc, sizes, 0, 1),
        "NaN component sizes through the min/max folds",
    )


def test_place_components_in_zone_with_nan_component_sizes():
    """Same NaN fold hazard on the zone entry point."""
    zone = Zone(name="Z", bounds=(0.0, 0.0, 50.0, 50.0))
    comps = ["A", "B", "C"]
    sizes = {"A": (float("nan"), 2.0), "B": (3.0, float("nan")), "C": (2.0, 2.0)}
    assert_identical(
        _capture(lambda: place_components_in_zone(zone, comps, sizes)),
        _capture(lambda: ip_oracle.place_components_in_zone(zone, comps, sizes)),
        "NaN sizes in place_components_in_zone",
    )


def test_propagation_with_nan_distances():
    """NaN constraint distances through `tighten_min`/`tighten_max`."""
    nan = float("nan")
    live, orc = _pair(
        ["A", "B", "C"],
        [("A", "B", nan, "c1"), ("B", "C", 3.0, "c2")],
        [("A", "C", nan, "s1")],
    )
    p_live, p_orc = ConstraintPropagator(live), prop_oracle.ConstraintPropagator(orc)
    assert_identical(p_live.propagate(), p_orc.propagate(), "NaN propagate verdict")
    for a in ("A", "B", "C"):
        for b in ("A", "B", "C"):
            ba, bb = p_live.get_bound(a, b), p_orc.get_bound(a, b)
            assert_identical(
                (ba.min_distance, ba.max_distance),
                (bb.min_distance, bb.max_distance),
                f"NaN bound({a},{b})",
            )


def test_place_in_zone_total_area_catastrophic_cancellation():
    """A magnitude spread that a naive accumulator loses entirely: the
    compensated sum keeps the small terms, a naive one drops them."""
    comps = ["BIG", "A", "B", "C", "D", "E", "F", "G", "NEG"]
    sizes = {
        "BIG": (1e150, 1e150),
        "NEG": (1e150, -1e150),
        **dict.fromkeys(["A", "B", "C", "D", "E", "F", "G"], (0.1, 0.1)),
    }
    big_zone = Zone(name="B", bounds=(0.0, 0.0, 1e200, 1e200))
    got = _capture(lambda: place_components_in_zone(big_zone, comps, sizes))
    want = _capture(lambda: ip_oracle.place_components_in_zone(big_zone, comps, sizes))
    assert_identical(got, want, "catastrophic cancellation in total_area")


def _capture(fn):
    """Run ``fn``, returning either its value or a (type, message) pair, so a
    raised PlacementError is itself part of the compared behaviour."""
    try:
        return ("ok", fn())
    except Exception as exc:  # noqa: BLE001 -- error identity is under test
        return ("raised", type(exc).__name__, str(exc))


@pytest.mark.parametrize(
    "bounds,n,size",
    [
        ((0.0, 0.0, 5.0, 5.0), 1, (10.0, 1.0)),   # too wide
        ((0.0, 0.0, 5.0, 5.0), 1, (1.0, 10.0)),   # too tall
        ((0.0, 0.0, 10.0, 10.0), 6, (4.0, 4.0)),  # over the 80% packing limit
        ((0.0, 0.0, 10.0, 10.0), 2, (3.0, 3.0)),  # fits
    ],
)
def test_place_components_in_zone_errors_identical(bounds, n, size):
    zone = Zone(name="Z", bounds=bounds)
    comps = [f"U{i}" for i in range(n)]
    sizes = dict.fromkeys(comps, size)
    assert_identical(
        _capture(lambda: place_components_in_zone(zone, comps, sizes)),
        _capture(lambda: ip_oracle.place_components_in_zone(zone, comps, sizes)),
        f"placement error parity[{bounds}/{n}/{size}]",
    )


@pytest.mark.parametrize("name", sorted(GRAPH_CASES))
def test_identify_clusters_identical(name):
    comps, adj, sep = GRAPH_CASES[name]
    live, orc = _pair(comps, adj, sep)
    assert_identical(
        identify_clusters(live, list(comps)),
        ip_oracle.identify_clusters(orc, list(comps)),
        f"identify_clusters[{name}]",
    )


def test_identify_clusters_empty_identical():
    live, orc = _pair(["A"], [], [])
    assert_identical(
        identify_clusters(live, []), ip_oracle.identify_clusters(orc, []), "identify_clusters empty"
    )


@pytest.mark.parametrize("name", ["pair_adjacent", "chain3", "star4", "clique4", "cycle4"])
@pytest.mark.parametrize("total_clusters", [1, 2, 3])
def test_place_cluster_identical(name, total_clusters):
    comps, adj, sep = GRAPH_CASES[name]
    live, orc = _pair(comps, adj, sep)
    sizes = {ref: (2.0 + 0.5 * i, 1.0 + 0.25 * i) for i, ref in enumerate(comps)}
    for idx in range(total_clusters):
        assert_identical(
            place_cluster(set(comps), ZONE, live, sizes, idx, total_clusters),
            ip_oracle.place_cluster(set(comps), ZONE, orc, sizes, idx, total_clusters),
            f"place_cluster[{name}/{idx}/{total_clusters}]",
        )


def test_place_cluster_empty_identical():
    live, orc = _pair(["A"], [], [])
    assert_identical(
        place_cluster(set(), ZONE, live, {}, 0, 1),
        ip_oracle.place_cluster(set(), ZONE, orc, {}, 0, 1),
        "place_cluster empty",
    )


def test_place_cluster_default_adjacency_distance_identical():
    """No adjacency edge inside the cluster -> the 15.0 default is used."""
    live, orc = _pair(["A", "B", "C"], [], [])
    sizes = dict.fromkeys(["A", "B", "C"], (2.0, 2.0))
    assert_identical(
        place_cluster({"A", "B", "C"}, ZONE, live, sizes, 0, 1),
        ip_oracle.place_cluster({"A", "B", "C"}, ZONE, orc, sizes, 0, 1),
        "place_cluster default adjacency",
    )


# ---------------------------------------------------------------------------
# generate_initial_placement -- the composed pipeline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GRAPH_CASES))
@pytest.mark.parametrize("force_iterations", [0, 10, 100])
def test_generate_initial_placement_identical(name, force_iterations):
    from temper_placer.topological import generate_initial_placement

    comps, adj, sep = GRAPH_CASES[name]
    live, orc = _pair(comps, adj, sep)
    sizes = {ref: (2.0 + 0.5 * i, 1.5 + 0.25 * i) for i, ref in enumerate(comps)}
    zones = [Zone(name="Z", bounds=(0.0, 0.0, 100.0, 80.0))]

    def mk(mod):
        return mod.ZoneAssignment(
            assignments=dict.fromkeys(comps, "Z"), unassigned=[], conflicts=[]
        )

    got = _capture(
        lambda: generate_initial_placement(
            live, mk(_live_zs()), zones, sizes, None, force_iterations
        )
    )
    want = _capture(
        lambda: ip_oracle.generate_initial_placement(
            orc, mk(zs_oracle), zones, sizes, None, force_iterations
        )
    )
    got = _norm_placement(got)
    want = _norm_placement(want)
    assert_identical(got, want, f"generate_initial_placement[{name}/{force_iterations}]")


def _live_zs():
    import temper_placer.topological.zone_solver as m

    return m


def _norm_placement(captured):
    if captured[0] != "ok":
        return captured
    p = captured[1]
    return ("ok", p.positions, p.zone_assignments, p.clusters, p.rotation_hints, p.warnings)


def test_generate_initial_placement_conflicts_identical():
    from temper_placer.topological import generate_initial_placement

    live, orc = _pair(["A"], [], [])
    zones = [Zone(name="Z", bounds=(0.0, 0.0, 50.0, 50.0))]

    def mk(mod):
        return mod.ZoneAssignment(
            assignments={}, unassigned=[], conflicts=[("A", "ctx", "boom")]
        )

    assert_identical(
        _capture(lambda: generate_initial_placement(live, mk(_live_zs()), zones, {})),
        _capture(lambda: ip_oracle.generate_initial_placement(orc, mk(zs_oracle), zones, {})),
        "generate_initial_placement conflicts",
    )


def test_generate_initial_placement_unassigned_identical():
    from temper_placer.topological import generate_initial_placement

    live, orc = _pair(["A"], [], [])
    zones = [Zone(name="Z", bounds=(0.0, 0.0, 50.0, 50.0))]

    def mk(mod):
        return mod.ZoneAssignment(assignments={}, unassigned=["A"], conflicts=[])

    assert_identical(
        _capture(lambda: generate_initial_placement(live, mk(_live_zs()), zones, {})),
        _capture(lambda: ip_oracle.generate_initial_placement(orc, mk(zs_oracle), zones, {})),
        "generate_initial_placement unassigned",
    )


def test_generate_initial_placement_missing_zone_identical():
    from temper_placer.topological import generate_initial_placement

    live, orc = _pair(["A"], [], [])

    def mk(mod):
        return mod.ZoneAssignment(assignments={"A": "NOPE"}, unassigned=[], conflicts=[])

    assert_identical(
        _capture(lambda: generate_initial_placement(live, mk(_live_zs()), [], {"A": (1.0, 1.0)})),
        _capture(lambda: ip_oracle.generate_initial_placement(orc, mk(zs_oracle), [], {"A": (1.0, 1.0)})),
        "generate_initial_placement missing zone",
    )


def test_generate_initial_placement_board_pseudo_zone_identical():
    from temper_placer.topological import generate_initial_placement

    comps = ["A", "B"]
    live, orc = _pair(comps, [("A", "B", 6.0, "c1")], [])
    sizes = dict.fromkeys(comps, (3.0, 2.0))

    def mk(mod):
        return mod.ZoneAssignment(
            assignments=dict.fromkeys(comps, "_BOARD_"), unassigned=[], conflicts=[]
        )

    got = _norm_placement(
        _capture(
            lambda: generate_initial_placement(
                live, mk(_live_zs()), [], sizes, (0.0, 0.0, 60.0, 40.0), 30
            )
        )
    )
    want = _norm_placement(
        _capture(
            lambda: ip_oracle.generate_initial_placement(
                orc, mk(zs_oracle), [], sizes, (0.0, 0.0, 60.0, 40.0), 30
            )
        )
    )
    assert_identical(got, want, "generate_initial_placement _BOARD_")


# ---------------------------------------------------------------------------
# zone_solver.py -- outcome depends on an incidental set order
# ---------------------------------------------------------------------------


def _zone_list(names):
    return [Zone(name=n, bounds=(0.0, 0.0, 10.0, 10.0)) for n in names]


@pytest.mark.parametrize(
    "zone_names,components",
    [
        ([], []),
        (["Z1"], []),
        (["Z1"], ["A"]),
        (["Z1"], ["A", "B", "C"]),
        (["Z1", "Z2"], ["A"]),
        (["Z1", "Z2", "Z3"], ["A", "B"]),
    ],
)
def test_zone_solver_identical(zone_names, components):
    zones = _zone_list(zone_names)
    live = ZoneSolver(zones, [], list(components))
    orc = zs_oracle.ZoneSolver(_zone_list(zone_names), [], list(components))
    a, b = live.solve(), orc.solve()
    assert_identical(
        (a.assignments, a.unassigned, a.conflicts),
        (b.assignments, b.unassigned, b.conflicts),
        f"ZoneSolver.solve[{zone_names}/{components}]",
    )


def test_zone_solver_candidate_sets_identical():
    zones = _zone_list(["Z1", "Z2", "Z3"])
    live = ZoneSolver(zones, [], ["A", "B"])
    orc = zs_oracle.ZoneSolver(_zone_list(["Z1", "Z2", "Z3"]), [], ["A", "B"])
    assert_identical(live._candidates, orc._candidates, "ZoneSolver candidates")


def test_zone_solver_enclosing_constraint_identical():
    from temper_placer.pcl.constraints import ConstraintTier, EnclosingConstraint

    def mk():
        return [
            EnclosingConstraint(
                outer="Z2", inner=["A"], tier=ConstraintTier.HARD,
                because="pin A into zone Z2 for the differential", id="e1"
            )
        ]

    zones = _zone_list(["Z1", "Z2"])
    live = ZoneSolver(zones, mk(), ["A", "B"])
    orc = zs_oracle.ZoneSolver(_zone_list(["Z1", "Z2"]), mk(), ["A", "B"])
    a, b = live.solve(), orc.solve()
    assert_identical(a.assignments["A"], b.assignments["A"], "enclosing pins A to Z2")
    assert_identical(
        (a.unassigned, a.conflicts), (b.unassigned, b.conflicts), "enclosing residue"
    )


def test_zone_solver_missing_zone_conflict_identical():
    from temper_placer.pcl.constraints import ConstraintTier, EnclosingConstraint

    def mk():
        return [
            EnclosingConstraint(
                outer="GONE", inner=["A"], tier=ConstraintTier.HARD,
                because="reference a zone that does not exist", id="e1"
            )
        ]

    zones = _zone_list(["Z1"])
    live = ZoneSolver(zones, mk(), ["A", "B"])
    orc = zs_oracle.ZoneSolver(_zone_list(["Z1"]), mk(), ["A", "B"])
    a, b = live.solve(), orc.solve()
    assert_identical(
        (a.assignments, a.unassigned, a.conflicts),
        (b.assignments, b.unassigned, b.conflicts),
        "missing-zone conflict",
    )
