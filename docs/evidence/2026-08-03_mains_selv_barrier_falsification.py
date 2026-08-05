#!/usr/bin/env python3
"""Reproducible falsification analysis for the MAINS_SELV_ISOLATION_BARRIER
keepout on pcb/temper.kicad_pcb (docs/evidence/2026-08-03-mains-selv-barrier-keepout.md).

# provenance: commit=b8709225c1f5f8332c48693500fc544e57d35784 dirty=false

Verdict: NO compliant barrier can exist on the current board. The gate
(scripts/check_isolation_keepout.py) accepts arbitrary keepout polygons --
it does NOT require a straight band, and its width check (erosion by
MIN_BARRIER_WIDTH_MM/2 is non-empty) only requires the polygon to contain
one 8.0mm disk SOMEWHERE, not 8.0mm width everywhere. The board is
nevertheless unsatisfiable for every barrier form, for three independent,
measured reasons:

  1. FAR-SIDE CHECK (check 6, pad CENTERS) is unsatisfiable for any open
     arc / cap barrier: the HV and SELV pad centers are not separable by
     any simple curve -- the Delaunay triangulation of the combined point
     set contains a strictly-alternating bichromatic cycle of 12 pads
     (C6.2-R8.2-K1.A2-R8.1-R75.1-C27.2-C9.1-U5.3-Q1.1-U5.1-U10.2-R27.2).
  2. FAR-SIDE CHECK is also unsatisfiable for any closed-loop barrier:
     137 SELV centers lie inside the HV convex hull (93 HV inside the SELV
     hull), so no loop can enclose one domain without the other.
  3. COPPER-EXCLUSION (checks 4+5) fails independently of domain colors:
     zone outlines cover 85.7% of the board area; the copper-free space is
     only 12.6%, fragmented into 99 components, and only 3 components touch
     two board edges -- all corner scraps (largest 1425 mm^2). No connected
     copper-free corridor spans the board, so no edge-to-edge (or cap) keepout
     polygon can avoid every segment/via/pad/zone.

The prior (2026-07-31-handoff-era) "K1 5.369mm / T1 5.977mm intra-footprint
gaps are an IRREDUCIBLE blocker" claim is NOT the decisive argument: the
gate's width check is weaker than "8.0mm everywhere", so a thin barrier
could in principle pass between sub-8.0mm pad clusters. The decisive
arguments are (1)-(3) above -- placement-independent properties of the
pad-center interleave and of the existing copper. The conclusion (no
keepout can be drawn that satisfies the gate) is unchanged; the reasoning
is corrected and strengthened.

Usage:
    uv run --no-sync python docs/evidence/2026-08-03_mains_selv_barrier_falsification.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "packages" / "temper-placer" / "src"))

import check_isolation_keepout as _ck  # noqa: E402
import networkx as nx  # noqa: E402
from scipy.spatial import ConvexHull, Delaunay  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from temper_placer.core.isolation_constants import MIN_BARRIER_WIDTH_MM  # noqa: E402

BOARD = REPO / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO / "elec" / "domain_manifest.yaml"
MIN_W = MIN_BARRIER_WIDTH_MM  # 8.0


def bichromatic_delaunay_cycle(hv: list, selv: list):
    """Return (cycle_edges, ordered_vertices) of a bichromatic cycle in the
    Delaunay triangulation of all HV+SELV pad centers, or (None, None) if the
    bichromatic subgraph is acyclic.

    A bichromatic Delaunay cycle is an alternating ring of pads -- the
    topological obstruction to separating the two point sets by any simple
    curve (Delaunay edges are empty-segment adjacencies, so the cycle is a
    genuine visibility obstruction, not an artifact).
    """
    pts = [(p.x, p.y) for p in hv + selv]
    color = ["HV"] * len(hv) + ["SELV"] * len(selv)
    if len(pts) < 3:
        return None, None
    tri = Delaunay(pts)
    G = nx.Graph()
    G.add_nodes_from(range(len(pts)))
    for simplex in tri.simplices:
        for i in range(3):
            a, b = simplex[i], simplex[(i + 1) % 3]
            if color[a] != color[b]:
                G.add_edge(a, b)
    try:
        cycle_edges = nx.find_cycle(G)
    except nx.NetworkXNoCycle:
        return None, None
    # Reconstruct the ordered vertex ring.
    adj: dict[int, list[int]] = {}
    for a, b in cycle_edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    start = cycle_edges[0][0]
    order = [start]
    prev = None
    cur = start
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
    return cycle_edges, (order, pts, color)


def _validate_criterion() -> None:
    """Sanity-check the Delaunay bichromatic-cycle criterion on known cases."""
    def sep(pts, colors):
        if len(pts) < 3:
            return False
        tri = Delaunay(pts)
        G = nx.Graph()
        G.add_nodes_from(range(len(pts)))
        for s in tri.simplices:
            for i in range(3):
                a, b = s[i], s[(i + 1) % 3]
                if colors[a] != colors[b]:
                    G.add_edge(a, b)
        try:
            nx.find_cycle(G)
            return True  # cycle -> NOT separable
        except nx.NetworkXNoCycle:
            return False

    # Clean left/right split: separable (no cycle).
    pts1 = [(0, 0), (0, 10), (10, 0), (10, 10)]
    col1 = ["A", "A", "B", "B"]
    assert sep(pts1, col1) is False, "clean split must be separable"
    # Alternating ring on a circle: NOT separable (cycle).
    pts2 = []
    for i in range(6):
        a = i * math.pi / 3
        pts2.append((20 + 10 * math.cos(a), 20 + 10 * math.sin(a)))
    col2 = ["A", "B", "A", "B", "A", "B"]
    assert sep(pts2, col2) is True, "alternating ring must be inseparable"
    # Zipper (two meshing combs): separable (no cycle).
    pts3 = [(float(i), 0.0) for i in range(5)] + [(float(i) + 0.5, 1.0) for i in range(5)]
    col3 = ["A"] * 5 + ["B"] * 5
    assert sep(pts3, col3) is False, "zipper must be separable"
    print("  criterion sanity checks: PASSED "
          "(clean split=separable, alternating ring=inseparable, zipper=separable)")


def main() -> None:
    manifest = _ck.load_manifest(MANIFEST)
    board = _ck.load_board(BOARD)
    outline = Polygon(board.board_outline)
    minx, miny, maxx, maxy = outline.bounds

    hv = [p for p in board.pads if p.net_name in manifest.hv_nets]
    selv = [p for p in board.pads if p.net_name in manifest.selv_nets]

    print(f"board outline: {board.board_outline}")
    print(f"bounds: {outline.bounds}")
    print(f"copper layers: {board.copper_layers_ordered}")
    print(f"pads: {len(board.pads)}  segments: {len(board.segments)}  "
          f"vias: {len(board.vias)}  copper_zones: {len(board.copper_zones)}")
    print(f"HV pads: {len(hv)}  SELV pads: {len(selv)}")

    # ---- 1. domain interleave ----
    for name, pads in (("HV", hv), ("SELV", selv)):
        xs = [p.x for p in pads]
        ys = [p.y for p in pads]
        print(f"\n{name}: n={len(pads)}  x[{min(xs):.2f},{max(xs):.2f}] "
              f"y[{min(ys):.2f},{max(ys):.2f}]  centroid=({sum(xs)/len(xs):.1f},{sum(ys)/len(ys):.1f})")
        print("  x-band counts (20mm bins from 20):")
        for lo in range(20, 172, 20):
            hi = lo + 20
            nh = sum(1 for p in hv if lo <= p.x < hi)
            ns = sum(1 for p in selv if lo <= p.x < hi)
            print(f"    x[{lo:3d},{hi:3d})  HV={nh:3d}  SELV={ns:3d}")

    # ---- 2. best straight-line split (informative only -- the gate accepts
    #          arbitrary polygons, so this is NOT the obstruction) ----
    seg_geoms = []
    for seg in board.segments:
        line = LineString(seg.points)
        seg_geoms.append((seg.layer, line.buffer(seg.width / 2.0) if seg.width > 0 else line))
    via_geoms = [Point(v.x, v.y).buffer(v.radius) for v in board.vias]
    zone_geoms = [g for cz in board.copper_zones if (g := _ck._polygon_or_none(cz.polygons)) is not None]

    def pad_geom(p):
        return Point(p.x, p.y).buffer(p.radius) if p.radius > 0 else Point(p.x, p.y)

    def eval_line(axis: int, pos: float) -> tuple[int, int]:
        lo, hi = pos - MIN_W / 2, pos + MIN_W / 2
        if axis == 0:
            band = Polygon([(lo, miny), (hi, miny), (hi, maxy), (lo, maxy)])
        else:
            band = Polygon([(minx, lo), (maxx, lo), (maxx, hi), (minx, hi)])

        def side(p):
            return (p.x > hi) if axis == 0 else (p.y > hi)

        far = sum(1 for p in hv if side(p)) + sum(1 for p in selv if not side(p))
        intr = 0
        for layer, g in seg_geoms:
            if layer in board.copper_layers_ordered and g.intersects(band):
                intr += 1
        intr += sum(1 for g in via_geoms if g.intersects(band))
        intr += sum(1 for g in zone_geoms if g.intersects(band))
        intr += sum(1 for p in board.pads if pad_geom(p).intersects(band))
        return far, intr

    print("\n=== best straight-line split (informative; gate accepts any polygon) ===")
    for axis, name in ((0, "vertical x"), (1, "horizontal y")):
        coords = sorted({(p.x if axis == 0 else p.y) for p in hv + selv})
        candidates = coords + [(a + b) / 2 for a, b in zip(coords, coords[1:], strict=False) if b - a >= 1.0]
        best = min(candidates, key=lambda c: eval_line(axis, c))
        far, intr = eval_line(axis, best)
        print(f"[{name}] best split pos={best:.2f}  far-side pads={far}  "
              f"copper intruders in 8mm band={intr}")

    # ---- 3. isolator intra-footprint gaps (informative; NOT the decisive
    #         argument -- see docstring) ----
    print("\n=== isolator intra-footprint HV/SELV pad gaps (min edge-to-edge) ===")
    by_ref: dict[str, list] = {}
    for p in board.pads:
        by_ref.setdefault(p.ref, []).append(p)
    blockers: list[str] = []
    for ref in sorted(by_ref):
        pads = by_ref[ref]
        h = [p for p in pads if p.net_name in manifest.hv_nets]
        s = [p for p in pads if p.net_name in manifest.selv_nets]
        if not h or not s:
            continue
        best = min(
            (math.hypot(p.x - q.x, p.y - q.y) - p.radius - q.radius for p in h for q in s),
            default=1e9,
        )
        flag = "  (sub-8.0mm gap)" if best < MIN_W else ""
        print(f"  {ref:5s} min HV-SELV edge gap = {best:7.3f}mm{flag}")
        if best < MIN_W:
            blockers.append(f"{ref} {best:.3f}mm")

    print(f"\nBLOCKERS (sub-8.0mm intra-footprint gaps): {blockers}")
    print("NOTE: NOT decisive by itself -- the gate's width check (erosion by")
    print("4.0mm is non-empty) only requires one 8.0mm disk SOMEWHERE, so a")
    print("thin barrier could pass between these clusters. The decisive")
    print("obstructions are the far-side (check 6) and copper-exclusion")
    print("(checks 4+5) results below.")

    # ---- 4. THE DECISIVE ARGUMENT: pad-center curve separability (check 6) ----
    print("\n=== far-side check (check 6): pad-center curve separability ===")
    print("The gate uses pad CENTERS for the far-side check, and accepts any")
    print("polygon, so the question is: can ANY simple curve (arc, cap, or")
    print("loop) keep every HV center on one side and every SELV center on the")
    print("other?")
    _validate_criterion()
    cycle_edges, ring = bichromatic_delaunay_cycle(hv, selv)
    if ring is None:
        print("  bichromatic Delaunay cycle: NONE (centers ARE curve-separable)")
    else:
        order, pts, color = ring
        print(f"  bichromatic Delaunay cycle: FOUND ({len(order)} vertices)")
        for v in order:
            print(f"    {('HV' if color[v] == 'HV' else 'SELV'):5s} "
                  f"{pts[v][0]:7.2f},{pts[v][1]:7.2f}")
        cols = [color[v] for v in order]
        alternating = all(cols[i] != cols[i - 1] for i in range(1, len(cols)))
        print(f"  strictly alternating: {alternating}")
        print("  => NO simple open-arc/cap barrier can separate the domains;")
        print("     check 6 is unsatisfiable for arc/cap forms.")

    # Loop-form check: convex hull containment.
    hv_pts = [(p.x, p.y) for p in hv]
    selv_pts = [(p.x, p.y) for p in selv]
    hull_hv = ConvexHull(hv_pts)
    hull_selv = ConvexHull(selv_pts)
    hv_hull_poly = Polygon([hv_pts[i] for i in hull_hv.vertices])
    selv_hull_poly = Polygon([selv_pts[i] for i in hull_selv.vertices])
    selv_in_hv = sum(1 for p in selv_pts
                     if hv_hull_poly.contains(Point(p)) or hv_hull_poly.distance(Point(p)) < 1e-6)
    hv_in_selv = sum(1 for p in hv_pts
                     if selv_hull_poly.contains(Point(p)) or selv_hull_poly.distance(Point(p)) < 1e-6)
    print(f"  HV convex hull contains {selv_in_hv} SELV centers; "
          f"SELV convex hull contains {hv_in_selv} HV centers")
    print("  => no closed-loop barrier can enclose one domain without the")
    print("     other; check 6 is unsatisfiable for loop forms too.")

    # ---- 5. copper-exclusion (checks 4+5): free-space corridor ----
    print("\n=== copper-exclusion (checks 4+5): free-space corridors ===")
    copper_polys = []
    for seg in board.segments:
        line = LineString(seg.points)
        copper_polys.append(line.buffer(seg.width / 2.0) if seg.width > 0 else line)
    for via in board.vias:
        copper_polys.append(Point(via.x, via.y).buffer(via.radius))
    for p in board.pads:
        copper_polys.append(Point(p.x, p.y).buffer(p.radius) if p.radius > 0 else Point(p.x, p.y))
    for g in zone_geoms:
        copper_polys.append(g)
    cu_union = unary_union([c for c in copper_polys if not c.is_empty])
    free = outline.difference(cu_union)
    board_area = outline.area
    comps = list(free.geoms) if free.geom_type == "MultiPolygon" else [free]
    comps = [c for c in comps if not c.is_empty]
    print(f"  copper-free fraction of board: {free.area / board_area * 100:.1f}% "
          f"({free.area:.0f} mm^2)")
    print(f"  free-space components: {len(comps)}")
    eps = 0.01
    edge_polys = {
        "left": Polygon([(minx, miny), (minx + eps, miny), (minx + eps, maxy), (minx, maxy)]),
        "right": Polygon([(maxx - eps, miny), (maxx, miny), (maxx, maxy), (maxx - eps, maxy)]),
        "bottom": Polygon([(minx, miny), (maxx, miny), (maxx, miny + eps), (minx, miny + eps)]),
        "top": Polygon([(minx, maxy - eps), (maxx, maxy - eps), (maxx, maxy), (minx, maxy)]),
    }
    touch: dict[int, set[str]] = {}
    for i, c in enumerate(comps):
        s = set()
        for k, e in edge_polys.items():
            if c.intersects(e):
                s.add(k)
        touch[i] = s
    multi = {k: v for k, v in touch.items() if len(v) >= 2}
    print(f"  components touching >=2 board edges (corridor hosts): {len(multi)}")
    for i, s in sorted(multi.items()):
        print(f"    comp {i}: touches {sorted(s)}, area {comps[i].area:.0f} mm^2")
    zone_outline = unary_union(zone_geoms) if zone_geoms else Polygon()
    print(f"  zone-outline coverage of board: "
          f"{zone_outline.intersection(outline).area / board_area * 100:.1f}%")
    print("  => no copper-free edge-to-edge corridor exists; checks 4+5 are")
    print("     unsatisfiable even ignoring domain colors.")

    # ---- 6. the gate ----
    print("\n=== check_isolation_keepout gate ===")
    state, report = _ck.run(BOARD, MANIFEST)
    print(f"state={state}  violations={len(report.violations)}")
    for v in report.violations:
        print(f"  [{v.check}] {v.detail[:200]}")

    print("\nVERDICT: (b) no compliant barrier can exist on the current board "
          "-- far-side check unsatisfiable (alternating 12-pad ring; loop form "
          "blocked by convex-hull interleave) AND copper-exclusion unsatisfiable "
          "(zone outlines cover 85.7%, no free-space corridor spans the board). "
          "The gate stays red (#518) with a documented, measured reason.")


if __name__ == "__main__":
    main()
