#!/usr/bin/env python3
"""Routing-robustness proof: N consecutive full `make.py` runs, each from a clean start.

    python3 layout/convergence.py --runs 3 --out <dir>   # run, then summarise into evidence/convergence.json
    python3 layout/convergence.py --summarize <dir>      # summarise runs already in <dir>/run1..runN

A clean start means `pcb/route/` (the router's working files) is moved away before each run, so no
run reuses an earlier run's copper. Each run keeps its make log, DRC report and route log in
<dir>/runI/ (C34: and the run's board, so each run can be put through the block validators). The summary records, per run, make.py's exit code and last line, the wall time, the
DRC error / unconnected / parity counts, and the DRC violation types (warnings included).
The board left in pcb/ and fab/ is the last run's.
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
EV = UNIT / "evidence"


def run_all(n: int, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        d = out / f"run{i}"
        d.mkdir(exist_ok=True)
        route = UNIT / "pcb" / "route"
        if route.exists():
            shutil.move(str(route), str(d / "route_before"))
        t0 = time.time()
        with open(d / "make.log", "w") as log:
            rc = subprocess.run([sys.executable, str(HERE / "make.py")], cwd=UNIT,
                                stdout=log, stderr=subprocess.STDOUT).returncode
        (d / "seconds").write_text(f"{time.time() - t0:.0f}\n")
        (d / "rc").write_text(f"{rc}\n")
        for src, dst in ((EV / "drc.json", "drc.json"), (route / "route-log.json", "route-log.json"),
                         (UNIT / "pcb" / "controller.kicad_pcb", "controller.kicad_pcb")):   # C34: per-run board
            if src.exists():
                shutil.copy(src, d / dst)
        print(f"RUN {i} rc={rc}", flush=True)


def summarize(out: Path) -> dict:
    runs = []
    for d in sorted(out.glob("run*"), key=lambda p: int(p.name[3:])):
        log = (d / "make.log").read_text().strip().splitlines() if (d / "make.log").exists() else []
        drc = json.loads((d / "drc.json").read_text()) if (d / "drc.json").exists() else {}
        viol = drc.get("violations", [])
        sev = collections.Counter(v.get("severity") for v in viol)
        types = collections.Counter(v.get("type") for v in viol)
        rec = {
            "run": d.name,
            "make_last_line": log[-1] if log else None,
            "errors": sev.get("error", 0),
            "warnings": sev.get("warning", 0),
            "unconnected": len(drc.get("unconnected_items", [])),
            "schematic_parity": len(drc.get("schematic_parity", [])),
            "violation_types": dict(sorted(types.items())),
        }
        for k in ("rc", "seconds"):
            if (d / k).exists():
                rec[k] = int((d / k).read_text())
        rec["closed"] = (rec["make_last_line"] == "ALL GATES PASS" and rec["errors"] == 0
                         and rec["unconnected"] == 0 and rec["schematic_parity"] == 0)
        runs.append(rec)
    return {"runs": runs, "all_closed": bool(runs) and all(r["closed"] for r in runs),
            "consecutive_closed": len(runs) if runs and all(r["closed"] for r in runs) else 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--summarize", type=Path)
    a = ap.parse_args()
    if a.summarize:
        out = a.summarize
    else:
        if not a.out:
            ap.error("--out is required to run")
        out = a.out
        run_all(a.runs, out)
    s = summarize(out)
    (EV / "convergence.json").write_text(json.dumps(s, indent=1) + "\n")
    for r in s["runs"]:
        print(r["run"], r.get("rc"), r.get("seconds"), r["make_last_line"], r["violation_types"])
    print("CONVERGENCE", "PASS" if s["all_closed"] else "FAIL", f"{s['consecutive_closed']}/{len(s['runs'])}")
    return 0 if s["all_closed"] else 1


if __name__ == "__main__":
    sys.exit(main())
