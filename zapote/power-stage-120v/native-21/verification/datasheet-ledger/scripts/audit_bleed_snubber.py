#!/usr/bin/env python3
"""Stress arithmetic behind the ledger entries 1206W4F1003T5E (R1/R2) and CC1206JKNPOCBN102 (C12/C13/C19/C20; GRM31A5C3A102JW01D until stage 43).

Stdlib only; run `python3 -I audit_bleed_snubber.py`. Every input is cited in ledger.json; this file only does the
arithmetic so the ledger numbers are reproducible.
"""
import math

# ---- R1/R2 X-capacitor bleed pair, two 100 k 1 % in series across the mains after F1
V_LINE = 139.7                      # Vrms, 127 V + 10 % (DECISIONS.md:306)
R_NOM, R_LOW = 100e3, 99e3          # 1 % tolerance, low corner raises power
V_RES = V_LINE / 2                  # two equal resistors, V per resistor
P_RES_MW = V_RES ** 2 / R_LOW * 1e3
P_RATED_70, T_ZERO = 250.0, 155.0   # mW at 70 C, derates linearly to 0 at 155 C (UniOhm V.3 p.5 fig. 1)
T_LOCAL = 85.0                      # C, enclosure ambient bound (DECISIONS.md:457)
P_RATED_LOCAL = P_RATED_70 * (T_ZERO - T_LOCAL) / (T_ZERO - 70.0)
RCWV = math.sqrt(0.25 * R_NOM)      # sqrt(P*R), UniOhm V.3 p.5
V_OVERLOAD = min(2.5 * RCWV, 400.0)  # 1206 max overload voltage 400 V (p.5)
V_CLAMP_RV1 = 455.0                 # V, TMOV20RP175E Vc at 100 A (parts.ato:85)
V_SURGE_RES = V_CLAMP_RV1 / 2
# discharge: 198 V crest to 34 V, C1+C2 = 2 uF +20 %, R +1 % (calc_discharge.py)
tau = 2 * R_NOM * 1.01 * 2e-6 * 1.2
t34 = tau * math.log(140 * math.sqrt(2) / 34.0)

# ---- snubbers
C = 1e-9                            # F
DVDT = 95e9                         # V/s, modelled hard edge (DECISIONS.md:845)
DV = 286.0                          # V, static OVP bus (PROPOSALS.md:82)
F_SW = 60e3                         # Hz, control-window maximum (DECISIONS.md:450)
I_PK = C * DVDT
T_EDGE = DV / DVDT
I_RMS = math.sqrt(2 * F_SW * I_PK ** 2 * T_EDGE)  # two edges per cycle, rectangular pulse bound

if __name__ == "__main__":
    print(f"R pair: V/res {V_RES:.2f} Vrms; P/res {P_RES_MW:.1f} mW (R 99k); RCWV {RCWV:.1f} V; overload {V_OVERLOAD:.1f} V")
    print(f"R pair: rated at {T_LOCAL:.0f} C = {P_RATED_LOCAL:.1f} mW; ratio {P_RES_MW / P_RATED_LOCAL:.4f}")
    print(f"R pair: surge V/res {V_SURGE_RES:.1f} V vs overload -> {V_SURGE_RES / V_OVERLOAD:.4f}; Vc at which pair hits overload {2 * V_OVERLOAD:.0f} V")
    print(f"R pair: tau {tau:.4f} s, t(198 V->34 V) {t34:.3f} s")
    print(f"C: I_pk = C dv/dt = {I_PK:.0f} A for {T_EDGE * 1e9:.2f} ns; I_rms bound at {F_SW / 1e3:.0f} kHz = {I_RMS:.2f} A")
    for name, v in (("die VDS", 490), ("bus no-clamp worst", 451), ("static OVP", 286)):
        print(f"C: {name} {v} V / 1000 V = {v / 1000:.3f}")
