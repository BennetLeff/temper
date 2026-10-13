#!/usr/bin/env python3
"""Board-level DFM numbers and test-access coverage from the stage-20 copper dump.

    python3 -I board_test_dfm.py  ->  results/board_test_dfm.json

(a) outline bbox / area, SMD pad distance to the outline (JLC process-edge question),
(b) the 0.8 mm vias (JLC tents/fills only <= 0.5 mm),
(c) test access per net: board-only TP, THT lead (bottom), top SMD pad >= 0.5 mm (flying-probe reachable before
    parts are loaded; on the loaded board only if not under a body), tented via only (NOT probeable).
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely.geometry import MultiPoint, Point, Polygon

from common import R2, copper

d = copper()
prim = d["primitives"]
out_poly = Polygon(d["outline"]["shell"], [h for h in d["outline"]["holes"]] or None)
minx, miny, maxx, maxy = out_poly.bounds
res = {"outline_bbox_mm": [round(maxx - minx, 2), round(maxy - miny, 2)],
       "outline_area_cm2": round(out_poly.area / 100, 1), "bbox_area_cm2": round((maxx - minx) * (maxy - miny) / 100, 1)}

# (a) SMD pad edge distance
bnd = out_poly.exterior
mins = []
for p in prim:
    if p["kind"] == "pad" and p["drill_mm"] == [0.0, 0.0] and p["layer"] == "F.Cu":
        poly = Polygon(p["shell"])
        mins.append((bnd.distance(poly), p["ref"]))
mins.sort()
res["closest_smd_pads_to_edge_mm"] = [(round(a, 2), b) for a, b in mins[:5]]
res["smd_pads_within_3mm_of_edge"] = sum(1 for a, _ in mins if a < 3.0)
res["smd_pads_within_5mm_of_edge"] = sum(1 for a, _ in mins if a < 5.0)

# (b) big vias
big = {}
for p in prim:
    if p["kind"] == "via" and p["drill_mm"] > 0.5 and p["layer"] == "F.Cu":
        big[tuple(p["centre"])] = (p["net"], p["drill_mm"])
res["vias_over_0p5mm"] = [{"at": list(k), "net": v[0], "drill": v[1]} for k, v in sorted(big.items())]
res["vias_over_0p5mm_nets"] = dict(collections.Counter(v[0] for v in big.values()))

# (c) test access
nets = collections.defaultdict(lambda: {"tp": 0, "tht": 0, "smd_top": 0, "via": set(), "pads": set(), "track_len": 0.0})
for p in prim:
    n = p.get("net")
    if not n:
        continue
    if p["kind"] == "pad" and p["layer"] in ("F.Cu", "B.Cu"):
        key = p["ref"]
        nets[n]["pads"].add(key)
        ref = key.split(".")[0]
        if ref.startswith("TP"):
            nets[n]["tp"] += 1
        elif p["drill_mm"] != [0.0, 0.0]:
            nets[n]["tht"] += 1
        elif p["layer"] == "F.Cu":
            xs = [q[0] for q in p["shell"]]; ys = [q[1] for q in p["shell"]]
            if min(max(xs) - min(xs), max(ys) - min(ys)) >= 0.5:
                nets[n]["smd_top"] += 1
    elif p["kind"] == "via" and p["layer"] == "F.Cu":
        nets[n]["via"].add(tuple(p["centre"]))
    elif p["kind"] == "track":
        nets[n]["track_len"] += abs(p["end"][0] - p["start"][0]) + abs(p["end"][1] - p["start"][1])
real = {n: v for n, v in nets.items() if len(v["pads"]) >= 2}      # a net with one pad is a stub/NC, not a test target
tot = len(real)
c_tp = sum(1 for v in real.values() if v["tp"])
c_tp_tht = sum(1 for v in real.values() if v["tp"] or v["tht"])
c_any = sum(1 for v in real.values() if v["tp"] or v["tht"] or v["smd_top"])
no = sorted(n for n, v in real.items() if not (v["tp"] or v["tht"] or v["smd_top"]))
tp_only_other = sorted(n for n, v in real.items() if not v["tp"] and (v["tht"] or v["smd_top"]))
res["nets_with_2plus_pads"] = tot
res["nets_with_board_TP"] = c_tp
res["nets_with_TP_or_THT_lead"] = c_tp_tht
res["nets_with_any_probeable_feature"] = c_any
res["nets_unreachable"] = no
res["pct"] = {"tp": round(100 * c_tp / tot, 1), "tp_or_tht": round(100 * c_tp_tht / tot, 1), "any": round(100 * c_any / tot, 1)}
# pad-count weighted: how many pads sit on a net that has a TP (ICT-style 'every net touched once' needs all nets)
res["tp_count"] = sum(1 for p in prim if p["kind"] == "pad" and p["layer"] in ("F.Cu", "B.Cu") and p["ref"].startswith("TP")) // 1
tp_refs = {p["ref"].split(".")[0] for p in prim if p["kind"] == "pad" and p["ref"].startswith("TP")}
res["tp_refs"] = len(tp_refs)
# nets that carry the safety-relevant signals in BRINGUP-PROBES but have no TP
res["probeable_without_tp_count"] = len(tp_only_other)
json.dump(res, open(R2 / "results/board_test_dfm.json", "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ("nets_unreachable",)}, indent=1))
print("unreachable", len(no), no[:60])
