#!/usr/bin/env python3
"""Partition the native-21 stage-20 board into S1 / S2-A / S2-B resulting boards; list crossing nets,
placement counts, courtyard areas and a density-based board-area estimate.
    python3 -I partition.py -> ../results/partition.json
Read-only: native-21/section.kicad_pcb, layout/parts.json, placement.json, layout/domains.py (SELV list from audit.rs),
11-candidates/scripts/map_groups.py (group assignment), fab/bom-jlcpcb.csv."""
import sys, json, re, csv, math
sys.dont_write_bytecode = True
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
PS = HERE.parents[3]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(PS/"native-21/layout")); sys.path.insert(0, str(PS/"validation-results/11-candidates/scripts"))
import netparse, domains, map_groups

fp = netparse.footprints(); parts = netparse.parts(); pl = netparse.placement()
grp = {}
for r, p in parts.items():
    grp[r] = map_groups.assign(p["path"], p["group"])
unassigned = [r for r, g in grp.items() if g is None]
dom = domains.domain
GATE_FET = {f"leg_{l}-gate_{h}" for l in "ab" for h in "hl"}
KEEP_NETS = {"bus_p", "rect_p", "rect_n", "vdiv_1", "vdiv_2", "vdiv_3"}      # HV nodes never leave the power board
FORCE_POW = {"R5", "T1", "PS1", "PS2", "F2", "J11", "J3", "J6", "R38", "BR1"}
# refs for which the netlist says SELV-less mains/HV connection: parts of the line_zc group stay (mains tap)
def side_common(r):
    g = grp[r]; n = fp[r]["nets"]
    if g in ("G01", "G02", "G03", "G04") or r in FORCE_POW: return "P"
    if parts[r]["group"] == "line_zc" or parts[r]["group"].startswith("other:c_ref_xfer"): return "P"
    if n & GATE_FET: return "P"            # F6 network + gate resistors sit at the FET gate pins
    if n & KEEP_NETS: return "P"
    return None
def S2A(r):
    s = side_common(r)
    if s: return s
    return "P" if grp[r] in ("G05", "G06", "G07") else "D"
def S2B(r):
    s = side_common(r)
    if s: return s
    return "D"
def S2L(r):
    s = side_common(r)
    if s: return s
    return "P" if grp[r] in ("G05", "G06", "G07", "G08") else "D"
def S1(r):
    return "I" if grp[r] == "G01" and r not in ("BR1", "J6") else "M"  # J6 stays as the main board PE landing (R38 strap)
bom = list(csv.DictReader(open(PS/"validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv")))
mount = {}
for row in bom:
    for d in [x.strip() for x in row["Designator"].split(",")]: mount[d] = row["Mount"]
def area(r):
    p = parts[r]; return p["w"]*p["h"]
def stats(sel):
    refs = sel
    xs = [pl[parts[r]["path"]][0] for r in refs]; ys = [pl[parts[r]["path"]][1] for r in refs]
    ca = sum(area(r) for r in refs)
    tht = sum(1 for r in refs if mount.get(r) == "THT")
    return dict(n=len(refs), tht=tht, courtyard_mm2=round(ca), bbox=[round(min(xs),1), round(min(ys),1), round(max(xs),1), round(max(ys),1)])
def cross(assign, sides):
    nets = {}
    for r in parts:
        for n in fp[r]["nets"]:
            nets.setdefault(n, {}).setdefault(assign(r), []).append(r)
    rows = []
    for n, d in nets.items():
        if len(d) > 1:
            rows.append(dict(net=n, domain=dom(n), sides={k: sorted(v) for k, v in d.items()}))
    return sorted(rows, key=lambda x: (x["domain"], x["net"]))
res = {"unassigned": unassigned, "n_parts_pcb": len(parts)}
for name, f, sides in (("S1", S1, "IM"), ("S2A", S2A, "PD"), ("S2B", S2B, "PD"), ("S2L", S2L, "PD")):
    asg = {r: f(r) for r in parts}
    res[name] = {s: stats([r for r in parts if asg[r] == s]) for s in sides}
    res[name]["refs"] = {s: sorted(r for r in parts if asg[r] == s) for s in sides}
    cr = cross(lambda r: asg[r], sides)
    # a net 'crosses' only if it has pads on both boards; also keep global nets (selv_gnd, v3v3) in the list
    res[name]["crossing"] = cr
    res[name]["crossing_by_domain"] = {}
    for c in cr: res[name]["crossing_by_domain"][c["domain"]] = res[name]["crossing_by_domain"].get(c["domain"], 0) + 1
json.dump(res, open(OUT/"results/partition.json", "w"), indent=1)
for k in ("S1", "S2A", "S2B", "S2L"):
    print(k, {s: {a: b for a, b in v.items() if a != "refs"} for s, v in res[k].items() if s in "IMPD" and len(s) == 1}, res[k]["crossing_by_domain"])
print("unassigned", unassigned)
