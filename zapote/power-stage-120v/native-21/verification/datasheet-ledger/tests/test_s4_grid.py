#!/usr/bin/env python3
"""Negative controls for the ledger gate's slew basis (s4_grid citations):  python3 -I tests/test_s4_grid.py

Every V/ns stress must cite the switching grid it comes from, and the gate refuses a grid with rows whose edge fell
outside the measurement window (validation-results/01-switching-parasitics/s4_edges.py; c55 section 1.3).
"""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER_DIR = HERE.parent
GATE = LEDGER_DIR / "gate.py"
LEDGER = LEDGER_DIR / "ledger.json"
BOM = LEDGER_DIR.parents[1] / "frozen" / "default.csv"
SHORT = "validation-results/11-candidates/c55-device-trade/sims/cfd7_c39_tt260/full/results.json"
FAILS = []


def expect(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def run(data):
    with tempfile.TemporaryDirectory() as td:
        led, rep = Path(td) / "ledger.json", Path(td) / "r.json"
        led.write_text(json.dumps(data, indent=1) + "\n")
        p = subprocess.run([sys.executable, "-I", str(GATE), "--ledger", str(led), "--bom", str(BOM), "--report", str(rep)],
                           capture_output=True, text=True)
        return p.returncode, json.loads(rep.read_text())["errors"] if rep.exists() else [p.stderr]


def stress(d, mpn, param):
    return next(s for s in d["entries"][mpn]["stresses"] if s["parameter"] == param)


def grid_cite(s):
    return next(c for c in s["evidence"] if isinstance(c, dict) and "s4_grid" in c)


base = json.loads(LEDGER.read_text(encoding="utf-8"))
CFD7, MAXQ, TYP = "IPW65R018CFD7", "dv/dt diode commutation (S4), maximum Qrr", "dv/dt diode commutation (S4)"

rc, errs = run(base)
expect("the live ledger passes", rc == 0, errs[:3])
expect("the live ledger's maximum-Qrr stress cites a long-window grid at 68.58",
       grid_cite(stress(base, CFD7, MAXQ))["s4_grid"]["slew_Vns"] == 68.58)

d = copy.deepcopy(base)
grid_cite(stress(d, CFD7, MAXQ))["file"] = SHORT
rc, errs = run(d)
expect("a short-window grid with no-edge rows is refused", rc == 1 and any("s4_grid refused" in e for e in errs), errs[:3])

d = copy.deepcopy(base)
s = stress(d, CFD7, MAXQ)
s["worst_case_value"] = 68.16
grid_cite(s)["s4_grid"]["slew_Vns"] = 68.16
for c in d["entries"][CFD7]["checks"]:
    if c["stress"] == MAXQ:
        c["ratio"] = round(68.16 / 70, 4)
rc, errs = run(d)
expect("citing 68.16 against the grid's 68.58 is stale", rc == 1 and any("stale s4_grid slew" in e for e in errs), errs[:3])

d = copy.deepcopy(base)
stress(d, CFD7, MAXQ)["worst_case_value"] = 68.16
for c in d["entries"][CFD7]["checks"]:
    if c["stress"] == MAXQ:
        c["ratio"] = round(68.16 / 70, 4)
rc, errs = run(d)
expect("a stress value that differs from its cited grid is caught",
       rc == 1 and any("worst_case_value 68.16 != the cited grid" in e for e in errs), errs[:3])

d = copy.deepcopy(base)
s = stress(d, CFD7, TYP)
s["evidence"] = [c for c in s["evidence"] if not isinstance(c, dict)]
rc, errs = run(d)
expect("a V/ns stress without a grid or an exemption is caught",
       rc == 1 and any("needs an s4_grid citation" in e for e in errs), errs[:3])

d = copy.deepcopy(base)
stress(d, CFD7, TYP)["s4_grid_exempt"] = "no reason really"
rc, errs = run(d)
expect("a citation and an exemption together are caught", rc == 1 and any("both an s4_grid" in e for e in errs), errs[:3])

d = copy.deepcopy(base)
s = stress(d, CFD7, "dv/dt hard edge")
s["s4_grid_exempt"] = "  "
rc, errs = run(d)
expect("a blank exemption is not an exemption", rc == 1 and any("needs an s4_grid citation" in e for e in errs), errs[:3])

d = copy.deepcopy(base)
grid_cite(stress(d, CFD7, MAXQ))["s4_grid"] = {"case": "S9", "slew_Vns": 68.58}
rc, errs = run(d)
expect("a malformed s4_grid citation is caught", rc == 1 and any("s4_grid citation needs" in e for e in errs), errs[:3])

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
