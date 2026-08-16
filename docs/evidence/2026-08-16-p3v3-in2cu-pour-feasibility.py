#!/usr/bin/env python3
"""Data-driven feasibility test: can the Rust zone generator pour +3V3 on In2.Cu?

Read-only measurement supporting the +3V3 (50 pads) connectivity decision:

- A. Obstacle set on In2.Cu (the plane layer): every other net's copper that
     physically exists there (THT pads + through vias; SMD pads/tracks on
     F.Cu/B.Cu do NOT exist on In2.Cu), each buffered at
     max(clearance, creepage) for that net-class pair -- the same
     collect_zone_obstacle_records / creepage-twin-table machinery the
     production `_emit_zone_pours` seam uses.
- B. Region: (a) full board minus HV keepout minus edge margin (the
     gnd-plane-style full-region pour, IslandPolicy=KeepAll) and
     (b) per-cluster hulls (the _power_islands.py style, PadsOnly).
- C. Coverage: how many of +3V3's 50 pad positions fall inside the emitted
     outline(s), split by THT (barrel through In2.Cu -- directly connected)
     vs SMD (needs a drop via + stub, the _ground_plane/_power_islands
     pattern).  Islands: how many disconnected outlines result.

Usage:
    .venv/bin/python docs/evidence/2026-08-16-p3v3-in2cu-pour-feasibility.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DOMAIN_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"

NET = "+3V3"
LAYER = "In2.Cu"
EDGE_MARGIN_MM = 1.0


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer"))

    import temper_geometry as _tg
    from shapely.geometry import Point as ShapelyPoint
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from temper_io_types import strip_existing_copper
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.placer.cp_sat.isolation_barrier import (
        DEFAULT_CORRIDOR_WIDTH_MM,
        load_domain_manifest_nets,
    )
    from temper_placer.router_v6._ground_plane import (
        _collect_hv_copper_geometry,
        compute_hv_selv_keepout,
    )
    from temper_placer.router_v6.pad_connectivity_audit import ALL_LAYERS, _pads_by_net
    from temper_placer.router_v6.routing_space import _get_board_polygon
    from temper_placer.router_v6.topology_copper_audit import net_number_to_name_map
    from temper_placer.router_v6.zone_emission import compute_zones_for_net
    from temper_placer.router_v6.zone_pour_clearance import collect_zone_obstacle_records, default_table
    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    pcb = parse_kicad_pcb_v6(PCB_PATH)
    content = PCB_PATH.read_text()
    num_to_name = net_number_to_name_map(content)
    name_to_num = {v: k for k, v in num_to_name.items()}

    pads_by_net = _pads_by_net(pcb)
    net_num = name_to_num.get(NET)
    print(f"board nets with pads: {len(pads_by_net)}; {NET} net number = {net_num}")

    own = pads_by_net.get(NET, [])
    print(f"{NET} pads: {len(own)}")
    n_tht = sum(1 for p in own if p.layer == ALL_LAYERS)
    n_smd = len(own) - n_tht
    print(f"  THT (barrel through In2.Cu): {n_tht}, SMD (needs drop via): {n_smd}")
    own_positions = sorted({(round(p.position[0], 3), round(p.position[1], 3)) for p in own})
    print(f"  unique positions: {len(own_positions)}")

    # --- HV keepout (same construction _ground_plane/_power_islands use) ---
    hv_nets, _selv = load_domain_manifest_nets(DOMAIN_MANIFEST)
    hv_positions = [
        pad.position
        for net_name in sorted(hv_nets)
        for pad in pads_by_net.get(net_name, [])
    ]
    board_polygon = _get_board_polygon(pcb)
    keepout_pads = compute_hv_selv_keepout(
        hv_positions, [], board_polygon, DEFAULT_CORRIDOR_WIDTH_MM
    )
    hv_extra = _collect_hv_copper_geometry(pcb, hv_nets, DEFAULT_CORRIDOR_WIDTH_MM)
    keepout_parts = [g for g in (keepout_pads, hv_extra) if g is not None]
    keepout = unary_union(keepout_parts).intersection(board_polygon) if keepout_parts else None
    plane_region = board_polygon.buffer(-EDGE_MARGIN_MM)
    if keepout is not None and not keepout.is_empty:
        plane_region = plane_region.difference(keepout)
    print(f"HV keepout established: {keepout is not None}; plane region area: {plane_region.area:.0f} mm2")

    # --- Obstacles on In2.Cu via the production record collector ---
    clearance_table = default_table()
    creepage_table = default_creepage_table()
    obstacles = collect_zone_obstacle_records(
        NET,
        LAYER,
        pcb=pcb,
        segments=[],
        net_number_to_name=num_to_name,
        clearance_table=clearance_table,
        creepage_table=creepage_table,
    )
    print(f"obstacle records on {LAYER}: {len(obstacles)}")
    # breakdown by kind and separation
    by_sep: dict[float, int] = {}
    for rec in obstacles:
        by_sep[rec[6]] = by_sep.get(rec[6], 0) + 1
    print(f"  obstacle separation histogram: {dict(sorted(by_sep.items()))}")

    own_pads_for_rust = [(x, y) for x, y in own_positions]
    obs_for_rust = [tuple(rec) for rec in obstacles]

    # --- A. Full-board region pour (gnd-plane style, KeepAll) ---
    print("\n=== A. full-board region (board - keepout - edge margin), KeepAll ===")
    # The keepout carve splits the region into a MultiPolygon; the pour
    # region is the union of its parts (the Rust generator handles the
    # per-part carve itself, and this keeps the comparison honest with
    # the gnd-plane full-region construction).
    region_geoms = list(plane_region.geoms) if hasattr(plane_region, "geoms") else [plane_region]
    region_pts = []
    for g in region_geoms:
        if g.is_empty or not hasattr(g, "exterior"):
            continue
        pts = [(float(x), float(y)) for x, y in g.exterior.coords]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        if len(pts) >= 3:
            region_pts.append(pts)
    res_a: list = []
    for part in region_pts:
        res_a.extend(_tg.pour_outline_py(part, own_pads_for_rust, obs_for_rust, 0.25 * 0.25, False))
    covered_a = [
        (x, y) for (x, y) in own_positions
        if _point_in_rings(x, y, res_a)
    ]
    print(f"  outlines: {len(res_a)}")
    print(f"  +3V3 pad positions inside pour: {len(covered_a)}/{len(own_positions)}")
    area = sum(_ring_area(z[0]) - sum(_ring_area(h) for h in z[1:]) for z in res_a)
    print(f"  pour area: {area:.0f} mm2")
    uncovered_a = [p for p in own_positions if p not in covered_a]
    print(f"  uncovered: {len(uncovered_a)} {sorted(uncovered_a)[:20]}...")

    # --- B. Per-cluster hulls (power-islands style), PadsOnly ---
    print("\n=== B. per-cluster hulls (compute_zones_for_net cluster=True), PadsOnly ===")
    zds = compute_zones_for_net(
        NET, net_num, list(own_positions), layer=LAYER, margin=0.5, cluster=True,
        board_polygon=board_polygon,
    )
    print(f"  clusters: {len(zds)}")
    covered_b: list[tuple[float, float]] = []
    n_b_zones = 0
    for zd in zds:
        hull = Polygon(zd.points)
        clipped = hull.intersection(plane_region)
        if clipped.is_empty:
            continue
        geoms = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
        for g in geoms:
            if not hasattr(g, "exterior") or g.is_empty or len(g.exterior.coords) < 4:
                continue
            pts = [(float(x), float(y)) for x, y in g.exterior.coords]
            if pts[0] == pts[-1]:
                pts.pop()
            # carve against the same obstacle set with the Rust generator
            pour = _tg.pour_outline_py(pts, own_pads_for_rust, obs_for_rust, 0.25 * 0.25, True)
            for zone_rings in pour:
                n_b_zones += 1
                for (x, y) in own_positions:
                    if _point_in_rings(x, y, [zone_rings]):
                        covered_b.append((x, y))
    covered_b = sorted(set(covered_b))
    print(f"  outlines after carve: {n_b_zones}")
    print(f"  +3V3 pad positions inside pour: {len(covered_b)}/{len(own_positions)}")
    uncovered_b = [p for p in own_positions if p not in covered_b]
    print(f"  uncovered: {len(uncovered_b)} {sorted(uncovered_b)[:20]}...")

    # --- verdict ---
    print("\n=== verdict ===")
    print(f"A full-board KeepAll: {len(covered_a)}/{len(own_positions)} pads, {len(res_a)} islands")
    print(f"B per-cluster PadsOnly: {len(covered_b)}/{len(own_positions)} pads, {n_b_zones} zones")
    return 0


def _point_in_rings(x: float, y: float, zones) -> bool:
    import temper_geometry as _tg
    for zone_rings in zones:
        exterior = zone_rings[0]
        if not _point_in_poly(x, y, exterior):
            continue
        if any(_point_in_poly(x, y, h) for h in zone_rings[1:]):
            continue
        return True
    return False


def _point_in_poly(x: float, y: float, ring) -> bool:
    # ray-casting point-in-polygon on an open ring
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-300) + xi):
            inside = not inside
        j = i
    return inside


def _ring_area(ring) -> float:
    n = len(ring)
    s = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


if __name__ == "__main__":
    sys.exit(main())
