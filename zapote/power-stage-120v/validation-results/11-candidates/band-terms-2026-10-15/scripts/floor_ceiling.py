#!/usr/bin/env python3
"""Item 1, which floor governs: the shunt-OCP low corner against the floor at the commissioned tank ceiling.

    python3 -I floor_ceiling.py [PS_DIR]   -> ../results/floor_ceiling.json   (run band_cmrr.py first)

Floor rule (round 6 / stage 15, DECISIONS 13): envelope peak at the ceiling + coil-pickup stack + 2 A.
  envelope peak: round6 board-side-protection.csv tank_pk_max_A (22..30 A rows). 17.5 A is below the grid, so the
    pk/RMS ratio is extrapolated linearly from the 22-30 A rows (it rises as current falls: 2.113 at 28 A, 2.170 at 22 A).
    A second basis uses the firmware peak trip at 17.5 A, 2.17 x 17.5 + 3 = 40.975 A (DECISIONS 61), which the
    hardware trip must sit above anyway.
  pickup: the stage-15 PLAN bases A / B / C at 28 A (3.00 / 3.99 / 9.31 A). EMF scales with I_pk x f; at 17.5 A
    I_pk x f (38.7 A x <= 60 kHz) is below the 28 A grid maximum (58.6 A x 51.13 kHz), so the 28 A values bound it.
"""
import sys
sys.dont_write_bytecode = True
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1] if len(sys.argv) > 1 else
          "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
OUT = HERE.parent / "results"
rows = list(csv.DictReader(open(PS / "validation-results/05-resonant-tank-envelope/round6-full-power/outputs/board-side-protection.csv")))
I = [float(r["I_max_A"]) for r in rows]
K = [float(r["tank_pk_max_A"]) / float(r["I_max_A"]) for r in rows]
n = len(I)
mi, mk = sum(I) / n, sum(K) / n
slope = sum((a - mi) * (b - mk) for a, b in zip(I, K)) / sum((a - mi) ** 2 for a in I)
k175 = mk + slope * (17.5 - mi)
pk175 = 17.5 * k175
pk28 = float(next(r for r in rows if float(r["I_max_A"]) == 28.0)["tank_pk_max_A"])
assert pk28 == 59.17
PICKUP = {"A (DECISIONS 9 as written)": 3.0, "B (FEM phase, scaled)": 3.99, "C (any phase, scaled)": 9.31}
fw175 = 2.17 * 17.5 + 3.0
floors = {"28 A (committed, 64.17 A)": {p: round(pk28 + v + 2.0, 2) for p, v in PICKUP.items()},
          "17.5 A, envelope extrapolated": {p: round(pk175 + v + 2.0, 2) for p, v in PICKUP.items()},
          "17.5 A, firmware peak trip 40.975 A": {p: round(fw175 + v + 2.0, 2) for p, v in PICKUP.items()}}
cm = json.loads((OUT / "band_cmrr.json").read_text())
lows = {}
for r in cm["rows"]:
    if r["hot5"].startswith("Q1") and (r["psrr"] or r["reading"] == "R0"):
        key = f"{r['case']} {r['reading']}{' +PSRR' if r['psrr'] else ''}"
        lows[key] = r["ocp_low_after"]["census -2.391"]
margins = {f: {k: {p: round(v - fl, 2) for p, fl in fs.items()} for k, v in lows.items()} for f, fs in floors.items()}
out = {"pk_over_rms_fit": {"slope_per_A": round(slope, 5), "at_17p5": round(k175, 4)}, "envelope_peak_17p5_A": round(pk175, 2),
       "firmware_peak_trip_17p5_A": fw175, "floors_A": floors, "ocp_low_after_census_kelvin_A": lows, "margins_A": margins}
OUT.mkdir(exist_ok=True)
(OUT / "floor_ceiling.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({k: out[k] for k in ("pk_over_rms_fit", "envelope_peak_17p5_A", "floors_A")}, indent=1))
for f, mm in margins.items():
    print(f)
    for k, v in mm.items():
        print("   ", k, v)
