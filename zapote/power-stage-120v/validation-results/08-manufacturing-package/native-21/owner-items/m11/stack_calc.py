"""M11: insulation requirement lookup and thermal cost of candidate HOT->PE sink stacks.

  python3 -B stack_calc.py > stack-calc.txt   (also writes stack-calc.json)

Every input carries its source. 'EST' marks an engineering estimate, not a datasheet value.

Sources (local copies, SHA-256 in RECOMMENDATION.md):
  [IPW]  Infineon IPW65R018CFD7 Rev 2.0 (2021-04-19): p.3 RthJC 0.28 max, mounting torque 60 Ncm, VISO n.a.;
         p.12 PG-TO247-3 outline (E1, D1).
  [GBJ]  Diodes GBJ2510 DS21221 Rev 11-2 (May 2025): p.1 case dielectric strength 2500 Vrms,
         #6 screw, 5.0 in-lb max; p.2 RthJC 1.0 typ per element; p.4 A 29.70-30.30, B 19.70-20.30.
  [HNK]  Henkel/Bergquist Thermal Interface Selection Guide (2017): printed p.60 breakdown table,
         p.62-63 selection tables (thickness, TO-220 test, impedance, breakdown), p.41 TIC 1000A
         (0.32 C/W TO-220 @50 psi, electrically conductive filler -> excluded near the barrier),
         p.51 HI-FLOW 300P (0.13 C-in2/W @25 psi, 5000 Vac, polyimide).
  [KYO]  Kyocera Fineceramics Europe AN216A AlN, 2023-04-03, p.1: k 150 W/mK, 14 kV/mm, er 8.6,
         CTE 4.6 ppm/K, flexural 310 MPa.
  [DOW]  DOWSIL TC-5622, Form 11-3087-01 C (2017), p.1: 4.3 W/mK, 0.06 C-cm2/W at 25 N/cm2, BLT 0.02 mm.
  [T03]  validation-results/03-loss-thermal-budget/round3 README + outputs (losses, tab area 151.2-240.1 mm2).
  [IS302] IS 302-1:2008 (= IEC 60335-1 ed. 4.x), OCR text: Table 7 (16.3), Table 15, Table 16, Table 17,
         29.1, 29.2 note 2, 29.3, Table 19 (Annex A).
"""
import json
import math

IN2 = 645.16           # mm2 per in2
TAB = (151.2, 240.1)   # [T03] TO-247 exposed metal area, mm2 (min, max); E1 x D1 less the hole
BR1_AREA = 29.70 * 19.70   # [GBJ] p.4 min outline -> 585 mm2 (rear face, optimistic as in T03)
RJC_FET = 0.28         # [IPW] p.3 max
RJC_BR1_ELEM = 1.0     # [GBJ] p.2 typ per element

# ---- losses ---------------------------------------------------------------------------------
# [T03] conduction 6.78 W/device at 21.47 A tank (typ RDS(on) 29.4 mOhm at 125 C), covered turn-off
# 0.26 W (HS) / 0.33 W (LS). Scaled to the D-? envelope ceiling of 22 A tank (I^2).
I_T03, I_ENV = 21.47, 22.0
P_cond = 6.78 * (I_ENV / I_T03) ** 2
P_HS, P_LS = P_cond + 0.26, P_cond + 0.33
# BR1: [T03] 28.36 W at 15 A sine and 1.05 V (two diodes, Iavg = 0.9 Irms). Envelope hold 11.1 A
# (DECISIONS 2026-10-08, input current), trip 12.45 A. The 15 A figure is kept as the bound.
def p_br1(i_rms):
    return 2 * 1.05 * 0.9 * i_rms
P_BR1 = {"11.1 A hold": p_br1(11.1), "12.45 A trip": p_br1(12.45), "15 A (T03 bound)": p_br1(15.0)}

# ---- interface candidates (per TO-247; ranges are the TAB area range) ------------------------
def per_area(r_in2):           # C-in2/W -> C/W over TAB (max area gives min R)
    return (r_in2 * IN2 / TAB[1], r_in2 * IN2 / TAB[0])

def cm2(r_cm2):                # C-cm2/W -> C/W
    return (r_cm2 * 100 / TAB[1], r_cm2 * 100 / TAB[0])

grease_opt = cm2(0.06)                       # [DOW] TC-5622 TDS fixture value (optimistic)
grease_cons = per_area(0.32 * 0.2)           # [HNK] TIC1000A 0.32 C/W TO-220; TO-220 test area ~0.2 in2 (EST, see note)
def aln(t_mm, k=150.0):                      # [KYO] k = 150 W/mK; 1-D, no spreading credit (conservative)
    return (t_mm * 1e-3 / (k * TAB[1] * 1e-6), t_mm * 1e-3 / (k * TAB[0] * 1e-6))

def add(*rs):
    return (sum(r[0] for r in rs), sum(r[1] for r in rs))

cands = {
    "SIL PAD K-10 0.152 mm (D-18 rejected)": dict(r=per_area(0.41), t=0.152, bd_kv=6.0, src="[HNK] p.62-63",
                                                  er=3.7, layers=1),
    "SIL PAD 1500ST 0.203 mm": dict(r=per_area(0.23), t=0.203, bd_kv=3.0, src="[HNK] p.62", er=None, layers=1),
    "HI-FLOW 300P 0.102-0.127 mm (1 mil coat)": dict(r=per_area(0.13), t=0.102, bd_kv=5.0, src="[HNK] p.51", er=None, layers=1),
    "AlN 1.0 mm + 2x grease": dict(r=add(aln(1.0), grease_opt, grease_opt), r_cons=add(aln(1.0), grease_cons, grease_cons),
                                   t=1.0, bd_kv=14.0 * 1.0, src="[KYO] + [DOW]/[HNK]", er=8.6, layers=1),
    "AlN 2.0 mm + 2x grease (RECOMMENDED)": dict(r=add(aln(2.0), grease_opt, grease_opt), r_cons=add(aln(2.0), grease_cons, grease_cons),
                                                 t=2.0, bd_kv=14.0 * 2.0, src="[KYO] + [DOW]/[HNK]", er=8.6, layers=1),
    "Al2O3 2.0 mm (k 24 EST) + 2x grease": dict(r=add(aln(2.0, 24.0), grease_opt, grease_opt),
                                               r_cons=add(aln(2.0, 24.0), grease_cons, grease_cons),
                                               t=2.0, bd_kv=None, src="EST k=24 W/mK (96 % alumina class)", er=None, layers=1),
}

EPS0 = 8.854e-12
def cap_pf(er, t_mm):
    return (EPS0 * er * TAB[0] * 1e-6 / (t_mm * 1e-3) * 1e12, EPS0 * er * TAB[1] * 1e-6 / (t_mm * 1e-3) * 1e12)

# ---- requirement lookup [IS302] --------------------------------------------------------------
REQ = {
    "rated voltage": "120 V (Table 15 row ii: >50 and <=150 V) -> rated impulse 1500 V, OVC II",
    "working voltage HOT->PE (normal)": "<= 99 V rms / 198 V pk at 127 V + 10 % (ORACLE-ANSWER Q2); |rail-PE| <= Vbus + Vf",
    "clearance basic": "Table 16 @1500 V: 0.5 mm, PD3 footnote 0.8 mm; +0.5 mm (29.1, assembly-affected) -> 1.3 mm",
    "clearance reinforced": "29.1.3 next step 2500 V: 1.5 mm; +0.5 mm (29.1) -> 2.0 mm; with 400 V bus (29.1.5: +202 V over 198 V pk) "
                            "interpolate 2702 V -> 1.70 mm + 0.5 = 2.2 mm",
    "creepage basic": "Table 17 row iii (>125-250 V) PD3: I 3.2 / II 3.6 / IIIa 4.0 mm; row iv (>250-400 V) PD3 IIIa 6.3 mm",
    "creepage reinforced": "29.2.3: 2x -> 8.0 mm (row iii, IIIa) = D5-BASIS floor; 12.6 mm if 400 V were a working voltage",
    "creepage ceramic": "Table 17 note 2: glass/ceramic that do not track -> creepage need not exceed clearance",
    "solid reinforced": "29.3: (a) >= 2 mm thick (29.3.1), or (b) >= 3 layers each passing the supplementary 16.3 test (29.3.2), "
                        "or (c) thermal assessment + 16.3 test (29.3.3)",
    "solid supplementary": "29.3.1 >= 1 mm, or >= 2 layers (29.3.2), or 29.3.3",
    "type test 16.3 (Table 7)": "basic 1250 V; supplementary 1250 V (<=150 V) / 1750 V (>150-250 V working); reinforced 2500 V (<=150 V) / "
                                "3000 V (>150-250 V working) / 2.4U + 2400 V above 250 V; 50 Hz, 1 min",
    "routine (Annex A, Table 19)": "rated <=150 V: basic 800 V, double/reinforced 2000 V, 1 s; dc alternative 1.5x",
}
def table7_reinforced(u):
    return 2500 if u <= 150 else (3000 if u <= 250 else 2.4 * u + 2400)

# ---- junction screen --------------------------------------------------------------------------
TA = 50.0              # D-18 design inlet temperature
RSA = 0.237            # R25 airflow model at 22.7 CFM (BENCH-PLAN P2); D-18 hard limit 0.29
R_PEDESTAL = None      # filled below
# Spreader bar ("pedestal"): 8 mm 6061-class Al (k 167 W/mK, EST) over 117 x 47.4 mm, plus one greased
# Al-Al joint at the conservative 0.413 C-cm2/W.
ped_area_cm2 = 11.7 * 4.74
R_PEDESTAL = 0.008 / (167 * ped_area_cm2 * 1e-4) + 0.413 / ped_area_cm2


def main():
    out = {"losses_W": {"FET_HS_22A": P_HS, "FET_LS_22A": P_LS, "BR1": P_BR1}, "candidates": {}, "requirements": REQ}
    print("Losses at 22 A tank: HS %.2f W, LS %.2f W; BR1 %s" % (P_HS, P_LS, {k: round(v, 2) for k, v in P_BR1.items()}))
    print("Grease per TO-247 interface: TC-5622 TDS %.3f-%.3f C/W; TIC1000A-proxy %.3f-%.3f C/W" % (*grease_opt, *grease_cons))
    print("Pedestal + joint: %.4f C/W (shared)" % R_PEDESTAL)
    p_total = 2 * P_HS + 2 * P_LS + P_BR1["15 A (T03 bound)"]
    ts = TA + (RSA + R_PEDESTAL) * p_total
    print("Sink load %.1f W; Ts = %.1f C at RSA %.3f + pedestal" % (p_total, ts, RSA))
    for name, c in cands.items():
        r_lo, r_hi = c.get("r_cons", c["r"])[0], c.get("r_cons", c["r"])[1]
        r_opt = c["r"]
        tj = ts + P_LS * (RJC_FET + r_hi)
        row = {"R_cs_opt_C_per_W": [round(v, 3) for v in r_opt],
               "R_cs_cons_C_per_W": [round(v, 3) for v in (r_lo, r_hi)],
               "meets_0p7": r_hi <= 0.7, "thickness_mm": c["t"], "breakdown_kV": c["bd_kv"], "source": c["src"],
               "Tj_LS_worst_C": round(tj, 1)}
        if c.get("er"):
            row["C_tab_PE_pF"] = [round(v, 1) for v in cap_pf(c["er"], c["t"])]
        row["29.3_route"] = ("29.3.1 (a): >= 2 mm" if c["t"] >= 2.0 else "29.3.3 (c) only: single thin layer, lab test")
        out["candidates"][name] = row
        print(f"{name:45s} Rcs opt {r_opt[0]:.3f}-{r_opt[1]:.3f}  cons {r_lo:.3f}-{r_hi:.3f}  <=0.7:{r_hi <= 0.7!s:5s}  "
              f"Tj_LS {tj:5.1f} C  C {row.get('C_tab_PE_pF', '-')} pF  {row['29.3_route']}")
    # BR1: case (basic, 2500 Vrms) + 0.5 mm gap filler (EST k 3 W/mK) + AlN 2 mm + grease, over 585 mm2
    r_br1 = (0.5e-3 / (3.0 * BR1_AREA * 1e-6) + 2e-3 / (150 * BR1_AREA * 1e-6) + 0.413 / (BR1_AREA / 100))
    for k, p in P_BR1.items():
        tj = ts + p * r_br1 + (p / 4) * RJC_BR1_ELEM
        print(f"BR1 {k}: Rcs {r_br1:.3f} C/W, Tj {tj:.1f} C (Tj max 150 C)")
    out["BR1_Rcs_C_per_W"] = r_br1
    out["Ts_C"] = ts
    out["R_pedestal_C_per_W"] = R_PEDESTAL
    out["clamp_force_N_per_TO247"] = {"25 N/cm2 (DOW test)": [round(2.5 * a / 10, 1) for a in TAB],
                                      "50 psi (HNK test)": [round(0.3447 * a, 1) for a in TAB]}
    print("Clamp force for 25 N/cm2: %s N; for 50 psi: %s N" % tuple(out["clamp_force_N_per_TO247"].values()))
    out["hipot"] = {"type_reinforced_V": {u: table7_reinforced(u) for u in (140, 198, 250, 400)},
                    "routine_reinforced_V_ac_1s": 2000, "routine_dc_V_1s": 3000}
    print("Table 7 reinforced test V for U = 140/198/250/400 V:", out["hipot"]["type_reinforced_V"])
    # AlN CTE slip over the longest tile (76 mm) for a 50 K rise, vs 6061 (23.6 ppm/K EST)
    slip = 76 * (23.6 - 4.6) * 1e-6 * 50
    out["tile_B_slip_mm_50K"] = slip
    print("Tile B (76 mm) differential expansion vs Al over 50 K: %.3f mm" % slip)
    # HF field in the insulator, low-side tab (switch node), 198 V pk-pk at 33-40 kHz, 470 V die transient
    for t in (0.102, 0.152, 1.0, 2.0):
        print(f"  E_pk at 470 V across {t} mm: {470 / t / 1000:.2f} kV/mm")
    json.dump(out, open("stack-calc.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
