#!/usr/bin/env python3 -I
"""G01: leakage trade table.  Reuses the formulas and inputs of 07-conducted-emi/leakage/leakage_budget.py
(132 V, 60 Hz, +20 % on Y, open-PE touch current per polarity), but sweeps the Y split and the supply
assumption/limit class instead of fixing them.  stdlib only; writes leakage_g01_results.json."""
import json, math
from pathlib import Path
W = 2 * math.pi * 60.0
V = 132.0
TOL = 1.2
COIL_PF = 31.0
def i_ma(c): return W * c * V * 1e3
def supply_ma(kind, n=3):
    if kind == "datasheet_max":   # 0.25 mA @ 277 Vac each (IRM-20/IRM-60 SPEC p.2), x132/277, x60/50
        return n * 0.25 * (V / 277.0) * 1.2
    if kind == "typical":         # Simpex IRM-20-15 report 0.015 mA @ 240 V (1 unit, informational)
        return n * 0.015 * (V / 240.0) * 1.2
    if kind == "two_supplies_max":  # if one of PS1/PS2/PS3 is removed or replaced (G06/G10 options)
        return 2 * 0.25 * (V / 277.0) * 1.2
    raise KeyError(kind)
Y = {  # nominal nF per line: (board C3/C4, module 4.7 nF, module 2.2 nF)
    "as built (2.2+4.7+2.2)": (2.2, 4.7, 2.2),
    "board Y removed": (0, 4.7, 2.2),
    "board Y removed, module 2.2 only": (0, 0, 2.2),
    "board Y removed, module 4.7 only": (0, 4.7, 0),
    "board 2.2 only (module Y removed)": (2.2, 0, 0),
    "board 1.0 + module 2.2": (1.0, 0, 2.2),
    "board 2.2 + module 2.2": (2.2, 0, 2.2),
    "all Y removed": (0, 0, 0),
}
LIM = {"UL1026 portable 0.5 mA, 50 % budget (repo rule)": 0.25,
       "UL1026 portable 0.5 mA, 80 % budget": 0.40,
       "0.5 mA full limit": 0.5,
       "0.75 mA stationary, 50 % budget": 0.375,
       "0.75 mA stationary full": 0.75}
out = {"rows": []}
hdr = ["Y config (nominal nF/line)", "Y_tot nF", "Y mA", "total mA datasheet-max PS", "total mA typical PS", "total mA 2 PS max"]
print(" | ".join(hdr))
for name, (a, b, c) in Y.items():
    yt = a + b + c
    ym = i_ma(yt * 1e-9 * TOL)
    coil = i_ma(COIL_PF * 1e-12 * TOL)
    row = {"config": name, "Y_total_nF": yt, "Y_mA": ym}
    for k in ("datasheet_max", "typical", "two_supplies_max"):
        row[k] = ym + coil + supply_ma(k)
    out["rows"].append(row)
    print(f"{name:40s} | {yt:5.1f} | {ym:.3f} | {row['datasheet_max']:.3f} | {row['typical']:.3f} | {row['two_supplies_max']:.3f}")
print()
out["limits"] = {}
for ln, lim in LIM.items():
    out["limits"][ln] = {}
    for k in ("datasheet_max", "typical", "two_supplies_max"):
        room = lim - i_ma(COIL_PF * 1e-12 * TOL) - supply_ma(k)
        yallow = max(room, 0) / (W * V * 1e3 * TOL) * 1e9   # nominal nF
        out["limits"][ln][k] = round(yallow, 2)
    print(f"{ln:52s} max NOMINAL Y per line (nF): " + ", ".join(f"{k}={v}" for k, v in out["limits"][ln].items()))
out["finding"] = ("With the three IRM supplies at their datasheet MAX (0.4285 mA incl. 60/50 factor) the supplies alone exceed the "
                  "0.25 mA repo budget; no Y reduction can pass the 50 % rule. The F5 text 'Y <= 5.0 nF/line' ignores the supply term "
                  "(it is the Y+coil capacity at 0.25 mA with supplies at 0).")
print("\n" + out["finding"])
Path(__file__).resolve().parent.joinpath("leakage_g01_results.json").write_text(json.dumps(out, indent=1))
