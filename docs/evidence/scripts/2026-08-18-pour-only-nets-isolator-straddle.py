#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
"""Re-verify isolator straddle feasibility at PD3 12.6mm on TODAY's parts."""
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.placer.cp_sat.isolation_barrier import (
    load_domain_manifest_nets, compute_pad_groups, evaluate_isolator_feasibility)
from temper_placer.core.isolation_constants import MIN_BARRIER_WIDTH_MM

hv_nets, selv_nets = load_domain_manifest_nets(Path("elec/domain_manifest.yaml"))
pcb = parse_kicad_pcb_v6(Path("pcb/temper.kicad_pcb"))
W = MIN_BARRIER_WIDTH_MM
print(f"manifest: {len(hv_nets)} HV nets, {len(selv_nets)} SELV nets; corridor = {W}mm")
iso=[]
for c in pcb.components:
    nets = {p.net for p in getattr(c,'pins',[]) or [] if p.net}
    if (nets & hv_nets) and (nets & selv_nets): iso.append(c)
print(f"isolators (components with pads on BOTH domains): {len(iso)} -> {sorted(x.ref for x in iso)}")
for axis, aname in ((0,"vertical/X"),(1,"horizontal/Y")):
    print(f"\n--- barrier axis {aname}, width {W}mm")
    infeas=[]
    for c in sorted(iso, key=lambda x:x.ref):
        pg = compute_pad_groups(c, hv_nets, selv_nets)
        f = evaluate_isolator_feasibility(pg, W, barrier_axis=axis)
        ok = getattr(f,'feasible', None)
        gap = getattr(f,'achievable_gap_mm', None)
        gx = getattr(f,'gap_x_mm',None); gy=getattr(f,'gap_y_mm',None)
        if not ok: infeas.append(c.ref)
        print(f"   {c.ref:5} feasible={str(ok):5} achievable_gap={gap if gap is None else round(gap,3)}mm "
              f"gap_x={None if gx is None else round(gx,3)} gap_y={None if gy is None else round(gy,3)}  need>={W}")
    print(f"   INFEASIBLE isolators: {len(infeas)}/{len(iso)} -> {infeas}")
