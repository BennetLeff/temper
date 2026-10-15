#!/usr/bin/env python3
"""Negative controls for the datasheet ledger gate (plain python, no pytest):  python3 -I tests/test_gate.py

Copies ledger.json to a temp dir, damages it, and asserts gate.py fails for the right reason; asserts the
real ledger's result; asserts a clean synthetic ledger passes (so the gate can return PASS at all).
"""
import copy
import csv
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
FAILS = []


def run(ledger, *extra, bom=BOM):
    with tempfile.TemporaryDirectory() as td:
        rep = Path(td) / "r.json"
        p = subprocess.run([sys.executable, "-I", str(GATE), "--ledger", str(ledger), "--bom", str(bom),
                            "--report", str(rep), *extra], capture_output=True, text=True)
        return p.returncode, p.stdout, json.loads(rep.read_text()) if rep.exists() else None


def expect(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def write(td, data):
    p = Path(td) / "ledger.json"
    p.write_text(json.dumps(data))
    return p


def main():
    base = json.loads(LEDGER.read_text())
    ent = base["entries"]

    # 1. the real ledger: one known VIOLATION since 2026-10-15 (DECISIONS 49: IPW65R018CFD7 reverse-diode dv/dt in S4),
    # no unaudited SAFETY/POWER line. Update KNOWN_VIOLATIONS when a fix lands or a new finding is recorded.
    KNOWN_VIOLATIONS = ["IPW65R018CFD7"]
    rc, out, rep = run(LEDGER)
    expect("real ledger exits 1 on exactly the known violations", rc == 1 and rep and rep["violations"] == KNOWN_VIOLATIONS,
           str(rep and rep["violations"]))
    expect("real ledger: no malformed entries", rep and not rep["errors"], str(rep and rep["errors"][:3]))
    # stage 27: J1 is the MKDS 5/2-9,5 (UL group B 30 A); its ratings source keeps it PARTIAL
    expect("real ledger: J1 1714971 is PARTIAL, not VIOLATION", rep and "1714971" in rep["partial"] and "1714971" not in rep["violations"])
    # stage 28: F2 is the 1.5 kA UMT-H, bounded by the R130 limiter; the limiter stays PARTIAL until the bench short
    expect("real ledger: F2 3403.0279.23 not PARTIAL or VIOLATION, R130 AC05 PARTIAL",
           rep and "3403.0279.23" not in rep["violations"] + rep["partial"] and "AC05000001507JAC00" in rep["partial"])
    expect("real ledger: no BOM MPN missing", rep and rep["missing_from_ledger"] == [])
    expect("real ledger: 2EDR8259X is PARTIAL", rep and "2EDR8259XXUMA1" in rep["partial"])
    expect("real ledger: report names every violation in failures",
           rep and all(any(v in f for f in rep["failures"]) for v in rep["violations"]))

    # 2. delete one SAFETY entry
    with tempfile.TemporaryDirectory() as td:
        d = copy.deepcopy(base)
        del d["entries"]["KLDR025.TXP"]
        rc, out, rep = run(write(td, d))
        expect("deleted SAFETY entry -> exit 1 and reported missing",
               rc == 1 and rep["missing_from_ledger"] == ["KLDR025.TXP"])

    # 3. set a non-violating entry to VIOLATION
    with tempfile.TemporaryDirectory() as td:
        d = copy.deepcopy(base)
        d["entries"]["GBJ2510-F"]["status"] = "VIOLATION"
        d["entries"]["GBJ2510-F"]["finding"] = "synthetic"
        rc, out, rep = run(write(td, d))
        expect("BR1 set to VIOLATION -> reported", rc == 1 and "GBJ2510-F" in rep["violations"])

    # 4. set an audited SAFETY entry to UNAUDITED
    with tempfile.TemporaryDirectory() as td:
        d = copy.deepcopy(base)
        # picked from the ledger, not named: a fixed MPN goes stale when the BOM drops the part (ISO7710DWR, stage 31)
        mpn = next(k for k, e in d["entries"].items() if e.get("class") == "SAFETY" and e.get("status") != "UNAUDITED")
        d["entries"][mpn]["status"] = "UNAUDITED"
        rc, out, rep = run(write(td, d))
        expect(f"SAFETY UNAUDITED ({mpn}) -> reported", rc == 1 and mpn in rep["unaudited_safety_power"])

    # 5. a lie: VERIFIED with a failing check, and with a tampered ratio
    with tempfile.TemporaryDirectory() as td:
        d = copy.deepcopy(base)
        f2 = d["entries"]["3403.0279.23"]
        f2["stresses"][0]["worst_case_value"] = 3567          # the unbounded F4 fault: 2.378x the 1.5 kA
        f2["checks"][0]["ratio"] = 2.378                      # ratio kept consistent, so only the status is a lie
        rc, out, rep = run(write(td, d))
        expect("F2 VERIFIED over its breaking capacity is rejected as inconsistent",
               rc == 1 and any("violation-severity" in e or "VERIFIED" in e for e in rep["errors"]))
    with tempfile.TemporaryDirectory() as td:
        d = copy.deepcopy(base)
        d["entries"]["1714971"]["stresses"][0]["worst_case_value"] = 9.0  # hide the stress
        rc, out, rep = run(write(td, d))
        expect("tampered stress (stored ratio stale) is rejected", rc == 1 and any("stored ratio" in e for e in rep["errors"]))
    with tempfile.TemporaryDirectory() as td:
        d = copy.deepcopy(base)
        d["entries"]["1704004"]["stresses"][0]["evidence"] = "no/such/file.md:3"
        rc, out, rep = run(write(td, d))
        expect("dangling evidence path is rejected", rc == 1 and any("not found" in e for e in rep["errors"]))

    # 6. designator drift
    with tempfile.TemporaryDirectory() as td:
        d = copy.deepcopy(base)
        d["entries"]["IPW65R018CFD7"]["designators"] = ["Q2", "Q3"]
        rc, out, rep = run(write(td, d))
        expect("designator drift is rejected", rc == 1 and any("designators differ" in e for e in rep["errors"]))

    # 7. --strict fails on PARTIAL even when nothing else is wrong; clean synthetic ledger passes
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        bom = tdp / "bom.csv"
        bom.write_text("Comment,Designator,Footprint,LCSC,Price\nx,J6,fp,1704004,0\ny,R99,fp,0603WAF1002T5E,0\n")
        d = {"entries": {"1704004": copy.deepcopy(ent["1704004"]), "0603WAF1002T5E": copy.deepcopy(ent["0603WAF1002T5E"])}}
        d["entries"]["1704004"]["designators"] = ["J6"]
        d["entries"]["0603WAF1002T5E"]["designators"] = ["R99"]
        lp = write(td, d)
        rc, out, rep = run(lp, bom=bom)
        expect("clean ledger (VERIFIED + SIGNAL UNAUDITED) passes", rc == 0, out[-300:])
        rc, out, rep = run(lp, "--strict", bom=bom)
        expect("--strict fails on the UNAUDITED SIGNAL line", rc == 1)
        d["entries"]["1704004"]["status"] = "PARTIAL"
        d["entries"]["1704004"]["gaps"] = ["synthetic gap"]
        d["entries"]["0603WAF1002T5E"]["status"] = "VERIFIED"  # invalid on purpose: no datasheet
        rc, out, rep = run(write(td, d), bom=bom)
        expect("VERIFIED without datasheet/ratings is rejected", rc == 1 and any("VERIFIED needs" in e for e in rep["errors"]))

    print("\n%d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
