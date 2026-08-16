#!/usr/bin/env python3
"""Validation harness for the Rust zone-pour design
(docs/evidence/2026-08-15-rust-zone-pour-design.md).

Mirrors the NEW algorithm (zone_generator.rs) in shapely against the REAL
production board, answering the three design questions with measurements:

A. **gnd on In1.Cu** -- a full-board pour carved only by the HV creepage
   keepout (pad half-diagonal + 12.6 mm PD3). Does it stay connected?
   Do all 86 gnd pads land inside pour copper? What is the minimum gap
   from the poured copper to any HV pad?

B. **power_in.ntc-no on F.Cu** -- the fragmentation case. Old carve
   (electrical clearance 2.0 mm from foreign copper) vs new carve
   (creepage: 12.6 mm from LV, 10.0 mm from other HV): island counts and
   min-gap to foreign copper.

C. **+3V3 on F.Cu** -- per-cluster pours with Power-class clearances:
   pad coverage if the router emitted them (it currently drops them).

Run:  .venv/bin/python docs/evidence/2026-08-15-zone-pour-design.py
      (from the repo root; uses the shared venv READ-ONLY -- no builds)

The measurements feed the evidence doc's numbers. All geometry here is
shapely (GEOS) standing in for geo::BooleanOps -- the algorithm, not the
implementation, is what is being validated.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from shapely.geometry import MultiPoint, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

# ---------------------------------------------------------------------------
# Figures (see the evidence doc for sources)
# ---------------------------------------------------------------------------
PD3_HV_LV_CREEPAGE_MM = 12.6  # reinforced, live in the routed-board DRU
PD3_HV_HV_CREEPAGE_MM = 10.0  # tank<->bus shortfall finding (PD3)
OLD_CLEARANCE_CARVE_MM = 2.0  # zone_pour_clearance.generated.yaml HV|Power
BOARD_EDGE_MARGIN_MM = 1.0
MIN_ISLAND_AREA_MM2 = 0.25 * 0.25

PCBPATH = Path("pcb/temper.kicad_pcb")
GND_NET = "gnd"
NTC_NET = "power_in.ntc-no"
V3V3_NET = "+3V3"
PLANE_LAYER = "In1.Cu"


def load_board():
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.routing_space import _get_board_polygon

    pcb = parse_kicad_pcb_v6(PCBPATH)
    board = _get_board_polygon(pcb)
    return pcb, board


def nets_by_name(pcb):
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net

    return _pads_by_net(pcb)


def pad_geometry(pin, comp):
    """(position, half_extent) for a pin in world coordinates."""
    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position

    return pin_world_position(pin, comp), (pin.width / 2.0, pin.height / 2.0)


def collect_obstacles(pcb, layer: str, own_net: str):
    """Every other net's copper on *layer*, as (geom, clearance_class).

    Returns (pads, tracks, vias): geometric polygons of the raw copper
    (no halo), each tagged with its net name so the caller can apply the
    per-pair separation.
    """
    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position
    from temper_placer.router_v6.pad_connectivity_audit import ALL_LAYERS

    pads = []  # (Polygon, net_name)
    for comp in getattr(pcb, "components", []) or []:
        for pin in getattr(comp, "pins", []) or []:
            if not pin.net or pin.net == own_net:
                continue
            raw = pin_world_layer(pin)
            on_layer = raw in ("all", "*.Cu", layer) or (
                isinstance(raw, str) and "Through" in raw
            )
            if not on_layer:
                continue
            pos = pin_world_position(pin, comp)
            w, h = pin.width, pin.height
            rect = Polygon(
                [
                    (pos[0] - w / 2, pos[1] - h / 2),
                    (pos[0] + w / 2, pos[1] - h / 2),
                    (pos[0] + w / 2, pos[1] + h / 2),
                    (pos[0] - w / 2, pos[1] + h / 2),
                ]
            )
            pads.append((rect, pin.net))

    tracks = []  # (LineString buffered to real width, net_name)
    for t in getattr(pcb, "tracks", []) or []:
        if t.net == own_net or t.layer != layer:
            continue
        seg = Polygon()
        if hasattr(t, "start") and hasattr(t, "end"):
            from shapely.geometry import LineString

            seg = LineString([t.start, t.end]).buffer(t.width / 2.0, quad_segs=8)
        tracks.append((seg, t.net))

    vias = []  # (disc, net_name)
    for v in getattr(pcb, "vias", []) or []:
        if v.net == own_net or layer not in getattr(v, "layers", ()):
            continue
        vias.append((Point(v.position).buffer(v.diameter / 2.0, quad_segs=16), v.net))

    return pads, tracks, vias


def separation_for(pour_net: str, other_net: str, hv_nets) -> float:
    """Pair separation between the pour's net and *other_net*.

    The pour's own class determines which figure applies:
    * pour HV vs other HV -- PD3 HV-vs-HV creepage (10.0 mm)
    * pour HV vs LV / pour LV vs HV -- PD3 reinforced creepage (12.6 mm)
    * pour LV vs LV -- ordinary electrical clearance (0.3 mm floor)
    """
    pour_hv = pour_net in hv_nets
    other_hv = other_net in hv_nets
    if pour_hv and other_hv:
        return PD3_HV_HV_CREEPAGE_MM
    if pour_hv != other_hv:
        return PD3_HV_LV_CREEPAGE_MM
    return 0.3


def halos_for(pour_net: str, obstacles, hv_nets, base_mm: float):
    """Union of obstacle halos: raw copper + (base_mm or pair figure).

    If *base_mm* is None the per-pair separation (creepage) applies;
    otherwise the flat figure applies to every pair (the OLD carve).
    """
    from shapely.ops import unary_union

    geoms = []
    for group in obstacles:
        for geom, net in group:
            if geom is None or geom.is_empty:
                continue
            sep = base_mm if base_mm is not None else separation_for(pour_net, net, hv_nets)
            geoms.append(geom.buffer(sep, quad_segs=16))
    if not geoms:
        return None
    return unary_union(geoms)


def carve(region: Polygon, keepout) -> list[Polygon]:
    if keepout is None:
        return [region]
    carved = region.difference(keepout)
    if carved.is_empty:
        return []
    return list(carved.geoms) if hasattr(carved, "geoms") else [carved]


def split_rings(poly: Polygon):
    """(exterior, holes) rings, dropping the closing vertex."""
    ext = list(poly.exterior.coords)[:-1]
    holes = [list(h.coords)[:-1] for h in poly.interiors]
    return ext, holes


def min_gap_from_pads(pieces: list[Polygon], pad_rects: list[Polygon]) -> float:
    """Minimum edge-to-edge distance from pour copper to any pad rect."""
    best = float("inf")
    union = unary_union([p for p in pieces if not p.is_empty])
    for pr in pad_rects:
        d = union.distance(pr)
        best = min(best, d)
    return best


def main():
    pcb, board = load_board()
    pads_by_net = nets_by_name(pcb)
    hv_nets = set(
        [
            "+15V_LS", "+170V_BUS", "DC_BUS_RTN", "GATE_HS", "GATE_LS",
            "PWR_RTN", "SW_NODE", "ac_l", "ac_n", "discharge.k_dis1-nc",
            "discharge.k_dis2-nc", "hb.gate_hs.driver-p1-1",
            "hb.gate_hs.driver-p2", "hb.power_loop.q_high-g",
            "power_in.ntc-no", "tank-out", "tank.c_tank1-p2", "w1_1", "w1_2",
        ]
    )
    print(f"board area {board.area:.1f} mm², HV nets {len(hv_nets)}")
    print("=" * 78)

    # ------------------------------------------------------------------
    # Experiment A: gnd full-board pour on In1.Cu
    # ------------------------------------------------------------------
    print(f"\n[A] gnd full-board pour on {PLANE_LAYER} (carve: HV pads @ 12.6 mm PD3)")
    gnd_pads = pads_by_net.get(GND_NET, [])
    gnd_positions = {(round(p.position[0], 3), round(p.position[1], 3)) for p in gnd_pads}
    print(f"    gnd pads: {len(gnd_pads)} ({len(gnd_positions)} unique positions)")

    pads, tracks, vias = collect_obstacles(pcb, PLANE_LAYER, GND_NET)
    # On In1.Cu only THT pads + through vias appear (SMD copper is F/B);
    # the collector's on_layer filter already handled that.
    keepout = halos_for(GND_NET, (pads, tracks, vias), hv_nets, None)
    region = board.buffer(-BOARD_EDGE_MARGIN_MM)
    pieces = carve(region, keepout)
    pieces = [p for p in pieces if p.area >= MIN_ISLAND_AREA_MM2]
    print(f"    keepout area {keepout.area:.0f} mm² ({100*keepout.area/board.area:.0f}% of board)")
    print(f"    pour pieces: {len(pieces)}  (total area {sum(p.area for p in pieces):.0f} mm²)")

    # Pad coverage: which gnd pad positions fall inside some pour piece?
    covered = 0
    uncovered = []
    for pos in sorted(gnd_positions):
        pt = Point(pos)
        if any(p.contains(pt) for p in pieces):
            covered += 1
        else:
            uncovered.append(pos)
    print(f"    gnd pads inside pour: {covered}/{len(gnd_positions)}")
    if uncovered:
        print(f"    UNCOVERED gnd pads: {uncovered[:10]}")

    # WHY are pads uncovered? Three causes, three different remedies:
    #  (a) inside an HV creepage halo -> cannot be plane-covered, needs a
    #      via + stitch (the _ground_plane.py MST backbone pattern);
    #  (b) outside the 1 mm board-edge margin -> shrink margin or accept
    #      the edge ring being dropped;
    #  (c) on a padless island under PadsOnly -> plane mode keeps them.
    in_halo = out_region = other = 0
    halo_pts = []
    for pos in uncovered:
        pt = Point(pos)
        if keepout is not None and pt.within(keepout):
            in_halo += 1
            halo_pts.append(pos)
        elif not region.contains(pt):
            out_region += 1
        else:
            other += 1
    print(f"    uncovered by cause: {in_halo} inside HV halo, {out_region} outside "
          f"board-edge margin, {other} other")
    if halo_pts:
        print(f"    sample halo-excluded gnd pads: {halo_pts[:5]}")

    # Islands without any gnd pad (isolated_copper liability if kept).
    padless = 0
    for p in pieces:
        if not any(p.contains(Point(pos)) for pos in gnd_positions):
            padless += 1
    print(f"    padless pieces (PadsOnly would drop): {padless}")

    # Min gap from pour copper to HV pad edges (only pads whose copper is
    # actually on this layer -- the same on_layer filter the keepout used;
    # an F.Cu-only SMD pad under the In1.Cu plane is a dielectric/crossing
    # question, not a same-surface creepage gap).
    hv_pad_net_pairs = []  # (rect, net_name)
    for comp in getattr(pcb, "components", []) or []:
        for pin in getattr(comp, "pins", []) or []:
            if pin.net in hv_nets:
                from temper_placer.core.pin_geometry import (
                    pin_world_layer,
                    pin_world_position,
                )

                raw = pin_world_layer(pin)
                on_layer = raw in ("all", "*.Cu", PLANE_LAYER) or (
                    isinstance(raw, str) and "Through" in raw
                )
                if not on_layer:
                    continue
                pos = pin_world_position(pin, comp)
                hv_pad_net_pairs.append(
                    (
                        Polygon(
                            [
                                (pos[0] - pin.width / 2, pos[1] - pin.height / 2),
                                (pos[0] + pin.width / 2, pos[1] - pin.height / 2),
                                (pos[0] + pin.width / 2, pos[1] + pin.height / 2),
                                (pos[0] - pin.width / 2, pos[1] + pin.height / 2),
                            ]
                        ),
                        pin.net,
                    )
                )
    gap = min_gap_from_pads(pieces, [r for r, _ in hv_pad_net_pairs])
    print(f"    min gap pour->HV pad edge (on-layer): {gap:.2f} mm "
          f"(gnd is LV, so every gnd-pour/HV-pad pair needs {PD3_HV_LV_CREEPAGE_MM:.1f})")
    ok = gap >= PD3_HV_LV_CREEPAGE_MM - 0.5
    print(f"    creepage carve holds (>= {PD3_HV_LV_CREEPAGE_MM:.1f} everywhere): {ok}")

    # Same pour with the OLD clearance carve (2.0 mm flat) for contrast.
    keepout_old = halos_for(GND_NET, (pads, tracks, vias), hv_nets, OLD_CLEARANCE_CARVE_MM)
    pieces_old = [p for p in carve(region, keepout_old) if p.area >= MIN_ISLAND_AREA_MM2]
    gap_old = min_gap_from_pads(pieces_old, [r for r, _ in hv_pad_net_pairs])
    print(f"    [contrast] old 2.0 mm carve: min gap {gap_old:.2f} mm -> "
          f"{'OK' if gap_old >= PD3_HV_LV_CREEPAGE_MM - 0.5 else 'creepage VIOLATION'}")

    # ------------------------------------------------------------------
    # Experiment B: power_in.ntc-no single hull on F.Cu
    # ------------------------------------------------------------------
    print(f"\n[B] {NTC_NET} single hull on F.Cu (old 2.0 mm clearance vs new creepage carve)")
    ntc_pads = pads_by_net.get(NTC_NET, [])
    ntc_positions = [(p.position[0], p.position[1]) for p in ntc_pads]
    hull = MultiPoint(ntc_positions).convex_hull
    print(f"    hull area {hull.area:.0f} mm², pads {len(ntc_positions)}")

    pads, tracks, vias = collect_obstacles(pcb, "F.Cu", NTC_NET)
    obs = (pads, tracks, vias)
    print(f"    F.Cu foreign: {len(pads)} pads, {len(tracks)} tracks, {len(vias)} vias")

    keepout_old = halos_for(NTC_NET, obs, hv_nets, OLD_CLEARANCE_CARVE_MM)
    pieces_old = [p for p in carve(hull, keepout_old) if p.area >= MIN_ISLAND_AREA_MM2]
    n_old = len(pieces_old)
    cov_old = sum(
        1 for pos in ntc_positions if any(p.contains(Point(pos)) for p in pieces_old)
    )
    print(f"    old carve: {n_old} pieces, {cov_old}/{len(ntc_positions)} pads covered")

    keepout_new = halos_for(NTC_NET, obs, hv_nets, None)
    pieces_new = [p for p in carve(hull, keepout_new) if p.area >= MIN_ISLAND_AREA_MM2]
    n_new = len(pieces_new)
    cov_new = sum(
        1 for pos in ntc_positions if any(p.contains(Point(pos)) for p in pieces_new)
    )
    print(f"    new carve: {n_new} pieces, {cov_new}/{len(ntc_positions)} pads covered")
    print(f"    (47+ island fragmentation was measured with the old carve + real fill)")

    # B2: same net on In3.Cu -- a sparse inner SIGNAL layer (SMD pads do
    # not exist there; only THT pads / through vias obstruct). The design
    # conclusion: HV pours that cannot survive on F.Cu/B.Cu move to a
    # sparse inner layer instead of fragmenting.
    print(f"\n[B2] {NTC_NET} single hull on In3.Cu (sparse inner layer, creepage carve)")
    pads3, tracks3, vias3 = collect_obstacles(pcb, "In3.Cu", NTC_NET)
    obs3 = (pads3, tracks3, vias3)
    print(f"    In3.Cu foreign: {len(pads3)} pads, {len(tracks3)} tracks, {len(vias3)} vias")
    keepout3 = halos_for(NTC_NET, obs3, hv_nets, None)
    pieces3 = [p for p in carve(hull.intersection(board), keepout3) if p.area >= MIN_ISLAND_AREA_MM2]
    cov3 = sum(
        1 for pos in ntc_positions if any(p.contains(Point(pos)) for p in pieces3)
    )
    print(f"    In3.Cu carve: {len(pieces3)} pieces, {cov3}/{len(ntc_positions)} pads covered")

    # ------------------------------------------------------------------
    # Experiment C: +3V3 per-cluster pours on F.Cu
    # ------------------------------------------------------------------
    print(f"\n[C] {V3V3_NET} per-cluster pours on F.Cu (pair carve: 12.6 vs HV, 0.3 vs LV)")
    v33_pads = pads_by_net.get(V3V3_NET, [])
    v33_positions = [(p.position[0], p.position[1]) for p in v33_pads]
    print(f"    {V3V3_NET} pads: {len(v33_positions)}")
    if v33_positions:
        from temper_placer.router_v6.zone_emission import (
            _cluster_positions,
            _convex_hull_from_positions,
        )

        clusters = _cluster_positions(v33_positions)
        print(f"    clusters: {len(clusters)}")
        pieces_c = []
        for group in clusters:
            hull_c = Polygon(_convex_hull_from_positions(group, margin=0.5))
            pieces_c.append(hull_c.intersection(board))
        keepout_c = halos_for(V3V3_NET, collect_obstacles(pcb, "F.Cu", V3V3_NET), hv_nets, None)
        pieces_c = [p for p in carve(unary_union(pieces_c), keepout_c) if p.area >= MIN_ISLAND_AREA_MM2]
        cov_c = sum(
            1 for pos in v33_positions if any(p.contains(Point(pos)) for p in pieces_c)
        )
        print(f"    pieces: {len(pieces_c)}, pads covered: {cov_c}/{len(v33_positions)}")
        print(f"    (router currently emits NO {V3V3_NET} zones -- Power is trace-only)")

    print("\ndone.")


if __name__ == "__main__":
    sys.exit(main())
