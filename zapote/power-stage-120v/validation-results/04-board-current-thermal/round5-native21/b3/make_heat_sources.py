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
import re
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
# Stage 49 (DECISIONS 68, candidate 34): the bank is 5 x TDK B32643B8104J000. TDK B3264*B data sheet
# (MMKP_B32641B_B32643B.pdf 6/26, sha256 ab9fdca0..., not committed): p.11 ESR_typ 8 mOhm at 85 C / 100 kHz (IRMS,max
# 8.3 A for dT <= 15 K); p.12 tan d upper limits 0.6e-3 at 10 kHz and 1.5e-3 at 100 kHz. Worst: those limits fitted the
# same way, ESR = R_s + D / (2 pi f C): R_s 15.9 mOhm, D 5.00e-4. (B32654A1104: 19.3 mOhm typ; R_s 35.3 mOhm, D 7.77e-4.)
# Stage 51 (DECISIONS 73, 11-candidates/c51-bank-source): the bank is 5 x KNSCHA MMK104J3DF1KN208G2 (MMKP82). KNSCHA
# publishes no ESR per part. Typical: the ESR its current rating implies, 10.7 mOhm at 35 kHz (6.2 A for a 10 K internal
# rise; heat 10 K x G_vtest 0.41 W at the lo G_board bound; c51-bank-source README "Decision inputs" (3) item 2). Worst:
# the only published loss limit, tan d <= 0.1 % at 1 kHz (spec KNS20200505002 p.4), held flat as the dielectric term
# with R_s 0: 39.8 mOhm at 40 kHz, 3.7 x the rating-implied value and above c34's 35.8 mOhm. Both ASSUMED (bench item:
# ESR / tan d at 35 and 40 kHz). (B32643B8104J000, the 28 A alternate: 8 mOhm typ; R_s 15.9 mOhm, D 5.00e-4.)
# Stage 52 (DECISIONS 74, prototype lot): the bank is 5 x TDK B32643H8104J000 (B3264*H, June 2026, owner-supplied,
# sha256 69b56e62..., not committed). p.14: ESRtyp 10.9 mOhm at 100 kHz (IRMS,max 9.17 A at 85 C for dT <= 20 K), held
# flat below 100 kHz as the typical row (as the B32654A rows above). p.15: tan d upper limits 0.3e-3 at 1 kHz and
# 1.0e-3 at 100 kHz (C <= 0.1 uF). Worst: those two limits fitted as ESR = R_s + D / (2 pi f C): R_s 11.26 mOhm,
# D 2.93e-4, i.e. 22.9 mOhm at 40 kHz. (KNSCHA MMK104J3DF1KN208G2, the s51 part and now the in-stock fallback: 10.7 mOhm
# typ / R_s 0, D 1.0e-3, 39.8 mOhm at 40 kHz.)
C_RES, ESR_TYP = 0.1e-6, 10.9e-3
_W1, _W100 = 2 * math.pi * 1e3 * C_RES, 2 * math.pi * 100e3 * C_RES
R_S = (1.0e-3 - 0.3e-3) / (_W100 - _W1)                 # tan d = D + R_s w C at both points
D_LIM = 0.3e-3 - R_S * _W1
BANK_MPN = "B32643H8104J000"
FROZEN_CSV = (UNIT / "native-21/frozen/default.csv").read_text()
assert f"{BANK_MPN},\"C21," in FROZEN_CSV, "the heat rows' bank MPN is not the frozen BOM's"
SHARE = 6.55 / 28.0
I_T = {"nominal": 21.47, "worst": 29.4, "c28": 29.4}      # run_study.py OPS tank RMS (worst: the 1.05 x 28 A trip)


def esr_worst(f):
    return R_S + D_LIM / (2 * math.pi * f * C_RES)


# Stage 52 (DECISIONS 74, prototype lot): L1 is TDK B82726S2243A020. Its copper loss replaces task 03's B82726S2203A020
# row: 2 windings x R_typ x 15 A^2 (the owner's 15 A inlet cap, the same current task 03 used: 2 x 4.5 mOhm x 15^2 =
# 2.025 W). R_typ per winding at 20 C: 4.5 mOhm (2203) / 3.2 mOhm (2243), TDK B82726S22*3A020 (5/26) p.4 ordering table.
L1_RTYP = {"B82726S2203A020": 4.5e-3, "B82726S2243A020": 3.2e-3}
L1_MPN = next(m for m in L1_RTYP if f"{m},L1," in FROZEN_CSV)
for r in rows:
    if r["ref"] == "L1":
        w = 2 * L1_RTYP[L1_MPN] * 15.0 ** 2
        r.update(watts_nominal=w, watts_worst=w,
                 note=f"{L1_MPN}, 2 x {L1_RTYP[L1_MPN] * 1e3:.1f} mOhm (TDK p.4, typ at 20 C) x 15 A^2 (task 03 basis)")

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
# Board fraction 0.3 (estimate): a radial film part sheds most of its heat from its body (stage 49: TDK 14.5 x 29.5 x
# 26.5 mm, <= 15 K at 0.55 W typ, p.11; stage 51: KNSCHA 11 x 19.5 x 31.5 mm, 10 K at about 0.41 W); the leads carry the
# rest into the board.
# The bank's own acceptance is the bench hot-spot gate on TDK's curve (DECISIONS 2026-10-10), not B3.
for ref in BANK:
    add(ref, (SHARE * I_T["nominal"]) ** 2 * ESR_TYP, (SHARE * I_T["worst"]) ** 2 * esr_worst(F_WORST), "estimate",
        f"{BANK_MPN}: (worst-share {SHARE:.3f} x I_t)^2 x ESR (typ {ESR_TYP * 1e3:.1f} mOhm / tan d limit {esr_worst(F_WORST) * 1e3:.1f} mOhm at 40 kHz)",
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
# Stage 48 (c48-ldo-en-ref-watch): U3 deposits its bound, not a typical: IN 15.46 V (S16 rail model maximum) - HOT5 4.89 V
# (TPS70950QDBVRQ1 -2 %, SLVSCE6D 5.5 p.5) = 10.57 V x 15.1 mA (the HOT5 loads of the Kelvin census at their maxima, U9 at
# the CA-IS3720HW 4.1 mA, the REF25 watchdog inside U5's bound) = 0.160 W; 0.1 W until s47
add("U3", 0.160, 0.26, "estimate", "TPS70950QDBVRQ1 HOT5: 10.57 V drop (IN 15.46 V max - OUT 4.89 V min) x 15.1 mA (Kelvin census); "
    "heat on pads 1 / 2 / 3 / 5 (pin 4 NC: 'No internal connection', SLVSCE6D Table 4-1 p.3)")
# U3's pin 4 has no internal connection, so no die heat enters its pad (as R5's sense fingers above). Heated, the isolated
# NC pad floats to the junction node and its cell became U3's "pad copper" (s48 runs 3-5: 124.8 / 116.4 / 124.1 C with
# the pad as the hottest cell, swinging with how the 0.25 mm mesh rasterised the GND run 0.21-0.4 mm from it).
rows[-1]["pad_numbers"] = ["1", "2", "3", "5"]
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
# thermal-refine 2026-10-15: in the c28 file the frequency-set rows sit at the 60 kHz top of the control window (DECISIONS 1:
# "module temperature at the 60 kHz control-window maximum (~1.4 W)") and the gate rows follow the s29 drive (DECISIONS 31:
# 2EDR8259X, R10/R12/R18/R20 8.2 ohm RS-06L8R20FT, R53/R54/R57/R58 1 ohm 1206W4F100KT5E via the PMEG discharge diode).
# Q_DECK = the worst gate-loop charge per edge on the as-built 2EDR8259X + 8.2 ohm deck, 382.6 nC (S2; device study
# validation-results/01-switching-parasitics/device-study-2026-10-15/results/bias.json, DECISIONS 49) - not the 740 nC
# Q_WORST allowance, which stays the sizing basis of the worst-case file above.
# Load per channel as native-21/bias_sizing.py (I_ch = Q f + 22.9 mA); module P_out = 17 V x I_ch at the
# ALT-BIAS 45 % allocation; U26 = (24 - 17 V)(2 I_ch + 30 mA); PS2 = the ALT-BIAS budget (7.45 W at 40 kHz reproduced).
# Gate energy Q x 17 V per FET per cycle, half in each path, split by resistance: on = Ron_SRC 0.95 (2EDR8259 Rev.1.7
# p.15) + 8.2 + Rg,int 2.7 (IPW65R018CFD7 p.5); off = 2.7 + [8.2 || (PMEG Vf 0.35 V, 0.1 ohm + 1.0)] + Ron_SNK 0.39.
# Driver quiescent 2 x 1.14 mA x 17 V + 2.12 mA x 3.3 V (2EDR8259 Table 12 p.12).
F_WIN, Q_DECK = 60e3, 382.6e-9
# Candidate 39 (DECISIONS 54, stage 42): the gate network is read from the frozen BOM (native-21/frozen/resolved-
# components.json), so the c28 gate rows follow the board: R_on = R10/R12/R18/R20, Cgs = C55/C56/C62/C63. The FET's own
# charge stays Q_DECK (382.6 nC, the deck's worst S2 charge with the as-built 1 nF Cgs). A larger external Cgs adds its
# own charge per edge, taken from the gate-network study (validation-results/01-switching-parasitics/gate-network-
# 2026-10-15/README.md section 3a note "R_on power": "With 4.7 nF the charge is +61 nC, so it is scaled to 444 nC");
# an unlisted Cgs value raises instead of extrapolating. That charge flows through the driver source / sink and R_on or
# the PMEG branch only (Cgs sits on the board side of the FET's Rg,int). With R_on 8.2 ohm and Cgs 1 nF (s29-s41) the
# rows are exactly those of the thermal-refine model.
R_SRC, R_SNK, RG_INT, R_BR, VF_OFF = 0.95, 0.39, 2.7, 1.0 + 0.1, 0.35
Q_CGS_EXTRA = {1.0e-9: 0.0, 4.7e-9: 61e-9}                       # C per edge over the 1 nF deck basis
RC = {c["attributes"]["designator"]: c["attributes"]
      for c in json.loads((UNIT / "native-21/frozen/resolved-components.json").read_text())["components"]}


def _si(v, unit):
    m = re.fullmatch(r"([0-9.]+)\s*([munpkM]?)" + unit, v.strip())
    assert m, (v, unit)
    return float(m.group(1)) * {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "k": 1e3, "M": 1e6}[m.group(2)]


def _one(refs, unit):
    vals = {round(_si(RC[r]["value"], unit), 15) for r in refs}
    assert len(vals) == 1, (refs, vals)
    return vals.pop()


R_ON = _one(("R10", "R12", "R18", "R20"), "ohm")
C_GS = _one(("C55", "C56", "C62", "C63"), "F")
Q_EXT = Q_CGS_EXTRA[round(C_GS, 15)]
I_CH = (Q_DECK + Q_EXT) * F_WIN + 0.0044 + 0.003 + 0.0015 + 0.014
E_F = Q_DECK * SWING * F_WIN                                     # W of gate drive per FET (the FET's own charge)
E_X = Q_EXT * SWING * F_WIN                                      # W per FET for the extra Cgs charge


def gate_split(r_on, rg_int):
    """Shares of Q x 17 V x f per FET: half on turn-on (R_SRC + r_on + rg_int), half on turn-off (rg_int + [r_on ||
    PMEG branch] + R_SNK, less the diode's forward-drop share). rg_int = 0 for the external Cgs charge."""
    on = R_SRC + r_on + rg_int
    vf = VF_OFF / (0.5 * SWING)                                  # diode forward-drop share of the turn-off energy
    rpar = r_on * R_BR / (r_on + R_BR)
    tot, res = rg_int + rpar + R_SNK, 1.0 - vf
    p_par = res * rpar / tot
    return {"rg": 0.5 * r_on / on + 0.5 * p_par * R_BR / (r_on + R_BR),
            "roff": 0.5 * p_par * r_on / (r_on + R_BR) * 1.0 / R_BR,
            "drv": 0.5 * R_SRC / on + 0.5 * res * R_SNK / tot}


SPLIT, SPLIT_X = gate_split(R_ON, RG_INT), gate_split(R_ON, 0.0)
C28_F = {"U41": 17.0 * I_CH * (1 / 0.45 - 1), "U42": 17.0 * I_CH * (1 / 0.45 - 1), "U26": (24 - 17) * (2 * I_CH + 0.030),
         "PS2": (2 * 17.0 * I_CH / 0.45 + 24 * (2 * I_CH + 0.030) + 24 * 0.010) * (1 / 0.84 - 1)}
for drv, rg, roff in (("U1", ("R10", "R12"), ("R53", "R54")), ("U2", ("R18", "R20"), ("R57", "R58"))):
    C28_F[drv] = 2 * (SPLIT["drv"] * E_F + SPLIT_X["drv"] * E_X) + 2 * 1.14e-3 * 17.0 + 2.12e-3 * 3.3
    C28_F.update({r: SPLIT["rg"] * E_F + SPLIT_X["rg"] * E_X for r in rg})
    C28_F.update({r: SPLIT["roff"] * E_F + SPLIT_X["roff"] * E_X for r in roff})
C28.update(C28_F)
c28_rows = []
for r in rows:
    w = C28.get(r["ref"], r["watts_nominal"] * C28_SCALE.get(r["ref"], 1.0))
    c28_rows.append({**r, "watts_nominal": w, "watts_worst": w})
    if r["ref"] in C28_F:
        c28_rows[-1]["note"] = (f"60 kHz window top, 2EDR8259X / {R_ON:g} ohm turn-on, Cgs {C_GS * 1e9:g} nF, Q {Q_DECK * 1e9:.1f}"
                                + (f" + {Q_EXT * 1e9:.0f}" if Q_EXT else "") + " nC (thermal-refine 2026-10-15; candidate 39)")
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
