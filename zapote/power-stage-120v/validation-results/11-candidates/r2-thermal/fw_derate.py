#!/usr/bin/env python3
"""Firmware-side derate table: sustained tank-current ceiling C and operating frequency f vs the three tightest 28 A margins.
Run: python3 -I fw_derate.py (needs results/f12.json, fet_tj_levers.py, bank_caps_limits.py imports) -> results/fw_derate.json
 * FET Tj: fet_tj_levers.solve, S8 sink, conservative Rcs 0.634 (as built in the model), 120 V / 1239 W, Tj rule 125 C.
 * Bank: J-tolerance worst-share ratio to the TDK 85 C curve (bank_options), at I = C.
 * R5.4 pad copper: converged-equivalent peak from the B3 tank-current sweep (R5 pad max cell, +6.7 K mesh offset), tank RMS = 1.05 C
   (firmware trip basis used by the c28 case); limit MOT 130 C, wanted margin 5 K.
Yield cost of a lower ceiling is NOT computed here (needs the round-6 grid: DECISIONS 10 gives 13 % of pan cases at 22 A, 85 % at 28 A).
"""
import importlib.util, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
def load(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    fj = load("fj", HERE / "fet_tj_levers.py")
bo = load("bo", HERE.parent / "g04-g09-tank-detect/scripts/bank_options.py")
f12 = json.loads((HERE / "results/f12.json").read_text())
r5 = {float(k): v for k, v in f12["R5_pad_max_C_vs_tank_RMS_A_converged_equiv"].items()}
xs = sorted(r5)
def r5_at(it):
    it = round(it, 6)
    for a, b in zip(xs, xs[1:]):
        if a <= it <= b: return r5[a] + (r5[b] - r5[a]) * (it - a) / (b - a)
    return float("nan")
rows = []
for C in (22, 24, 25, 26, 27, 28):
    for f in (40, 45, 50):
        tj = fj.solve(float(C), f * 1e3, 1239, 120, 50.0, 0.29 + fj.R_PED, 0.634)["tj_fet_max"]
        bank = max(C * s / bo.limit(100, f * 1e3) for s in bo.shares([100] * 5, 0.05))
        rows.append({"ceiling_A": C, "f_kHz": f, "Tj_FET_C": round(tj, 1), "Tj_margin_to_125": round(125 - tj, 1),
                     "bank_ratio": round(bank, 3), "R5_4_pad_C": round(r5_at(1.05 * C), 1), "R5_4_margin_to_MOT130": round(130 - r5_at(1.05 * C), 1)})
(HERE / "results/fw_derate.json").write_text(json.dumps(rows, indent=1) + "\n")
for r in rows: print(r)
