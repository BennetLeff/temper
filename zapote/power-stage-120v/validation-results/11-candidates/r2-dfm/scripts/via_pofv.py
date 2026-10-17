#!/usr/bin/env python3
"""Via-in-pad census on the stage-20 copper and a classification of which in-pad vias need to stay in the pad.

    python3 -I via_pofv.py   ->  results/via_pofv.json

Method: every 0.3 mm-drill via (unique centre) is tested against each SMD pad on F.Cu / B.Cu (pad polygon from the
copper dump). 'inside' = the whole drill circle is within the pad, 'edge' = the circle crosses the pad boundary.
Classes (rules, not judgment; the electrical reason is in PROPOSALS.md):
  TP     the pad is a board-only test pad (bare copper, no paste): the via is under it by construction.
  R5     the pad is the shunt R5 (current pads and Kelvin fingers).
  EP     the pad is an IC exposed/thermal pad (area >= 4 mm2 on a U* part): thermal + current vias.
  POWER  other pad >= 3 mm2 (D*, Q*, C* big pads, J*): current/thermal reason, move only with re-layout.
  SMALL  everything else (passive / signal pads): a dogbone off the pad is the normal practice.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shapely.geometry import Point, Polygon

from common import R2, copper

d = copper()
prim = d["primitives"]
vias = {}
for p in prim:
    if p["kind"] == "via" and abs(p["drill_mm"] - 0.3) < 1e-6:
        vias[tuple(p["centre"])] = p
pads = []
for p in prim:
    if p["kind"] == "pad" and p["drill_mm"] == [0.0, 0.0] and p["layer"] in ("F.Cu", "B.Cu"):
        poly = Polygon(p["shell"], p.get("holes") or None)
        if poly.is_valid and not poly.is_empty:
            pads.append((p, poly))

rows = []
for c, v in vias.items():
    circ = Point(c).buffer(v["drill_mm"] / 2, 16)
    hit = None
    for p, poly in pads:
        if p["net"] != v["net"]:
            continue
        if not poly.intersects(circ):
            continue
        if poly.contains(circ):
            hit = ("inside", p, poly)
            break
        hit = hit or ("edge", p, poly)
    if not hit:
        continue
    kind, p, poly = hit
    ref = p["ref"].split(".")[0]
    area = poly.area
    if ref.startswith("TP"):
        cls = "TP"
    elif ref == "R5":
        cls = "R5"
    elif ref.startswith("U") and area >= 4.0:
        cls = "EP"
    elif area >= 3.0:
        cls = "POWER"
    else:
        cls = "SMALL"
    rows.append({"via": list(c), "pad": p["ref"], "net": v["net"], "pos": kind, "pad_area_mm2": round(area, 2),
                 "pad_layer": p["layer"], "via_pad_dia": v["diameter_mm"], "class": cls})

cnt = collections.Counter((r["class"], r["pos"]) for r in rows)
bycls = collections.Counter(r["class"] for r in rows)
byref = collections.Counter(r["pad"].split(".")[0] for r in rows if r["class"] in ("EP", "POWER", "R5"))
res = {
    "vias_0p3_total": len(vias),
    "in_pad_total": len(rows),
    "inside": sum(r["pos"] == "inside" for r in rows),
    "edge": sum(r["pos"] == "edge" for r in rows),
    "by_class": dict(bycls),
    "by_class_pos": {f"{k[0]}/{k[1]}": n for k, n in sorted(cnt.items())},
    "by_ref_required_classes": dict(byref),
    "required_in_pad": sum(bycls[c] for c in ("EP", "R5")),
    "movable_without_function_change": sum(bycls[c] for c in ("TP", "SMALL", "POWER")),
    "rows": rows,
    "other_via_sizes": dict(collections.Counter(
        (p["diameter_mm"], p["drill_mm"]) for p in prim if p["kind"] == "via" and p["layer"] == "F.Cu")
        and {f"{k[0]}/{k[1]}": n for k, n in collections.Counter(
            (p["diameter_mm"], p["drill_mm"]) for p in prim if p["kind"] == "via" and p["layer"] == "F.Cu").items()}),
}
(R2 / "results").mkdir(exist_ok=True)
json.dump(res, open(R2 / "results/via_pofv.json", "w"), indent=1)
print({k: v for k, v in res.items() if k != "rows"})
