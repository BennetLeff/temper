#!/usr/bin/env python3
"""Stage 15b, deliverable 1c: how much the missing FET-lead path biases B3's FET-row temperature.

thermal.py gives the four TO-247s board_fraction 0 and NO path from their pads to the package: the board
neither receives lead heat from the die nor sheds heat into the heatsinked package. model/b3/thermal_lead.py
(a copy; only change: optional LEAD_SINK) ties each lead's pad (half on F.Cu, half on B.Cu cell at the pin
centre) to the package at a fixed case temperature through a lead conductance G.

G upper bound per lead (no committed lead section, so bound it from committed geometry):
  section <= the largest rectangle through the 1.5 mm drill (A4 json drill_mm 1.5): b = c = 1.5/sqrt2 -> 1.125 mm^2
  length  >= body bottom above the board, L1 min 3.85 mm (m11/RECOMMENDATION.md §1, Infineon PG-TO247-3 p.12)
  k       <= 390 W/mK (thermal.py K_CU; lead frames are Cu alloys at or below this)
  -> G <= 390 * 1.125e-6 / 3.85e-3 = 0.114 W/K. Solder joints and the in-body path only lower it.
Case temperature at 28 A (round6 board-side-fets.csv, 45 kHz row; R_thJC 0.28 C/W datasheet p.4 as cited in PLAN.md §2):
  basis B (ZVS): Tc = 81.6 - 11.86 * 0.28 = 78.3 C;   basis A (switching proxy): Tc <= 134.5 - 14.47 * 0.28 = 130.4 C.
Only the drain lead (pin 2) is part of the tab lead frame; pins 1 / 3 reach the die through bond wires, so
"drain" is the realistic set and "all" over-states the path.

    python3 lead_bias.py [tag geometry A4_DIR A4_COPPER] -> out/lead_bias[_tag].json
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = HERE / "model"
sys.path.insert(0, str(MODEL / "b3"))
import run_study as rs  # noqa: E402

G = 390 * (1.5 / 2 ** 0.5) ** 2 * 1e-6 / 3.85e-3
TC = {"basis_B_78.3C": 81.6 - 11.86 * 0.28, "basis_A_130.4C": 134.5 - 14.47 * 0.28}
TAG = sys.argv[1] if len(sys.argv) > 1 else ""
GEOM = sys.argv[2] if len(sys.argv) > 2 else str(MODEL / "native21s15-all-copper.json.gz")
RUNS = HERE / "runs" / ("lead" + TAG)
RUNS.mkdir(parents=True, exist_ok=True)
rows = []
for h in (25, 10):
    for label, spec in [("no lead path (as committed)", None)] + \
            [(f"{tk}, {which}, G {G:.3f} W/K", f"{tc}:{G}:{which}") for tk, tc in TC.items() for which in ("drain", "all")]:
        out = RUNS / f"h{h}_{abs(hash(label)) % 10**8}.json"
        env = {**os.environ}
        if len(sys.argv) > 4:
            env.update(A4_DIR=sys.argv[3], A4_COPPER=sys.argv[4])
        if spec:
            env["LEAD_SINK"] = spec
        subprocess.run([sys.executable, str(MODEL / "b3/thermal_lead.py"), "--geometry", GEOM,
                        "--case", rs.cases("c28"), "--pitch-mm", "1.0", "--h", str(h), "--a6-heat",
                        str(MODEL / "b3/inputs/native21-board-heat-sources-c28.json"), "--a6-mode", "nominal",
                        "--output", str(out)], check=True, stdout=subprocess.DEVNULL, env=env)
        r = json.loads(out.read_text())
        import numpy as np
        z = np.load(out.with_suffix(".npz"))
        x, y, rise = z["x_mm"], z["y_mm"], z["rise_k"]
        strip = 50 + rise[:, (x <= 80), :][:, :, (y <= 12.5)].max()
        rows.append({"h": h, "case": label, "board_peak": r["peak"], "fet_row_max_c": round(float(strip), 2),
                     "lead_w_to_package": round(r["balance"]["fixed_end_w"], 3)})
        print(h, label, round(r["peak"]["temperature_c"], 1), r["peak"]["x_mm"], r["peak"]["y_mm"],
              "row", round(float(strip), 1), "lead W", round(r["balance"]["fixed_end_w"], 2), flush=True)
        for f in (out, out.with_suffix(".npz"), out.with_suffix(".png")):
            f.unlink()
(HERE / "out").mkdir(exist_ok=True)
(HERE / f"out/lead_bias{('_' + TAG) if TAG else ''}.json").write_text(json.dumps({"G_upper_W_per_K": G, "Tc_C": TC, "rows": rows}, indent=1) + "\n")
