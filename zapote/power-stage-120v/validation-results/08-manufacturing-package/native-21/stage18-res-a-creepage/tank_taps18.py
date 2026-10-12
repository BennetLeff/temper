#!/usr/bin/env python3
"""Stage 18: working voltage to earth of the bank-bleed taps CRBLEED_1..3 at 28 A (which nets need the 12.6 mm rule?).

    python3 tank_taps18.py      (stdlib only, ~10 s, deterministic; asserts the RES_A control)

Same node model and round-6 28 A pan grid as owner-items/m6m10/coil-selv-28a/coil_selv_28a.py (earth reference,
line-cycle rms = carrier-crest rms / sqrt 2, phase from the tank). The bleed string R22..R25 is four equal resistors
from RES_A (R22.1) to SW_B (R25.2), so tap k sits at SW_B + (4 - k) / 4 x v_Cr: CRBLEED_1 = 3/4, CRBLEED_2 = 1/2,
CRBLEED_3 = 1/4. Control: the 1/1 tap is RES_A and must reproduce 297.0 V rms / 655.5 V pk (L70 / C050 grid).
"""
import csv
import glob
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT = os.path.abspath(os.path.join(HERE, "../../../.."))
R6 = os.path.join(UNIT, "validation-results/05-resonant-tank-envelope/round6-full-power/outputs")
SQ2 = math.sqrt(2.0)
TAPS = {"res_a": 1.0, "crbleed_1": 0.75, "crbleed_2": 0.5, "crbleed_3": 0.25, "sw_b": 0.0}


def nodes(vline, amp, phi, n=1024):
    vb, acc = vline * SQ2, {k: [0.0, 0.0] for k in TAPS}
    for i in range(n):
        t = 2 * math.pi * (i + 0.5) / n
        swb = 0.0 if math.sin(t) >= 0 else vb
        for k, fr in TAPS.items():
            v = swb - fr * amp * math.cos(t - phi)
            acc[k][0] += v * v
            acc[k][1] = max(acc[k][1], abs(v))
    return {k: (math.sqrt(a[0] / n) / SQ2, a[1]) for k, a in acc.items()}


def worst(sel):
    best = {k: [0.0, 0.0] for k in TAPS}
    for p in sorted(glob.glob(os.path.join(R6, "grid6-*-I28-*cases.csv"))):
        if sel not in os.path.basename(p):
            continue
        for r in csv.DictReader(open(p)):
            f, L, R, C = float(r["freq_hz"]), float(r["L_eq_uH"]) * 1e-6, float(r["R_eq_ohm"]), float(r["C_bank_uF"]) * 1e-6
            w = 2 * math.pi * f
            nd = nodes(float(r["line_vrms"]), float(r["i_tank_pk_a"]) / (w * C), math.atan2(w * L - 1 / (w * C), R))
            for k, (rm, pk) in nd.items():
                best[k] = [max(best[k][0], rm), max(best[k][1], pk)]
    return {k: (round(v[0], 1), round(v[1], 1)) for k, v in best.items()}


design, anyl = worst("-L70-C050-"), worst("")
assert design["res_a"] == (297.0, 655.5), design["res_a"]
print("28 A pan grid, line-cycle rms / pk to earth (V); Table 17 x 2 PD3 IIIa: <= 250 V rms -> 8.0 mm, >250-400 -> 12.6 mm")
print(f"{'net':10s} {'L70 / C050 (design)':>22s} {'any L 70-90 uH':>18s}")
for k in TAPS:
    print(f"{k:10s} {design[k][0]:10.1f} / {design[k][1]:6.1f} {anyl[k][0]:8.1f} / {anyl[k][1]:6.1f}")
print("CONTROL PASS: RES_A 297.0 / 655.5 reproduced")
