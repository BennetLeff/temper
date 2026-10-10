#!/usr/bin/env python3
"""Native-21 board heat sources for the B3 thermal solve (round 5).

    python3 make_heat_sources.py  ->  inputs/native21-board-heat-sources.json

Same schema as task 03's board_heat_sources.json (thermal.py --a6-heat). Heat is deposited
on each part's own pads, so only the references matter (positions are a fallback).

Sources, row by row (`basis` in the output):
- task03: task 03 round 3 board_heat_sources.json, carried over by reference where the part is
  unchanged on native-21 (C21-C23, L1, R5, R39, R22-R25). FETs and BR1 stay on the heatsink
  (board fraction 0, as task 03).
- bias: native-21/bias_sizing.py. Nominal = its 33 kHz row with the 234 nC datasheet typical
  gate charge; worst = its 40 kHz row with the 740 nC extracted F6 edge allowance.
- estimate: an engineering estimate stated in the row's note, with its bound. Not a measurement.

Gate loss per FET is Q·ΔV·f (17 V swing). It splits between the driver output stage, the 3.9 Ω
turn-on resistor and the 1 Ω F6 turn-off path. The split below (driver 50 %, R_g 25 %, R_off 25 %)
is an estimate; the FET's internal gate resistance takes part of it on the heatsink, so the board
share is overstated.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
T03 = json.loads((UNIT / "validation-results/03-loss-thermal-budget/round3/outputs/board_heat_sources.json").read_text())
PADS = json.loads((UNIT / "native-21/layout/pads.json").read_text())

F_NOM, F_WORST = 33e3, 40e3
Q_NOM, Q_WORST, SWING = 234e-9, 740e-9, 17.0
GATE_NOM, GATE_WORST = Q_NOM * SWING * F_NOM, Q_WORST * SWING * F_WORST       # W per FET

rows = []


def add(ref, nom, worst, basis, note, board=1.0):
    rows.append({"ref": ref, "watts_nominal": nom, "watts_worst": worst, "board_fraction": board,
                 "sink_fraction": 1.0 - board, "basis": basis, "note": note})


for p in T03["parts"]:
    if p["ref"] in ("C21", "C22", "C23", "L1", "R5", "R39", "R22", "R23", "R24", "R25") and p["watts_nominal"]:
        add(p["ref"], p["watts_nominal"], p["watts_worst"], "task03", f"{p['part']}, task 03 round 3", p["board_fraction"])

# gate drive: two FETs per driver (UCC21550 U1 leg A, U2 leg B), plus 0.1 W quiescent each (estimate)
for drv, rg, roff in (("U1", ("R10", "R12"), ("R53", "R54")), ("U2", ("R18", "R20"), ("R57", "R58"))):
    add(drv, 2 * 0.5 * GATE_NOM + 0.1, 2 * 0.5 * GATE_WORST + 0.1, "bias",
        "UCC21550: 50 % of two FETs' Q·ΔV·f + 0.1 W quiescent (estimate)")
    for r in rg:
        add(r, 0.25 * GATE_NOM, 0.25 * GATE_WORST, "bias", "3.9 Ω turn-on resistor: 25 % of one FET's gate loss (estimate)")
    for r in roff:
        add(r, 0.25 * GATE_NOM, 0.25 * GATE_WORST, "bias", "1 Ω F6 turn-off resistor: 25 % of one FET's gate loss (estimate)")

# stage 14: one isolated bias module per high side (RECOM R24C2T25/R-R, U41 / U42). Module loss
# 1.09 W at 40 kHz / 1.71 W at the 80 kHz F6 allocation (ALT-BIAS 3.2, 45 % efficiency allocation);
# the HS TPS7A47s and the SN6507 / T2 / T3 push-pull are gone.
for ref in ("U41", "U42"):
    add(ref, 1.09, 1.71, "bias", "R24C2T25/R module loss (ALT-BIAS 3.2; 40 / 80 kHz allocation)")
add("U26", 0.87248, 0.945, "bias", "TPS7A4700 low-side span LDO: (24 - 17 V) × load")

# AC-DC modules: loss = Pout (1/η - 1), η 0.84 (IRM-20 typical ~86 %); half to the board (pins,
# body on the board, the rest convects from the case) - estimate
add("PS2", 7.45 * (1 / 0.84 - 1), 11.10 * (1 / 0.80 - 1), "estimate",
    "IRM-20-24 at the stage-14 HOT allocation (ALT-BIAS budget.py: 7.45 W at 40 kHz, 11.10 W at 80 kHz); "
    "η 0.84 nominal / 0.80 worst", board=0.5)
add("PS1", 8.0 * (1 / 0.84 - 1), 12.0 * (1 / 0.80 - 1), "estimate",
    "IRM-20-15 SELV supply: 8 W nominal / 12 W worst load (controller allocation not final)", board=0.5)

# bus capacitors: C5/C6 (2.7 µF) take the switching-frequency ripple; the HF 0.1 µF film caps see
# edge harmonics only (Xc 48 Ω vs 1.8 Ω at 33 kHz)
for ref in ("C5", "C6"):
    add(ref, 0.3, 0.6, "estimate", "B32656 2.7 µF: ~10 A RMS each × ~5 mΩ ESR at 33 kHz (estimate)")
for ref in ("C38", "C39", "C40", "C41"):
    add(ref, 0.05, 0.2, "estimate", "B32652 0.1 µF HF film: edge-harmonic current only (estimate, bounded 0.2 W)")

# small rails
add("U3", 0.1, 0.26, "estimate", "TPS70950 HOT5: ≤ 19 V drop × 13.6 mA (Kelvin census)")
for ref in ("U37", "U38", "U39"):
    add(ref, 0.05, 0.1, "estimate", "TPS70950 monitor 5 V: (15 - 5 V) × ≤ 10 mA")
for ref in ("R67", "R68", "R69", "R70"):
    add(ref, 0.074, 0.074, "estimate", "LINE_ZC string at 140 V RMS (ECO: 0.297 W total)")

at = {}
for p in PADS:
    at.setdefault(p["ref"], []).append((p["x"], p["y"]))
missing = [r["ref"] for r in rows if r["ref"] not in at]
assert not missing, missing
for r in rows:
    xs, ys = zip(*at[r["ref"]])
    r.update(x_mm=round((min(xs) + max(xs)) / 2, 3), y_mm=round((min(ys) + max(ys)) / 2, 3),
             has_unquantified_loss=r["basis"] == "estimate", use_as_complete_b3_heat_source=True,
             part=r["note"].split(":")[0])
out = {"status": "native-21 board heat: task 03 carry-over + bias sizing + stated estimates (round 5)",
       "parts": rows,
       "totals_W": {m: round(sum(r[f"watts_{m}"] * r["board_fraction"] for r in rows), 3) for m in ("nominal", "worst")}}
(HERE / "inputs").mkdir(exist_ok=True)
(HERE / "inputs" / "native21-board-heat-sources.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out["totals_W"]), len(rows), "parts")
