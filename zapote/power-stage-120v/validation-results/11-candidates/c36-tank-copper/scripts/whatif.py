"""Screen pour options on the body model (c22, bay 55, 0.5 mm, s38 A4 maps): add pours as zone primitives to the all-copper
export, forward-solve, report the gated rows near R5.   python3 whatif.py VARIANT[,VARIANT...] [--r5 0.5]"""
import argparse, gzip, hashlib, json, os, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import s41geo
from shapely.geometry import box, Polygon
from shapely.ops import unary_union
UNIT = Path(__file__).resolve().parents[4]
R = UNIT / "validation-results/04-board-current-thermal/round5-native21"
ap = argparse.ArgumentParser(); ap.add_argument("variants"); ap.add_argument("--r5", type=float, default=1.0)
ap.add_argument("--geom", default=str(UNIT / "native-21/verification/native21s38-all-copper.json.gz"))
ap.add_argument("--a4", default=os.path.join(os.environ.get("S41_RUNS", "."), "s38-task04"))
ap.add_argument("--pitch", type=float, default=0.5); ap.add_argument("--out", default=None)
a = ap.parse_args()
os.environ["B3_A4_DIR"] = a.a4
data, outlines = s41geo.load(a.geom, UNIT / "native-21/layout/copper.json")
HV_R54 = "hv_ret R5.4"; LR_F = "leg_ret Q6.3-R5.1-R13.2"
def zprim(net, layer, poly):
    out = []
    for q in getattr(poly, "geoms", [poly]):
        out.append({"kind": "zone", "net": net, "layer": layer, "shell": [list(c) for c in q.exterior.coords],
                    "holes": [[list(c) for c in r.coords] for r in q.interiors]})
    return out
V = {}
# Z1: F.Cu hv_ret from R5.4 to C40.2 (west of the leg_a-gate_l run at x 43.25, east of leg_b-out_l at x 35.95)
V["Z1"] = ("hv_ret", "F.Cu", box(35.4, 13.3, 43.0, 31.0), (HV_R54,))
# Z2: B.Cu leg_ret round R5.1's via field and Q6.3 (3.2 mm from the sw_b / sw_a B.Cu outlines)
V["Z1a"] = ("hv_ret", "F.Cu", box(35.4, 13.3, 43.0, 25.5), (HV_R54,))
V["Z1b"] = ("hv_ret", "F.Cu", box(35.4, 13.3, 43.0, 22.0), (HV_R54,))
V["Z2"] = ("leg_ret", "B.Cu", box(32.0, 0.6, 44.0, 12.6), ())
# Z3: B.Cu hv_ret round R5.4's via field
V["Z3"] = ("hv_ret", "B.Cu", box(32.0, 12.9, 41.0, 17.0), ())
# Z4: F.Cu leg_ret east of the R5.1 pour to Q3.1 / R12's west side (LOW nets only there)
V["Z4"] = ("leg_ret", "F.Cu", box(31.0, 0.6, 46.0, 10.4), (LR_F,))
add = []
polys = {}
for v in a.variants.split(","):
    if not v: continue
    net, layer, region, skip = V[v]
    # keep 0.25 mm from the other LOW pours of this stage (hv_ret vs leg_ret)
    keep = unary_union([p.buffer(0.25) for (n2, l2), p in polys.items() if l2 == layer and n2 != net]) if polys else None
    p = s41geo.legal(data, outlines, net, layer, region, skip_zone_names=skip, extra_keepout=keep if keep and not keep.is_empty else None)
    polys[(net, layer)] = p
    print(v, net, layer, "area", round(p.area, 1) if p else None, "bounds", [round(c, 2) for c in p.bounds] if p else None)
    add += zprim(net, layer, p)
d2 = dict(data); d2["primitives"] = data["primitives"] + add
d2["board_sha256"] = hashlib.sha256((data["board_sha256"] + a.variants + json.dumps(add)[:2000]).encode()).hexdigest()
work = Path(os.environ.get("S41_RUNS", ".")) / "adj"
gp = work / f"geom-{a.variants.replace(',', '+') or 'base'}.json.gz"
with gzip.open(gp, "wt") as f: json.dump(d2, f)
if a.out:
    Path(a.out).write_text(json.dumps({k[0] + "|" + k[1]: [[list(c) for c in q.exterior.coords] for q in getattr(p, "geoms", [p])] for k, p in polys.items()}))
sys.path.insert(0, str(R / "b3-convergence")); sys.path.insert(0, str(R / "b3-ratings"))
import thermal_body as tb, body_runs as br, fet_case
br.rs.GEOM = gp
BAY = 55.0
rs = br.rs
rs.OPS["c22"] = {"I_t": 1.05 * 22.0, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
heat = json.loads(rs.HEAT_C28.read_text())
k = (1.05 * 22.0 / 29.4) ** 2
for p in heat["parts"]:
    if p["ref"] in br.TANK_ROWS:
        p["watts_nominal"] *= k; p["watts_worst"] *= k
    if p["ref"] == "R5":
        p["watts_nominal"] *= a.r5; p["watts_worst"] *= a.r5
hp = work / f"heat-c22-r5x{a.r5}.json"; hp.write_text(json.dumps(heat))
br.op_inputs = lambda _op: (rs.cases("c22"), hp, "nominal")
brd = tb.Board(gp, work / "cache")
leads = {"pad": "2", "g": tb.drain_lead_conductance(), "t_rise": {r: t - BAY for r, t in fet_case.t_case(22.0).items()}}
res = br.run_case(brd, "c22", 10, a.pitch, "fraction", "network", {}, None, None, True, True, label=a.variants, leads=leads)
off = BAY - 50
P = {p["ref"]: p for p in res["parts"]}
row = {"variant": a.variants or "base", "r5x": a.r5, "block": round(res["peak_1mm_block"]["temperature_c"] + off, 2),
       "block_at": [res["peak_1mm_block"]["x_mm"], res["peak_1mm_block"]["y_mm"], res["peak_1mm_block"]["layer"]],
       "fet_row": round(res["fet_row_max_c"] + off, 2)}
for r in ("C40", "C38", "C41", "C39", "R12", "R20", "R10", "R18", "R5"):
    if r in P: row[r] = round(P[r]["tj_c"] + off, 2)
print(json.dumps(row))
with open(work / "whatif.jsonl", "a") as f: f.write(json.dumps(row) + "\n")
