#!/usr/bin/env python3 -I
"""C29 EMI: can an on-board inlet filter with a leakage-limited Y budget keep the conducted-EMI margin >= 6 dB?

Calls the committed, unmodified s19b model (07-conducted-emi/s19b/emi_s19b.py) through g01's wrapper
(11-candidates/g01-mains/emi_g01.py: margin(), sens_set(); imported, never run as __main__, so neither file is written).
Margin = limit - predicted line (CW-equivalent at the line crest); limit = 47 CFR 18.307(a) induction cooking,
9-150 kHz QP (110 dBuV < 50 kHz, 90 -> 80 dBuV log 50-150 kHz), 150 kHz-30 MHz QP/AV (66-56 / 56-46 dBuV ...);
fs 35-60 kHz; configs 170 V/22 A pan, 198 V/28 A pan, 198 V/22 A no-pan (emi_s19b.py:41-56, 724-731).
PASS rule (s19b README sec. 1): >= 6 dB nominal and in every one-at-a-time sensitivity.

On-board = the model's 'module' stage (inlet side of L1).  The model has no harness element, so moving the stage
from a separate box onto the board is electrically the same network; what changes is the parts in it.

Usage:
  python3 -I c29_emi.py scan  [--procs N]   nominal margin over the grid (2 kHz fs step) -> c29_emi_scan.json
  python3 -I c29_emi.py final [--procs N]   named candidates, 1 kHz step, nominal + g01 sensitivities + pan-earthed INFO,
                                             plus 0.5 kHz nominal re-check -> c29_emi_final.json
"""
import importlib.util, itertools, json, os, sys, time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
G01 = HERE.parent / "g01-mains" / "emi_g01.py"


def load():
    spec = importlib.util.spec_from_file_location("emi_g01", G01)
    g = importlib.util.module_from_spec(spec)
    sys.modules["emi_g01"] = g
    spec.loader.exec_module(g)
    return g


g = load()
import numpy as np

E = 1e-15
TDK = {"LCM": 1.6e-3, "LDM": 18e-6, "RCH": 4.5e-3}          # L1 as built, B82726S2203A020
SC201 = {"LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3}         # KEMET SC-20-201 (g01 P1; leakage assumed 1 %)


def stage1(lcm, ldm_frac=0.01, r=None):
    """Former-module CM choke (on-board 'stage 1'), leakage = ldm_frac x LCM (TDK 1.6 mH: 18 uH = 1.1 %)."""
    return {"LCMADD": lcm, "LDMADD": max(ldm_frac * lcm, 18e-6 if lcm >= 1.6e-3 else ldm_frac * lcm),
            "RCMADD": r if r is not None else (4.5e-3 if lcm <= 1.6e-3 else 10e-3)}


def yset(total_nF, split):
    """split: 'board' (all at C3/C4, L1 output), 'stage1' (all at stage-1 output = model CYHF), 'half'."""
    t = total_nF * 1e-9
    if split == "board": return {"CY": max(t, E), "CYADD": E, "CYHF": E}
    if split == "stage1": return {"CY": E, "CYADD": E, "CYHF": max(t, E)}
    return {"CY": max(t / 2, E), "CYADD": E, "CYHF": max(t / 2, E)}


def run_nominal(args):
    name, over, step = args
    fs = list(np.arange(35000, 60001, step * 1000.0))
    t = time.time()
    w = g.margin(over, fs_list=fs)
    return name, over, w, time.time() - t


def grid():
    c = {}
    for T in (0.0, 1.0, 1.5, 2.2, 3.3, 4.4):
        for split in ("board", "stage1", "half"):
            if T == 0.0 and split != "board": continue
            for l1n, l1 in (("L1tdk1.6", TDK), ("L1sc201", SC201), ("L1_6.4mH", {"LCM": 6.4e-3, "LDM": 64e-6, "RCH": 12e-3})):
                for s1 in (1.6e-3, 2.0e-3, 3.2e-3, 6.4e-3, 10e-3):
                    for ln in (41e-6, 0.0):
                        for sh in (0.0, 0.75):
                            name = f"Y{T}_{split}|{l1n}|S1_{s1*1e3:.1f}mH|LNEW{ln*1e6:.0f}|shield{sh}"
                            c[name] = {**l1, **stage1(s1), **yset(T, split), "LNEW": ln, "COIL_SHIELD_FRAC": sh}
    return c


def finals():
    """Named candidates chosen from the scan (c29_scan_summary.txt) with real or catalogue-class parts.
    Stage-1 chokes: SC201 = KEMET SC-20-201 2.0 mH 20 A (g01 P1); NC3.6 = KEMET SCF39XV-200-Z2R1A012JH 3.6 mH 20 A
    nanocrystalline; NC5.7 = KEMET SCF31X-220-2R1A011JH 5.68 mH 22 A nanocrystalline (distributor listings, see
    README).  Their DM leakage is not published: 1 % of LCM is assumed (TDK 1.6 mH has 1.1 %), with a 0.3 % variant.
    LNEW = discrete DM inductor per leg (41 uH = the s19b module assumption; no MPN exists, g01 P3)."""
    f = {}
    f["REF_B0_s19b_nominal (module as modelled: 1.6 mH + 2x41 uH DM, Y 9.1)"] = {}
    f["REF_D22_as_specified_18uH (LNEW 0)"] = {"LNEW": 0.0}
    f["REF_g01_M2 (SC201 x2, Y 2.2+2.2=4.4)"] = {"LCMADD": 2.0e-3, "LDMADD": 20e-6, "RCMADD": 10e-3, "LNEW": 41e-6,
                                                "LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3, "CYADD": E}
    NC57 = {"LCM": 5.68e-3, "LDM": 56.8e-6, "RCH": 5.2e-3}
    for T, tag in ((3.3, "A"), (2.2, "B"), (1.0, "D")):
        y = yset(T, "board")
        f[f"C29-{tag}{T}_L1tdk_S1sc201_LNEW41"] = {**TDK, **stage1(2.0e-3), **y, "LNEW": 41e-6}
        f[f"C29-{tag}{T}_L1tdk_S1nc3.6_LNEW41"] = {**TDK, **stage1(3.6e-3, r=4.2e-3), **y, "LNEW": 41e-6}
        f[f"C29-{tag}{T}_L1tdk_S1nc5.7_LNEW41"] = {**TDK, **stage1(5.68e-3, r=5.2e-3), **y, "LNEW": 41e-6}
        f[f"C29-{tag}{T}_L1tdk_S1nc5.7_LNEW0"] = {**TDK, **stage1(5.68e-3, r=5.2e-3), **y, "LNEW": 0.0}
        f[f"C29-{tag}{T}_L1tdk_S1nc5.7_leak0.3pct_LNEW41"] = {**TDK, **stage1(5.68e-3, 0.003, 5.2e-3), "LDMADD": 17e-6, **y, "LNEW": 41e-6}
        f[f"C29-{tag}{T}_L1sc201_S1nc5.7_LNEW41"] = {**SC201, **stage1(5.68e-3, r=5.2e-3), **y, "LNEW": 41e-6}
        f[f"C29-{tag}{T}_L1nc5.7_S1nc5.7_LNEW41"] = {**NC57, **stage1(5.68e-3, r=5.2e-3), **y, "LNEW": 41e-6}
        f[f"C29-{tag}{T}_L1tdk_S1sc201_LNEW41_shield75"] = {**TDK, **stage1(2.0e-3), **y, "LNEW": 41e-6, "COIL_SHIELD_FRAC": 0.75}
    for T, tag in ((1.0, "D"),):
        y = yset(T, "half")
        f[f"C29-{tag}{T}half_L1nc5.7_S1nc5.7_LNEW41"] = {**NC57, **stage1(5.68e-3, r=5.2e-3), **y, "LNEW": 41e-6}
    # parts-reduction variants on the 3.3 nF / 5.68 mH set: drop the 2.2 uF input X, or the damping branch
    y = yset(3.3, "board")
    base = {**TDK, **stage1(5.68e-3, r=5.2e-3), **y, "LNEW": 41e-6}
    f["C29-A3.3_L1tdk_S1nc5.7_LNEW41_noXin"] = {**base, "CXIN": 1e-12}
    f["C29-A3.3_L1tdk_S1nc5.7_LNEW41_noDamp"] = {**base, "CDAMP": 1e-12}
    # round 2 (after the first finals): cheaper chokes at 2.2 / 3.3 nF and parts reductions on the 3.6 mH set
    for T, tag in ((3.3, "A"), (2.2, "B")):
        f[f"X-{tag}{T}_L1sc201_S1sc201_LNEW41"] = {**SC201, **stage1(2.0e-3), **yset(T, "board"), "LNEW": 41e-6}
    b36 = {**TDK, **stage1(3.6e-3, r=4.2e-3), **yset(2.2, "board"), "LNEW": 41e-6}
    f["X-B2.2_L1tdk_S1nc3.6_LNEW41_noDamp"] = {**b36, "CDAMP": 1e-12}
    f["X-B2.2_L1tdk_S1nc3.6_leak0.3pct_LNEW41"] = {**b36, "LDMADD": 10.8e-6}
    f["X-B2.2_L1tdk_S1nc3.6_LNEW20"] = {**b36, "LNEW": 20e-6}
    f["X-B2.2_L1tdk_S1nc3.6_LNEW41_Ystage1"] = {**b36, **yset(2.2, "stage1")}
    # round 3: intermediate Y 2.7 nF/line (e.g. 2.2 + 0.47 nF) with the stocked 2 mH SC-20-201 parts
    f["Y-2.7_L1sc201_S1sc201_LNEW41"] = {**SC201, **stage1(2.0e-3), **yset(2.7, "board"), "LNEW": 41e-6}
    f["Y-2.7_L1sc201_S1sc201_leak10uH_LNEW41"] = {**SC201, "LDM": 10e-6, **stage1(2.0e-3), "LDMADD": 10e-6,
                                                   **yset(2.7, "board"), "LNEW": 41e-6}
    f["Y-2.7_L1tdk_S1sc201_LNEW41"] = {**TDK, **stage1(2.0e-3), **yset(2.7, "board"), "LNEW": 41e-6}
    return f


def run_full(args):
    name, over = args
    fs1 = list(np.arange(35000, 60001, 1000.0))
    fs05 = list(np.arange(35000, 60001, 500.0))
    r = {"override": over, "nominal": g.margin(over, fs_list=fs1)}
    r["nominal_0p5kHz"] = g.margin(over, fs_list=fs05)
    r["sens"] = {sn: g.margin({**over, **so}, fs_list=fs1) for sn, so in g.sens_set(over).items()}
    r["sens_min_dB"] = min(v["margin_dB"] for v in r["sens"].values())
    r["sens_min_case"] = min(r["sens"], key=lambda k: r["sens"][k]["margin_dB"])
    r["INFO_pan_earthed_91pF"] = g.margin({**over, "CCOILA": 46.2e-12, "CCOILB": 45.2e-12}, fs_list=fs1)
    r["verdict_6dB"] = "PASS" if min(r["nominal"]["margin_dB"], r["nominal_0p5kHz"]["margin_dB"], r["sens_min_dB"]) >= 6 else (
        "FAIL" if r["nominal"]["margin_dB"] < 0 else "INCONCLUSIVE")
    return name, r


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    procs = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 6
    # control: the wrapper must reproduce the scorecard 10.5 dB (s19b nominal) before anything else
    _, _, w0, _ = run_nominal(("ctl", {}, 2.0))
    assert abs(w0["margin_dB"] - 10.479) < 0.01, w0
    print(f"control: s19b nominal reproduced {w0['margin_dB']:.3f} dB at {w0['f_hz']/1e3:.0f} kHz", flush=True)
    if mode == "scan":
        c = grid()
        out = {}
        with Pool(procs) as p:
            for i, (name, over, w, dt) in enumerate(p.imap_unordered(run_nominal, [(k, v, 2.0) for k, v in c.items()])):
                out[name] = {"override": over, "nominal": w}
                if i % 50 == 0: print(f"{i}/{len(c)} {name} {w['margin_dB']:.1f} dB ({dt:.1f} s)", flush=True)
        json.dump(out, open(HERE / "c29_emi_scan.json", "w"), indent=0, default=float)
        print("wrote c29_emi_scan.json", len(out))
    else:
        f = finals()
        if "--only" in sys.argv:
            keys = sys.argv[sys.argv.index("--only") + 1].split(",")
            f = {k: v for k, v in f.items() if any(k.startswith(x) for x in keys)}
        path = HERE / "c29_emi_final.json"
        out = json.load(open(path)) if path.exists() else {}
        with Pool(procs) as p:
            for name, r in p.imap_unordered(run_full, list(f.items())):
                out[name] = r
                n = r["nominal"]
                print(f"{name:62s} nom {n['margin_dB']:6.1f} ({n['band']} {n['f_hz']/1e3:.0f}k {n['cfg']}) "
                      f"0.5k {r['nominal_0p5kHz']['margin_dB']:6.1f}  sens_min {r['sens_min_dB']:6.1f} [{r['sens_min_case']}]  "
                      f"panE {r['INFO_pan_earthed_91pF']['margin_dB']:5.1f}  {r['verdict_6dB']}", flush=True)
                json.dump(out, open(path, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
