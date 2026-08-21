#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
from pathlib import Path
from collections import Counter
from temper_placer.io.netclass_loader import load_netclass_rules
from temper_placer.placer.cp_sat.netclass_constraints import generate_netclass_separated_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
nr = load_netclass_rules(Path("packages/temper-placer/configs/netclass_rules.yaml"))
pcb = parse_kicad_pcb_v6(Path("pcb/temper.kicad_pcb"))
class N: pass
nl=N(); nl.components = pcb.components
cons = generate_netclass_separated_constraints(nl, pcb.components, nr.design_rules,
                                               existing_constraints=[], touch_refs=None)
NINE = {"+170V_BUS","DC_BUS_RTN","PWR_RTN","SW_NODE","ac_n","power_in.ntc-no",
        "tank.c_tank1-p2","w1_1","w1_2"}
refs9=set()
for c in pcb.components:
    for p in getattr(c,'pins',[]) or []:
        if p.net in NINE: refs9.add(c.ref)
t=[c for c in cons if c.a in refs9 or c.b in refs9]
print(f"constraints touching the 9's {len(refs9)} components: {len(t)}")
print("their min_distance_mm:", Counter(round(c.min_distance_mm,3) for c in t).most_common())
# pairs at 6.0 = the strictest the model ever asks for
print("max over those:", max(c.min_distance_mm for c in t))
# The real DRC-graded pairs: check a few
for c in t[:5]: print("  ", c.id, c.a, c.b, c.min_distance_mm, "|", c.because[:80])
