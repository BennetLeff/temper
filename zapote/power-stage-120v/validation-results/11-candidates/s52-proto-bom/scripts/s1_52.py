#!/usr/bin/env python3
"""Stage 52 S1 touch current with the fitted C3 / C4 (DE1E3RA222MJ4BH01F), by the record's own method.

    python3 -I validation-results/11-candidates/s52-proto-bom/scripts/s1_52.py   -> results/s1-s52.json

Imports 07-conducted-emi/leakage/leakage_budget.py read-only (its main() is not called, nothing is written there):
132 V, 60 Hz, open PE per polarity, every Y at its +tolerance maximum, supplies at their datasheet maximum. The C3/C4 row
is re-charged at the fitted part's own nominal and tolerance, read from the frozen BOM: DE1E3RA222MJ4BH01F 2200 pF +-20 %
(Murata Type RA reference specification, Jun. 2023, part list PDF p.9 (printed 8/17); LCSC copy sha256 c959488a...). Same method as
11-candidates/b15-proto-alternates/scripts/s1_leakage_alt.py, on this tree. Control: the record row (2.2 nF +20 %)
reproduces 0.2412 mA, and +-30 % must FAIL. Exit 1 on a failed control or a FAIL.
"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PS = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("lb", PS / "validation-results/07-conducted-emi/leakage/leakage_budget.py")
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)
PARTS = {"DE1E3RA222MJ4BH01F": (2.2e-9, 0.20, "Murata Type RA H01F reference specification (Jun. 2023) PDF p.9 part list: 2200 pF +-20 %"),
         "DE1E3RA222MA4BP01F": (2.2e-9, 0.20, "Murata EGD08G p.7: 2200 pF +-20 %")}


def design(c_nom, tol):
    items = lb.build()
    for it in items:
        if it["name"].startswith("C3/C4"):
            it["mA"] = lb.i_ma(c_nom * (1 + tol))
            it["c_nom_nF"] = c_nom * 1e9
    return lb.evaluate("alt", items)


mpn = next(r["LCSC"] for r in csv.DictReader(open(PS / "native-21/frozen/default.csv"))     # the MPN column ('LCSC')
           if "C3" in [d.strip() for d in r["Designator"].split(",")])
c, t, src = PARTS[mpn]
rec = lb.evaluate("record", lb.build())
fit = design(c, t)
ctl = design(2.2e-9, 0.30)
fails = []
if abs(rec["governing_touch_mA"] - 0.2412) > 5e-5:
    fails.append(f"record {rec['governing_touch_mA']}")
out = {"fitted_mpn": mpn, "source": src, "record_mA": round(rec["governing_touch_mA"], 5), "budget_mA": rec["budget_mA"],
       "fitted_mA": round(fit["governing_touch_mA"], 5), "fitted_margin_uA": round(fit["margin_mA"] * 1e3, 2),
       "fitted_verdict": fit["verdict"], "control_pm30_mA": round(ctl["governing_touch_mA"], 5),
       "control_pm30_verdict": ctl["verdict"], "failed": fails}
if ctl.get("verdict") != "FAIL":
    fails.append(f"+-30 % control did not fail: {ctl.get('verdict')}")
if fit.get("verdict") == "FAIL":
    fails.append("fitted part FAILS")
(Path(__file__).resolve().parents[1] / "results/s1-s52.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
sys.exit(1 if fails else 0)
