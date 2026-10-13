#!/usr/bin/env python3 -I
"""S2-B: displacement current when the high-side driver islands (riding sw_a / sw_b) sit on a second board.
I = C dv/dt with C = eps0*A/d for an island of area A over the power board's planes at the stack gap d, dv/dt = 95 V/ns (the modelled
hard edge in 06-controller-interface/cmti, DECISIONS 22 F6). Island area, gap and the pin-to-pin C are ASSUMPTIONS (printed).
    python3 -I cm_coupling.py -> ../results/cm_coupling.json"""
import json, sys
sys.dont_write_bytecode = True
from pathlib import Path
E0 = 8.854e-12
out = {"dvdt_V_per_ns": 95, "assumptions": "island area per leg 10 cm2 (HS bias module + driver HS side + monitor HS side), stack gap 11 mm, adjacent-pin C 0.3 pF (UNVERIFIED)"}
for A_cm2 in (5, 10, 20):
    for d_mm in (8, 11, 15):
        C = E0*A_cm2*1e-4/(d_mm*1e-3)
        out[f"A{A_cm2}cm2_gap{d_mm}mm"] = dict(C_pF=round(C*1e12, 2), I_mA=round(C*95e9*1e3, 1))
out["adjacent_pin_0p3pF_I_mA"] = round(0.3e-12*95e9*1e3, 1)
json.dump(out, open(Path(__file__).resolve().parent.parent/"results/cm_coupling.json", "w"), indent=1); print(json.dumps(out, indent=1))
