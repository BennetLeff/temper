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

The oracle blocks below are copied VERBATIM from the module AS COMMITTED on
``origin/main`` before this migration (``git show HEAD:.../bundle_analyzer.py``);
do not edit — they are the reference.  The `# @req`-free, verbatim body of
``_compute_geometric_footprint``, ``_build_edge_index`` and
``_compute_covered_edges`` is embedded as ``_oracle_*`` and driven by an
``_OracleBundleAnalyzer`` that shares the unchanged orchestration.

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

import math
import random
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest
import shapely
import temper_geometry as _tg
from shapely import STRtree
from shapely.geometry import MultiPoint, Polygon

from temper_placer.router_v6.bundle_analyzer import BundleAnalyzer

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the module AS COMMITTED before
# the Wave 4 migration; do not edit — they are the reference).
# ---------------------------------------------------------------------------


def _oracle_compute_geometric_footprint(positions, median_edge_length) -> Polygon:
    """Verbatim pre-migration ``_compute_geometric_footprint`` geometry."""
    if len(positions) < 2:
        # Single pad: create a small square around it
        if positions:
            cx, cy = positions[0]
            m = median_edge_length
            return Polygon(
                [
                    (cx - m, cy - m),
                    (cx + m, cy - m),
                    (cx + m, cy + m),
                    (cx - m, cy + m),
                ]
            )
        # No positions: empty polygon
        return Polygon()

    if len(positions) == 2:
        # Two pads: create a rectangular envelope
        (x1, y1), (x2, y2) = positions
        _dx, _dy = abs(x2 - x1), abs(y2 - y1)
        margin = median_edge_length
        minx = min(x1, x2) - margin
        maxx = max(x1, x2) + margin
        miny = min(y1, y2) - margin
        maxy = max(y1, y2) + margin
        return Polygon(
            [
                (minx, miny),
                (maxx, miny),
                (maxx, maxy),
                (minx, maxy),
            ]
        )

    mp = MultiPoint(positions)
    hull = mp.convex_hull
    if isinstance(hull, Polygon):
        return hull.buffer(median_edge_length)
    return Polygon()


def _oracle_build_edge_index(skeletons) -> tuple[np.ndarray, np.ndarray, STRtree]:
    """Verbatim pre-migration ``_build_edge_index`` (id + STRtree)."""
    edge_ids: list[str] = []
    mids_x: list[float] = []
    mids_y: list[float] = []
    for layer_name, skeleton in skeletons.items():
        for i, (_u, _v) in enumerate(skeleton.graph.edges):  # type: ignore[attr-defined]
            n1, n2 = sorted([_u, _v])
            edge_ids.append(f"{layer_name}_E{i}_{n1}_{n2}")
            mids_x.append((n1[0] + n2[0]) / 2.0)
            mids_y.append((n1[1] + n2[1]) / 2.0)

    ids = np.array(edge_ids, dtype=object)
    if edge_ids:
        edge_points = shapely.points(np.array(mids_x), np.array(mids_y))
        edge_tree = STRtree(edge_points)
    else:
        edge_points = np.empty(0, dtype=object)
        edge_tree = None
    return ids, edge_points, edge_tree


def _oracle_compute_covered_edges(edge_ids, edge_tree, footprint: Polygon) -> frozenset[str]:
    """Verbatim pre-migration ``_compute_covered_edges``."""
    if edge_tree is None or footprint.is_empty:
        return frozenset()
    try:
        idx = edge_tree.query(footprint, predicate="contains")
    except Exception:
        return frozenset()
    if len(idx) == 0:
        return frozenset()
    return frozenset(edge_ids[idx].tolist())


# ---------------------------------------------------------------------------
# Oracle analyzer: the pre-migration module with its GEOS internals restored,
# sharing the unchanged orchestration with the shim.
# ---------------------------------------------------------------------------


class _OracleBundleAnalyzer(BundleAnalyzer):
    """The pre-migration BundleAnalyzer (GEOS footprints + STRtree covers).

    Overrides only the two migrated kernels with the verbatim pre-migration
    implementations; ``analyze()`` and every other method are the shim's
    (unchanged) orchestration, so the end-to-end comparison pins exactly the
    GEOS seam replacement.
    """

    def _compute_geometric_footprint(self, net) -> Polygon:
        return _oracle_compute_geometric_footprint(
            self._net_pad_positions(net), self._median_edge_length
        )

    def _build_edge_index(self) -> None:
        if self._edge_ids is not None:
            return
        self._edge_ids, self._edge_points, self._edge_tree = _oracle_build_edge_index(
            self.skeletons
        )

    def _compute_covered_edges(self, footprint: Polygon) -> frozenset[str]:
        self._build_edge_index()
        assert self._edge_ids is not None
        return _oracle_compute_covered_edges(self._edge_ids, self._edge_tree, footprint)


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
        ref = _OracleBundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb).analyze()

        assert _consumed_surface(mine) == _consumed_surface(ref), f"manifest mismatch trial {trial}"


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
    ref = _OracleBundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)

    for net in nets:
        mine_fp = mine._compute_geometric_footprint(net)
        ref_fp = ref._compute_geometric_footprint(net)
        # footprint regions identical (vertex sets; empty iff empty)
        if mine_fp.is_empty:
            assert ref_fp.is_empty
        else:
            assert _canon(list(mine_fp.exterior.coords)) == _canon(list(ref_fp.exterior.coords))
        assert mine._compute_covered_edges(mine_fp) == ref._compute_covered_edges(ref_fp)
