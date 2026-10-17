#!/usr/bin/env python3
"""FET Tj levers at 28 A (basis A = the conservative switching proxy of DECISIONS 15 / round-6 board_side.py).
Self-contained copy of the R33 requirement.py solve()/rds() (D-18 loss model; sources cited in that file's docstring:
IPW65R018CFD7 Rev 2.0 RthJC 0.28 K/W max; switching 12.7574 W HS / 13.1537 W LS at 36 kHz, scaled by f).
Levers: (1) interface Rcs (grease Electrolube HTCP20S 2.5 W/mK as chosen in DECISIONS M11, R = BLT/k/A; AlN k 150 W/mK 2 mm 1-D, Kyocera AN216A);
(2) sink R_SA (S8 0.29+0.0161 ped, K1 0.214); (3) firmware I_tank(f) cap that holds Tj <= 125 C.
Control: reproduces round-6 board-side-fets.csv A_tj_max_C 129.0 / 134.5 / 140.1 (28 A, 40/45/50 kHz, 120 V).
Run: python3 -I fet_tj_levers.py  -> results/fet_tj_levers.json"""
import json, math
from pathlib import Path
HERE = Path(__file__).resolve().parent
MOS = ("Q5", "Q6", "Q3", "Q2")
SW = {"Q2": 12.7574, "Q5": 12.7574, "Q3": 13.1537, "Q6": 13.1537}
R_PED = 0.0161
TAB = (151.2, 240.1)        # mm2 exposed drain metal (m11 stack_calc.py, T03)

def rds(t): return .018 * (1 + 1.2 * (t - 25) / 125)

def solve(i_rms, f, P, V, ambient, rsa, rcs, flow=13, order=("Q5", "Q6", "Q3", "Q2", "BR1"), bridge_rcs=0.378):
    tj = {r: ambient for r in order}
    i2 = i_rms ** 2 / 2
    bridge = 2 * 1.05 * (P / (.95 * V)) * 2 * math.sqrt(2) / math.pi
    cpflow = 1.09 * 1005 * flow * .00047194745
    for _ in range(300):
        pw = {"BR1": bridge}
        for r in MOS: pw[r] = i2 * rds(tj[r]) + SW[r] * f / 36000
        ps = sum(pw.values()); ts = ambient + rsa * ps
        up, nx = 0.0, {}
        for r in order:
            loc = ts + up / cpflow
            nx[r] = loc + pw[r] * (.25 + bridge_rcs if r == "BR1" else .28 + rcs)
            up += pw[r]
        d = max(abs(nx[r] - tj[r]) for r in order); tj = nx
        if max(tj.values()) > 400: return None
        if d < 1e-8: break
    fets = {r: tj[r] for r in MOS}
    return {"tj_fet_max": max(fets.values()), "worst": max(fets, key=fets.get), "sink_W": ps, "fet_W": {r: round(pw[r], 2) for r in MOS}}

def grease(blt_um, k=2.5, area=TAB[0]): return (blt_um * 1e-6 / k) / (area * 1e-6)
def aln(t=2.0, k=150.0, area=TAB[0]): return (t * 1e-3 / k) / (area * 1e-6)

RCS = {"cons_TIC1000A_proxy (as built in the model)": 0.634, "cons_low_end_of_model_range": 0.399}
for blt in (25, 50, 75, 100):     # Electrolube HTCP20S 2.5 W/mK (DECISIONS 2026-10-08 M11 resolution); BLT 25-100 um on lapped AlN + TO-247 tab
    RCS[f"AlN2mm+2xHTCP20S BLT{blt}um (A=151.2 mm2)"] = round(aln() + 2 * grease(blt), 3)

def tj_table(rsa, rcs):
    return {f"{f}kHz": round(solve(28.0, f * 1e3, 1239, 120, 50.0, rsa, rcs)["tj_fet_max"], 1) for f in (40, 45, 50)}

def imax(f, rsa, rcs, lim=125.0):
    lo, hi = 5.0, 40.0
    for _ in range(50):
        m = (lo + hi) / 2
        r = solve(m, f * 1e3, 1239, 120, 50.0, rsa, rcs)
        lo, hi = (m, hi) if (r and r["tj_fet_max"] <= lim) else (lo, m)
    return round(lo, 2)

out = {"control_expect": {"40kHz": 129.0, "45kHz": 134.5, "50kHz": 140.1}, "tj_28A": {}, "imax_for_125C": {}}
ctrl = tj_table(0.29 + R_PED, 0.634)
assert ctrl == out["control_expect"], ctrl
for sink, rsa in (("S8 0.29", 0.29 + R_PED), ("K1 0.214+ped (DECISIONS 15 states 118.9/123.8/128.7 at its own flow; this solve is 1.8-2.1 K lower)", 0.214 + R_PED)):
    for name, rcs in RCS.items():
        out["tj_28A"][f"{sink} | {name} Rcs={rcs}"] = tj_table(rsa, rcs)
        out["imax_for_125C"][f"{sink} | {name}"] = {f"{f}kHz": imax(f, rsa, rcs) for f in (35, 40, 45, 50)}
Path(HERE / "results").mkdir(exist_ok=True)
(HERE / "results/fet_tj_levers.json").write_text(json.dumps(out, indent=1) + "\n")
for k, v in out["tj_28A"].items(): print(k, v)
for k, v in out["imax_for_125C"].items(): print("Imax", k, v)
