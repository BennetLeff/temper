#!/usr/bin/env python3
"""Independent pad-level HV/SELV separability analysis for the isolation-barrier
DRC deployment blocker (docs/evidence/2026-08-08-isolation-barrier-geometry-analysis.md).

# provenance: commit=adf482564470c02cdf849c52be48db3ec0d5365a dirty=false

Uses ONLY project-blessed parsing/geometry code:

  - temper_placer.io.kicad_parser.parse_kicad_pcb  (the project's PCB parser)
  - temper_placer.core.pin_geometry.pin_world_position  (the canonical,
    rotation-and-side-aware pad-position function -- NOT the raw
    ParseResult.pads field, which this analysis found to skip footprint
    rotation entirely; see PARSER-BUG CHECK output below)
  - temper_placer.core.pad_geometry.pad_bounding_radius (exact, shape-aware,
    rotation-invariant conservative pad radius)
  - temper_placer.io.real_board._load_manifest (the project's own
    elec/domain_manifest.yaml reader)

Read-only against pcb/temper.kicad_pcb and elec/domain_manifest.yaml -- makes
no changes anywhere.

Usage (needs a Python environment with the compiled temper_design_bundle_python
extension available -- e.g. any already-built temper-placer .venv):
    PYTHONPATH=<repo>/packages/temper-placer/src <python> \
        docs/evidence/scripts/2026-08-08_isolation_barrier_analysis.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402
from temper_placer.core.pin_geometry import pin_world_position, pin_world_layer, pin_world_radius  # noqa: E402
from temper_placer.io.real_board import _load_manifest  # noqa: E402

PCB = REPO / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO / "elec" / "domain_manifest.yaml"
CLEARANCE_MM = 8.0  # IEC60335_REQUIREMENTS REINFORCED creepage, this project's live path


class PadRec:
    __slots__ = ("ref", "number", "x", "y", "net", "layer", "radius", "domain", "pin")

    def __init__(self, ref, number, x, y, net, layer, radius, domain, pin):
        self.ref = ref
        self.number = number
        self.x = x
        self.y = y
        self.net = net
        self.layer = layer
        self.radius = radius
        self.domain = domain
        self.pin = pin


def load_pads():
    result = parse_kicad_pcb(PCB, normalize=False)
    nl = result.netlist
    domains, _chains = _load_manifest(MANIFEST)
    hv_nets = set(domains["HV"])
    selv_nets = set(domains["SELV"])
    overlap = hv_nets & selv_nets
    assert not overlap, f"manifest declares nets in both domains: {overlap}"

    recs: list[PadRec] = []
    unclassified_nets: set[str] = set()
    for comp in nl.components:
        for pin in comp.pins:
            net = pin.net
            if net is None:
                continue
            if net in hv_nets:
                domain = "HV"
            elif net in selv_nets:
                domain = "SELV"
            else:
                unclassified_nets.add(net)
                continue
            x, y = pin_world_position(pin, comp)
            recs.append(
                PadRec(
                    ref=comp.ref,
                    number=pin.number,
                    x=x,
                    y=y,
                    net=net,
                    layer=pin_world_layer(pin),
                    radius=pin_world_radius(pin),
                    domain=domain,
                    pin=pin,
                )
            )
    return recs, hv_nets, selv_nets, unclassified_nets, result


def demonstrate_parser_bug(result):
    """Show that ParseResult.pads (the raw/naive field) disagrees with
    pin_world_position (the canonical helper) for a rotated footprint,
    to justify why this analysis does NOT use ParseResult.pads directly."""
    naive = {(p.component_ref, p.number): p.position for p in result.pads}
    nl = result.netlist
    mismatches = []
    for comp in nl.components:
        for pin in comp.pins:
            key = (comp.ref, pin.number)
            if key not in naive:
                continue
            wx, wy = pin_world_position(pin, comp)
            nx, ny = naive[key]
            if math.hypot(wx - nx, wy - ny) > 0.01:
                mismatches.append((comp.ref, pin.number, (nx, ny), (wx, wy)))
    return mismatches


def best_single_line(hv, selv):
    """Best axis-aligned single straight-line split (informative baseline,
    reproducing the 2026-08-03/2026-07-29 methodology on today's data)."""
    out = {}
    for axis in (0, 1):
        coords = sorted({(p.x if axis == 0 else p.y) for p in hv + selv})
        candidates = [(a + b) / 2 for a, b in zip(coords, coords[1:]) if b > a]
        best_pos, best_wrong = None, None
        for pos in candidates:
            def side(p, pos=pos, axis=axis):
                return (p.x > pos) if axis == 0 else (p.y > pos)
            wrong = sum(1 for p in hv if side(p)) + sum(1 for p in selv if not side(p))
            if best_wrong is None or wrong < best_wrong:
                best_wrong, best_pos = wrong, pos
        out["x" if axis == 0 else "y"] = (best_pos, best_wrong)
    return out


def bichromatic_delaunay_cycle(hv, selv):
    from scipy.spatial import Delaunay
    import networkx as nx

    pts = [(p.x, p.y) for p in hv + selv]
    labels = list(hv) + list(selv)
    colors = ["HV"] * len(hv) + ["SELV"] * len(selv)
    tri = Delaunay(pts)
    g = nx.Graph()
    g.add_nodes_from(range(len(pts)))
    for simplex in tri.simplices:
        for i in range(3):
            a, b = simplex[i], simplex[(i + 1) % 3]
            if colors[a] != colors[b]:
                g.add_edge(a, b)
    try:
        cycle_edges = nx.find_cycle(g)
    except nx.NetworkXNoCycle:
        return None
    adj = {}
    for a, b in cycle_edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    start = cycle_edges[0][0]
    order = [start]
    prev, cur = None, start
    while True:
        nxts = [n for n in adj[cur] if n != prev]
        if not nxts:
            break
        nxt = nxts[0]
        if nxt == start and len(order) > 2:
            break
        order.append(nxt)
        prev, cur = cur, nxt
        if len(order) > len(cycle_edges):
            break
    return [(colors[i], labels[i]) for i in order]


def convex_hull_containment(hv, selv):
    from scipy.spatial import ConvexHull
    from shapely.geometry import Point, Polygon

    hv_pts = [(p.x, p.y) for p in hv]
    selv_pts = [(p.x, p.y) for p in selv]
    hull_hv = ConvexHull(hv_pts)
    hull_selv = ConvexHull(selv_pts)
    hv_poly = Polygon([hv_pts[i] for i in hull_hv.vertices])
    selv_poly = Polygon([selv_pts[i] for i in hull_selv.vertices])
    selv_in_hv = [p for p in selv if hv_poly.contains(Point(p.x, p.y)) or hv_poly.distance(Point(p.x, p.y)) < 1e-9]
    hv_in_selv = [p for p in hv if selv_poly.contains(Point(p.x, p.y)) or selv_poly.distance(Point(p.x, p.y)) < 1e-9]
    return selv_in_hv, hv_in_selv


def per_component_domain_view(hv, selv):
    """Component-level (not pad-level) classification: a component whose
    pins touch ONLY HV nets is HV; ONLY SELV nets is SELV; touching BOTH
    (an isolator, e.g. an opto or a Y-cap) is reported separately."""
    by_ref = {}
    for p in hv + selv:
        by_ref.setdefault(p.ref, {"HV": [], "SELV": []})[p.domain].append(p)
    pure_hv, pure_selv, mixed = {}, {}, {}
    for ref, d in by_ref.items():
        if d["HV"] and d["SELV"]:
            mixed[ref] = d
        elif d["HV"]:
            pure_hv[ref] = d["HV"]
        else:
            pure_selv[ref] = d["SELV"]
    return pure_hv, pure_selv, mixed


def stepped_polyline_sweep(hv, selv, y0, y1):
    def best_x_in_band(hv_b, selv_b):
        pts = hv_b + selv_b
        if not pts:
            return None, 0
        coords = sorted({p.x for p in pts})
        cands = [(a + b) / 2 for a, b in zip(coords, coords[1:]) if b > a] or [coords[0]]
        best_pos, best_wrong = None, None
        for pos in cands:
            wrong = sum(1 for p in hv_b if p.x > pos) + sum(1 for p in selv_b if p.x <= pos)
            if best_wrong is None or wrong < best_wrong:
                best_wrong, best_pos = wrong, pos
        return best_pos, best_wrong

    results = {}
    for k in (1, 2, 4, 8, 16):
        band_h = (y1 - y0) / k
        total_wrong = 0
        total_n = 0
        for i in range(k):
            lo, hi = y0 + i * band_h, y0 + (i + 1) * band_h
            hv_b = [p for p in hv if lo <= p.y < hi or (i == k - 1 and p.y == hi)]
            selv_b = [p for p in selv if lo <= p.y < hi or (i == k - 1 and p.y == hi)]
            _, wrong = best_x_in_band(hv_b, selv_b)
            total_wrong += wrong
            total_n += len(hv_b) + len(selv_b)
        results[k] = (total_wrong, total_n)
    return results


def main():
    recs, hv_nets, selv_nets, unclassified_nets, result = load_pads()
    hv = [p for p in recs if p.domain == "HV"]
    selv = [p for p in recs if p.domain == "SELV"]

    print("=" * 78)
    print("PARSER-BUG CHECK: ParseResult.pads vs pin_world_position")
    print("=" * 78)
    mismatches = demonstrate_parser_bug(result)
    print(f"pads where ParseResult.pads disagrees with pin_world_position by >0.01mm: "
          f"{len(mismatches)} / {len(result.pads)}")
    for ref, num, naive_pos, correct_pos in mismatches[:5]:
        print(f"  {ref} pad {num}: naive(ParseResult.pads)={naive_pos} "
              f"vs correct(pin_world_position)={correct_pos}")

    print()
    print("=" * 78)
    print("DOMAIN CLASSIFICATION")
    print("=" * 78)
    print(f"HV nets declared: {len(hv_nets)}   SELV nets declared: {len(selv_nets)}")
    print(f"HV pads: {len(hv)}   SELV pads: {len(selv)}")
    print(f"Nets present on real board pads but NOT in manifest (unclassified): "
          f"{len(unclassified_nets)}")

    xs_hv, ys_hv = [p.x for p in hv], [p.y for p in hv]
    xs_selv, ys_selv = [p.x for p in selv], [p.y for p in selv]
    print(f"\nHV   bbox x[{min(xs_hv):.3f},{max(xs_hv):.3f}] y[{min(ys_hv):.3f},{max(ys_hv):.3f}]  "
          f"centroid=({sum(xs_hv)/len(xs_hv):.3f},{sum(ys_hv)/len(ys_hv):.3f})")
    print(f"SELV bbox x[{min(xs_selv):.3f},{max(xs_selv):.3f}] y[{min(ys_selv):.3f},{max(ys_selv):.3f}]  "
          f"centroid=({sum(xs_selv)/len(xs_selv):.3f},{sum(ys_selv)/len(ys_selv):.3f})")

    board = result.board
    print(f"\nBoard: {board.width}mm x {board.height}mm, origin={board.origin}")

    print()
    print("=" * 78)
    print("BEST SINGLE STRAIGHT-LINE SPLIT (pad centers)")
    print("=" * 78)
    lines = best_single_line(hv, selv)
    total = len(hv) + len(selv)
    for axis, (pos, wrong) in lines.items():
        print(f"  {axis}={pos:.3f}mm  misclassified pads={wrong}/{total} ({100*wrong/total:.1f}%)")

    print()
    print("=" * 78)
    print("TOPOLOGICAL SEPARABILITY: bichromatic Delaunay cycle (pad centers)")
    print("=" * 78)
    cycle = bichromatic_delaunay_cycle(hv, selv)
    if cycle is None:
        print("  NO bichromatic cycle found -- pad centers ARE separable by some simple curve.")
    else:
        print(f"  FOUND: alternating ring of {len(cycle)} pads "
              f"(no simple open curve/arc/polyline can separate the domains):")
        for domain, p in cycle:
            print(f"    {domain:5s} {p.ref:6s} pad{p.number:>3s} net={p.net:14s} "
                  f"({p.x:.3f},{p.y:.3f}) layer={p.layer}")

    print()
    print("=" * 78)
    print("CONVEX HULL MUTUAL CONTAINMENT (loop-barrier feasibility)")
    print("=" * 78)
    selv_in_hv, hv_in_selv = convex_hull_containment(hv, selv)
    print(f"  SELV pads inside HV convex hull: {len(selv_in_hv)} / {len(selv)}")
    print(f"  HV pads inside SELV convex hull: {len(hv_in_selv)} / {len(hv)}")

    print()
    print("=" * 78)
    print("COMPONENT-LEVEL VIEW (not pad-level)")
    print("=" * 78)
    pure_hv, pure_selv, mixed = per_component_domain_view(hv, selv)
    print(f"  pure-HV components: {len(pure_hv)}   pure-SELV components: {len(pure_selv)}   "
          f"mixed (isolator/dual-domain) components: {len(mixed)}")
    print(f"  mixed refs: {sorted(mixed.keys())}")

    print()
    print("=" * 78)
    print("CLOSEST HV<->SELV PAD PAIRS (conservative bounding-radius bound)")
    print("=" * 78)
    pairs = []
    for h in hv:
        for s in selv:
            if abs(h.x - s.x) > 20 or abs(h.y - s.y) > 20:
                continue
            d_center = math.hypot(h.x - s.x, h.y - s.y)
            d_conservative = d_center - h.radius - s.radius
            if d_conservative > 20:
                continue
            pairs.append((d_conservative, h, s))
    pairs.sort(key=lambda t: t[0])
    for d, h, s in pairs[:15]:
        flag = "  <8.0mm CREEPAGE (conservative)" if d < CLEARANCE_MM else ""
        print(f"    {d:7.3f}mm  HV {h.ref:6s} pad{h.number:>3s} ({h.x:8.3f},{h.y:8.3f}) net={h.net:12s}"
              f"  <->  SELV {s.ref:6s} pad{s.number:>3s} ({s.x:8.3f},{s.y:8.3f}) net={s.net:12s}{flag}")

    print()
    print("=" * 78)
    print("STEPPED (PIECEWISE-VERTICAL) POLYLINE SWEEP")
    print("=" * 78)
    sweep = stepped_polyline_sweep(hv, selv, board.origin[1], board.origin[1] + board.height)
    for k, (wrong, n) in sweep.items():
        print(f"  K={k:2d} bands: misclassified {wrong}/{n} ({100*wrong/n:.2f}%)")


if __name__ == "__main__":
    main()
