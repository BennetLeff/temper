#!/usr/bin/env python3
"""Stage 15: which B3 (task 04 round 5) board heat sources scale with the tank ceiling, and by how much.

Reads the committed B3 inputs (b3/inputs/native21-board-heat-sources.json, b3/run_study.py OPS) and the
round-6 config summary (bank worst-part current). Prints the per-source heat at the B3 nominal point
(21.47 A), at 22 A, 28 A and the 28 A RMS trip level (1.05 x 28 = 29.4 A).
  * R5 (1 mOhm), R39 (CT burden, 1.5 ohm at I/100): I^2 R, exact scaling.
  * tank copper (sw_a, sw_b, res_a, coil_feed, leg_*, hv/bus mixed): (I / I_case)^2 as run_study.cases().
  * bank: B3 still carries the old CDE 942C rows for C21-C23 (task 03 round 3) and has no C151/C152.
    Stage 15 must replace them; the per-part current here is round 6's worst-share current.
usage: python3 thermal_scale.py [UNIT] -> out/thermal_scale.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
B3 = UNIT / "validation-results/04-board-current-thermal/round5-native21/b3"
R6 = UNIT / "validation-results/05-resonant-tank-envelope/round6-full-power/outputs"
I_NOM = 21.47
POINTS = {"B3 nominal 21.47 A": 21.47, "22 A (ships)": 22.0, "28 A (ceiling)": 28.0, "29.4 A (RMS trip 1.05x28)": 29.4}


def main():
    heat = json.loads((B3 / "inputs/native21-board-heat-sources.json").read_text())
    rows = heat.get("parts") or heat.get("rows")
    by = {r["ref"]: r for r in rows}
    cs = list(csv.DictReader(open(R6 / "config-summary6.csv")))
    cap_i = {float(r["I_max_A"]): float(r["cap_part_I_worst_A"]) for r in cs
             if r["geom"] == "d228_gap84" and r["L_free_uH"] == "70" and float(r["C_bank_uF"]) == 0.5}
    out = {"sources": {}, "copper_scale": {}, "bank": {}, "notes": []}
    for name, i in POINTS.items():
        out["sources"][name] = {"R5_W": round(i * i * 1e-3, 3), "R39_W": round((i / 100) ** 2 * 1.5, 4),
                                "R5_B3_row_nominal_W": by["R5"]["watts_nominal"],
                                "R39_B3_row_nominal_W": by["R39"]["watts_nominal"]}
        out["copper_scale"][name] = {"tank_x_vs_B3_nominal": round((i / I_NOM) ** 2, 3),
                                     "sw_a_case_scale_(I/18.7)^2": round((i / 18.7) ** 2, 3)}
    out["bank"] = {"B3_rows_present": {k: by[k]["note"] for k in ("C21", "C22", "C23") if k in by},
                   "B3_rows_missing": [k for k in ("C151", "C152") if k not in by],
                   "round6_worst_part_current_A_by_ceiling": cap_i}
    out["notes"].append("B3 R5 nominal row equals 21.47^2 x 1 mOhm: " + str(round(I_NOM ** 2 * 1e-3, 4)))
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/thermal_scale.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
