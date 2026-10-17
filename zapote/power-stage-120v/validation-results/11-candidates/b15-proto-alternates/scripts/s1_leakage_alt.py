#!/usr/bin/env python3
"""S1 touch current with a C3 / C4 alternate, computed exactly as the record does
(07-conducted-emi/leakage/leakage_budget.py, imported read-only; its main() is NOT called, so nothing is written there):
132 V, 60 Hz, open-PE per polarity, every Y at its +tolerance maximum, supplies at datasheet maximum.
The record charges C3/C4 at 2.2 nF x (1 + 0.20). Here the C3/C4 row uses each candidate's own nominal and tolerance.
Usage: python3 -I s1_leakage_alt.py OUT.json"""
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
P = "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-results/07-conducted-emi/leakage/leakage_budget.py"
spec = importlib.util.spec_from_file_location("lb", P)
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)

CANDS = {  # MPN: (nominal F, + tolerance, source)
    "DE1E3RA222MA4BP01F (fitted)": (2.2e-9, 0.20, "Murata EGD08G p.7: 2200 pF +/-20 %"),
    "DE1E3RA222MJ4BH01F": (2.2e-9, 0.20, "Murata RA H01F spec (Jun 2023) p.8: 2200 pF +/-20 %"),
    "DE1E3RA222MN4AP01F": (2.2e-9, 0.20, "Murata EGD08E (Jun 2019) part list: 2200 pF +/-20 %"),
    "DE1E3RA222MA4BQ01F": (2.2e-9, 0.20, "Murata EGD08E Q01F part list: 2200 pF +/-20 %"),
    "VY1222M47Y5UQ6TV0": (2.2e-9, 0.20, "Vishay VY1 doc 28537 p.2: 2200 pF, M = +/-20 %"),
    "CD45-E2GA222M-NKA": (2.2e-9, 0.20, "TDK CD series: 2200 pF, M = +/-20 %"),
    "CONTROL 2.2 nF +/-30 % (must FAIL)": (2.2e-9, 0.30, "hypothetical"),
}


def design(c_nom, tol):
    items = lb.build()
    for it in items:
        if it["name"].startswith("C3/C4"):
            it["mA"] = lb.i_ma(c_nom * (1 + tol))
            it["c_nom_nF"] = c_nom * 1e9
    return lb.evaluate("alt", items)


rec = lb.evaluate("record", lb.build())
assert abs(rec["governing_touch_mA"] - 0.2412) < 5e-5, rec["governing_touch_mA"]
out = {"record_mA": rec["governing_touch_mA"], "budget_mA": rec["budget_mA"], "candidates": {}}
for n, (c, t, src) in CANDS.items():
    r = design(c, t)
    out["candidates"][n] = {"C_max_nF": c * (1 + t) * 1e9, "touch_mA": r["governing_touch_mA"],
                            "margin_uA": 1e3 * r["margin_mA"], "verdict": r["verdict"], "src": src}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(f"record {rec['governing_touch_mA']:.5f} mA, budget {rec['budget_mA']} mA, margin {1e3 * rec['margin_mA']:.2f} uA")
for n, v in out["candidates"].items():
    print(f"  {n:38s} Cmax {v['C_max_nF']:.3f} nF  touch {v['touch_mA']:.5f} mA  margin {v['margin_uA']:+.2f} uA  {v['verdict']}")
