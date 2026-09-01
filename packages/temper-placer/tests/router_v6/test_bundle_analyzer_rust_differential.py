"""Differential tests: the Rust `temper-geometry.bundle_analyzer` GEOS-seam
kernels vs the pre-migration pure-shapely reference.

The pre-migration module computed each net's geometric footprint with
``MultiPoint(positions).convex_hull.buffer(m)`` and each net's edge cover
with ``STRtree(points).query(footprint, predicate="contains")``.  Both are
transcribed into ``temper-geometry``'s ``bundle_analyzer`` module:

- ``convex_hull_ring_py`` — GEOS ``ConvexHull`` verbatim (preSort + Graham
  scan + cleanRing, with the ``CGAlgorithmsDD`` filter + double-double
  orientation predicate).
- ``hull_buffer_ring_py`` — GEOS ``OffsetSegmentGenerator`` verbatim for a
  convex ring buffered on the LEFT (the module's ``quad_segs=16`` — shapely's
  default, not GEOS's own 8).
- ``covered_edge_indices_py`` — the STRtree ``contains`` query replaced by a
  strict point-in-convex-polygon scan; the result set is a pure function of
  the footprint region, so it is identical.

The end-to-end comparison uses the standalone ``_bundle_analyzer_py_oracle``
module pinned to the module as committed immediately before the orchestration
migration (``git show 8fd69df1:.../bundle_analyzer.py``).  Its orchestration
and all manifest decisions are pure Python; it does not inherit from or call
the production adapter.

Comparisons are bit-exact:

- footprint rings compare as canonicalized vertex sets (``float`` tuples,
  order-insensitive).  Ring start/orientation are GEOS emission artifacts
  (docs/evidence/2026-08-04-geos-polygon-algebra-spike.md §3.1) that do not
  change the region; the region is what the edge-cover predicate consumes.
- edge-cover id sets compare with exact ``==`` (frozenset equality).
- the end-to-end manifest comparison covers the exact surface the production
  consumer serializes (``_pipeline_route.py``: ``bundle_id``,
  ``net_indices``, ``constraint_types``, ``is_diff_pair``,
  ``bundle_id_for_net``, ``unbundled_net_indices``).  ``geometric_footprint``
  and ``type_signature`` are not compared: ``geometric_footprint`` has zero
  production readers and ``type_signature`` is never serialized.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import shapely
import temper_geometry as _tg
from shapely import STRtree
from shapely.geometry import MultiPoint, Polygon

import tests.graph_fixtures as nx
from temper_placer.router_v6.bundle_analyzer import BundleAnalyzer
from tests.router_v6._bundle_analyzer_py_oracle import BundleAnalyzer as OracleBundleAnalyzer

# ---------------------------------------------------------------------------
# Test fixtures (mocks mirror the existing test_bundle_analyzer.py)
# ---------------------------------------------------------------------------


class _MockPin:
    def __init__(self, x, y):
        self.position = (x, y)


class _MockComponent:
    def __init__(self, ref, pos, pins):
        self.ref = ref
        self.initial_position = pos
        self._pins = pins

    def get_pin(self, pin_name):
        return self._pins.get(pin_name)


class _MockPCB:
    def __init__(self, components=None):
        self.components = components or []


class _MockNet:
    def __init__(self, name, pin_positions=None):
        self.name = name
        self._pos = pin_positions or []
        self.pins = [(f"COMP_{name}_{i}", f"PIN_{i}") for i in range(len(self._pos))]

    def __repr__(self):
        return f"MockNet({self.name!r})"


class _MockDesignRules:
    def __init__(self, trace_width=0.2, clearance=0.2):
        self._width = trace_width
        self._clearance = clearance

    def get_rules_for_net(self, _net_name):
        from temper_placer.router_v6.stage0_data import NetClassRules

        return NetClassRules(
            name="Default",
            clearance_mm=self._clearance,
            trace_width_mm=self._width,
            via_diameter_mm=0.6,
            via_drill_mm=0.3,
        )


class _MockSafetyDesignRules(_MockDesignRules):
    """Design-rule fixture retaining the real board's gate-drive safety tier."""

    def __init__(self, safety_categories):
        super().__init__()
        self._safety_categories = safety_categories

    def get_rules_for_net(self, net_name):
        rule = super().get_rules_for_net(net_name)
        rule.safety_category = self._safety_categories.get(net_name)
        return rule


class _MockDiffPair:
    def __init__(self, base_name, p_net, n_net):
        self.base_name = base_name
        self.p_net = p_net
        self.n_net = n_net


class _DuplicateEdgeGraph:
    """Graph-like fixture that emits duplicate IDs for Rust canonicalization."""

    def __init__(self, edges):
        self._edges = edges

    @property
    def edges(self):
        return [(u, v) for u, v, _data in self._edges]

    def edges_with_data(self):
        return list(self._edges)


class _DuplicateEdgeSkeleton:
    def __init__(self):
        self.graph = _DuplicateEdgeGraph([
            ((0.0, 0.0), (10.0, 0.0), {"weight": 10.0}),
            ((0.0, 0.0), (10.0, 0.0), {"weight": 10.0}),
            ((10.0, 0.0), (20.0, 0.0), {"weight": 10.0}),
        ])


class _MockSkeleton:
    def __init__(self, graph=None):
        self.graph = graph or nx.Graph()


def _make_pcb_for_nets(*nets) -> _MockPCB:
    components = []
    for net in nets:
        for i, (comp_ref, pin_name) in enumerate(net.pins):
            if i < len(net._pos):
                x, y = net._pos[i]
                components.append(
                    _MockComponent(comp_ref, pos=(x, y), pins={pin_name: _MockPin(0, 0)})
                )
    return _MockPCB(components)


def _make_grid_skeleton(x_range, y_range, spacing=10.0) -> _MockSkeleton:
    """A grid skeleton graph; edge weights are edge lengths (>= 0)."""
    G = nx.Graph()
    xs = [x_range[0] + i * spacing for i in range(int((x_range[1] - x_range[0]) / spacing) + 1)]
    ys = [y_range[0] + i * spacing for i in range(int((y_range[1] - y_range[0]) / spacing) + 1)]
    for x in xs:
        for y in ys:
            G.add_node((x, y))
    for x in xs:
        for i in range(len(ys) - 1):
            G.add_edge((x, ys[i]), (x, ys[i + 1]), weight=spacing)
    for y in ys:
        for i in range(len(xs) - 1):
            G.add_edge((xs[i], y), (xs[i + 1], y), weight=spacing)
    return _MockSkeleton(G)


def _canon(ring) -> frozenset[tuple[float, float]]:
    """Canonicalized vertex set of a closed ring (region equality)."""
    return frozenset((x, y) for (x, y) in ring[:-1])


def _rand_pads(rng, n, scale=10.0):
    return [(rng.uniform(-scale, scale), rng.uniform(-scale, scale)) for _ in range(n)]


# ---------------------------------------------------------------------------
# Kernel differentials
# ---------------------------------------------------------------------------


def test_convex_hull_ring_vertex_set_bit_identical():
    """Rust hull vertex set == GEOS ``MultiPoint(pads).convex_hull`` vertex set."""
    rng = random.Random(11)
    for _ in range(150):
        pads = _rand_pads(rng, rng.randint(3, 8), scale=rng.uniform(1, 20))
        ref = MultiPoint(pads).convex_hull
        mine = _tg.convex_hull_ring_py(pads)
        if isinstance(ref, Polygon):
            assert _canon(mine) == _canon(list(ref.exterior.coords)), f"hull mismatch {pads}"
        else:
            # not a polygon (collinear/degenerate) -> the shim maps to empty
            assert not mine, f"expected empty ring for {pads}"


def test_convex_hull_ring_edge_cases():
    """Duplicates, collinear pads, and sub-polygon inputs."""
    # duplicate pads collapse (extractUnique)
    assert _canon(_tg.convex_hull_ring_py([(1.0, 1.0), (1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)])) == _canon(
        [(1.0, 1.0), (1.0, 5.0), (5.0, 5.0), (5.0, 1.0), (1.0, 1.0)]
    )
    # collinear pads -> GEOS returns a LineString, the shim maps to empty
    assert _tg.convex_hull_ring_py([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]) == []
    assert _tg.convex_hull_ring_py([]) == []
    assert _tg.convex_hull_ring_py([(0.0, 0.0)]) == []
    assert _tg.convex_hull_ring_py([(0.0, 0.0), (3.0, 0.0)]) == []
    # collinear boundary points are dropped (cleanRing)
    ref = MultiPoint([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (5.0, 0.5), (3.0, 2.0)]).convex_hull
    mine = _tg.convex_hull_ring_py([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (5.0, 0.5), (3.0, 2.0)])
    assert _canon(mine) == _canon(list(ref.exterior.coords))


def test_buffer_ring_region_bit_identical():
    """Rust ``hull.buffer(m)`` region == shapely ``hull.buffer(m)`` (vertex set)."""
    rng = random.Random(23)
    for _ in range(150):
        pads = _rand_pads(rng, rng.randint(3, 8), scale=rng.uniform(1, 20))
        m = rng.uniform(0.05, 8.0)
        ref = MultiPoint(pads).convex_hull
        if not isinstance(ref, Polygon):
            continue
        ref_buf = ref.buffer(m)
        mine = _tg.hull_buffer_ring_py(_tg.convex_hull_ring_py(pads), m)
        assert _canon(mine) == _canon(list(ref_buf.exterior.coords)), f"buffer mismatch pads={pads} m={m}"


def test_buffer_ring_zero_distance_is_hull_ring():
    """``hull.buffer(0)`` returns the hull ring itself (GEOS fast path)."""
    pads = [(0.0, 0.0), (10.0, 0.0), (5.0, 7.0)]
    ring = _tg.convex_hull_ring_py(pads)
    assert _tg.hull_buffer_ring_py(ring, 0.0) == ring
    ref = MultiPoint(pads).convex_hull.buffer(0.0)
    assert _canon(ring) == _canon(list(ref.exterior.coords))


def test_covered_edge_ids_bit_identical():
    """Rust covered-edge indices == STRtree ``contains`` query, incl. boundaries."""
    rng = random.Random(37)
    for _ in range(60):
        pads = _rand_pads(rng, rng.randint(3, 7), scale=10.0)
        m = rng.uniform(0.05, 5.0)
        ref = MultiPoint(pads).convex_hull
        if not isinstance(ref, Polygon):
            continue
        footprint = ref.buffer(m)
        ring = _tg.hull_buffer_ring_py(_tg.convex_hull_ring_py(pads), m)

        n = rng.randint(20, 200)
        xs = [rng.uniform(-15, 15) for _ in range(n)]
        ys = [rng.uniform(-15, 15) for _ in range(n)]
        # boundary-exact probes: the ring's own vertices (contains excludes them)
        xs += [p[0] for p in ring[:-1]]
        ys += [p[1] for p in ring[:-1]]

        ids = np.arange(n + len(ring) - 1, dtype=object)
        tree = STRtree(shapely.points(np.array(xs), np.array(ys)))
        ref_idx = tree.query(footprint, predicate="contains")
        ref_set = frozenset(ids[ref_idx].tolist())

        mine = _tg.covered_edge_indices_py(ring, xs, ys)
        mine_set = frozenset(ids[mine].tolist())
        assert mine_set == ref_set, f"covered mismatch pads={pads} m={m}"


# ---------------------------------------------------------------------------
# End-to-end differential: the consumed BundleManifest surface
# ---------------------------------------------------------------------------


def _consumed_surface(manifest):
    """The exact surface ``_pipeline_route.py`` serializes for the solver."""
    return {
        "bundles": {
            b.bundle_id: {
                "net_indices": list(b.net_indices),
                "constraint_types": sorted(b.constraint_types),
                "is_diff_pair": b.is_diff_pair,
            }
            for b in manifest.bundles.values()
        },
        "bundle_id_for_net": dict(manifest.bundle_id_for_net),
        "unbundled_net_indices": list(manifest.unbundled_net_indices),
    }


def _assert_manifest_matches_oracle(
    nets, skeletons, *, design_rules=None, diff_pairs=None, threshold=0.5
):
    mine = BundleAnalyzer(
        nets,
        skeletons,
        design_rules=design_rules,
        diff_pairs=diff_pairs,
        pcb=_make_pcb_for_nets(*nets),
        jaccard_threshold=threshold,
    ).analyze()
    reference = OracleBundleAnalyzer(
        nets,
        skeletons,
        design_rules=design_rules,
        diff_pairs=diff_pairs,
        pcb=_make_pcb_for_nets(*nets),
        jaccard_threshold=threshold,
    ).analyze()
    assert _consumed_surface(mine) == _consumed_surface(reference), "manifest differential mismatch"
    return mine, reference


def test_analyze_consumed_surface_bit_identical():
    """Rust-backed analyze() == pre-migration analyze() on the consumed surface."""
    rng = random.Random(101)
    for trial in range(40):
        nets = [
            _MockNet(f"SIG_{k}", _rand_pads(rng, rng.randint(2, 5), scale=12.0))
            for k in range(rng.randint(3, 8))
        ]
        # some identical nets to force bundling
        nets += [_MockNet("SIG_DUP_A", nets[0]._pos), _MockNet("SIG_DUP_B", nets[0]._pos)]
        rng.shuffle(nets)
        skeletons = {
            "F.Cu": _make_grid_skeleton((-15, 15), (-15, 15), spacing=5.0),
        }
        pcb = _make_pcb_for_nets(*nets)
        dr = _MockDesignRules()

        mine = BundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb).analyze()
        ref = OracleBundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb).analyze()

        assert _consumed_surface(mine) == _consumed_surface(ref), f"manifest mismatch trial {trial}"


def test_analyze_preserves_gate_drive_safety_categories():
    """GATE_HS/GATE_LS use the live board's HV safety category in grouping."""
    positions = [(0.0, 0.0), (10.0, 0.0), (5.0, 5.0)]
    nets = [
        _MockNet("GATE_HS", positions),
        _MockNet("GATE_LS", positions),
        _MockNet("SIG_GATE_SHAPED", positions),
    ]
    rules = _MockSafetyDesignRules({"GATE_HS": "HV", "GATE_LS": "HV"})
    mine, reference = _assert_manifest_matches_oracle(
        nets, {"F.Cu": _make_grid_skeleton((-5, 15), (-5, 10), spacing=5.0)},
        design_rules=rules,
    )
    assert _consumed_surface(mine) == _consumed_surface(reference)
    gate_bundle = next(b for b in mine.bundles.values() if 0 in b.net_indices)
    assert gate_bundle.net_indices == [0, 1]
    assert all(2 not in b.net_indices for b in mine.bundles.values())
    assert 2 in mine.unbundled_net_indices


def test_analyze_canonicalizes_duplicate_edge_ids():
    """Duplicate edge IDs retain Python's frozenset semantics in Rust."""
    nets = [_MockNet("SIG_A", [(0.0, 0.0), (10.0, 0.0)]),
            _MockNet("SIG_B", [(0.0, 0.0), (10.0, 0.0)])]
    mine, reference = _assert_manifest_matches_oracle(
        nets, {"F.Cu": _DuplicateEdgeSkeleton()}
    )
    assert _consumed_surface(mine) == _consumed_surface(reference)
    assert mine.bundles[0].net_indices == [0, 1]


def test_analyze_matches_unmatched_diff_pair_and_threshold_ordering():
    """Pair order, duplicate bases, unmatched diff nets, and strict threshold agree."""
    positions = [(0.0, 0.0), (10.0, 0.0)]
    nets = [
        _MockNet("PAIR_N", positions),
        _MockNet("PAIR_P", positions),
        _MockNet("ORPHAN_P", positions),
        _MockNet("SIG_A", positions),
    ]
    diff_pairs = [
        _MockDiffPair("PAIR", "PAIR_P", "PAIR_N"),
        _MockDiffPair("PAIR", "ORPHAN_P", "MISSING_N"),
    ]
    skeletons = {"F.Cu": _make_grid_skeleton((-5, 15), (-5, 5), spacing=5.0)}
    mine, reference = _assert_manifest_matches_oracle(
        nets, skeletons, diff_pairs=diff_pairs, threshold=0.5
    )
    assert _consumed_surface(mine) == _consumed_surface(reference)
    assert any(b.is_diff_pair and b.net_indices == [0, 1] for b in mine.bundles.values())
    # Empty edge-cover overlap is exactly Jaccard=1.0; the boundary is strict.
    boundary_nets = [_MockNet("BOUND_A"), _MockNet("BOUND_B")]
    _assert_manifest_matches_oracle(
        boundary_nets, {}, threshold=1.0
    )
    below_boundary, _ = _assert_manifest_matches_oracle(
        boundary_nets, {}, threshold=0.999
    )
    assert below_boundary.bundles[0].net_indices == [0, 1]


def test_mutated_rust_manifest_output_fails_differential(monkeypatch):
    """A manifest-record mutation cannot make the oracle comparison vacuous."""
    nets = [_MockNet("SIG_A", [(0.0, 0.0), (10.0, 0.0)]),
            _MockNet("SIG_B", [(0.0, 0.0), (10.0, 0.0)])]
    original = _tg.analyze_bundle_manifest_py

    def mutate_manifest(*args, **kwargs):
        records, id_pairs, unbundled = original(*args, **kwargs)
        assert records
        mutated = list(records)
        record = list(mutated[0])
        record[6] = ["mutated-constraint"]
        mutated[0] = tuple(record)
        return mutated, id_pairs, unbundled

    monkeypatch.setattr(_tg, "analyze_bundle_manifest_py", mutate_manifest)
    with pytest.raises(AssertionError, match="differential|constraint|mutated"):
        _assert_manifest_matches_oracle(nets, {})


def test_edge_cover_sets_bit_identical_per_net():
    """Per-net edge-cover sets (the clustering input) match bit-for-bit."""
    rng = random.Random(202)
    nets = [
        _MockNet(f"SIG_{k}", _rand_pads(rng, rng.randint(2, 5), scale=12.0))
        for k in range(6)
    ]
    skeletons = {"F.Cu": _make_grid_skeleton((-15, 15), (-15, 15), spacing=5.0)}
    pcb = _make_pcb_for_nets(*nets)
    dr = _MockDesignRules()

    mine = BundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)
    ref = OracleBundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)

    for net in nets:
        mine_fp = mine._compute_geometric_footprint(net)
        ref_fp = ref._compute_geometric_footprint(net)
        # footprint regions identical (vertex sets; empty iff empty)
        if mine_fp.is_empty:
            assert ref_fp.is_empty
        else:
            assert _canon(list(mine_fp.exterior.coords)) == _canon(list(ref_fp.exterior.coords))
        assert mine._compute_covered_edges(mine_fp) == ref._compute_covered_edges(ref_fp)
