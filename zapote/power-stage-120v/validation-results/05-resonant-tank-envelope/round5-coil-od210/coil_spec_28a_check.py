#!/usr/bin/env python3
"""Recompute every number changed in COIL-SPEC-ELECTRICAL.md for the 28 A ceiling.

Inputs are the cited constants below (DECISIONS item / file) plus the committed round-6 and round-5
CSV/JSON outputs. Writes coil_spec_28a_check.json and asserts each value printed in the spec.

Run:  python3 coil_spec_28a_check.py        (from any directory; stdlib only)
"""
import csv, glob, json, math, pathlib

HERE = pathlib.Path(__file__).resolve().parent
TASK05 = HERE.parent
SPEC = HERE / "COIL-SPEC-ELECTRICAL.md"

# ---- cited inputs -------------------------------------------------------------------------------
I_CEIL = 28.0            # DECISIONS item 10 (hardware sized for 28 A), item 13 (Kconfig up to 28 A)
I_SHIP = 22.0            # DECISIONS item 10/13: ships at 22 A
RAC_LIMIT_HOT = 0.25     # DECISIONS item 12: 0.25 ohm acceptance limit, 40 kHz / 100 C
RAC_TARGET_HOT = 0.23    # DECISIONS item 10 "Coil RFQ" target
P_BASIS_W = 200.0        # DECISIONS item 5 / item 12: enclosure plenum basis
ALPHA_CU = 0.00393       # spec convention (Cu +0.393 %/K)
DT = 75.0                # 100 C -> 25 C
F_EXP = 0.55             # round 4 R_ac ~ f^0.55
R36_RAC = (0.116, 0.136) # DECISIONS item 12, 40 kHz / 100 C
SHUNT_BAND = (67.72, 116.44)   # DECISIONS item 17 (OCP band after Kelvin shift)
OLD_SHUNT_UPPER = 97.77        # stage-13 band, superseded
CT_BAND = (64.55, 76.09)       # DECISIONS item 13
ENVELOPE_PEAK_28 = 59.17       # DECISIONS item 13
PEAK_PER_RMS, PEAK_PICKUP, PEAK_MAX = 2.17, 3.0, 62.0   # firmware/components/power/include/tank_freq.h:75-80, Kconfig:44
RMS_TRIP_K = 1.05              # Kconfig:44, DECISIONS item 10
U_PK, U_RMS = 640.0, 242.0     # DECISIONS item 7 (ORACLE Q2)
OLD_R_MAX = 0.41               # R32 study 02 old maximum R_ac (DECISIONS item 8 case)
OLD_T_140 = 140.7              # DECISIONS item 8: 22 A, old max R, 50 C inlet
TURNS_70 = 21.9                # DECISIONS item 12 (R36)

out, checks = {}, []
def rec(key, val, text):
    out[key] = val
    checks.append((key, text))

k_hot_cold = 1 + ALPHA_CU * DT
RAC_OLD_HOT = RAC_LIMIT_HOT           # 0.25 ohm, superseded acceptance limit (DECISIONS item 12)
RAC_LIMIT_HOT = RAC_TARGET_HOT        # row 5 binding figure: 0.23 ohm (DECISIONS item 10)
r25 = RAC_LIMIT_HOT / k_hot_cold
rec("row5_limit_25C_ohm", r25, f"{r25:.3f}")
shape = lambda f: r25 * (f / 40.0) ** F_EXP
loss = lambda i, r: i * i * r
cap_hot = P_BASIS_W / I_CEIL**2
cap_25 = cap_hot / k_hot_cold
f_knee = 40.0 * (cap_hot / RAC_LIMIT_HOT) ** (1 / F_EXP)
rhot = lambda f: RAC_LIMIT_HOT * (f / 40.0) ** F_EXP
rec("rac_cap_hot_ohm", cap_hot, f"{cap_hot:.4f} Ω")
rec("rac_cap_25C_ohm", cap_25, f"{cap_25:.3f}")
rec("cap_knee_kHz", f_knee, f"{f_knee:.1f} kHz")
rec("cap_knee_kHz_short", f_knee, f"{f_knee:.1f} kHz")
rec("curve_25C_20k", shape(20), f"{shape(20):.3f}")
rec("curve_25C_40k", shape(40), f"{shape(40):.3f}")
rec("curve_25C_60k_uncapped", shape(60), f"{shape(60):.3f}")
rec("curve_25C_60k_capped", min(shape(60), cap_25), f"{min(shape(60), cap_25):.3f}")
assert shape(60) > cap_25 > shape(f_knee - 1)
# first-article hot points
assert min(rhot(40), cap_hot) == RAC_LIMIT_HOT and min(rhot(60), cap_hot) == cap_hot
# losses at 28 A under the new limits
rec("loss_28A_40k_W", loss(I_CEIL, RAC_LIMIT_HOT), f"{loss(I_CEIL, RAC_LIMIT_HOT):.0f} W")
rec("loss_28A_35k_W", loss(I_CEIL, rhot(35)), f"{loss(I_CEIL, rhot(35)):.0f} W at 35 kHz")
rec("r_hot_60k_uncapped_ohm", rhot(60), f"{rhot(60):.4f} Ω")
rec("loss_28A_60k_uncapped_W", loss(I_CEIL, rhot(60)), f"{loss(I_CEIL, rhot(60)):.0f} W")
rec("loss_28A_60k_capped_W", loss(I_CEIL, cap_hot), f"{loss(I_CEIL, cap_hot):.0f} W")
assert loss(I_CEIL, cap_hot) <= P_BASIS_W + 1e-9 and loss(I_CEIL, RAC_LIMIT_HOT) <= P_BASIS_W
# F_R / R_dc derivation
rec("fr_for_rdc_100mohm", r25 / 0.100, f"{r25 / 0.100:.2f}")
rec("fr_at_target_rdc_80mohm", r25 / 0.080, f"{r25 / 0.080:.1f}")
# superseded 0.25 ohm limit, for the record
rec("old_loss_22A_40k_W", loss(I_SHIP, RAC_OLD_HOT), f"{loss(I_SHIP, RAC_OLD_HOT):.0f} W at 40 kHz")
rec("old_loss_22A_60k_W", loss(I_SHIP, RAC_OLD_HOT * 1.5**F_EXP), f"{loss(I_SHIP, RAC_OLD_HOT * 1.5**F_EXP):.0f} W at 60 kHz")
rec("old_loss_28A_40k_W", loss(I_CEIL, RAC_OLD_HOT), f"{loss(I_CEIL, RAC_OLD_HOT):.0f} W at 40 kHz")
rec("old_loss_28A_60k_W", loss(I_CEIL, RAC_OLD_HOT * 1.5**F_EXP), f"{loss(I_CEIL, RAC_OLD_HOT * 1.5**F_EXP):.0f} W at 60 kHz")
# R36
lo, hi = (loss(I_CEIL, r) for r in R36_RAC)
rec("r36_loss_28A_lo_W", lo, f"{lo:.0f}")
rec("r36_loss_28A_hi_W", hi, f"{hi:.0f}")
assert R36_RAC[1] < RAC_LIMIT_HOT and R36_RAC[1] * 1.5**F_EXP < cap_hot   # R36 passes both limits
r36_60 = R36_RAC[1] * (60 / 40) ** F_EXP
rec("r36_hot_60k_hi_ohm", r36_60, f"{r36_60:.3f} Ω")
rec("r36_loss_28A_60k_hi_W", loss(I_CEIL, r36_60), f"{loss(I_CEIL, r36_60):.0f} W at 60 kHz")
out["r36_loss_within_basis"] = hi <= P_BASIS_W and loss(I_CEIL, r36_60) <= P_BASIS_W
assert out["r36_loss_within_basis"]
# thermal equivalence with the R32 study-02 140.7 C case
eq = loss(I_SHIP, OLD_R_MAX)
rec("old_case_loss_W", eq, f"{eq:.0f} W")
assert loss(I_CEIL, RAC_LIMIT_HOT) < eq and abs(loss(I_CEIL, cap_hot) - eq) < 3
# peak current spec
spec_peak = math.ceil(SHUNT_BAND[1])
rec("peak_spec_A", spec_peak, f"{spec_peak} A peak")
rec("peak_margin_A", spec_peak - SHUNT_BAND[1], f"{spec_peak - SHUNT_BAND[1]:.2f} A")
rec("old_peak_spec_A", math.ceil(OLD_SHUNT_UPPER), f"{math.ceil(OLD_SHUNT_UPPER)} A")
rec("peak_over_envelope", spec_peak / ENVELOPE_PEAK_28, f"{spec_peak / ENVELOPE_PEAK_28:.2f}")
# firmware peak trip: min(2.17 c + 3, 62), RMS trip 1.05 c
trip = lambda c: min(PEAK_PER_RMS * c + PEAK_PICKUP, PEAK_MAX)
rec("peak_trip_22A", trip(22), f"{trip(22):.2f} A")
rec("peak_trip_28A", trip(28), f"{trip(28):.1f} A")
rec("rms_trip_28A", RMS_TRIP_K * I_CEIL, f"{RMS_TRIP_K * I_CEIL:.1f} A")
rec("effective_cap_A", (PEAK_MAX - PEAK_PICKUP) / PEAK_PER_RMS, f"{(PEAK_MAX - PEAK_PICKUP) / PEAK_PER_RMS:.1f} A")
rec("peak_trip_28A_uncapped", PEAK_PER_RMS * 28 + PEAK_PICKUP, f"{PEAK_PER_RMS * 28 + PEAK_PICKUP:.2f} A")
assert trip(28) < CT_BAND[0] < trip(28) + 3         # trip below CT band low corner
assert CT_BAND[1] < SHUNT_BAND[0] * 1.2 and SHUNT_BAND[0] > ENVELOPE_PEAK_28
# insulation levels
rec("pd_lower_V", 1.5 * U_PK, f"{1.5 * U_PK:.0f} V peak")
rec("pd_raise_V", 1.875 * U_PK, f"{1.875 * U_PK:.0f} V peak")
assert 125 < U_RMS <= 250    # IEC 60335-1 Table 17 band: reinforced PD3 IIIa = 8.0 mm (ORACLE-ANSWER Q3)
# alternate B turns (L ~ N^2)
tb = TURNS_70 * math.sqrt(80 / 70)
rec("altB_turns", tb, f"{tb:.1f} turns")
# window-top bound: x_reg across ceilings from the round-6 grids (R34-as-modelled, 70 uH / 0.50 uF)
xmax = {}
for c in (22, 24, 26, 28):
    m = 0.0
    for f in glob.glob(str(TASK05 / f"round6-full-power/outputs/grid6-d228_gap84-L70-C050-I{c}-pan*-cases.csv")):
        for r in csv.DictReader(open(f)):
            m = max(m, float(r["f_over_fres"]))
    xmax[c] = m
out["x_reg_round6_max"] = xmax
rec("x_reg_22", xmax[22], f"{xmax[22]:.3f}")
rec("x_reg_28", xmax[28], f"{xmax[28]:.3f}")
fl = json.load(open(HERE / "outputs/floor.json"))
assert max(xmax.values()) <= fl["window_top"]["x_reg_used"]
f_res_max = 60000 / fl["window_top"]["x_reg_used"]
L_min = 1 / ((2 * math.pi * f_res_max) ** 2 * fl["inputs"]["C_worst_uF"] * 1e-6) * 1e6
ratio = fl["window_top"]["kl_population_min"] / fl["window_top"]["kl_ref_cast_iron_nom"]
rec("floor_L_pop_uH", L_min, f"{L_min:.2f} µH")
rec("floor_L_ref_uH", L_min / ratio, f"{L_min / ratio:.1f} µH")

json.dump(out, open(HERE / "coil_spec_28a_check.json", "w"), indent=1, sort_keys=True)

spec = SPEC.read_text()
bad = [(k, t) for k, t in checks if t not in spec]
for k, t in checks:
    print(f"{'OK  ' if t in spec else 'MISS'} {k:28s} {t}")
assert not bad, f"values not found in spec: {bad}"
print("all", len(checks), "printed values match")
