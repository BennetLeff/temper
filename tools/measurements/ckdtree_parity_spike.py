#!/usr/bin/env python3
"""Spike S2: is ``scipy.spatial.cKDTree`` result order observable downstream?

Measures, for the two ``router_v6`` modules the Wave-4 migration survey put in
the BLOCKED bucket on this primitive
(``docs/evidence/2026-08-04-router-v6-migration-survey.md`` §2.3):

* ``router_v6/constraints_spatial_index.py`` -- three ``cKDTree`` builds, three
  ``query_ball_point`` call sites, no kNN at all.
* ``router_v6/_zone_pour_stitch.py`` -- one ``cKDTree`` build, one ``query()``
  (k=1) whose returned *index* selects the endpoint of an emitted KiCad
  ``(segment ...)``.

The experiments deliberately do **not** need a Rust k-d tree. Each one perturbs
the tie-break/ordering *within Python* -- by permuting insertion order, by
rotating a polygon ring, or by substituting a brute-force index-ordered
reference tree -- and asks whether a production output changes.

Nothing here mutates production code. ``E3`` monkeypatches the ``cKDTree`` name
*inside this process only*, to stand in for "a Rust port that returns indices in
ascending order", which is what every straightforward radius-search port does.

Run (from the repo root, with the workspace venv):

    ./.venv/bin/python tools/measurements/ckdtree_parity_spike.py

Individual experiments: ``--only e1`` ... ``--only e5``.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import math
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[2]
if importlib.util.find_spec("temper_placer") is None:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

PRODUCTION_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


# ---------------------------------------------------------------------------
# Reference implementation: what a straightforward Rust radius search returns
# ---------------------------------------------------------------------------


class IndexOrderTree:
    """Brute-force stand-in for ``cKDTree`` that returns ascending indices.

    Mirrors only the surface ``constraints_spatial_index`` actually uses:
    construction from an (n, 2) array and ``query_ball_point(point, radius)``.
    Membership uses the same ``<=`` predicate on the *unsquared* Euclidean
    distance that ``cKDTree`` documents, so any divergence this class shows
    against ``cKDTree`` is an ordering difference, not a membership one.
    """

    def __init__(self, data: object) -> None:
        self.data = np.asarray(data, dtype=float)

    def query_ball_point(self, point: object, radius: float) -> list[int]:
        p = np.asarray(point, dtype=float)
        d = np.hypot(self.data[:, 0] - p[0], self.data[:, 1] - p[1])
        return [int(i) for i in np.nonzero(d <= radius)[0]]


class SortedCKDTree(cKDTree):
    """``cKDTree`` with ``return_sorted=True`` forced on radius queries.

    Stands for the single-keyword precondition that would let a Rust port
    match: scipy's ``return_sorted`` default is ``None``, which means "do not
    sort single-point queries", and that default is the entire source of the
    ordering divergence E1/E3 measure.
    """

    def query_ball_point(self, x, r, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
        kwargs["return_sorted"] = True
        return super().query_ball_point(x, r, *args, **kwargs)


# ---------------------------------------------------------------------------
# E1 -- is query_ball_point's returned order the input index order?
# ---------------------------------------------------------------------------


def _grid_points(rng: np.random.Generator, n: int, pitch: float) -> np.ndarray:
    """PCB-like point set: everything snapped to a regular pitch."""
    side = int(math.ceil(math.sqrt(n * 4)))
    cells = rng.choice(side * side, size=n, replace=False)
    xs = (cells % side) * pitch
    ys = (cells // side) * pitch
    return np.column_stack([xs, ys]).astype(float)


def experiment_e1(seed: int = 20260804) -> dict[str, object]:
    """Census: how often is ``query_ball_point``'s output not in index order?"""
    rng = np.random.default_rng(seed)
    stats: dict[str, dict[str, int]] = {}

    for label, maker in (
        ("uniform-random", lambda n: rng.random((n, 2)) * 100.0),
        ("grid-0.1mm", lambda n: _grid_points(rng, n, 0.1)),
        ("grid-1.27mm", lambda n: _grid_points(rng, n, 1.27)),
    ):
        s = {"queries": 0, "nonempty": 0, "unsorted": 0, "set_mismatch": 0, "max_hits": 0}
        for _ in range(400):
            n = int(rng.integers(4, 600))
            pts = maker(n)
            tree = cKDTree(pts)
            for _ in range(10):
                q = pts[int(rng.integers(0, n))] + rng.normal(0.0, 1.0, 2)
                r = float(rng.uniform(0.5, 25.0))
                got = tree.query_ball_point([q[0], q[1]], r)
                ref = IndexOrderTree(pts).query_ball_point([q[0], q[1]], r)
                s["queries"] += 1
                if got:
                    s["nonempty"] += 1
                    s["max_hits"] = max(s["max_hits"], len(got))
                    if list(got) != sorted(got):
                        s["unsorted"] += 1
                if set(got) != set(ref):
                    s["set_mismatch"] += 1
        stats[label] = s

    return {"name": "E1 query_ball_point return order", "stats": stats}


# ---------------------------------------------------------------------------
# E2 -- is *membership* invariant under insertion-order permutation?
# ---------------------------------------------------------------------------


def experiment_e2(seed: int = 4242) -> dict[str, object]:
    """Permute insertion order; check the returned *set* of points is stable.

    Also probes the exact-boundary case (radius set to a point's exact
    distance), which is where a ``<=`` predicate can disagree between
    implementations independently of any ordering question.
    """
    rng = np.random.default_rng(seed)
    trials = 0
    set_mismatch = 0
    order_mismatch = 0
    boundary_trials = 0
    boundary_mismatch = 0

    for _ in range(600):
        n = int(rng.integers(5, 300))
        pts = _grid_points(rng, n, 0.1)
        q = np.array([float(rng.uniform(0, 20)), float(rng.uniform(0, 20))])
        r = float(rng.uniform(0.5, 6.0))

        base = cKDTree(pts)
        base_idx = base.query_ball_point([q[0], q[1]], r)
        base_pts = {tuple(pts[i]) for i in base_idx}
        base_seq = [tuple(pts[i]) for i in base_idx]

        perm = rng.permutation(n)
        ptree = cKDTree(pts[perm])
        perm_idx = ptree.query_ball_point([q[0], q[1]], r)
        perm_pts = {tuple(pts[perm][i]) for i in perm_idx}
        perm_seq = [tuple(pts[perm][i]) for i in perm_idx]

        trials += 1
        if base_pts != perm_pts:
            set_mismatch += 1
        if base_seq != perm_seq:
            order_mismatch += 1

        # Exact-boundary probe: radius == the distance to some stored point.
        d = np.hypot(pts[:, 0] - q[0], pts[:, 1] - q[1])
        r_exact = float(d[int(np.argmin(np.abs(d - r)))])
        boundary_trials += 1
        b_base = {tuple(pts[i]) for i in base.query_ball_point([q[0], q[1]], r_exact)}
        b_perm = {tuple(pts[perm][i]) for i in ptree.query_ball_point([q[0], q[1]], r_exact)}
        if b_base != b_perm:
            boundary_mismatch += 1

    return {
        "name": "E2 query_ball_point membership under permutation",
        "trials": trials,
        "set_mismatch": set_mismatch,
        "order_mismatch": order_mismatch,
        "boundary_trials": boundary_trials,
        "boundary_mismatch": boundary_mismatch,
    }


# ---------------------------------------------------------------------------
# E3 -- does module 1's ordering reach an observable DRCOracle output?
# ---------------------------------------------------------------------------


def _build_oracle_geometry(
    rng: np.random.Generator, module: object, oracle: object, scale: int, span: int
) -> None:
    """Populate an oracle with grid-snapped, deliberately crowded geometry.

    ``span`` is the number of 0.5 mm grid cells per side: shrinking it while
    holding ``scale`` raises density, which is what makes several violating
    neighbours land inside one query radius.
    """
    nets = ["NET_A", "NET_B", "NET_C", "GND"]
    for i in range(40 * scale):
        x = round(float(rng.integers(0, span)) * 0.5, 4)
        y = round(float(rng.integers(0, span)) * 0.5, 4)
        oracle.register_pad(
            module.Pad(
                center=module.Point(x, y),
                shape="rect",
                size=(0.8, 0.8),
                net=nets[i % len(nets)],
                layer=0,
            )
        )
    for i in range(60 * scale):
        x = round(float(rng.integers(0, span)) * 0.5, 4)
        y = round(float(rng.integers(0, span)) * 0.5, 4)
        dx, dy = ((0.5, 0.0), (0.0, 0.5))[i % 2]
        oracle.register_track(
            module.Track(
                start=module.Point(x, y),
                end=module.Point(x + dx, y + dy),
                width=0.25,
                net=nets[(i + 1) % len(nets)],
                layer=0,
            )
        )
    for i in range(25 * scale):
        x = round(float(rng.integers(0, span)) * 0.5, 4)
        y = round(float(rng.integers(0, span)) * 0.5, 4)
        oracle.register_via(
            module.Via(
                center=module.Point(x, y),
                diameter=0.6,
                drill=0.3,
                net=nets[(i + 2) % len(nets)],
            )
        )


def _run_oracle_probe(tree_cls: object, seed: int, scale: int, span: int) -> dict[str, object]:
    """Build + probe a DRCOracle with ``tree_cls`` installed as the index."""
    import temper_placer.router_v6.constraints_spatial_index as idx_mod
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
    from temper_placer.router_v6.constraints_drc_oracle import DRCOracle

    original = idx_mod.cKDTree
    idx_mod.cKDTree = tree_cls  # process-local substitution; see module docstring
    try:
        rng = np.random.default_rng(seed)
        oracle = DRCOracle(rules=ClearanceMatrix())
        _build_oracle_geometry(rng, idx_mod, oracle, scale, span)
        oracle.geometry.rebuild_index()

        seg_probes = []
        probe_rng = np.random.default_rng(seed + 1)
        for _ in range(200):
            x = round(float(probe_rng.integers(0, span)) * 0.5, 4)
            y = round(float(probe_rng.integers(0, span)) * 0.5, 4)
            seg_probes.append(
                oracle.can_place_track_segment(
                    start=(x, y), end=(x + 0.5, y), layer=0, net="NET_D", width=0.25
                )
            )

        via_probes = []
        for _ in range(200):
            x = round(float(probe_rng.integers(0, span)) * 0.5, 4)
            y = round(float(probe_rng.integers(0, span)) * 0.5, 4)
            via_probes.append(oracle.can_place_via((x, y), 0.6, "NET_D"))

        violations = oracle.validate_all()
        vio_seq = [
            (v.type, v.geometry_a_id, v.geometry_b_id, v.clearance_actual, v.clearance_required)
            for v in violations
        ]
        return {"segments": seg_probes, "vias": via_probes, "violations": vio_seq}
    finally:
        idx_mod.cKDTree = original


def _compare_one(seed: int, scale: int, span: int, tree_a: object = cKDTree) -> dict[str, object]:
    a = _run_oracle_probe(tree_a, seed, scale, span)
    b = _run_oracle_probe(IndexOrderTree, seed, scale, span)

    def _split(pairs: list[tuple[bool, str]]) -> tuple[list[bool], list[str]]:
        return [p[0] for p in pairs], [p[1] for p in pairs]

    seg_ok_a, seg_msg_a = _split(a["segments"])
    seg_ok_b, seg_msg_b = _split(b["segments"])
    via_ok_a, via_msg_a = _split(a["vias"])
    via_ok_b, via_msg_b = _split(b["vias"])

    seg_msg_diff = [i for i in range(len(seg_msg_a)) if seg_msg_a[i] != seg_msg_b[i]]
    via_msg_diff = [i for i in range(len(via_msg_a)) if via_msg_a[i] != via_msg_b[i]]

    example = None
    if seg_msg_diff:
        i = seg_msg_diff[0]
        example = {"cKDTree": seg_msg_a[i], "index_order": seg_msg_b[i]}
    elif via_msg_diff:
        i = via_msg_diff[0]
        example = {"cKDTree": via_msg_a[i], "index_order": via_msg_b[i]}

    first_vio_diff = next(
        (
            {"cKDTree": x, "index_order": y}
            for x, y in itertools.zip_longest(a["violations"], b["violations"])
            if x != y
        ),
        None,
    )

    return {
        "geometry": f"scale={scale} span={span} "
        f"({40 * scale} pads, {60 * scale} tracks, {25 * scale} vias)",
        "segment_probes": len(seg_ok_a),
        "segment_rejections": sum(1 for x in seg_ok_a if not x),
        "segment_bool_diffs": sum(1 for x, y in zip(seg_ok_a, seg_ok_b, strict=True) if x != y),
        "segment_msg_diffs": len(seg_msg_diff),
        "via_probes": len(via_ok_a),
        "via_rejections": sum(1 for x in via_ok_a if not x),
        "via_bool_diffs": sum(1 for x, y in zip(via_ok_a, via_ok_b, strict=True) if x != y),
        "via_msg_diffs": len(via_msg_diff),
        "violations_ckdtree": len(a["violations"]),
        "violations_index_order": len(b["violations"]),
        "violation_multiset_equal": sorted(a["violations"]) == sorted(b["violations"]),
        "violation_sequence_equal": a["violations"] == b["violations"],
        "first_message_divergence": example,
        "first_violation_sequence_divergence": first_vio_diff,
    }


def experiment_e3(seed: int = 991) -> dict[str, object]:
    """Compare every DRCOracle output under cKDTree vs an index-ordered tree.

    Swept over three densities: order can only become observable when several
    *violating* neighbours share one query result, so a sparse board proves
    nothing on its own.
    """
    cases = [
        ("sparse", 1, 40),
        ("dense", 2, 20),
        ("very-dense", 4, 12),
    ]
    out: dict[str, object] = {
        "name": "E3 DRCOracle observable outputs, cKDTree vs index-order tree"
    }
    for i, (label, scale, span) in enumerate(cases):
        out[label] = _compare_one(seed + i, scale, span)
    # Control arm: the same comparison with return_sorted=True forced on.
    out["very-dense/return_sorted=True"] = _compare_one(seed + 2, 4, 12, tree_a=SortedCKDTree)
    return out


# ---------------------------------------------------------------------------
# Real production zone polygons (shared by E4 and E5)
# ---------------------------------------------------------------------------


def _real_pad_positions() -> dict[str, list[tuple[float, float]]]:
    """Replicate ``_adapter_convert._write_routes_to_content``'s pad-position
    collection verbatim, against the production board."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    pcb = parse_kicad_pcb_v6(PRODUCTION_BOARD)
    comp_by_ref = {c.ref: c for c in pcb.components}
    out: dict[str, list[tuple[float, float]]] = {}
    for net in pcb.nets:
        positions: list[tuple[float, float]] = []
        for comp_ref, pin_name in getattr(net, "pins", []):
            comp = comp_by_ref.get(comp_ref)
            if comp is None:
                continue
            comp_pos = getattr(comp, "initial_position", (0.0, 0.0))
            pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
            if pin is None:
                positions.append((float(comp_pos[0]), float(comp_pos[1])))
            else:
                px, py = pin.position
                positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
        if positions:
            out[net.name] = positions
    return out


def _real_zone_points(
    margin_override: float | None = None,
    cluster_override: bool | None = None,
) -> tuple[
    dict[str, list[tuple[float, float]]],
    dict[str, list[tuple[tuple[float, float], ...]]],
]:
    """Build the real ``zone_points`` dict ``_stitch_isolated_pads`` receives.

    Replicates ``_emit_zone_pours``'s loop, including ``cluster=not exempt``
    -- every zone-eligible net on this board is ACMains or HighVoltage, both
    of which are in ``_CONTINUITY_EXEMPT_CLASSES``, so production always takes
    the single-hull (``cluster=False``) path.

    ``margin_override`` replaces ``_zone_params_for_net``'s value. Production
    is 6.0 mm (the ACMains/HighVoltage clearance); the override exists to shrink
    the pour until pads fall outside it, which is the only way to exercise the
    ``cKDTree`` branch at all on this board.
    """
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
    from temper_placer.router_v6._zone_pour_stitch import (
        _CONTINUITY_EXEMPT_CLASSES,
        _zone_layers_for_net,
        _zone_params_for_net,
    )
    from temper_placer.router_v6.zone_emission import compute_zones_for_net

    pad_positions = _real_pad_positions()
    zone_points: dict[str, list[tuple[tuple[float, float], ...]]] = {}
    for net_name, positions in pad_positions.items():
        layers = _zone_layers_for_net(net_name)
        if not layers or not positions:
            continue
        margin, _clearance = _zone_params_for_net(net_name)
        if margin_override is not None:
            margin = margin_override
        exempt = TEMPER_NET_ASSIGNMENTS.get(net_name, "") in _CONTINUITY_EXEMPT_CLASSES
        cluster = (not exempt) if cluster_override is None else cluster_override
        for layer in layers:
            try:
                for zd in compute_zones_for_net(
                    net_name, 1, positions, layer=layer, margin=margin, cluster=cluster
                ):
                    zone_points.setdefault(net_name, []).append(zd.points)
            except ValueError:
                pass
    return pad_positions, zone_points


# ---------------------------------------------------------------------------
# E4 -- do exact ties occur in _zone_pour_stitch's k=1 query, on real data?
# ---------------------------------------------------------------------------


def _tie_census(
    margin_override: float | None, cluster_override: bool | None = None
) -> dict[str, object]:
    """Tie census over the board's zone pours at a given pour margin.

    Replicates ``_stitch_isolated_pads``'s ``all_verts`` construction exactly
    (including shapely re-closing each ring, which reintroduces the duplicate
    first/last vertex ``_convex_hull_from_positions`` had popped) and counts,
    for each outside pad, how many vertices sit at the exact minimum distance
    and how many *distinct coordinates* are among them.
    """
    from shapely.geometry import Point as ShapelyPoint
    from shapely.geometry import Polygon

    pad_positions, zone_points = _real_zone_points(margin_override, cluster_override)

    nets_examined = 0
    queries = 0
    dup_vertex_rings = 0
    total_rings = 0
    tied_queries = 0
    tied_distinct_coord_queries = 0
    max_tie_multiplicity = 0
    examples: list[dict[str, object]] = []

    for net_name, positions in pad_positions.items():
        zps = zone_points.get(net_name)
        if not zps or len(positions) <= 1:
            continue
        pour_polys = [Polygon(pts) for pts in zps if len(pts) >= 3]
        if not pour_polys:
            continue
        nets_examined += 1

        outside = [
            (x, y)
            for x, y in positions
            if not any(
                p.contains(ShapelyPoint(x, y)) or p.touches(ShapelyPoint(x, y)) for p in pour_polys
            )
        ]
        all_verts: list[tuple[float, float]] = []
        for poly in pour_polys:
            total_rings += 1
            coords = [(float(x), float(y)) for x, y in poly.exterior.coords]
            if len(coords) > 1 and coords[0] == coords[-1]:
                dup_vertex_rings += 1
            all_verts.extend(coords)
        if not all_verts or not outside:
            continue

        arr = np.asarray(all_verts, dtype=float)
        for px, py in outside:
            queries += 1
            d = np.hypot(arr[:, 0] - px, arr[:, 1] - py)
            dmin = d.min()
            tied = np.nonzero(d == dmin)[0]
            max_tie_multiplicity = max(max_tie_multiplicity, int(tied.size))
            if tied.size > 1:
                tied_queries += 1
                distinct = {all_verts[int(i)] for i in tied}
                if len(distinct) > 1:
                    tied_distinct_coord_queries += 1
                    if len(examples) < 5:
                        examples.append(
                            {
                                "net": net_name,
                                "pad": (px, py),
                                "tied_indices": [int(i) for i in tied],
                                "distinct_coords": sorted(distinct),
                            }
                        )

    return {
        "nets_examined": nets_examined,
        "rings": total_rings,
        "rings_with_duplicate_closing_vertex": dup_vertex_rings,
        "outside_pad_queries": queries,
        "queries_with_exact_tie": tied_queries,
        "queries_with_distinct_coord_tie": tied_distinct_coord_queries,
        "max_tie_multiplicity": max_tie_multiplicity,
        "distinct_coord_tie_examples": examples,
    }


def experiment_e4() -> dict[str, object]:
    """Tie census at the production margin and at shrunken margins."""
    out: dict[str, object] = {
        "name": "E4 exact-tie census on real production zone pours",
        "board": str(PRODUCTION_BOARD.relative_to(REPO_ROOT)),
    }
    out["production (cluster=False, margin=6.0mm)"] = _tie_census(None)
    for m in (1.0, 0.3, 0.05):
        out[f"cluster=False, margin={m}mm"] = _tie_census(m)
    # Counterfactual: the only way the cKDTree branch becomes reachable is a
    # plane_required netclass outside _CONTINUITY_EXEMPT_CLASSES, which routes
    # compute_zones_for_net through cluster=True (several hulls per net, so a
    # pad can sit outside every one of them).
    for m in (6.0, 1.0, 0.3, 0.05):
        out[f"cluster=True, margin={m}mm"] = _tie_census(m, cluster_override=True)
    return out


# ---------------------------------------------------------------------------
# E5 -- falsifier: is _stitch_isolated_pads' output invariant under ring
#       rotation (a relabelling that leaves the polygon unchanged)?
# ---------------------------------------------------------------------------


def _stitch(
    pad_positions: dict[str, list[tuple[float, float]]],
    zone_points: dict[str, list[tuple[tuple[float, float], ...]]],
) -> list[str]:
    from temper_placer.router_v6._zone_pour_stitch import _stitch_isolated_pads

    segments: list[str] = []
    net_numbers = {name: i + 1 for i, name in enumerate(sorted(pad_positions))}
    _stitch_isolated_pads(pad_positions, segments, net_numbers, zone_points)
    return segments


def _rotate_rings(
    zone_points: dict[str, list[tuple[tuple[float, float], ...]]], k: int
) -> dict[str, list[tuple[tuple[float, float], ...]]]:
    """Rotate every ring's vertex list by k. Same polygon, different indices."""
    out: dict[str, list[tuple[tuple[float, float], ...]]] = {}
    for net, rings in zone_points.items():
        out[net] = [tuple(ring[k % len(ring) :]) + tuple(ring[: k % len(ring)]) for ring in rings]
    return out


def _crafted_tie_case() -> tuple[
    dict[str, list[tuple[float, float]]],
    dict[str, list[tuple[tuple[float, float], ...]]],
]:
    """A deliberately-tied configuration built from the real degenerate path.

    ``_convex_hull_from_positions`` emits an axis-aligned square for a
    single-position cluster. A pad on that square's vertical centre line is
    exactly equidistant from its two nearest corners -- two *distinct*
    coordinates. ``ac_l`` is a real ACMains net, so the netclass gate passes.
    """
    net = "ac_l"
    h = 6.0  # ACMains clearance -> margin, per _zone_params_for_net
    cx, cy = 50.0, 50.0
    square = (
        (cx - h, cy - h),
        (cx + h, cy - h),
        (cx + h, cy + h),
        (cx - h, cy + h),
    )
    # Pad on the square's vertical centre line, well below it: equidistant from
    # the two bottom corners.
    tied_pad = (cx, cy - h - 10.0)
    pad_positions = {net: [(cx, cy), tied_pad]}
    return pad_positions, {net: [square]}


def experiment_e5() -> dict[str, object]:
    """Run ``_stitch_isolated_pads`` for real; perturb only the index order."""
    results: dict[str, object] = {"name": "E5 _stitch_isolated_pads under ring rotation"}

    pad_positions, zone_points = _real_zone_points()
    base = _stitch(pad_positions, zone_points)
    rotated_diffs = []
    for k in range(1, 6):
        rot = _stitch(pad_positions, _rotate_rings(zone_points, k))
        if rot != base:
            rotated_diffs.append(
                {
                    "k": k,
                    "first_diff": next(
                        (
                            {"base": b, "rotated": r}
                            for b, r in itertools.zip_longest(base, rot)
                            if b != r
                        ),
                        None,
                    ),
                }
            )
    results["real_board"] = {
        "segments_emitted": len(base),
        "rotations_tested": 5,
        "rotations_changing_output": len(rotated_diffs),
        "diffs": rotated_diffs,
    }

    craft_pads, craft_zones = _crafted_tie_case()
    craft_base = _stitch(craft_pads, craft_zones)
    craft_variants = {}
    for k in range(4):
        craft_variants[k] = _stitch(craft_pads, _rotate_rings(craft_zones, k))
    distinct = {tuple(v) for v in craft_variants.values()}
    results["crafted_tie"] = {
        "segments_emitted": len(craft_base),
        "emitted": craft_base,
        "rotations_tested": 4,
        "distinct_outputs": len(distinct),
        "all_outputs": [list(v) for v in sorted(distinct)],
    }
    return results


# ---------------------------------------------------------------------------


EXPERIMENTS = {
    "e1": experiment_e1,
    "e2": experiment_e2,
    "e3": experiment_e3,
    "e4": experiment_e4,
    "e5": experiment_e5,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=sorted(EXPERIMENTS), default=None)
    args = parser.parse_args()

    names = [args.only] if args.only else sorted(EXPERIMENTS)
    for name in names:
        result = EXPERIMENTS[name]()
        print("=" * 72)
        print(result.pop("name"))
        print("=" * 72)
        for key, value in result.items():
            print(f"  {key}: {value}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
