#!/usr/bin/env python3
"""Stage 15: FET, bank, CT and sense-chain checks for the candidate OCP bands at the 28 A ceiling.

ASSUMED / bounded calculation. Reads out/ocp_bands.json (run ocp_bands.py first) and round-6 outputs.
Datasheet constants (cite page; the PDFs are not committed):
  IPW65R018CFD7, Infineon Final Data Sheet Rev. 2.0, 2021-04-19:
    p.3 Table 2: I_D,pulse 495 A (T_C 25 C, t_p limited by T_j,max); T_j max 150 C.
    p.4 Table 3: R_thJC 0.28 C/W.
    p.5 Table 4: R_DS(on) 0.015 typ / 0.018 max at 25 C; 0.033 typ at 150 C (max not given -> x 18/15 here).
    p.7 Diagram 3 (SOA, T_C 80 C) and Diagram 4 (Z_thJC): READ BY EYE, conservative side (constants below).
  TDK B32654A1104K000: 1600 Vdc / 500 Vac (DECISIONS.md 2026-10-09 bank entry; B3265*A data sheet pp. 3, 22).
  CT T1 (CST3015-100ED): 638 V.us, 1.5 ohm DCR, 1:100, 88 A thermal reference (02-protection-timing/scripts/detector_chain.py).
Delay terms: 02-protection-timing README (shunt front end ~555 ns past its own threshold at 3 MA/s; native-13 SPICE)
and D-31 out-D31/README.md (chain 573.2 ns after the native-20 DIS stiffening; Q1/Q4 charge bound 1.17 us vs
181.6 ns allocation). Basis-A hot Tj from round-6 board-side-fets.csv.
usage: python3 fault_check.py [UNIT]  -> out/fault_check.json
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
R6 = UNIT / "validation-results/05-resonant-tank-envelope/round6-full-power/outputs"

# ---- IPW65R018CFD7 (Rev 2.0)
ID_PULSE = 495.0            # p.3
TJ_MAX = 150.0              # p.3
RTH_JC = 0.28               # p.4
RDS_150_MAX = 0.033 * 18 / 15   # p.5 typ at 150 C scaled by the 25 C max/typ ratio (estimate)
ZTH_100US = 0.02            # p.7 Diagram 4, single pulse at 1e-4 s: read <= 0.02 C/W (by eye, upper side)
SOA_1US_400V_A = 100.0      # p.7 Diagram 3 (T_C 80 C): 1 us line at 400 V read >= 100 A (by eye, lower side)
SOA_TC = 80.0
SURVIVAL_MAX_TESTED_A = 330.0   # D-31 survival.md / survival-short.md (die VDS <= 350 V)
VDS_DIE_MAX = 350.0             # D-31, 60-330 A
T_SW_OFF = 50e-9            # assumed turn-off V/I overlap (Table 5 t_f 6 ns typ at 58 A, R_G 1.8 ohm; x8 margin)

# ---- tank (round-6 MC basis: L0 66.5 uH installed +/-10 %, bank 0.50 uF +/-10 %)
L_NOM, C_NOM = 66.5e-6, 0.50e-6
L_MIN, L_MAX, C_MIN = L_NOM * 0.9, L_NOM * 1.1, C_NOM * 0.9
F_RES_MIN = 1 / (2 * math.pi * math.sqrt(L_MAX * C_NOM * 1.1))
BANK_VR = 1600.0
BUS = {"198 V (140 V line crest)": 198.0, "280 V (OVP screen, D-31)": 280.0}

# ---- delays
T_FRONT = 555e-9            # shunt comparator, past its own threshold at 3 MA/s (task 02 SPICE, native-13)
T_CHAIN = 573.2e-9          # comparator out -> DIS complete (D-31 after R8/R16 330 ohm)
T_Q_EXTRA = 1.17e-6 - 181.6e-9   # Q1/Q4 datasheet-charge bound minus its allocation (D-31 limits)
T_GATE = 150e-9             # FET gate discharge (task 02 assumption)
T_D = T_FRONT + T_CHAIN + T_Q_EXTRA + T_GATE

# ---- CT
CT_VT, CT_RSEC, CT_RB, CT_N, CT_RATED = 638e-6, 1.5, 1.5, 100, 88.0


def ct_flux_vus(i_pk, f):
    return 2 * (i_pk / CT_N * (CT_RSEC + CT_RB)) / (2 * math.pi * f) * 1e6


def main():
    ob = json.loads((HERE / "out/ocp_bands.json").read_text())
    pk28 = ob["envelope_peak_A"]["28"]
    fets = list(csv.DictReader(open(R6 / "board-side-fets.csv")))
    tj_hot = max(float(r["A_tj_max_C"]) for r in fets if float(r["I_tank_A"]) == 28.0)
    z0_max = math.sqrt(L_MAX / C_MIN)
    want = {(12400, 11700): "today 12.4k/11.7k", (12600, 11700): "R34 12.6k (E192), R35 kept",
            (12700, 11700): "R34 12.7k (E96), R35 kept", (11300, 10500): "11.3k/10.5k (E96 pair)"}
    cands = [dict(r, label=want[(round(r["R34"]), round(r["R35"]))]) for r in ob["shunt_candidates"] if (round(r["R34"]), round(r["R35"])) in want]
    ct = next(r for r in ob["ct_candidates"] if round(r["R43"]) == 2210)
    rows = []
    for c in cands:
        lo, hi = c["band_after_bound_A"]
        for bl, vb in BUS.items():
            dA = vb / (math.pi * L_MIN * F_RES_MIN)          # max amplitude growth per half cycle at resonance
            didt = (vb + z0_max * (hi + dA)) / L_MIN          # coil slope bound with V_C <= Z0 * A
            over = min(dA, didt * T_D)
            i_off = hi + over
            p_avg = 0.5 * i_off ** 2 * RDS_150_MAX * 0.5      # half-sine, one device conducts half the time
            dtj = p_avg * ZTH_100US
            tc_hot = tj_hot                                   # T_C <= T_j (bound)
            e_soa = 400 * SOA_1US_400V_A * 1e-6 * (TJ_MAX - tc_hot) / (TJ_MAX - SOA_TC)
            e_off = 0.5 * VDS_DIE_MAX * i_off * T_SW_OFF
            rows.append({"divider": c["label"], "bus": bl, "band_A": [lo, hi], "t_d_us": round(T_D * 1e6, 3),
                         "dA_halfcycle_A": round(dA, 1), "didt_bound_A_per_us": round(didt * 1e-6, 1),
                         "I_off_max_A": round(i_off, 1), "ID_pulse_margin_x": round(ID_PULSE / i_off, 2),
                         "within_D31_survival_range": i_off <= SURVIVAL_MAX_TESTED_A,
                         "dTj_100us_K": round(dtj, 1), "Tj_after_C": round(tj_hot + dtj, 1),
                         "E_off_est_mJ": round(e_off * 1e3, 2), "E_1us_SOA_derated_mJ": round(e_soa * 1e3, 2),
                         "bank_Vpk_no_growth_V": round(z0_max * hi), "bank_Vpk_with_growth_V": round(z0_max * (hi + dA)),
                         "bank_no_growth_ok": z0_max * hi <= BANK_VR})
    # single fault (CT trips): CT band high corner
    ct_hi = ct["pos_band_A"][1]
    ct_rows = {"CT_band_A": ct["pos_band_A"], "bank_Vpk_at_CT_hi_V": round(z0_max * ct_hi),
               "flux_Vus_59A_35k": round(ct_flux_vus(pk28, 35e3), 1),
               "flux_Vus_CT_hi_35k": round(ct_flux_vus(ct_hi, 35e3), 1),
               "flux_Vus_160A_33k": round(ct_flux_vus(160.0, 33e3), 1), "flux_limit_Vus": CT_VT * 1e6,
               "ct_sense_mon_V_at_CT_hi": round(1.65 + ct_hi * CT_RB / CT_N, 3),
               "v3v3_min_V": 3.135, "T1_rms_ratio_28A": round(28 / CT_RATED, 3)}
    sense = {"ct_mon_ADC_V_at_62A": round(1.65 + 62 * 0.015, 3), "ct_mon_ADC_max_V": 2.85,
             "ct_mon_ADC_range_A": round((2850 - 1650) / 15.0, 1),
             "rms_chain_V_at_crest_1.05x28A": round(1.05 * 28 * math.sqrt(2) * 0.060, 3),
             "rms_chain_fullscale_V_min": 3.135, "ct_mon_adc_accuracy_A": round(50 / 15, 2)}
    res = {"status": "ASSUMED / bounded calc; datasheet curve reads are by eye", "tj_hot_basisA_28A_C": tj_hot,
           "z0_max_ohm": round(z0_max, 3), "f_res_min_hz": round(F_RES_MIN), "t_d_us": round(T_D * 1e6, 3),
           "shunt": rows, "ct": ct_rows, "sense": sense}
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/fault_check.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "shunt"}, indent=1))
    hdr = ["divider", "bus", "band_A", "I_off_max_A", "ID_pulse_margin_x", "Tj_after_C", "E_off_est_mJ",
           "E_1us_SOA_derated_mJ", "bank_Vpk_no_growth_V", "bank_Vpk_with_growth_V"]
    for r in rows:
        print(" | ".join(str(r[h]) for h in hdr))


if __name__ == "__main__":
    main()
