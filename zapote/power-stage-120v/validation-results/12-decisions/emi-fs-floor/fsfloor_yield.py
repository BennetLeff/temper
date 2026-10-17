#!/usr/bin/env python3
"""What raising the switching-frequency floor costs in full-power pan yield (F10 alternative to DM inductors).

    python3 -I validation-results/12-decisions/emi-fs-floor/fsfloor_yield.py   # -> fsfloor_yield.json, exit 1 if the control fails

Reruns round 6's Monte Carlo (05-resonant-tank-envelope/round6-full-power/scripts/analyze6.py mc(), same seeds, same
calibration6.json, same draws) for today's tank (70 uH free / 66.5 installed, 0.50 uF) with the window floor
max(F, 1.05 f_res) at F = 35 / 38 / 40 / 42 / 45 kHz. Pooled over 180/220/260 mm pans and every pan class, 108 and 120 V.
Control: F = 35 kHz must reproduce the committed yield-pooled.csv row for this config to the 3rd decimal.
ASSUMED basis (no measured coil or pan), as round 6.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R6 = HERE.parents[1] / "05-resonant-tank-envelope" / "round6-full-power"
sys.path.insert(0, str(R6 / "scripts"))
import analyze6 as A  # noqa: E402
import common6 as M  # noqa: E402
import fha6 as F  # noqa: E402

LFREE, C_UF = 70, 0.50
FLOORS = [35e3, 38e3, 40e3, 42e3, 45e3]
CEIL = [22.0, 26.0, 28.0]
PEAK = 60.0                                  # stage-15 raised peak setting (yield-pooled's pk60 columns)

cal = json.loads((R6 / "outputs" / "calibration6.json").read_text())
kp, ki = cal["kp_median"], cal["ki_median"]
a, b, rmax = cal["kpk_fit"]["a"], cal["kpk_fit"]["b_per_Q"], cal["kpk_fit"]["resid_max"]


def run(floor):
    out = {}
    for V in (108.0, 120.0):
        I_all, PK_all, F_all = [], [], []
        for pan_d in M.PAN_D:
            fk, fr = M.coupling(M.GEOM, pan_d)
            rng = np.random.default_rng([A.SEED, LFREE, int(C_UF * 100), pan_d, int(V)])
            tgt = min(M.P_REQ, M.I_PS_HOLD * M.ETA * V)
            for _, pan in M.B4.PANS.items():
                d = F.draws(pan, A.N_MC, rng, M.L_INSTALLED[LFREE], fk, fr, C_UF * 1e-6)
                i, f, st, _ = F.required_current(d, V, 0.99 * tgt, kp, ki, f_floor_min=floor)
                L, R = F.lr(d, f)
                Q = 2 * np.pi * f * L / R
                I_all.append(i)
                PK_all.append((a + b * Q + rmax) * i)
                F_all.append(f)
        I, PK, Fo = np.concatenate(I_all), np.concatenate(PK_all), np.concatenate(F_all)
        row = {"floor_limited": round(float(np.isinf(I).mean()), 3),
               "f_op_p10_kHz": round(float(np.percentile(Fo, 10)) / 1e3, 2)}
        for c in CEIL:
            row[f"yield_{int(c)}A"] = round(float((I <= c).mean()), 3)
            row[f"yield_{int(c)}A_pk60"] = round(float(((I <= c) & (PK <= PEAK)).mean()), 3)
        out[f"{int(V)}V"] = row
    return out


res = {f"{int(f / 1e3)}kHz": run(f) for f in FLOORS}

# control against the committed pooled rows
ref = {}
with open(R6 / "outputs" / "yield-pooled.csv") as fh:
    for r in csv.DictReader(fh):
        if r["L_free_uH"] == "70" and r["C_bank_uF"] == "0.5" and r["pan_d_mm"] == "180/220/260":
            ref[f"{int(float(r['line_vrms']))}V"] = r
fails = []
for v, r in ref.items():
    got = res["35kHz"][v]
    for k in ("floor_limited", "yield_22A", "yield_26A", "yield_28A", "yield_22A_pk60", "yield_26A_pk60", "yield_28A_pk60"):
        if abs(got[k] - float(r[k])) > 5e-4:
            fails.append((v, k, got[k], r[k]))

out = {"basis": "round 6 MC, today's tank (70 uH / 0.50 uF), ASSUMED", "control_fails": fails, "by_floor": res}
(HERE / "fsfloor_yield.json").write_text(json.dumps(out, indent=1) + "\n")
print("control:", "ok" if not fails else f"FAIL {fails}")
for fl, r in res.items():
    print(fl, r["120V"], "| 108V", r["108V"])
raise SystemExit(1 if fails else 0)
