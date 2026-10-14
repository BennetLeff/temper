#!/usr/bin/env python3
"""D-22 rev B: the chosen DM inductor (Wurth 74437636355602, 49.7 uH at 21 A) on the low-leakage filter basis.

    python3 -I validation-results/12-decisions/d22-dm-inductor/revb_check.py   # -> revb_check.json, exit 1 if a control fails

Basis = c29 design C29-B as an OFF-BOARD module (the model has no harness, c29 README s3, so the network is identical):
TDK L1 1.6 mH on the board, module stage-1 CM choke 3.6 mH nanocrystalline (KEMET SCF39XV, 4.2 mohm, 1 % leakage
assumed), all line-to-PE Y at C3/C4 = 2.2 nF per line (module Y deleted), D-22's X caps and damping kept.
Uses c29_emi.py's helpers and run_full() unchanged (imported).
Controls: C29-B with LNEW 41 uH reproduces c29_emi_final.json's figure for that case to 0.01 dB.
"""
import importlib.util, json, sys
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("c29_emi", HERE.parents[1] / "11-candidates/c29-inlet-filter/c29_emi.py")
c = importlib.util.module_from_spec(spec)
sys.modules["c29_emi"] = c
spec.loader.exec_module(c)

WE = {"LNEW": 49.7e-6, "RNEW": 3.19e-3 * 1.1, "CPNEW": 1.0 / ((2 * 3.14159265 * 7.41e6) ** 2 * 56e-6)}  # SURVEY.md #1
B = {**c.TDK, **c.stage1(3.6e-3, r=4.2e-3), **c.yset(2.2, "board")}
CTL = "C29-B2.2_L1tdk_S1nc3.6_LNEW41"
CASES = {CTL: {**B, "LNEW": 41e-6},
         "revB_WE56uH@21A_S1nc3.6_Y2.2": {**B, **WE},
         "revB_WE56uH@21A_S1nc3.6_Y2.2_L-20pct": {**B, **WE, "LNEW": 49.7e-6 * 0.8},
         "revB_WE56uH@21A_S1nc3.6_leak0.3pct_Y2.2": {**B, **WE, "LDMADD": 10.8e-6}}

if __name__ == "__main__":
    with Pool(4) as p:
        res = dict(p.map(c.run_full, list(CASES.items())))
    ref = json.load(open(HERE.parents[1] / "11-candidates/c29-inlet-filter/c29_emi_final.json"))[CTL]
    fails = []
    for k in ("nominal",):
        if abs(res[CTL][k]["margin_dB"] - ref[k]["margin_dB"]) > 0.01:
            fails.append(f"control {k}: {res[CTL][k]['margin_dB']} vs {ref[k]['margin_dB']}")
    if abs(res[CTL]["sens_min_dB"] - ref["sens_min_dB"]) > 0.01:
        fails.append(f"control sens_min: {res[CTL]['sens_min_dB']} vs {ref['sens_min_dB']}")
    out = {k: {"nominal_dB": round(v["nominal"]["margin_dB"], 2), "nominal_0p5kHz_dB": round(v["nominal_0p5kHz"]["margin_dB"], 2),
               "sens_min_dB": round(v["sens_min_dB"], 2), "sens_min_case": v["sens_min_case"],
               "pan_earthed_INFO_dB": round(v["INFO_pan_earthed_91pF"]["margin_dB"], 2), "verdict": v["verdict_6dB"]}
           for k, v in res.items()}
    out["control_fails"] = fails
    (HERE / "revb_check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    raise SystemExit(1 if fails else 0)
