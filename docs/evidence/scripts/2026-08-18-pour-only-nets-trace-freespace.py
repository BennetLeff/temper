#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
"""Exact free-space feasibility for routing the 9 nets as TRACES. READ-ONLY."""
import sys, re, math
from pathlib import Path
from collections import Counter
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.zone_pour_clearance import default_table, collect_zone_obstacle_records
from temper_placer.router_v6.zone_pour_creepage import default_creepage_table
from temper_placer.router_v6.routing_space import _get_board_polygon
from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES
import temper_orchestration as _to

BOARD = Path("pcb/temper.kicad_pcb")
NINE = ["+170V_BUS","DC_BUS_RTN","PWR_RTN","SW_NODE","ac_n","power_in.ntc-no",
        "tank.c_tank1-p2","w1_1","w1_2"]
pcb = parse_kicad_pcb_v6(BOARD)
pads_by_net = dict(_to.run_collect_pad_positions(pcb))
content = BOARD.read_text()
n2n = {m.group(2): int(m.group(1)) for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', content)}
num2name = {v:k for k,v in n2n.items()}
board = _get_board_polygon(pcb)
ctab, creep = default_table(), default_creepage_table()
LAYERS = ["F.Cu","In3.Cu","In4.Cu","B.Cu"]
EDGE_CLEAR = 0.5  # manufacturing min edge-to-copper (generate_kicad_dru)

def halo(rec, extra):
    kind,x,y,a,b,w,sep = rec
    r = sep + extra
    if kind == 0:   # pad rect half-extents a,b
        return box(x-a, y-b, x+a, y+b).buffer(r, join_style=2)
    if kind == 1:   # track
        return LineString([(x,y),(a,b)]).buffer(w/2.0 + r, cap_style=2, join_style=2)
    return Point(x,y).buffer(a/2.0 + r)  # via, a=diameter

WIDTHS = {}
for net in NINE:
    nc = TEMPER_NET_ASSIGNMENTS.get(net,"")
    WIDTHS[net] = TEMPER_NET_CLASSES[nc].trace_width

print("net -> netclass trace_width:", WIDTHS)
print()
for net in NINE:
    nc = TEMPER_NET_ASSIGNMENTS.get(net,"")
    pads = pads_by_net.get(net, [])
    print(f"=== {net}  class={nc}  pads={len(pads)}  spec_width={WIDTHS[net]}mm")
    for wname, w in (("spec", WIDTHS[net]), ("min0.2", 0.2)):
        hw = w/2.0
        for layer in LAYERS:
            recs = collect_zone_obstacle_records(net, layer, pcb=pcb, segments=[],
                net_number_to_name=num2name, clearance_table=ctab, creepage_table=creep)
            seps = Counter(round(r[6],2) for r in recs)
            free = board.buffer(-(hw + EDGE_CLEAR))
            if free.is_empty:
                print(f"   [{wname:6}] {layer}: board buffer(-{hw+EDGE_CLEAR}) EMPTY")
                continue
            obs = unary_union([halo(r, hw) for r in recs])
            free = free.difference(obs)
            geoms = list(free.geoms) if hasattr(free,"geoms") else ([free] if not free.is_empty else [])
            # which component does each pad land in
            comp_of = []
            for p in pads:
                pt = Point(p)
                idx = None
                for i,g in enumerate(geoms):
                    if g.covers(pt): idx = i; break
                comp_of.append(idx)
            reach = [c for c in comp_of if c is not None]
            ncomp = len(set(reach))
            inside = len(reach)
            verdict = "FEASIBLE" if (inside==len(pads) and ncomp==1) else "INFEASIBLE"
            print(f"   [{wname:6}] {layer}: free_area={free.area:8.1f}mm2 pieces={len(geoms):3} "
                  f"pads_in_free={inside}/{len(pads)} distinct_components={ncomp} -> {verdict}"
                  f"   seps={dict(sorted(seps.items()))}" if wname=="spec" and layer=="F.Cu" else
                  f"   [{wname:6}] {layer}: free_area={free.area:8.1f}mm2 pieces={len(geoms):3} "
                  f"pads_in_free={inside}/{len(pads)} distinct_components={ncomp} -> {verdict}")
    print()
