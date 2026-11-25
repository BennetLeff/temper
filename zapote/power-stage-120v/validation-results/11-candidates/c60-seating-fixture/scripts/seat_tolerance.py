#!/usr/bin/env python3
"""OPEN-ITEMS S32: can one flat bar hold four TO-247 tabs coplanar while their leads sit in the s57 holes?

    python3 -I seat_tolerance.py      -> ../seat-tolerance.json  (exit 1 if a control fails)

The bar sets the tab plane; every lead must then lie freely inside its hole, or it is bent and the tab springs off the bar when released.
Lead = a b x c rectangle in a round hole, so the CORNER limits the play across the tab plane: sqrt((D/2)^2 - (b/2 + ex)^2) - c/2.
bench-sink-r1 and DECISIONS 87 use the flat-strip form (D - c)/2, which ignores b. Sharp corners assumed (bounds a real lead).
Parameters are bench-sink-r1's (bench_params.py, imported): TO247 b, c, A1; PTH_TOL; HOLE_POS_TOL; A1_LOT_TOL (EST).
ex = lead-to-hole offset along the row left after the part is centred: one hole-position tolerance (EST).
Bar setting: the bar floats in y with the parts lightly clamped, is slid to both stops (indicator) and locked at mid-travel, so a lot-mean A1 and a
common board offset drop out. What is left per FET: hole position + lot A1 spread + bar flatness."""
import importlib.util, json, math
from pathlib import Path
H = Path(__file__).resolve().parent
S = H.parents[1] / "bench-sink-r1/scripts/bench_params.py"
spec = importlib.util.spec_from_file_location("bp", S); P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
FLAT, EX = 0.03, P.HOLE_POS_TOL
DMIN, DNOM, DMAX = P.FET_DRILL + P.PTH_TOL[0], P.FET_DRILL + sum(P.PTH_TOL) / 2, P.FET_DRILL + P.PTH_TOL[1]
NEED = P.HOLE_POS_TOL + P.A1_LOT_TOL + FLAT
NEED_DS = P.HOLE_POS_TOL + (P.TO247["A1"][1] - P.TO247["A1"][0]) / 2 + FLAT
def play(d, b, c, ex=EX):
    r, h = d / 2, b / 2 + ex
    return math.sqrt(r * r - h * h) - c / 2 if r > h else -c / 2
flat = lambda d, c: (d - c) / 2
b0, b1 = P.TO247["b"]; c0, c1 = P.TO247["c"]
corners = {f"D {d:.2f} b {b:.2f} c {c:.2f}": {"flat_strip": round(flat(d, c), 3), "corner": round(play(d, b, c, 0), 3), "corner_ex": round(play(d, b, c), 3),
            "closes": play(d, b, c) >= NEED} for d in (DMIN, DNOM, DMAX) for b, c in ((b0, c0), (1.2, 0.6), (b1, c1))}
def cmax(b, d):                       # largest lead thickness that closes at this width
    r, h = d / 2, b / 2 + EX
    return round(2 * (math.sqrt(r * r - h * h) - NEED), 3)
limit = {f"{b:.2f}": {"c_max_min_hole": cmax(b, DMIN), "c_max_nominal_hole": cmax(b, DNOM)} for b in (1.0, 1.1, 1.2, 1.3, 1.4)}
drill_for_worst = round(2 * math.hypot(b1 / 2 + EX, NEED + c1 / 2) - P.PTH_TOL[0], 3)
bt, bw = P.GBJ["lead_t"], P.GBJ["lead_w"]; D1 = P.BR1_DRILL_FIN
br1 = {"step_shift_needed_mm": 0.2, "flat_strip_worst": round((D1[0] - bt[1]) / 2, 3), "corner_worst": round(play(D1[0], bw[1], bt[1], 0), 3),
       "corner_nominal": round(play(sum(D1) / 2, 1.0, 0.7, 0), 3), "need_with_hole_pos": round(0.2 + P.HOLE_POS_TOL, 3)}
br1["closes_worst"] = br1["corner_worst"] >= br1["need_with_hole_pos"]; br1["closes_nominal"] = br1["corner_nominal"] >= br1["need_with_hole_pos"]
fails = []
if abs(flat(DMIN, c1) - 0.415) > 1e-6: fails.append("flat form does not reproduce DECISIONS 87's 0.415")
if not play(DMIN, b1, c1, 0) < flat(DMIN, c1): fails.append("corner must be below flat")
if abs(math.hypot(b1 / 2, c1 / 2 + play(DMIN, b1, c1, 0)) - DMIN / 2) > 1e-9: fails.append("corner does not land on the hole wall")
if play(1.5 + P.PTH_TOL[0], b1, c1, 0) >= 0: fails.append("negative control: the s56 1.5 mm hole must refuse the largest lead")
out = {"need_mm": round(NEED, 3), "need_datasheet_A1_mm": round(NEED_DS, 3), "corners": corners, "lead_limit_one_lot": limit,
       "drill_that_closes_the_worst_lead_mm": drill_for_worst, "BR1": br1, "control_fails": fails}
(H.parent / "seat-tolerance.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1)); raise SystemExit(1 if fails else 0)
