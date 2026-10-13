#!/usr/bin/env python3 -I
"""G01 candidate filter evaluation: calls the committed s19b model (not edited) with candidate parts.

Usage: python3 -I emi_g01.py [--step KHZ] [--only NAME[,NAME]] [--sens]
Writes emi_g01_results.json next to this file.  Read-only on ../../07-conducted-emi/s19b.
Margin definition and PASS rule (>= 6 dB nominal and in every one-at-a-time sensitivity) are s19b's.
"""
import importlib.util, json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
S19B = HERE.parents[1] / "07-conducted-emi/s19b/emi_s19b.py"
sys.argv_backup = list(sys.argv)
spec = importlib.util.spec_from_file_location("emi_s19b", S19B)
m = importlib.util.module_from_spec(spec)
sys.modules["emi_s19b"] = m
spec.loader.exec_module(m)
m.COPPER = Path("/nonexistent")          # force the committed read-only fallback (never rewrite s19b/inputs)
import numpy as np

STEP = 2.0
for i, a in enumerate(sys.argv):
    if a == "--step": STEP = float(sys.argv[i + 1])
ONLY = None
for i, a in enumerate(sys.argv):
    if a == "--only": ONLY = sys.argv[i + 1].split(",")
SENS = "--sens" in sys.argv

REP = [(170.0, "pan_22A"), (198.0, "pan_28A"), (198.0, "nopan_22A")]
FS = list(np.arange(35000, 60001, STEP * 1000.0))

cm = m.cm_capacitances()
NOM = m.nominal_params(cm)

def margin(over, cfgs=REP, fs_list=FS, edge=1.0):
    """min margin over cfgs/fs: returns dict lo (9-150k QP), hi (150k-30M), min, CM/DM attribution of the worst."""
    over = dict(over)
    module = over.pop("_module", True)
    p = {**NOM, **over}
    res = {}
    worst_all = None
    for vc, cn in cfgs:
        trs = {}
        for fs in fs_list:
            h = np.arange(1, int(30e6 / fs) + 1)
            t = m.transfers({**p, **m.tank_for(vc, m.case_at(vc, m.CASES[cn], fs), fs)}, module, h * fs)
            t["h"] = h
            trs[fs] = t
        rows = m.aggregate(trs, None, vc, m.CASES[cn], fs_list, edge, 1.0)
        lo, hi = m.worst(rows, "terminal", "lo"), m.worst(rows, "terminal", "hi")
        for tag, w in (("lo", lo), ("hi", hi)):
            if w and (worst_all is None or w["margin_dB"] < worst_all["margin_dB"]):
                worst_all = dict(w, band=tag, cfg=f"{int(vc)}V/{cn}")
    return worst_all

# ---- candidate definitions (override dicts on the s19b nominal; names are the proposal ids)
# CY = board Y (C3/C4); CYADD + CYHF = module Y (4.7 + 2.2 nF); LCM/LDM = L1; LCMADD/LDMADD/LNEW = module choke / DM inductors
def cand():
    c = {}
    c["B0_baseline_s19b_nominal"] = {}
    # Y-only reductions (no compensation)
    c["Y1_board_Y_removed"] = {"CY": 1e-15}
    c["Y2_module_Y_2n2_only"] = {"CYADD": 1e-15}
    c["Y3_module_Y_4n7_only"] = {"CYHF": 1e-15}
    c["Y4_board_1n0_module_2n2"] = {"CY": 1.0e-9, "CYADD": 1e-15}
    c["Y5_board_2n2_module_0"] = {"CYADD": 1e-15, "CYHF": 1e-15}
    c["Y6_board_0_module_4n7"] = {"CY": 1e-15, "CYHF": 1e-15}
    # bigger module CM choke (REC2 = 3.2 mH with DM leakage 36 uH) combined with Y cuts
    big = {"LCMADD": 3.2e-3, "LDMADD": 36e-6, "LNEW": 32e-6}      # s19b REC2 (DM total 36+64 = 100 uH)
    c["K0_REC2_3p2mH_module_choke_full_Y"] = dict(big)
    c["K1_REC2_board_Y_removed"] = {**big, "CY": 1e-15}
    c["K2_REC2_module_Y_2n2_only"] = {**big, "CYADD": 1e-15}
    c["K3_REC2_board_Y_removed_module_2n2"] = {**big, "CY": 1e-15, "CYADD": 1e-15}
    c["K4_REC2_board_Y_removed_module_4n7"] = {**big, "CY": 1e-15, "CYHF": 1e-15}
    c["K5_REC2_all_Y_0"] = {**big, "CY": 1e-15, "CYADD": 1e-15, "CYHF": 1e-15}
    big2 = {"LCMADD": 6.4e-3, "LDMADD": 72e-6, "LNEW": 14e-6}
    c["K6_6p4mH_module_choke_Y_2n2_only"] = {**big2, "CY": 1e-15, "CYADD": 1e-15}
    # L1 alternates (board choke), module as specified
    c["L1_SC-20-201_2mH_leak20uH"] = {"LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3}
    c["L1_SC-20-201_2mH_leak10uH"] = {"LCM": 2.0e-3, "LDM": 10e-6, "RCH": 10e-3}
    c["L1_SC-20-104_1mH_leak10uH"] = {"LCM": 1.0e-3, "LDM": 10e-6, "RCH": 8e-3}
    c["L1_WE-CMB_1p3mH_leak13uH"] = {"LCM": 1.3e-3, "LDM": 13e-6, "RCH": 4.7e-3}
    c["L1_removed_module_only"] = {"LCM": 1e-9, "LDM": 0.0, "RCH": 1e-3}
    # combined: L1=SC-20-201, module choke 3.2 mH, Y cut
    c["C1_SC201_REC2_board_Y_removed_module_2n2"] = {**big, "LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3, "CY": 1e-15, "CYADD": 1e-15}
    c["C2_SC201_REC2_board_Y_removed_module_4n7"] = {**big, "LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3, "CY": 1e-15, "CYHF": 1e-15}
    c["C3_SC201_REC2_board_Y_1n0_module_2n2"] = {**big, "LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3, "CY": 1.0e-9, "CYADD": 1e-15}
    # ---- batch 2: lowest-Y combinations with the 3.2 mH module choke (Y in nominal nF/line = board + CYADD + CYHF)
    E = 1e-15
    sc201 = {"LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3}
    we13 = {"LCM": 1.3e-3, "LDM": 13e-6, "RCH": 4.7e-3}
    c["D1_REC2_L1stock_board1p0_mod2p2_Y3.2"] = {**big, "CY": 1.0e-9, "CYADD": E}
    c["D2_REC2_L1stock_board0_mod1p0+2p2_Y3.2"] = {**big, "CY": E, "CYADD": 1.0e-9}
    c["D3_REC2_SC201_board0_mod1p0+2p2_Y3.2"] = {**big, **sc201, "CY": E, "CYADD": 1.0e-9}
    c["D4_REC2_SC201_board0_mod3p3_Y3.3"] = {**big, **sc201, "CY": E, "CYADD": 3.3e-9, "CYHF": E}
    c["D5_REC2_SC201_board1p0_mod1p0_Y2.0"] = {**big, **sc201, "CY": 1.0e-9, "CYADD": E, "CYHF": 1.0e-9}
    c["D6_REC2_SC201leak10_board1p0_mod2p2_Y3.2"] = {**big, **sc201, "LDM": 10e-6, "CY": 1.0e-9, "CYADD": E}
    c["D7_REC2_WE13_board1p0_mod2p2_Y3.2"] = {**big, **we13, "CY": 1.0e-9, "CYADD": E}
    c["D8_REC2_SC201_board2p2_mod1p0_Y3.2"] = {**big, **sc201, "CYADD": E, "CYHF": 1.0e-9}
    c["D9_REC2_SC201_board1p0_mod1p0+2p2_Y4.2"] = {**big, **sc201, "CY": 1.0e-9, "CYADD": 1.0e-9}
    c["D10_REC2_WE13_board0_mod4p7_Y4.7"] = {**big, **we13, "CY": E, "CYHF": E}
    # ---- batch 3: F10 DM-inductor sweep on the lowest-Y passing combination (C3) - module DM inductor value per leg
    for ln in (0, 10, 20, 32, 41):
        c[f"F10_C3_LNEW_{ln}uH"] = {**big, **sc201, "CY": 1.0e-9, "CYADD": E, "LNEW": ln * 1e-6}
    for ln in (0, 10, 20, 32):
        c[f"F10_K2_LNEW_{ln}uH"] = {**big, "CYADD": E, "LNEW": ln * 1e-6}
    # ---- batch 4: module choke = real stocked part (Kemet SC-20-201, 2.0 mH, 20 uH leakage assumed 1 %, 10 mohm)
    mod201 = {"LCMADD": 2.0e-3, "LDMADD": 20e-6, "RCMADD": 10e-3, "LNEW": 41e-6}
    c["M1_mod201_L1stock_board2p2_modHF2p2_Y4.4"] = {**mod201, "CYADD": E}
    c["M2_mod201_L1SC201_board2p2_modHF2p2_Y4.4"] = {**mod201, **sc201, "CYADD": E}
    c["M3_mod201_L1SC201_board1p0_modHF2p2_Y3.2"] = {**mod201, **sc201, "CY": 1.0e-9, "CYADD": E}
    c["M4_mod201_L1WE13_board2p2_modHF2p2_Y4.4"] = {**mod201, **we13, "CYADD": E}
    c["M5_mod201_L1stock_board2p2_mod4p7_Y6.9"] = {**mod201, "CYHF": E}
    c["M6_mod201_L1SC201_board2p2_mod4p7_Y6.9"] = {**mod201, **sc201, "CYHF": E}
    return c

def sens_set(over):
    """One-at-a-time sensitivities (s19b definitions applied to the candidate's own values)."""
    p = {**m.BASE, **NOM, **over}
    s = {}
    s["Y-20%"] = {"CY": p["CY"] * 0.8, "CYADD": p["CYADD"] * 0.8, "CYHF": p["CYHF"] * 0.8}
    s["Y ESL x3"] = {"ESLY": 45e-9, "ESLYADD": 45e-9, "ESLYHF": 30e-9}
    s["chokes -30%"] = {"LCM": p["LCM"] * 0.7, "LCMADD": p["LCMADD"] * 0.7}
    s["choke winding C x2"] = {"CCH": p["CCH"] * 2, "CCMADD": p["CCMADD"] * 2}
    s["X caps -20%"] = {"CX": 0.8e-6, "CXIN": 1.76e-6, "CXNEW": 3.76e-6, "CDAMP": 3.76e-6}
    s["coil+board 51 pF"] = {"CCOILA": 25.7e-12, "CCOILB": 25.3e-12}
    s["module DM 80 uH"] = {"LNEW": p["LNEW"] * 31 / 41}
    s["PE bond 200 nH"] = {"LPE": 200e-9}
    return s

if __name__ == "__main__":
    out_path = HERE / "emi_g01_results.json"
    out = json.load(open(out_path)) if out_path.exists() else {}
    for name, over in cand().items():
        if ONLY and name not in ONLY: continue
        r = {"override": {k: v for k, v in over.items()}, "nominal": margin(over)}
        if SENS:
            r["sens"] = {}
            for sn, so in sens_set(over).items():
                r["sens"][sn] = margin({**over, **so})
            r["sens_min_dB"] = min(v["margin_dB"] for v in r["sens"].values())
            r["INFO_pan_earthed_91pF"] = margin({**over, "CCOILA": 46.2e-12, "CCOILB": 45.2e-12})
        out[name] = r
        w = r["nominal"]
        print(f"{name:52s} nominal {w['margin_dB']:6.1f} dB  ({w['band']}, {w['cfg']}, f={w['f_hz']/1e3:.0f} kHz, CM {w['CM_dBuV']:.0f}/DM {w['DM_dBuV']:.0f})"
              + (f"  sens_min {r['sens_min_dB']:.1f}" if SENS else ""), flush=True)
        json.dump(out, open(out_path, "w"), indent=1, default=float)
