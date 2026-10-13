#!/usr/bin/env python3
"""Minimise the JLC-preview dependency of the 47 NEEDS-PREVIEW CPL lines.

    python3 -I cpl_preview.py  ->  results/cpl_preview.json, results/jlc-rotation-golden.csv

Classes (rules, written down so they can be argued with):
  SYM   a wrong rotation cannot change the circuit or the fit: non-polar 2-pad Y cap / MOV at 180 deg symmetric
        pads, and the REDCUBE studs (four same-net pads per stud, square body). Rotation is not a preview item.
  HAND  through-hole body keyed by shroud/pin-1 silk and inserted by a person at JLC or in-house: the CPL rotation is
        a hint. Cover it with pin-1 call-outs on the assembly drawing and first-article inspection, not a CPL preview.
  POL   polarised SMD (electrolytic): wrong rotation reverses the part. Preview mandatory, plus first-article.
  SMD   everything else, grouped per (LCSC, footprint); one designator per group settles the group.
The golden table is the artefact that removes the dependency for every later build: after one confirmed lot, the CPL
generator reads it by LCSC and nothing is previewed again (rotations are a property of the LCSC part and the KiCad
footprint, not of the board).
"""
import collections
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AUDIT, R2

rows = list(csv.DictReader(open(AUDIT)))
need = [r for r in rows if r["class"] == "NEEDS-PREVIEW"]
SYM_REF = {"C3", "C4", "RV1", "J2", "J5", "J7", "J8", "J9", "J10"}
HAND_REF = {"L1", "PS1", "PS2", "J4", "J6"}
POL_REF = {"C126", "C127", "C128", "C129"}


def cls(r):
    d = r["designator"]
    if d in SYM_REF:
        return "SYM"
    if d in HAND_REF:
        return "HAND"
    if d in POL_REF:
        return "POL"
    return "SMD"


by = collections.defaultdict(list)
for r in need:
    by[cls(r)].append(r)
groups = collections.defaultdict(list)
for r in need:
    groups[(cls(r), r["lcsc"], r["footprint"].split("_ReviewOnly")[0][:40])].append(r["designator"])
sot = [r for r in need if r["footprint"].startswith("SOT-23")]
out = {
    "needs_preview_lines": len(need),
    "groups_today": len({(r["lcsc"], r["footprint"]) for r in need}),
    "by_class_lines": {k: len(v) for k, v in by.items()},
    "by_class_groups": {k: len({(r["lcsc"], r["footprint"]) for r in v}) for k, v in by.items()},
    "preview_designators_needed_after_classing": len({(r["lcsc"], r["footprint"]) for r in by["SMD"] + by["POL"]}),
    "sot23_family": {"lines": len(sot), "lcsc_groups": len({r["lcsc"] for r in sot}),
                     "db_rot_all": sorted({r["db_rot"] for r in sot}), "fit_rot_all": sorted({r["proposed_jlc_rot"] for r in sot}),
                     "kicad_rot_all": sorted({r["kicad_rot"] for r in sot})},
    "groups": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in groups.items()},
}
json.dump(out, open(R2 / "results/cpl_preview.json", "w"), indent=1)

# golden table: one row per LCSC, status UNCONFIRMED until the owner records the preview result
with open(R2 / "results/jlc-rotation-golden.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["lcsc", "footprint", "kicad_rot", "proposed_jlc_rot", "db_alt_rot", "class", "designators", "status", "confirmed_by_preview_on"])
    gg = collections.defaultdict(list)
    for r in need:
        gg[(r["lcsc"], r["footprint"].split("_ReviewOnly")[0], r["kicad_rot"], r["proposed_jlc_rot"], r["db_rot"], cls(r))].append(r["designator"])
    for k, v in sorted(gg.items()):
        w.writerow([*k, " ".join(v), "UNCONFIRMED", ""])
print(json.dumps({k: v for k, v in out.items() if k != "groups"}, indent=1))
