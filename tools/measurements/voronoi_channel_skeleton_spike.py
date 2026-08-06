#!/usr/bin/env python3
"""Spike harness: GEOS/shapely Voronoi determinism and the downstream
channel-skeleton contract (`router_v6/channel_skeleton.py`).

Answers, in order:

  Q1  Is GEOS `voronoi_diagram` deterministic -- repeated in-process, across
      fresh processes, and under permutation of the input point order?
  Q2  Is the observable downstream artifact the skeleton graph's *topology*,
      or its exact vertex coordinates and edge order?
  Q3  Does a coordinate-level divergence survive the filter + connectivity
      stages, i.e. does it reach the consumer?

Falsifiers, stated before measuring (see the evidence doc for the recorded
outcome of each):

  F1  "GEOS voronoi_diagram is bit-identical across repeated calls with the
       same input in the same process."  FIRES if any repeat differs.
  F2  "The GEOS Voronoi *edge set* is invariant to permutation of the input
       point order."  FIRES if a permutation changes the set of edges.
  F3  "The GEOS Voronoi *edge sequence* is invariant to permutation of the
       input point order."  FIRES if a permutation changes the ordering.
  F4  "The downstream contract is graph topology only, so a permuted-but-
       valid Voronoi yields an equivalent skeleton for the consumer."
      FIRES if node identity or consumer-visible identifiers change.

`_extract_medial_axis_single` and `_ensure_skeleton_connectivity` are loaded
from the real module file rather than reimplemented, so the measurement
cannot drift from production. The module's sibling imports are stubbed
because the compiled `temper_design_bundle_python` in this checkout is stale
relative to the Python source and this spike must not build any Rust crate.
None of the stubbed names are reachable from the measured code paths
(`pcb=None` disables the only `pin_world_position` call site).

Usage:
    python3 tools/measurements/voronoi_channel_skeleton_spike.py            # full run
    python3 tools/measurements/voronoi_channel_skeleton_spike.py --child N  # subprocess probe
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO_ROOT
    / "packages"
    / "temper-placer"
    / "src"
    / "temper_placer"
    / "router_v6"
    / "channel_skeleton.py"
)


def _install_stubs() -> None:
    """Stub the sibling imports of channel_skeleton so the real module file
    can be loaded without the (stale) compiled extension."""

    def _mod(name: str, **attrs: Any) -> None:
        if name in sys.modules:
            return
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        m.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = m

    def _unreachable(*_a: Any, **_k: Any) -> Any:  # pragma: no cover - guard
        raise AssertionError("stubbed symbol reached; measurement is invalid")

    _mod("temper_placer")
    _mod("temper_placer.core")
    _mod("temper_placer.core.pin_geometry", pin_world_position=_unreachable)
    _mod("temper_placer.deterministic")
    _mod("temper_placer.deterministic.stages")
    _mod("temper_placer.deterministic.stages.base", Stage=object)
    _mod("temper_placer.deterministic.state", BoardState=object)
    _mod("temper_placer.router_v6")
    _mod("temper_placer.router_v6.routing_space", RoutingSpace=object)
    _mod("temper_placer.router_v6.stage0_data", ParsedPCB=object)
    _mod(
        "temper_placer.router_v6.stage_validators",
        StageDRCFailure=object,
        register_validator=lambda _name: (lambda fn: fn),
    )


def load_production_module() -> types.ModuleType:
    _install_stubs()
    spec = importlib.util.spec_from_file_location("_cs_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_cs_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# Test geometry: a rectangular board minus axis-aligned pad rectangles, which
# is exactly how RoutingSpace builds `available_area`
# (routing_space.py: `board_polygon.difference(obstacles)`).
# --------------------------------------------------------------------------


def build_routing_area(seed: int = 0, n_pads: int = 9):
    from shapely.geometry import MultiPolygon, Polygon, box
    from shapely.ops import unary_union

    rng = random.Random(seed)
    board = box(0.0, 0.0, 40.0, 30.0)
    pads = []
    for _ in range(n_pads):
        cx = rng.uniform(4.0, 36.0)
        cy = rng.uniform(4.0, 26.0)
        w = rng.choice([1.6, 2.0, 3.0])
        h = rng.choice([1.6, 2.0, 3.0])
        pads.append(box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    obstacles = unary_union(pads)
    area = board.difference(obstacles)
    if isinstance(area, Polygon):
        area = MultiPolygon([area])
    return area


def sample_boundary_points(polygon) -> list[tuple[float, float]]:
    """Replicate the module's boundary sampling (channel_skeleton.py lines
    ~240-269) so the Voronoi input matches production exactly."""
    from shapely.geometry import Point

    boundary = polygon.boundary
    parts = list(boundary.geoms) if hasattr(boundary, "geoms") else [boundary]
    points: list[Point] = []
    for part in parts:
        try:
            coords = list(part.coords)
        except (NotImplementedError, AttributeError):
            continue
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i + 1]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            dist = (dx**2 + dy**2) ** 0.5
            num_points = max(2, int(dist))
            for j in range(num_points):
                t = j / num_points
                points.append(Point(p1[0] + t * dx, p1[1] + t * dy))
    return [(p.x, p.y) for p in points]


# --------------------------------------------------------------------------
# Voronoi probes
# --------------------------------------------------------------------------


def voronoi_edges(points: list[tuple[float, float]]) -> list[tuple]:
    """Return the raw GEOS Voronoi edge sequence, flattened exactly the way
    `_extract_medial_axis_single` flattens it."""
    from shapely.geometry import LineString, MultiLineString, MultiPoint
    from shapely.ops import voronoi_diagram

    vor = voronoi_diagram(MultiPoint(points), edges=True)
    out: list[tuple] = []
    geoms = list(vor.geoms) if hasattr(vor, "geoms") else [vor]
    for g in geoms:
        if isinstance(g, MultiLineString):
            out.extend(tuple(x.coords) for x in g.geoms)
        elif isinstance(g, LineString):
            out.append(tuple(g.coords))
    return out


def canon_edge(e: tuple) -> tuple:
    """Orientation-normalised edge, using exact float bits."""
    pts = tuple(tuple(c) for c in e)
    return (min(pts), max(pts)) if len(pts) == 2 else pts


def digest(obj: Any) -> str:
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Q1: determinism
# --------------------------------------------------------------------------


def probe_repeat(points, n: int = 20) -> dict:
    base = voronoi_edges(points)
    digests = {digest(voronoi_edges(points)) for _ in range(n)}
    return {
        "n_repeats": n,
        "n_edges": len(base),
        "distinct_digests": len(digests),
        "F1_fired": len(digests) != 1,
    }


def probe_subprocess(n: int = 3) -> dict:
    """Fresh interpreters, different PYTHONHASHSEED values."""
    results = []
    for i in range(n):
        env = dict(os.environ, PYTHONHASHSEED=str(i * 7 + 1))
        out = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child", str(i)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        results.append(json.loads(out.stdout.strip().splitlines()[-1]))
    seq = {r["seq_digest"] for r in results}
    return {
        "n_processes": n,
        "hashseeds": [r["hashseed"] for r in results],
        "distinct_seq_digests": len(seq),
        "cross_process_stable": len(seq) == 1,
    }


def probe_permutation(points, n_perms: int = 8) -> dict:
    base_seq = voronoi_edges(points)
    base_set = {canon_edge(e) for e in base_seq}
    base_seq_canon = [canon_edge(e) for e in base_seq]

    set_diffs, seq_diffs, coord_only_diffs = 0, 0, 0
    max_extra = 0
    example: dict[str, Any] = {}

    for s in range(n_perms):
        rng = random.Random(1000 + s)
        perm = list(points)
        rng.shuffle(perm)
        seq = voronoi_edges(perm)
        st = {canon_edge(e) for e in seq}
        seq_canon = [canon_edge(e) for e in seq]

        if st != base_set:
            set_diffs += 1
            extra = len(st ^ base_set)
            max_extra = max(max_extra, extra)
            if not example:
                only_perm = sorted(st - base_set)[:2]
                only_base = sorted(base_set - st)[:2]
                example = {
                    "seed": 1000 + s,
                    "symmetric_difference_size": extra,
                    "base_edge_count": len(base_set),
                    "perm_edge_count": len(st),
                    "sample_only_in_permuted": only_perm,
                    "sample_only_in_base": only_base,
                }
        if seq_canon != base_seq_canon:
            seq_diffs += 1
        # rounded comparison: do the sets agree once coordinates are snapped?
        if {_round_edge(e) for e in seq_canon} != {_round_edge(e) for e in base_seq_canon}:
            coord_only_diffs += 1

    return {
        "n_permutations": n_perms,
        "base_edge_count": len(base_set),
        "F2_fired_set_changed": set_diffs > 0,
        "permutations_with_set_change": set_diffs,
        "F3_fired_sequence_changed": seq_diffs > 0,
        "permutations_with_sequence_change": seq_diffs,
        "permutations_differing_after_1e-9_rounding": coord_only_diffs,
        "max_symmetric_difference": max_extra,
        "example": example,
    }


def _round_edge(e: tuple, nd: int = 9) -> tuple:
    return tuple(tuple(round(c, nd) for c in pt) for pt in e)


# --------------------------------------------------------------------------
# Q2/Q3: does divergence reach the consumer?
# --------------------------------------------------------------------------


def build_skeleton_graph(mod, polygon, points_order=None):
    """Run the production medial-axis + graph build. When `points_order` is
    given the Voronoi input is permuted, standing in for any implementation
    whose edge emission order differs from GEOS's."""
    import networkx as nx

    if points_order is None:
        lines = mod._extract_medial_axis_single(polygon, 0.5)
    else:
        lines = _extract_medial_axis_single_permuted(mod, polygon, points_order)

    G = nx.Graph()
    total = 0.0
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i + 1]
            G.add_node(p1, pos=p1)
            G.add_node(p2, pos=p2)
            length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            G.add_edge(p1, p2, weight=length)
            total += length
    G = mod._ensure_skeleton_connectivity(G, max_bridge_distance=10.0)
    return G, total


def _extract_medial_axis_single_permuted(mod, polygon, points):
    """Same filter/simplify pipeline as `_extract_medial_axis_single`, but with
    a caller-supplied Voronoi input ordering."""
    import shapely.prepared
    from shapely.geometry import LineString, MultiLineString, MultiPoint
    from shapely.ops import voronoi_diagram

    vor = voronoi_diagram(MultiPoint(points), edges=True)
    raw: list[Any] = []
    geoms = list(vor.geoms) if hasattr(vor, "geoms") else [vor]
    for g in geoms:
        if isinstance(g, MultiLineString):
            raw.extend(list(g.geoms))
        elif isinstance(g, LineString):
            raw.append(g)

    prepped = shapely.prepared.prep(polygon.buffer(1e-3))
    out = []
    for geom in raw:
        if isinstance(geom, LineString):
            mid = geom.interpolate(0.5, normalized=True)
            if prepped.contains(mid):
                simp = geom.simplify(0.5)
                if simp.length > 0:
                    out.append(simp)
    return out


def consumer_edge_ids(G, layer_name: str = "F.Cu") -> list[str]:
    """Reproduce the identifiers `constraint_model.py` derives from the
    skeleton (`_create_per_net_channel_vars`, lines 325-337):

        for i, (u, v) in enumerate(skeleton.graph.edges):
            n1, n2 = sorted([u, v])
            edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
    """
    ids = []
    for i, (u, v) in enumerate(G.edges):
        n1, n2 = sorted([u, v])
        ids.append(f"{layer_name}_E{i}_{n1}_{n2}")
    return ids


def probe_consumer(mod, area) -> dict:
    polys = list(area.geoms)
    target = max(polys, key=lambda p: p.area)
    points = sample_boundary_points(target)

    G_base, len_base = build_skeleton_graph(mod, target)
    ids_base = consumer_edge_ids(G_base)

    rng = random.Random(2026)
    perm = list(points)
    rng.shuffle(perm)
    G_perm, len_perm = build_skeleton_graph(mod, target, points_order=perm)
    ids_perm = consumer_edge_ids(G_perm)

    nodes_base, nodes_perm = set(G_base.nodes), set(G_perm.nodes)
    edges_base = {tuple(sorted([u, v])) for u, v in G_base.edges}
    edges_perm = {tuple(sorted([u, v])) for u, v in G_perm.edges}

    # Would a topology-only contract have been satisfied?
    import networkx as nx

    return {
        "base_nodes": G_base.number_of_nodes(),
        "perm_nodes": G_perm.number_of_nodes(),
        "base_edges": G_base.number_of_edges(),
        "perm_edges": G_perm.number_of_edges(),
        "node_sets_identical": nodes_base == nodes_perm,
        "node_symmetric_difference": len(nodes_base ^ nodes_perm),
        "edge_sets_identical": edges_base == edges_perm,
        "edge_symmetric_difference": len(edges_base ^ edges_perm),
        "total_length_base": len_base,
        "total_length_perm": len_perm,
        "total_length_abs_delta": abs(len_base - len_perm),
        "graphs_isomorphic": nx.is_isomorphic(G_base, G_perm),
        "consumer_edge_ids_identical": ids_base == ids_perm,
        "consumer_edge_ids_first_divergence_index": next(
            (i for i, (a, b) in enumerate(zip(ids_base, ids_perm, strict=False)) if a != b),
            None,
        ),
        "consumer_edge_id_base_sample": ids_base[0] if ids_base else None,
        "consumer_edge_id_perm_sample": ids_perm[0] if ids_perm else None,
        "F4_fired": not (nodes_base == nodes_perm and ids_base == ids_perm),
    }


def probe_canonicalisation() -> dict:
    """GEOS's permutation-invariance should come from canonicalising its input
    (JTS `DelaunayTriangulationBuilder` sorts sites and drops repeats before
    triangulating). If so, reversing the input and injecting duplicate sites
    must both be no-ops -- including on a maximally degenerate cocircular set,
    where an order-sensitive implementation would be free to differ."""
    cocircular = [
        (0.0, 0.0),
        (1.0, 0.0),
        (0.0, 1.0),
        (1.0, 1.0),
        (0.5, 0.5),
        (2.0, 2.0),
        (2.0, 0.0),
        (0.0, 2.0),
    ]
    base = digest(voronoi_edges(cocircular))
    return {
        "input": "unit square + centre + 3 outer sites (4 cocircular corners)",
        "base_digest": base,
        "reversed_matches": digest(voronoi_edges(cocircular[::-1])) == base,
        "shuffled_matches": digest(
            voronoi_edges(random.Random(3).sample(cocircular, len(cocircular)))
        )
        == base,
        "duplicate_sites_are_noop": digest(
            voronoi_edges(cocircular + [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5)])
        )
        == base,
    }


def qhull_medial_axis(polygon, points, simplify_tolerance: float = 0.5):
    """Same filter/simplify pipeline as `_extract_medial_axis_single`, but the
    Voronoi comes from Qhull (scipy.spatial.Voronoi) instead of GEOS.

    Qhull stands in here for a Rust-side Voronoi (`voronator`, `spade`, `geo`):
    an independent, mature, non-GEOS implementation of the same mathematical
    object. Infinite ridges are dropped (GEOS clips them to an envelope
    instead); the interior-only comparison below isolates genuine algorithmic
    divergence from that clipping-convention difference.
    """
    import shapely.prepared
    from scipy.spatial import Voronoi as QhullVoronoi
    from shapely.geometry import LineString

    vor = QhullVoronoi([list(p) for p in points])
    prepped = shapely.prepared.prep(polygon.buffer(1e-3))

    out = []
    for va, vb in vor.ridge_vertices:
        if va < 0 or vb < 0:
            continue  # infinite ridge
        pa = tuple(vor.vertices[va])
        pb = tuple(vor.vertices[vb])
        if pa == pb:
            continue
        geom = LineString([pa, pb])
        mid = geom.interpolate(0.5, normalized=True)
        if prepped.contains(mid):
            simp = geom.simplify(simplify_tolerance)
            if simp.length > 0:
                out.append(simp)
    return out


def _graph_from_lines(mod, lines):
    import networkx as nx

    G = nx.Graph()
    total = 0.0
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i + 1]
            G.add_node(p1, pos=p1)
            G.add_node(p2, pos=p2)
            length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            G.add_edge(p1, p2, weight=length)
            total += length
    G = mod._ensure_skeleton_connectivity(G, max_bridge_distance=10.0)
    return G, total


def probe_cross_implementation(mod, area) -> dict:
    """Q4: would an independent Voronoi implementation reproduce GEOS's
    skeleton? This is the parity bar gate G2 (`==`, not tolerance) demands."""
    import networkx as nx

    target = max(area.geoms, key=lambda p: p.area)
    points = sample_boundary_points(target)

    G_geos, len_geos = build_skeleton_graph(mod, target)
    G_qh, len_qh = _graph_from_lines(mod, qhull_medial_axis(target, points))

    n_geos, n_qh = set(G_geos.nodes), set(G_qh.nodes)
    ids_geos = consumer_edge_ids(G_geos)
    ids_qh = consumer_edge_ids(G_qh)

    # Interior-only view: nodes strictly inside the polygon, which excludes
    # anything attributable to GEOS's envelope clipping of infinite ridges.
    from shapely.geometry import Point

    inner = target.buffer(-0.05)
    ni_geos = {n for n in n_geos if inner.contains(Point(n))}
    ni_qh = {n for n in n_qh if inner.contains(Point(n))}

    rounded = {}
    for nd in (9, 6, 3, 2):
        a = {tuple(round(c, nd) for c in n) for n in ni_geos}
        b = {tuple(round(c, nd) for c in n) for n in ni_qh}
        rounded[f"interior_nodes_match_at_{nd}dp"] = a == b
        rounded[f"interior_node_symdiff_at_{nd}dp"] = len(a ^ b)

    return {
        "geos_nodes": G_geos.number_of_nodes(),
        "qhull_nodes": G_qh.number_of_nodes(),
        "geos_edges": G_geos.number_of_edges(),
        "qhull_edges": G_qh.number_of_edges(),
        "node_sets_identical": n_geos == n_qh,
        "node_symmetric_difference": len(n_geos ^ n_qh),
        "interior_geos_nodes": len(ni_geos),
        "interior_qhull_nodes": len(ni_qh),
        "interior_node_sets_identical": ni_geos == ni_qh,
        "interior_node_symmetric_difference": len(ni_geos ^ ni_qh),
        **rounded,
        "total_length_geos": len_geos,
        "total_length_qhull": len_qh,
        "total_length_abs_delta": abs(len_geos - len_qh),
        "total_length_rel_delta": abs(len_geos - len_qh) / max(len_geos, 1e-12),
        "graphs_isomorphic": nx.is_isomorphic(G_geos, G_qh),
        "consumer_edge_ids_identical": ids_geos == ids_qh,
        "consumer_edge_ids_first_divergence_index": next(
            (i for i, (a, b) in enumerate(zip(ids_geos, ids_qh, strict=False)) if a != b),
            None,
        ),
        "consumer_edge_id_geos_sample": ids_geos[0] if ids_geos else None,
        "consumer_edge_id_qhull_sample": ids_qh[0] if ids_qh else None,
    }


def probe_cross_implementation_sweep(mod, n_boards: int = 12) -> dict:
    """Q4 over many boards: is the GEOS/Qhull agreement structural or a
    one-off? Reports the worst case across boards."""
    import networkx as nx

    rows = []
    for seed in range(n_boards):
        area = build_routing_area(seed=seed, n_pads=6 + (seed % 7))
        target = max(area.geoms, key=lambda p: p.area)
        points = sample_boundary_points(target)
        if len(points) < 3:
            continue
        G_geos, len_geos = build_skeleton_graph(mod, target)
        G_qh, len_qh = _graph_from_lines(mod, qhull_medial_axis(target, points))

        n_geos = {tuple(round(c, 9) for c in n) for n in G_geos.nodes}
        n_qh = {tuple(round(c, 9) for c in n) for n in G_qh.nodes}
        exact_geos, exact_qh = set(G_geos.nodes), set(G_qh.nodes)

        rows.append(
            {
                "seed": seed,
                "sites": len(points),
                "geos_nodes": G_geos.number_of_nodes(),
                "qhull_nodes": G_qh.number_of_nodes(),
                "geos_edges": G_geos.number_of_edges(),
                "qhull_edges": G_qh.number_of_edges(),
                "node_counts_equal": G_geos.number_of_nodes() == G_qh.number_of_nodes(),
                "edge_counts_equal": G_geos.number_of_edges() == G_qh.number_of_edges(),
                "isomorphic": nx.is_isomorphic(G_geos, G_qh),
                "exact_node_symdiff": len(exact_geos ^ exact_qh),
                "symdiff_at_9dp": len(n_geos ^ n_qh),
                "len_rel_delta": abs(len_geos - len_qh) / max(len_geos, 1e-12),
                "consumer_ids_equal": consumer_edge_ids(G_geos) == consumer_edge_ids(G_qh),
            }
        )

    return {
        "n_boards": len(rows),
        "boards_with_equal_node_counts": sum(r["node_counts_equal"] for r in rows),
        "boards_isomorphic": sum(r["isomorphic"] for r in rows),
        "boards_matching_at_9dp": sum(r["symdiff_at_9dp"] == 0 for r in rows),
        "boards_matching_exactly": sum(r["exact_node_symdiff"] == 0 for r in rows),
        "boards_with_equal_consumer_ids": sum(r["consumer_ids_equal"] for r in rows),
        "worst_symdiff_at_9dp": max((r["symdiff_at_9dp"] for r in rows), default=0),
        "worst_exact_node_symdiff": max((r["exact_node_symdiff"] for r in rows), default=0),
        "worst_len_rel_delta": max((r["len_rel_delta"] for r in rows), default=0.0),
        "rows": rows,
    }


def probe_ulp_sensitivity(mod, area) -> dict:
    """How much coordinate divergence does the consumer contract tolerate?
    Perturb every Voronoi input site by one ULP and count how many
    consumer-visible identifiers change."""
    import math

    target = max(area.geoms, key=lambda p: p.area)
    points = sample_boundary_points(target)
    G_base, _ = build_skeleton_graph(mod, target)
    ids_base = consumer_edge_ids(G_base)

    nudged = [(math.nextafter(x, math.inf), y) for x, y in points]
    G_ulp, _ = build_skeleton_graph(mod, target, points_order=nudged)
    ids_ulp = consumer_edge_ids(G_ulp)

    changed = sum(1 for a, b in zip(ids_base, ids_ulp, strict=False) if a != b) + abs(
        len(ids_base) - len(ids_ulp)
    )
    return {
        "perturbation": "one ULP on the x of every Voronoi input site",
        "base_consumer_ids": len(ids_base),
        "perturbed_consumer_ids": len(ids_ulp),
        "consumer_ids_changed": changed,
        "consumer_ids_identical": ids_base == ids_ulp,
        "node_sets_identical": set(G_base.nodes) == set(G_ulp.nodes),
    }


def probe_rounding_recovery(mod, area, nd_list=(9, 6, 3)) -> dict:
    """If coordinates were snapped to a grid, would the two skeletons agree?
    This bounds how much of the divergence is pure float noise."""
    polys = list(area.geoms)
    target = max(polys, key=lambda p: p.area)
    points = sample_boundary_points(target)
    G_base, _ = build_skeleton_graph(mod, target)
    rng = random.Random(2026)
    perm = list(points)
    rng.shuffle(perm)
    G_perm, _ = build_skeleton_graph(mod, target, points_order=perm)

    out = {}
    for nd in nd_list:
        nb = {tuple(round(c, nd) for c in n) for n in G_base.nodes}
        np_ = {tuple(round(c, nd) for c in n) for n in G_perm.nodes}
        out[f"nodes_match_at_{nd}dp"] = nb == np_
        out[f"node_symdiff_at_{nd}dp"] = len(nb ^ np_)
    return out


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--child", type=int, default=None)
    args = ap.parse_args()

    import shapely

    area = build_routing_area()
    target = max(area.geoms, key=lambda p: p.area)
    points = sample_boundary_points(target)

    if args.child is not None:
        seq = voronoi_edges(points)
        print(
            json.dumps(
                {
                    "hashseed": os.environ.get("PYTHONHASHSEED"),
                    "seq_digest": digest(seq),
                    "n_edges": len(seq),
                }
            )
        )
        return 0

    mod = load_production_module()

    report = {
        "environment": {
            "python": sys.version.split()[0],
            "shapely": shapely.__version__,
            "geos": ".".join(str(x) for x in shapely.geos_version),
            "platform": sys.platform,
        },
        "input": {
            "description": "board box(0,0,40,30) minus 9 pad rectangles "
            "(mirrors RoutingSpace.available_area = board - obstacles)",
            "largest_polygon_area_mm2": target.area,
            "boundary_sample_points": len(points),
        },
        "Q1_repeat_determinism": probe_repeat(points),
        "Q1_cross_process_determinism": probe_subprocess(),
        "Q1_permutation_sensitivity": probe_permutation(points),
        "Q1_canonicalisation_mechanism": probe_canonicalisation(),
        "Q2_Q3_consumer_impact": probe_consumer(mod, area),
        "Q3_rounding_recovery": probe_rounding_recovery(mod, area),
        "Q3_ulp_sensitivity": probe_ulp_sensitivity(mod, area),
        "Q4_cross_implementation_geos_vs_qhull": probe_cross_implementation(mod, area),
        "Q4_cross_implementation_sweep": probe_cross_implementation_sweep(mod),
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
