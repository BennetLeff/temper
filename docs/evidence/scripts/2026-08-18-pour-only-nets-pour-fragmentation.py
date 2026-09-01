#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
"""Per-net pour fragmentation: clustering vs carve. READ-ONLY on the board."""
from pathlib import Path
import temper_geometry as _tg
from shapely.geometry import Polygon
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.zone_emission import _cluster_positions, _convex_hull_from_positions, _clip_to_board, compute_zones_for_net
from temper_placer.router_v6._zone_pour_stitch import (
    _zone_layers_for_net, _zone_params_for_net, _own_pads_on_layer,
    _CONTINUITY_EXEMPT_CLASSES, _CONTINUITY_EXEMPT_NETS, _MIN_CARVED_AREA_MM2,
)
from temper_placer.router_v6.zone_pour_clearance import default_table, collect_zone_obstacle_records
from temper_placer.router_v6.zone_pour_creepage import default_creepage_table
from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
import temper_orchestration as _to

BOARD = Path("pcb/temper.kicad_pcb")
NINE = ["+170V_BUS","DC_BUS_RTN","PWR_RTN","SW_NODE","ac_n","power_in.ntc-no",
        "tank.c_tank1-p2","w1_1","w1_2"]

pcb = parse_kicad_pcb_v6(BOARD)
pad_positions = dict(_to.run_collect_pad_positions(pcb))
content = BOARD.read_text()
import re
net_name_to_number = {m.group(2): int(m.group(1)) for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', content)}
from temper_placer.router_v6.routing_space import _get_board_polygon
board_polygon = _get_board_polygon(pcb)
print(f"board polygon area = {board_polygon.area:.1f} mm2  bounds={tuple(round(v,2) for v in board_polygon.bounds)}")
number_to_name = {v:k for k,v in net_name_to_number.items()}
ctab, creep = default_table(), default_creepage_table()
stackup_layers = {ly.name for ly in pcb.stackup.layers}
print("stackup layers:", sorted(stackup_layers))
print()

for net in NINE:
    pos = pad_positions.get(net, [])
    nc = TEMPER_NET_ASSIGNMENTS.get(net,"")
    exempt = nc in _CONTINUITY_EXEMPT_CLASSES or net in _CONTINUITY_EXEMPT_NETS
    margin, _ = _zone_params_for_net(net)
    print(f"=== {net}  class={nc} pads={len(pos)} exempt={exempt} margin={margin}")
    xs=[p[0] for p in pos]; ys=[p[1] for p in pos]
    if pos:
        print(f"    pad bbox: x {min(xs):.2f}..{max(xs):.2f} ({max(xs)-min(xs):.2f}mm)  y {min(ys):.2f}..{max(ys):.2f} ({max(ys)-min(ys):.2f}mm)")
    groups = _cluster_positions(pos) if not exempt else [list(pos)]
    print(f"    CLUSTERS: {len(groups)}  sizes={[len(g) for g in groups]}")
    for gi,g in enumerate(groups):
        gx=[p[0] for p in g]; gy=[p[1] for p in g]
        print(f"      c{gi}: n={len(g)} centroid=({sum(gx)/len(gx):.1f},{sum(gy)/len(gy):.1f}) span=({max(gx)-min(gx):.1f}x{max(gy)-min(gy):.1f})")
    zl = [l for l in _zone_layers_for_net(net) if l in stackup_layers]
    tot_islands = 0
    for layer in zl:
        own = _own_pads_on_layer(net, layer, pcb=pcb, fallback_positions=pos)
        if not own:
            print(f"    layer {layer}: NO OWN PADS -> pour skipped entirely")
            continue
        obstacles = collect_zone_obstacle_records(net, layer, pcb=pcb, segments=[],
            net_number_to_name=number_to_name, clearance_table=ctab, creepage_table=creep)
        zds = compute_zones_for_net(net, net_name_to_number.get(net,0), pos, layer=layer,
                                    margin=margin, cluster=not exempt, board_polygon=board_polygon)
        pads_only = nc not in ("GND",)
        per_hull = []
        for zd in zds:
            pz = _tg.pour_outline_py(list(zd.points), own, obstacles, _MIN_CARVED_AREA_MM2, pads_only)
            per_hull.append(len(pz))
        tot_islands += sum(per_hull)
        print(f"    layer {layer}: own_pads={len(own)} obstacles={len(obstacles)} hulls_after_clip={len(zds)} islands_per_hull={per_hull} total={sum(per_hull)}")
    print(f"    TOTAL ISLANDS (all layers) = {tot_islands}")
    print()
