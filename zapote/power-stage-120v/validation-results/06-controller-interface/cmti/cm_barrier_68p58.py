#!/usr/bin/env python3
"""HOT-return common-mode divider at the c55 maximum-Qrr chord (68.58 V/ns), for cmti_table.py's "seen" column.

Rerun:  python3 -I validation-results/06-controller-interface/cmti/cm_barrier_68p58.py   (needs ngspice on PATH)

Runs the S6 study's committed cm_barrier.py unchanged (11-candidates/s6-cmti-2026-10-16/scripts/cm_barrier.py) at two
slews, writing to results-68p58/ here instead of the S6 folder:
  68.16 V/ns  control: must reproduce the S6 study's committed cm_barrier.json rows
  68.58 V/ns  the c55 long-window bound (11-candidates/c55-device-trade, section 1.3)
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
S6 = HERE.parents[1] / "11-candidates" / "s6-cmti-2026-10-16"
OUT = HERE / "results-68p58"

spec = importlib.util.spec_from_file_location("cm_barrier", S6 / "scripts" / "cm_barrier.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)
cm.RES = OUT
sys.argv = [sys.argv[0], "68.16", "68.58"]
cm.main()

# control: every 68.16 row against the committed S6 rows
ref = {r["case"]: r for r in json.loads((S6 / "results" / "cm_barrier.json").read_text())["rows"] if r["slew_sw"] == 68.16}
new = json.loads((OUT / "cm_barrier.json").read_text())["rows"]
worst = 0.0
for r in new:
    if r["slew_sw"] != 68.16:
        continue
    for k in ("bus_n", "line_f", "neut_f"):
        a, b = ref[r["case"]][k]["dvdt_1ns_max"], r[k]["dvdt_1ns_max"]
        worst = max(worst, abs(a - b))
n = sum(r["slew_sw"] == 68.16 for r in new)
ok = n == len(ref) and worst <= 1e-6
(OUT / "control.json").write_text(json.dumps(dict(rows=n, committed_rows=len(ref), max_abs_diff_1ns_Vns=worst, pass_=ok), indent=1) + "\n")
print(f"CONTROL 68.16 vs committed S6 rows: {n}/{len(ref)} rows, max |diff| {worst:.3g} V/ns -> {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
