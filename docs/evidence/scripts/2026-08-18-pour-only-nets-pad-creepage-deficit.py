#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
"""Per-pad: actual edge-to-edge gap to nearest other-net copper vs required separation."""
import re
from pathlib import Path
from shapely.geometry import Point, LineString, box
from shapely.strtree import STRtree
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.zone_pour_clearance import default_table, collect_zone_obstacle_records
from temper_placer.router_v6.zone_pour_creepage import default_creepage_table
from temper_placer.core.pin_geometry import pin_world_position, pin_world_layer
import temper_orchestration as _to

BOARD = Path("pcb/temper.kicad_pcb")
NINE = ["+170V_BUS","DC_BUS_RTN","PWR_RTN","SW_NODE","ac_n","power_in.ntc-no",
        "tank.c_tank1-p2","w1_1","w1_2"]
pcb = parse_kicad_pcb_v6(BOARD)
content = BOARD.read_text()
n2n = {m.group(2): int(m.group(1)) for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', content)}
num2name = {v:k for k,v in n2n.items()}
ctab, creep = default_table(), default_creepage_table()

def shape_of(rec):
    kind,x,y,a,b,w,sep = rec
    if kind == 0: return box(x-a,y-b,x+a,y+b)
    if kind == 1: return LineString([(x,y),(a,b)]).buffer(w/2.0, cap_style=2, join_style=2)
    return Point(x,y).buffer(a/2.0)

# own pads with geometry
own = {}
for comp in pcb.components:
    for pin in getattr(comp,'pins',[]) or []:
        if pin.net in NINE:
            pos = pin_world_position(pin, comp)
            own.setdefault(pin.net, []).append((f"{comp.ref}.{pin.number}", pos, pin.width, pin.height, pin_world_layer(pin)))

LAYERS=["F.Cu","In3.Cu","In4.Cu","B.Cu"]
worst_overall = []
for net in NINE:
    print(f"=== {net}")
    for layer in ("F.Cu",):
        recs = collect_zone_obstacle_records(net, layer, pcb=pcb, segments=[],
            net_number_to_name=num2name, clearance_table=ctab, creepage_table=creep)
        shapes = [shape_of(r) for r in recs]
        tree = STRtree(shapes)
        for ref, pos, w, h, pl in own.get(net, []):
            g = box(pos[0]-w/2, pos[1]-h/2, pos[0]+w/2, pos[1]+h/2)
            # find worst deficit
            worst = None
            for i in tree.query(g.buffer(20.0)):
                d = g.distance(shapes[i])
                req = recs[i][6]
                deficit = req - d
                if worst is None or deficit > worst[0]:
                    worst = (deficit, d, req, recs[i])
            if worst is None: continue
            deficit, d, req, rec = worst
            flag = "VIOLATES" if deficit > 1e-6 else "ok"
            print(f"   {ref:10} layer={str(pl):8} min_gap={d:7.3f}mm required={req:6.2f}mm deficit={deficit:+7.3f} {flag}")
            worst_overall.append((net, ref, deficit))
print()
bad = [x for x in worst_overall if x[2] > 1e-6]
print(f"pads whose EXISTING position already violates its own required separation (F.Cu obstacle set): {len(bad)}/{len(worst_overall)}")
