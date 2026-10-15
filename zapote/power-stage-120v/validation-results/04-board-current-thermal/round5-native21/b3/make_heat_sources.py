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
import math
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
    if p["ref"] in ("L1", "R5", "R39", "R22", "R23", "R24", "R25") and p["watts_nominal"]:
        add(p["ref"], p["watts_nominal"], p["watts_worst"], "task03", f"{p['part']}, task 03 round 3", p["board_fraction"])

# Resonant bank (stage 13, 5 x TDK B32654A1104K000; task 03's CDE 942C rows no longer apply). TDK B3265*A
# data sheet (MKP_B32651_658.pdf, not committed): p.23 ESR_typ 19.3 mOhm at 100 kHz (I_RMS 7.3 A at 85 C);
# p.35 tan d upper limits 1.0e-3 at 10 kHz and 3.0e-3 at 100 kHz (27 nF <= C <= 0.1 uF). Worst: those limits
# fitted as ESR = R_s + D / (2 pi f C) (R_s 35.3 mOhm, D 7.77e-4) at F_WORST. Nominal: ESR_typ held flat
# below 100 kHz (estimate: a polypropylene film's dielectric term adds a few mOhm at 33-40 kHz). Part current:
# round 6's worst-share part, 6.55 A of 28 A tank RMS (board_side.py), scaled with the tank current.
C_RES, ESR_TYP = 0.1e-6, 19.3e-3
R_S, D_LIM = 35.3e-3, 7.77e-4
SHARE = 6.55 / 28.0
I_T = {"nominal": 21.47, "worst": 29.4, "c28": 29.4}      # run_study.py OPS tank RMS (worst: the 1.05 x 28 A trip)


def esr_worst(f):
    return R_S + D_LIM / (2 * math.pi * f * C_RES)


# Stage 15: the firmware RMS trip (1.05 x ceiling <= 29.4 A) bounds the sustained tank current, so the worst
# column moves from round 3's 44.7 A grid extreme to 29.4 A: R5 / R39's task-03 worst rows are re-scaled.
for r in rows:
    if r["ref"] == "R5":
        r["watts_worst"] = I_T["worst"] ** 2 * 1e-3
        # Stage 17 (DECISIONS 17): R5 is a Bourns CSS2H-2512R-1L00F, still 1 mOhm, so the I^2 R rows stand. Its land
        # carries two sense fingers (pads 2 / 3) that are not part terminals: the heat goes into the current pads only.
        r["note"] = "CSS2H-2512R-1L00F (stage 17), I^2 x 1 mOhm; heat on current pads 1 / 4 only"
        r["pad_numbers"] = ["1", "4"]
    if r["ref"] == "R39":
        r["watts_worst"] = (I_T["worst"] / 100) ** 2 * 1.5
BANK = ("C21", "C22", "C23", "C151", "C152")
# Board fraction 0.3 (estimate): a radial film part sheds most of its heat from its 14 x 24.5 x 31.5 mm body
# (TDK rates I_RMS by the body's own rise, <= 20 K at 1.0 W typ); the leads carry the rest into the board.
# The bank's own acceptance is the bench hot-spot gate on TDK's curve (DECISIONS 2026-10-10), not B3.
for ref in BANK:
    add(ref, (SHARE * I_T["nominal"]) ** 2 * ESR_TYP, (SHARE * I_T["worst"]) ** 2 * esr_worst(F_WORST), "estimate",
        f"B32654A1104K000: (worst-share {SHARE:.3f} x I_t)^2 x ESR (typ 19.3 mOhm / tan d limit {esr_worst(F_WORST) * 1e3:.1f} mOhm at 40 kHz)",
        board=0.3)

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

# AC-DC module: loss = Pout (1/η - 1), η 0.84 nominal / 0.80 worst; half to the board (pins, body on the board, the
# rest convects from the case) - estimate. Stage 38 (candidate 23, DECISIONS 47): PS2 is the MEAN WELL MPM-20-24, typ.
# efficiency 87 % (MPM-20-SPEC 2024-10-30 p.2; the IRM-20-24 it replaces: 85 %, IRM-20-SPEC 2025-11-21 p.2), so the
# 0.84 / 0.80 rows stay as a conservative bound. PS1 (IRM-20-15, 8 / 12 W allocation) is deleted: its heat leaves the board.
add("PS2", 7.45 * (1 / 0.84 - 1), 11.10 * (1 / 0.80 - 1), "estimate",
    "MPM-20-24 at the stage-14 HOT allocation (ALT-BIAS budget.py: 7.45 W at 40 kHz, 11.10 W at 80 kHz); "
    "η 0.84 nominal / 0.80 worst (datasheet typ 87 %)", board=0.5)

# bus capacitors: C5/C6 (9 µF since stage 14) take the switching-frequency ripple; the HF 0.1 µF film caps
# see edge harmonics only (Xc 48 Ω vs 1.8 Ω at 33 kHz)
for ref in ("C5", "C6"):
    add(ref, 0.3, 0.6, "estimate", "B32676G1905K000 9 µF: ~10 A RMS each × ~5 mΩ ESR at 33 kHz (estimate, carried from the 2.7 µF row)")
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
# Stage 15: the 28 A ceiling case (run_study.py OPS "c28": 29.4 A tank RMS = the 1.05 x ceiling firmware
# trip, 11.1 A line). Its own heat file, with the case watts in watts_nominal: tank-scaled rows (R5 = I^2 x
# 1 mOhm, R39 = (I/100)^2 x 1.5 Ohm, the bank at ESR_typ, C5/C6 by (I/21.47)^2), L1 by (11.1 / 14.25)^2 (task
# 03's nominal line current 1710 W / 120 V); bias, gate drive and supplies as nominal (set by f, not by
# the ceiling).
C28 = {"R5": I_T["c28"] ** 2 * 1e-3, "R39": (I_T["c28"] / 100) ** 2 * 1.5}
C28.update({ref: (SHARE * I_T["c28"]) ** 2 * ESR_TYP for ref in BANK})
C28_SCALE = {"C5": (I_T["c28"] / 21.47) ** 2, "C6": (I_T["c28"] / 21.47) ** 2, "L1": (11.1 / (1710 / 120)) ** 2}
c28_rows = []
for r in rows:
    w = C28.get(r["ref"], r["watts_nominal"] * C28_SCALE.get(r["ref"], 1.0))
    c28_rows.append({**r, "watts_nominal": w, "watts_worst": w})
(HERE / "inputs").mkdir(exist_ok=True)
(HERE / "inputs" / "native21-board-heat-sources-c28.json").write_text(json.dumps(
    {"status": "native-21 board heat at the 28 A ceiling case (stage 15; watts_nominal = watts_worst = the case)",
     "parts": c28_rows, "totals_W": {"c28": round(sum(r["watts_nominal"] * r["board_fraction"] for r in c28_rows), 3)}},
    indent=1) + "\n")

out = {"status": "native-21 board heat: task 03 carry-over + bias sizing + stated estimates (round 5)",
       "parts": rows,
       "totals_W": {m: round(sum(r[f"watts_{m}"] * r["board_fraction"] for r in rows), 3) for m in ("nominal", "worst")}}
(HERE / "inputs").mkdir(exist_ok=True)
(HERE / "inputs" / "native21-board-heat-sources.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out["totals_W"]), len(rows), "parts")
