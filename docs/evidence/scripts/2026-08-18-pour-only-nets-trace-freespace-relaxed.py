#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
"""Relaxed Q4: FORGIVE the placement's pre-existing pad creepage violations.
Snap each pad to its nearest free-space piece; do the pads still share a corridor?"""
import re
from pathlib import Path
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.zone_pour_clearance import default_table, collect_zone_obstacle_records
from temper_placer.router_v6.zone_pour_creepage import default_creepage_table
from temper_placer.router_v6.routing_space import _get_board_polygon
from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES
import temper_orchestration as _to

BOARD=Path("pcb/temper.kicad_pcb")
NINE=["+170V_BUS","DC_BUS_RTN","PWR_RTN","SW_NODE","ac_n","power_in.ntc-no",
      "tank.c_tank1-p2","w1_1","w1_2"]
pcb=parse_kicad_pcb_v6(BOARD); pads_by_net=dict(_to.run_collect_pad_positions(pcb))
c=BOARD.read_text(); n2n={m.group(2):int(m.group(1)) for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"',c)}
num2name={v:k for k,v in n2n.items()}
board=_get_board_polygon(pcb); ctab,creep=default_table(),default_creepage_table()
def halo(r,e):
    k,x,y,a,b,w,s=r; R=s+e
    if k==0: return box(x-a,y-b,x+a,y+b).buffer(R,join_style=2)
    if k==1: return LineString([(x,y),(a,b)]).buffer(w/2+R,cap_style=2,join_style=2)
    return Point(x,y).buffer(a/2+R)
SNAP=25.0
for net in NINE:
    nc=TEMPER_NET_ASSIGNMENTS.get(net,""); W=TEMPER_NET_CLASSES[nc].trace_width
    pads=pads_by_net.get(net,[])
    line=f"{net:18} w={W:.1f} pads={len(pads):2} |"
    for W_use,tag in ((W,"spec"),(0.2,"0.2")):
        hw=W_use/2
        best=None
        for layer in ("F.Cu","In3.Cu","In4.Cu","B.Cu"):
            recs=collect_zone_obstacle_records(net,layer,pcb=pcb,segments=[],
                net_number_to_name=num2name,clearance_table=ctab,creepage_table=creep)
            free=board.buffer(-(hw+0.5)).difference(unary_union([halo(r,hw) for r in recs]))
            gs=list(free.geoms) if hasattr(free,'geoms') else ([free] if not free.is_empty else [])
            gs=[g for g in gs if g.area>0.01]
            assign=[]
            for p in pads:
                pt=Point(p); d=[(g.distance(pt),i) for i,g in enumerate(gs)]
                d=[x for x in d if x[0]<=SNAP]
                assign.append(min(d)[1] if d else None)
            uniq=len({a for a in assign if a is not None}); miss=sum(1 for a in assign if a is None)
            score=(miss, uniq)
            if best is None or score<best[0]: best=(score,layer,uniq,miss,max((g.area for g in gs),default=0.0))
        (sc,layer,uniq,miss,maxa)=best
        v="FEASIBLE" if (miss==0 and uniq==1) else "INFEASIBLE"
        line+=f"  [{tag}] best={layer} pads_snapped_to {uniq} distinct corridor(s), {miss} unreachable, largest_free={maxa:.0f}mm2 -> {v} |"
    print(line)
