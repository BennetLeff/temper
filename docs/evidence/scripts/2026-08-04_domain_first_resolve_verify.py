#!/usr/bin/env python3
"""Post-solve verification for the domain-first re-solve (#518).

# provenance: commit=ab11daaba37f1fca17d057fd087110a663e01deb dirty=false

Re-runs the three falsification criteria (docs/evidence/2026-08-03-mains-
selv-barrier-keepout.md §4) against the SOLVED placement from
2026-08-04_domain_first_resolve_solve_summary.json:

  (a) ring -- bichromatic Delaunay cycle in the HV+SELV pad centers
      (strictly-alternating ring = far-side check unsatisfiable);
  (b) far-side separability -- convex-hull interleave (loop form);
  (c) copper corridor -- free-space edge-to-edge corridor of width >= 8.0
      (checks 4+5), with pads at their NEW positions and zones/segments/vias
      at their current (placement-independent) positions.

Pad positions at the solved placement: new_abs = old_abs + (solved_local -
current_local) per ref (rotations are pinned by the recipe, so pad geometry
does not rotate).

NO pcb/** write. Read-only w.r.t. pcb/temper.kicad_pcb.

Usage:
    uv run --no-sync python docs/evidence/scripts/2026-08-04_domain_first_resolve_verify.py
"""

from __future__ import annotations

import json
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
SUMMARY = REPO / "docs" / "evidence" / "2026-08-04_domain_first_resolve_solve_summary.json"
MIN_W = MIN_BARRIER_WIDTH_MM


def bichromatic_delaunay_cycle(hv: list, selv: list):
    """Same criterion as the falsification script (validate-then-report)."""
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


def main() -> None:
    manifest = _ck.load_manifest(MANIFEST)
    board = _ck.load_board(BOARD)
    outline = Polygon(board.board_outline)
    minx, miny, maxx, maxy = outline.bounds

    summary = json.loads(SUMMARY.read_text())
    solved = summary["placement"]  # {ref: {position, rotation_idx}} local frame

    # Current (parsed) pad positions per ref.
    pads_by_ref: dict[str, list] = {}
    for p in board.pads:
        pads_by_ref.setdefault(p.ref, []).append(p)

    # Current component positions (local frame, from the solve summary's input
    # side we need the delta -- recompute current from the board parse).
    # The solve's placement dict has positions in the CP-SAT local frame;
    # the board's pads are in the absolute frame. Delta is frame-invariant.
    # Current local positions come from parsing (kicad_parser initial_position)
    # -- reuse by loading the same parse used by the solve.
    _PLACER_DIR = REPO / "packages" / "temper-placer"
    sys.path.insert(0, str(_PLACER_DIR))
    from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402

    pcb = parse_kicad_pcb(BOARD)
    cur_pos = {c.ref: c.initial_position for c in pcb.netlist.components}

    # Apply deltas to pads (only refs present in both solved and current).
    new_pads = []
    moved_refs = []
    for p in board.pads:
        new = solved.get(p.ref)
        cur = cur_pos.get(p.ref)
        if new is None or cur is None:
            new_pads.append(p)  # unmoved / unknown: keep
            continue
        dx = new["position"][0] - cur[0]
        dy = new["position"][1] - cur[1]
        if abs(dx) > 1e-6 or abs(dy) > 1e-6:
            moved_refs.append(p.ref)
        new_pads.append(
            type(p)(
                ref=p.ref, number=p.number, x=p.x + dx, y=p.y + dy,
                radius=p.radius, layers=p.layers, net_name=p.net_name,
            )
        )
    print(f"pads re-projected: {len(new_pads)} (moved-ref pad deltas applied; "
          f"{len(set(moved_refs))} refs moved >0.001mm)")

    hv = [p for p in new_pads if p.net_name in manifest.hv_nets]
    selv = [p for p in new_pads if p.net_name in manifest.selv_nets]
    print(f"HV pads: {len(hv)}  SELV pads: {len(selv)}")

    # ---- (a) ring check ----
    print("\n=== (a) bichromatic Delaunay cycle (far-side, open-curve form) ===")
    cycle_edges, ring = bichromatic_delaunay_cycle(hv, selv)
    if ring is None:
        print("  bichromatic Delaunay cycle: NONE (centers ARE curve-separable)")
        print("  => far-side check 6 satisfiable for arc/cap forms")
    else:
        order, pts, color = ring
        cols = [color[v] for v in order]
        alternating = all(cols[i] != cols[i - 1] for i in range(1, len(cols)))
        print(f"  bichromatic Delaunay cycle: FOUND ({len(order)} vertices), "
              f"strictly alternating: {alternating}")
        # Map cycle pads to refs + count minimal cycles.
        pads_all = hv + selv
        ref_of = {id(p): p.ref for p in pads_all}
        print("    cycle pad refs:", [ref_of[id(pads_all[v])] for v in order])
        # Count bichromatic cycles: enumerate cycles in the bichromatic
        # subgraph via DFS from each node (undirected, simple cycles).
        bichrom = nx.Graph()
        tri = Delaunay([(p.x, p.y) for p in pads_all])
        for s in tri.simplices:
            for i in range(3):
                a, b = s[i], s[(i + 1) % 3]
                if color[a] != color[b]:
                    bichrom.add_edge(a, b)
        cycles = nx.cycle_basis(bichrom)
        alt_cycles = [
            c for c in cycles
            if all(color[c[i]] != color[c[(i + 1) % len(c)]] for i in range(len(c)))
        ]
        print(f"  bichromatic subgraph: {bichrom.number_of_nodes()} nodes, "
              f"{bichrom.number_of_edges()} edges, "
              f"{len(nx.cycle_basis(bichrom))} cycle-basis cycles, "
              f"{len(alt_cycles)} strictly-alternating")

    # ---- (b) loop-form / hull interleave ----
    print("\n=== (b) convex-hull interleave (far-side, loop form) ===")
    hv_pts = [(p.x, p.y) for p in hv]
    selv_pts = [(p.x, p.y) for p in selv]
    hull_hv = ConvexHull(hv_pts)
    hull_selv = ConvexHull(selv_pts)
    hv_hull_poly = Polygon([hv_pts[i] for i in hull_hv.vertices])
    selv_hull_poly = Polygon([selv_pts[i] for i in hull_selv.vertices])
    selv_in_hv = sum(
        1 for p in selv_pts if hv_hull_poly.contains(Point(p)) or hv_hull_poly.distance(Point(p)) < 1e-6
    )
    hv_in_selv = sum(
        1 for p in hv_pts if selv_hull_poly.contains(Point(p)) or selv_hull_poly.distance(Point(p)) < 1e-6
    )
    print(f"  HV hull contains {selv_in_hv} SELV centers; "
          f"SELV hull contains {hv_in_selv} HV centers")

    # ---- (c) copper corridor (checks 4+5) ----
    print("\n=== (c) copper-free corridor (checks 4+5) ===")
    copper_polys = []
    for seg in board.segments:
        line = LineString(seg.points)
        copper_polys.append(line.buffer(seg.width / 2.0) if seg.width > 0 else line)
    for via in board.vias:
        copper_polys.append(Point(via.x, via.y).buffer(via.radius))
    for p in new_pads:
        copper_polys.append(Point(p.x, p.y).buffer(p.radius) if p.radius > 0 else Point(p.x, p.y))
    zone_geoms = [g for cz in board.copper_zones if (g := _ck._polygon_or_none(cz.polygons)) is not None]
    for g in zone_geoms:
        copper_polys.append(g)
    cu_union = unary_union([c for c in copper_polys if not c.is_empty])
    free = outline.difference(cu_union)
    board_area = outline.area
    comps = list(free.geoms) if free.geom_type == "MultiPolygon" else [free]
    comps = [c for c in comps if not c.is_empty and c.area > 1e-6]
    print(f"  copper-free fraction: {free.area / board_area * 100:.1f}% "
          f"({free.area:.0f} mm^2) in {len(comps)} component(s)")
    eps = 0.01
    edge_polys = {
        "left": Polygon([(minx, miny), (minx + eps, miny), (minx + eps, maxy), (minx, maxy)]),
        "right": Polygon([(maxx - eps, miny), (maxx, miny), (maxx, maxy), (maxx - eps, maxy)]),
        "bottom": Polygon([(minx, miny), (maxx, miny), (maxx, miny + eps), (minx, miny + eps)]),
        "top": Polygon([(minx, maxy - eps), (maxx, maxy - eps), (maxx, maxy), (minx, maxy)]),
    }
    opposite = {("left", "right"), ("top", "bottom")}
    hosts = []
    for i, c in enumerate(comps):
        s = {k for k, e in edge_polys.items() if c.intersects(e)}
        if len(s) >= 2 and any((a, b) in opposite for a in s for b in s):
            eroded = c.buffer(-MIN_W / 2.0)
            hosts.append((i, c, s, not eroded.is_empty))
    print(f"  components spanning OPPOSITE edges: {len(hosts)}")
    for i, c, s, w in hosts:
        print(f"    comp {i}: edges={sorted(s)} area={c.area:.0f} mm^2 "
              f"8mm-disk-bearing: {w}")
    if not hosts:
        print("  => NO edge-to-edge copper-free corridor; checks 4+5 "
              "unsatisfiable even with the solved placement")

    # ---- gate ----
    print("\n=== check_isolation_keepout gate (on the current board -- the "
          "solved placement is NOT written) ===")
    state, report = _ck.run(BOARD, MANIFEST)
    print(f"state={state}  violations={len(report.violations)}")
    for v in report.violations:
        print(f"  [{v.check}] {v.detail[:150]}")


if __name__ == "__main__":
    main()
