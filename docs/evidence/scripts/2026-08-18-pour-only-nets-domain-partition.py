#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
"""Q3: is a compliant HV/SELV partition of the current outline achievable at all?"""
from pathlib import Path
from collections import Counter, defaultdict
from shapely.geometry import box, MultiPoint, Point
from shapely.ops import unary_union
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES
from temper_placer.core.isolation_constants import MIN_BARRIER_WIDTH_MM
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.router_v6.routing_space import _get_board_polygon

pcb = parse_kicad_pcb_v6(Path("pcb/temper.kicad_pcb"))
board = _get_board_polygon(pcb)
print(f"board area={board.area:.0f}mm2 bounds={tuple(round(v,1) for v in board.bounds)}  MIN_BARRIER_WIDTH_MM={MIN_BARRIER_WIDTH_MM}")

RANK={"AC":3,"HV":2,"iso":1,"LV":1,None:0}
def cat_of(net):
    nc = TEMPER_NET_ASSIGNMENTS.get(net)
    r = TEMPER_NET_CLASSES.get(nc) if nc else None
    return getattr(r,'safety_category',None) if r else None

dom = {}   # ref -> 'HV' | 'SELV' | 'mixed'
pads_by_ref = defaultdict(list)
for c in pcb.components:
    cats=set()
    for p in getattr(c,'pins',[]) or []:
        if not p.net: continue
        cc = cat_of(p.net)
        cats.add(cc)
        pads_by_ref[c.ref].append((pin_world_position(p,c), p.width, p.height, cc))
    hv = bool(cats & {"AC","HV"})
    lv = bool(cats & {"LV","iso"}) or (None in cats and not hv)
    dom[c.ref] = "STRADDLE" if (hv and lv) else ("HV" if hv else "SELV")
print(Counter(dom.values()))
print("STRADDLE components (carry both HV and SELV nets):", sorted(r for r,d in dom.items() if d=="STRADDLE"))

def pad_geoms(pred):
    gs=[]
    for ref,pl in pads_by_ref.items():
        for (pos,w,h,cc) in pl:
            if pred(ref,cc): gs.append(box(pos[0]-w/2,pos[1]-h/2,pos[0]+w/2,pos[1]+h/2))
    return gs

hv_pads = pad_geoms(lambda r,c: c in ("AC","HV"))
lv_pads = pad_geoms(lambda r,c: c in ("LV","iso",None))
print(f"HV-net pads={len(hv_pads)}  SELV-net pads={len(lv_pads)}")
HU = unary_union(hv_pads); LU = unary_union(lv_pads)
print(f"HV pad hull area={MultiPoint([p for g in hv_pads for p in g.exterior.coords]).convex_hull.area:.0f}mm2 "
      f"({100*MultiPoint([p for g in hv_pads for p in g.exterior.coords]).convex_hull.area/board.area:.0f}% of board)")
print(f"SELV pad hull area={MultiPoint([p for g in lv_pads for p in g.exterior.coords]).convex_hull.area:.0f}mm2 "
      f"({100*MultiPoint([p for g in lv_pads for p in g.exterior.coords]).convex_hull.area/board.area:.0f}% of board)")
hvh = MultiPoint([p for g in hv_pads for p in g.exterior.coords]).convex_hull
lvh = MultiPoint([p for g in lv_pads for p in g.exterior.coords]).convex_hull
ov = hvh.intersection(lvh)
print(f"HV hull  n  SELV hull overlap = {ov.area:.0f}mm2 ({100*ov.area/board.area:.0f}% of board)")
print(f"current min HV-pad to SELV-pad gap = {HU.distance(LU):.3f}mm  (required {MIN_BARRIER_WIDTH_MM}mm)")

# Area accounting: what a compliant layout needs
need = HU.buffer(MIN_BARRIER_WIDTH_MM)
print(f"HV pads dilated by {MIN_BARRIER_WIDTH_MM}mm occupy {need.intersection(board).area:.0f}mm2 "
      f"= {100*need.intersection(board).area/board.area:.1f}% of the board -- SELV copper may not enter it.")
rem = board.difference(need)
print(f"remaining board available to ALL SELV copper: {rem.area:.0f}mm2 ({100*rem.area/board.area:.1f}%), "
      f"in {len(rem.geoms) if hasattr(rem,'geoms') else 1} piece(s)")
selv_area = LU.area
print(f"SELV pad copper area alone = {selv_area:.1f}mm2")
# how many SELV pads currently fall inside the HV halo
inside = sum(1 for g in lv_pads if need.intersects(g))
print(f"SELV pads currently inside the {MIN_BARRIER_WIDTH_MM}mm HV halo: {inside}/{len(lv_pads)}")
