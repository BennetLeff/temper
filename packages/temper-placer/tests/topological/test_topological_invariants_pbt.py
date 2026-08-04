"""R1c property-based invariants for the Rust-backed topological package.

Five or more non-vacuous properties per migrated module:

* ``graph.py``            -- TestGraphInvariants (5)
* ``propagation.py``      -- TestPropagationInvariants (5)
* ``force_refinement.py`` -- TestForceInvariants (6)
* ``initial_placement.py``-- TestInitialPlacementInvariants (6)
* ``zone_solver.py``      -- TestZoneSolverInvariants (5)

Non-vacuity discipline: every property that could be satisfied by an empty or
degenerate input records a ``hypothesis.event`` naming the interesting case
and, where the property is only meaningful on non-trivial input, asserts the
interesting branch was actually reached at least once across the run via the
module-level ``_Coverage`` counters checked in ``test_no_property_was_vacuous``.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

import temper_placement_topology as _rust  # noqa: F401 -- Rust-backed guard
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
from temper_placer.topological.initial_placement import PlacementError
from tests.topological._topo_strategies import (
    build_graph,
    component_lists,
    graph_specs,
    position_maps,
    size_maps,
)
from tests.topological._topo_strategies import zones as zone_strategy

SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)

# Counters proving each family actually reached its interesting branch.
_Coverage: Counter[str] = Counter()


def _seen(tag: str) -> None:
    _Coverage[tag] += 1
    event(tag)


def _graph(spec):
    comps, adj, sep = spec
    return comps, build_graph(TopologicalGraph, comps, adj, sep)


class TestGraphInvariants:
    """graph.py -- 5 properties."""

    @given(graph_specs())
    @SETTINGS
    def test_cluster_contains_its_seed(self, spec):
        comps, g = _graph(spec)
        for seed in comps:
            assert seed in g.get_adjacency_cluster(seed)

    @given(graph_specs())
    @SETTINGS
    def test_cluster_membership_is_symmetric(self, spec):
        comps, g = _graph(spec)
        for a in comps:
            ca = g.get_adjacency_cluster(a)
            if len(ca) > 1:
                _seen("graph:multi_node_cluster")
            for b in ca:
                assert a in g.get_adjacency_cluster(b)

    @given(graph_specs())
    @SETTINGS
    def test_cluster_is_transitively_closed(self, spec):
        comps, g = _graph(spec)
        for a in comps:
            ca = g.get_adjacency_cluster(a)
            for b in ca:
                assert g.get_adjacency_cluster(b) == ca

    @given(graph_specs())
    @SETTINGS
    def test_typed_neighbors_are_a_subset_of_all_neighbors(self, spec):
        comps, g = _graph(spec)
        for node in comps:
            all_n = Counter(g.get_neighbors(node))
            for etype in ("adjacent", "separated", "member_of"):
                typed = Counter(g.get_neighbors(node, edge_type=etype))
                if typed:
                    _seen(f"graph:typed_{etype}")
                for k, v in typed.items():
                    assert all_n[k] >= v

    @given(graph_specs())
    @SETTINGS
    def test_every_conflict_is_a_real_adjacency_separation_clash(self, spec):
        comps, g = _graph(spec)
        conflicts = g.find_separation_conflicts()
        if conflicts:
            _seen("graph:conflict_found")
        for u, v, reason in conflicts:
            assert u in comps and v in comps
            adj = [
                d["distance"]
                for _, t, d in g.graph.edges(u, data=True)
                if t == v and d.get("edge_type") == "adjacent"
            ]
            sep = [
                d["distance"]
                for _, t, d in g.graph.edges(u, data=True)
                if t == v and d.get("edge_type") == "separated"
            ]
            assert adj and sep, "conflict reported without both edge kinds"
            assert min(adj) < max(sep)
            assert "adjacent" in reason and "separated" in reason


class TestPropagationInvariants:
    """propagation.py -- 5 properties."""

    @given(graph_specs())
    @SETTINGS
    def test_bounds_matrix_is_symmetric(self, spec):
        comps, g = _graph(spec)
        p = ConstraintPropagator(g)
        p.propagate()
        for a in comps:
            for b in comps:
                if a == b:
                    continue
                ab, ba = p.get_bound(a, b), p.get_bound(b, a)
                assert ab.max_distance == ba.max_distance
                assert ab.min_distance == ba.min_distance

    @given(graph_specs())
    @SETTINGS
    def test_propagation_only_tightens(self, spec):
        comps, g = _graph(spec)
        p = ConstraintPropagator(g)
        before = {
            (a, b): (p.get_bound(a, b).min_distance, p.get_bound(a, b).max_distance)
            for a in comps
            for b in comps
        }
        p.propagate()
        tightened = False
        for (a, b), (mn, mx) in before.items():
            got = p.get_bound(a, b)
            assert got.max_distance <= mx
            assert got.min_distance >= mn
            if got.max_distance < mx or got.min_distance > mn:
                tightened = True
        if tightened:
            _seen("propagation:tightened")

    @given(graph_specs())
    @SETTINGS
    def test_triangle_inequality_holds_at_fixpoint(self, spec):
        comps, g = _graph(spec)
        p = ConstraintPropagator(g)
        p.propagate(max_iterations=200)
        idx = list(comps)
        for i in idx:
            for k in idx:
                for j in idx:
                    if i in (j, k) or j == k:
                        continue
                    lhs = p.get_bound(i, j).max_distance
                    rhs = p.get_bound(i, k).max_distance + p.get_bound(k, j).max_distance
                    if math.isfinite(rhs):
                        _seen("propagation:finite_triangle")
                        assert lhs <= rhs

    @given(graph_specs())
    @SETTINGS
    def test_feasibility_matches_the_bounds_matrix(self, spec):
        comps, g = _graph(spec)
        p = ConstraintPropagator(g)
        feasible = p.propagate()
        infeasible = p.get_infeasible_pairs()
        if not feasible:
            _seen("propagation:infeasible")
            assert infeasible, "reported infeasible but listed no pair"
        for a, b, bound in infeasible:
            assert bound.min_distance > bound.max_distance
            assert a in comps and b in comps

    @given(graph_specs())
    @SETTINGS
    def test_propagation_is_idempotent(self, spec):
        comps, g = _graph(spec)
        p = ConstraintPropagator(g)
        p.propagate()
        once = {
            (a, b): (p.get_bound(a, b).min_distance, p.get_bound(a, b).max_distance)
            for a in comps
            for b in comps
        }
        p.propagate()
        for (a, b), val in once.items():
            got = p.get_bound(a, b)
            assert (got.min_distance, got.max_distance) == val


class TestForceInvariants:
    """force_refinement.py -- 6 properties."""

    @given(graph_specs(), st.data())
    @SETTINGS
    def test_refinement_preserves_the_key_set(self, spec, data):
        comps, g = _graph(spec)
        positions = data.draw(position_maps(comps))
        out = apply_force_refinement(dict(positions), g, {}, {}, iterations=5, learning_rate=0.05)
        assert set(out) == set(positions)

    @given(graph_specs(), st.data())
    @SETTINGS
    def test_zero_iterations_is_the_identity(self, spec, data):
        comps, g = _graph(spec)
        positions = data.draw(position_maps(comps))
        out = apply_force_refinement(dict(positions), g, {}, {}, iterations=0, learning_rate=0.1)
        assert out == positions

    @given(graph_specs(), st.data())
    @SETTINGS
    def test_refined_positions_stay_finite(self, spec, data):
        comps, g = _graph(spec)
        positions = data.draw(position_maps(comps))
        zone = Zone(name="Z", bounds=(-1e4, -1e4, 1e4, 1e4))
        out = apply_force_refinement(
            dict(positions), g, {"Z": zone}, dict.fromkeys(comps, "Z"), 20, 0.01
        )
        for x, y in out.values():
            assert math.isfinite(x) and math.isfinite(y)

    @given(
        st.tuples(st.floats(-100, 100), st.floats(-100, 100)),
        st.tuples(st.floats(-100, 100), st.floats(-100, 100)),
        st.floats(min_value=0.0, max_value=50.0),
    )
    @SETTINGS
    def test_adjacency_force_is_antisymmetric(self, pa, pb, target):
        import numpy as np

        fa, fb = compute_adjacency_force(np.array(pa), np.array(pb), target)
        _seen("force:adjacency_evaluated")
        for u, v in zip(fa.tolist(), fb.tolist()):
            assert u == -v or (u == 0.0 and v == 0.0)

    @given(
        st.tuples(st.floats(-100, 100), st.floats(-100, 100)),
        st.tuples(st.floats(-100, 100), st.floats(-100, 100)),
        st.floats(min_value=0.0, max_value=50.0),
    )
    @SETTINGS
    def test_separation_force_vanishes_beyond_the_minimum(self, pa, pb, min_dist):
        import numpy as np

        a, b = np.array(pa), np.array(pb)
        dist = float(np.linalg.norm(b - a))
        fa, fb = compute_separation_force(a, b, min_dist)
        if dist >= 1e-6 and dist >= min_dist:
            _seen("force:separation_inactive")
            assert fa.tolist() == [0.0, 0.0] and fb.tolist() == [0.0, 0.0]
        elif dist >= 1e-6:
            _seen("force:separation_active")

    @given(st.tuples(st.floats(-200, 200), st.floats(-200, 200)))
    @SETTINGS
    def test_boundary_force_is_zero_exactly_inside(self, pos):
        import numpy as np

        zone = Zone(name="Z", bounds=(-50.0, -50.0, 50.0, 50.0))
        f = compute_boundary_force(np.array(pos), zone).tolist()
        inside = -50.0 <= pos[0] <= 50.0 and -50.0 <= pos[1] <= 50.0
        if inside:
            _seen("force:boundary_inside")
            assert f == [0.0, 0.0]
        else:
            _seen("force:boundary_outside")
            assert f != [0.0, 0.0]


class TestInitialPlacementInvariants:
    """initial_placement.py -- 6 properties."""

    @given(graph_specs())
    @SETTINGS
    def test_clusters_partition_the_component_list(self, spec):
        comps, g = _graph(spec)
        clusters = identify_clusters(g, list(comps))
        union: set[str] = set()
        for c in clusters:
            assert not (union & c), "clusters overlap"
            union |= c
        assert union == set(comps)
        if len(clusters) > 1:
            _seen("placement:multiple_clusters")

    @given(graph_specs())
    @SETTINGS
    def test_adjacent_components_share_a_cluster(self, spec):
        comps, adj, _sep = spec
        g = build_graph(TopologicalGraph, *spec)
        clusters = identify_clusters(g, list(comps))
        home = {ref: i for i, c in enumerate(clusters) for ref in c}
        for a, b, _d, _cid in adj:
            _seen("placement:adjacency_edge")
            assert home[a] == home[b]

    @given(graph_specs())
    @SETTINGS
    def test_separation_alone_never_merges_clusters(self, spec):
        comps, adj, sep = spec
        if adj:
            return
        g = build_graph(TopologicalGraph, comps, [], sep)
        clusters = identify_clusters(g, list(comps))
        if sep:
            _seen("placement:separation_only")
        assert len(clusters) == len(comps)

    @given(component_lists(min_size=1, max_size=6), st.data())
    @SETTINGS
    def test_placed_components_are_exactly_the_requested_ones(self, comps, data):
        zone = data.draw(zone_strategy())
        sz = data.draw(size_maps(comps))
        try:
            out = place_components_in_zone(zone, comps, sz)
        except PlacementError:
            _seen("placement:zone_rejected")
            return
        _seen("placement:zone_accepted")
        assert set(out) == set(comps)

    @given(component_lists(min_size=1, max_size=6), st.data())
    @SETTINGS
    def test_placed_positions_respect_the_zone_box(self, comps, data):
        zone = data.draw(zone_strategy())
        sz = data.draw(size_maps(comps))
        try:
            out = place_components_in_zone(zone, comps, sz)
        except PlacementError:
            return
        x0, y0, x1, y1 = zone.bounds
        for ref, (x, y) in out.items():
            w, h = sz[ref]
            assert x0 - 1e-9 <= x <= x1 + 1e-9
            assert y0 - 1e-9 <= y <= y1 + 1e-9

    @given(graph_specs(), st.data())
    @SETTINGS
    def test_place_cluster_returns_exactly_the_cluster(self, spec, data):
        comps, g = _graph(spec)
        zone = data.draw(zone_strategy())
        sz = data.draw(size_maps(comps))
        cluster = set(comps)
        out = place_cluster(cluster, zone, g, sz, 0, 1)
        assert set(out) == cluster


class TestZoneSolverInvariants:
    """zone_solver.py -- 5 properties."""

    @given(component_lists(min_size=0, max_size=5), st.integers(min_value=0, max_value=4))
    @SETTINGS
    def test_assignments_come_from_the_candidate_sets(self, comps, n_zones):
        names = [f"Z{i}" for i in range(n_zones)]
        zs = [Zone(name=n, bounds=(0.0, 0.0, 10.0, 10.0)) for n in names]
        solver = ZoneSolver(zs, [], list(comps))
        result = solver.solve()
        for ref, zone_name in result.assignments.items():
            _seen("zone:assigned")
            assert zone_name in solver._candidates[ref]

    @given(component_lists(min_size=1, max_size=5))
    @SETTINGS
    def test_no_zones_means_every_component_conflicts(self, comps):
        solver = ZoneSolver([], [], list(comps))
        result = solver.solve()
        _seen("zone:no_zones")
        assert result.assignments == {}
        assert sorted(result.unassigned) == sorted(comps)
        assert len(result.conflicts) == len(comps)

    @given(component_lists(min_size=1, max_size=5), st.integers(min_value=1, max_value=4))
    @SETTINGS
    def test_success_assigns_every_component_exactly_once(self, comps, n_zones):
        names = [f"Z{i}" for i in range(n_zones)]
        zs = [Zone(name=n, bounds=(0.0, 0.0, 10.0, 10.0)) for n in names]
        result = ZoneSolver(zs, [], list(comps)).solve()
        assert not result.conflicts
        assert set(result.assignments) == set(comps)
        assert result.unassigned == []

    @given(component_lists(min_size=1, max_size=5), st.integers(min_value=1, max_value=4))
    @SETTINGS
    def test_candidates_are_always_a_subset_of_the_zone_names(self, comps, n_zones):
        names = {f"Z{i}" for i in range(n_zones)}
        zs = [Zone(name=n, bounds=(0.0, 0.0, 10.0, 10.0)) for n in sorted(names)]
        solver = ZoneSolver(zs, [], list(comps))
        for ref in comps:
            assert solver._candidates[ref] <= names

    @given(component_lists(min_size=1, max_size=5), st.integers(min_value=1, max_value=4))
    @SETTINGS
    def test_enclosing_constraint_pins_its_components(self, comps, n_zones):
        from temper_placer.pcl.constraints import EnclosingConstraint

        names = [f"Z{i}" for i in range(n_zones)]
        zs = [Zone(name=n, bounds=(0.0, 0.0, 10.0, 10.0)) for n in names]
        target = names[-1]
        pinned = comps[0]
        cons = [
            EnclosingConstraint(
                id="e1", outer=target, inner=[pinned], source_line=1, raw_text="enclosing"
            )
        ]
        result = ZoneSolver(zs, cons, list(comps)).solve()
        _seen("zone:enclosing_applied")
        assert result.assignments[pinned] == target


@pytest.mark.order("last")
def test_no_property_was_vacuous():
    """G4 anti-vacuity: assert each interesting branch was reached at least
    once. If a strategy drifts so that (say) no conflict is ever generated,
    the conflict property silently degrades to ``for _ in []`` -- this test
    is what turns that into a failure."""
    required = [
        "graph:multi_node_cluster",
        "graph:typed_adjacent",
        "graph:typed_separated",
        "graph:conflict_found",
        "propagation:tightened",
        "propagation:finite_triangle",
        "propagation:infeasible",
        "force:adjacency_evaluated",
        "force:separation_inactive",
        "force:separation_active",
        "force:boundary_inside",
        "force:boundary_outside",
        "placement:multiple_clusters",
        "placement:adjacency_edge",
        "placement:zone_accepted",
        "zone:assigned",
        "zone:no_zones",
        "zone:enclosing_applied",
    ]
    missing = [tag for tag in required if _Coverage[tag] == 0]
    assert not missing, (
        "these interesting branches were never exercised, so the properties "
        f"guarding them are vacuous: {missing}"
    )
