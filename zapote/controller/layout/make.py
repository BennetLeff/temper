#!/usr/bin/env python3
"""Rebuild the controller layout end to end from the frozen netlist, and re-run every gate.

    python3 layout/make.py            # build, route, DRC, DFM, enclosure check, fab package, fab review
    python3 layout/make.py --no-route # reuse pcb/controller-routed.kicad_pcb (routing is the slow step)

Steps (each fails the run on error):
  1. layout/build_board.py      placed board, planes, pours, keep-outs, plane fan-out  (KiCad Python)
  2. layout/build_schematic.py  netlist rendering for schematic parity
  3. layout/route.py            grid router (layout/gridroute.py) rounds, the local repair step for pairs
                                left open, layout/cleanup.py (loops and dangling copper), then the outer
                                GND pours and designators
  4. kicad-cli pcb drc --schematic-parity --refill-zones  -> evidence/drc.json  (0 errors, 0 unconnected, parity 0)
  5. layout/jlc_dfm_check.py    -> evidence/jlc-dfm.json
  6. layout/check_layout.py     -> evidence/layout-check.json
  7. layout/fab.py              -> fab/
  8. layout/review_fab.py       -> evidence/fab-review.json (gerbv render of the Gerbers)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
KPY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
EV = UNIT / "evidence"


def step(name, cmd, out=None):
    print(f"== {name}", flush=True)
    r = subprocess.run(cmd, cwd=UNIT, capture_output=True, text=True)
    text = "\n".join(l for l in (r.stdout + r.stderr).splitlines()
                     if "assert" not in l and "Fontconfig" not in l and "traits" not in l)
    if out:
        Path(out).write_text(r.stdout)
    else:
        print(text[-2000:])
    if r.returncode:
        print(text[-4000:])
        raise SystemExit(f"{name} failed ({r.returncode})")


def main():
    route = "--no-route" not in sys.argv
    EV.mkdir(exist_ok=True)
    step("build board", [KPY, "layout/build_board.py"])
    step("build schematic", [sys.executable, "layout/build_schematic.py"])
    routed = UNIT / "pcb/controller-routed.kicad_pcb"
    if route:
        step("route", [sys.executable, "layout/route.py"])
    shutil.copy2(routed, UNIT / "pcb/controller.kicad_pcb")
    def drc():
        step("drc", [CLI, "pcb", "drc", "--refill-zones", "--save-board", "--schematic-parity", "--severity-all",
                     "--format", "json", "-o", str(EV / "drc.json"), "pcb/controller.kicad_pcb"])
        d = json.loads((EV / "drc.json").read_text())
        errs = [v for v in d["violations"] if v["severity"] == "error"]
        warns = [v for v in d["violations"] if v["severity"] == "warning"]
        print(json.dumps({"errors": len(errs), "warnings": len(warns), "unconnected": len(d["unconnected_items"]),
                          "parity": len(d["schematic_parity"])}))
        if errs or d["unconnected_items"] or d["schematic_parity"]:
            raise SystemExit("DRC not clean")
    drc()
    # stranded vias (copper of the net on < 2 layers) carry nothing; removing them cannot open a net. They are measured on the
    # refilled pours, so this runs after the DRC above, and the DRC runs again on the stripped board.
    r = subprocess.run([KPY, "layout/via_hygiene.py", "pcb/controller.kicad_pcb"], cwd=UNIT, capture_output=True, text=True)
    removed = next((l for l in r.stdout.splitlines() if l.startswith("stranded vias removed")), "stranded vias: not run")
    print("== " + removed, flush=True)
    if not removed.endswith(" 0"):
        drc()
    step("jlc dfm", [KPY, "layout/jlc_dfm_check.py", "pcb/controller.kicad_pcb"], out=EV / "jlc-dfm.json")
    step("layout check", [KPY, "layout/check_layout.py", "pcb/controller.kicad_pcb"])
    step("fab", [KPY, "layout/fab.py"])
    step("fab review", [sys.executable, "layout/review_fab.py", "fab/gerbers", "evidence/fab-review.json"])
    print("ALL GATES PASS")


if __name__ == "__main__":
    main()
