#!/usr/bin/env python3 -I
"""D-22 discrete DM inductor: conducted-EMI margin with real catalogue parts in the LNEW slot.

Calls the committed, unmodified s19b model through g01's wrapper (11-candidates/g01-mains/emi_g01.py: margin(),
sens_set(); imported, never run as __main__, so neither file is written).  Same calling convention as
11-candidates/c29-inlet-filter/c29_emi.py run_full(): fs 35-60 kHz at 1 kHz, 0.5 kHz nominal re-check, g01's eight
one-at-a-time sensitivities, pan-earthed INFO case.  PASS rule (s19b README sec. 1): >= 6 dB nominal and in every
sensitivity.

Basis = D-22 as specified + s19b nominal (= g01 'B0_baseline_s19b_nominal': TDK L1 1.6 mH, module TDK
B82726S2203A020 1.6 mH / 18 uH leakage, module Y 4.7 + 2.2 nF, board Y 2.2 nF, X 2.2 / 4.7 / damped 4.7 uF).
Only the per-leg DM inductor changes:
  LNEW  = the part's inductance read from the vendor L-vs-I curve at 21 A (line crest of 15 A rms), or at 0 A
  RNEW  = DCR max (series R in the model)
  CPNEW = self-capacitance from the published SRF, C = 1 / ((2 pi SRF)^2 L0); 30 pF (s19b default) where no SRF
Every number is cited in SURVEY.md.  The g01 sensitivity 'module DM 80 uH' scales LNEW by 31/41 (-24 %), which
also covers the parts' -20 % inductance tolerance.

Usage: python3 -I dm_emi_check.py [--procs N] [--only PREFIX[,PREFIX]]   -> dm_emi_check.json (next to this file)
"""
import importlib.util, json, math, sys
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
G01 = HERE.parents[1] / "11-candidates" / "g01-mains" / "emi_g01.py"
spec = importlib.util.spec_from_file_location("emi_g01", G01)
g = importlib.util.module_from_spec(spec)
sys.modules["emi_g01"] = g
spec.loader.exec_module(g)
import numpy as np


def cp(srf_hz, l0):
    return 1.0 / ((2 * math.pi * srf_hz) ** 2 * l0)


# (name, L0 uH, L at 21 A uH or None, DCR max mohm, SRF MHz or None) -- sources in SURVEY.md
PARTS = [
    ("WE_74437636355602_56uH_metal_alloy", 56.0, 49.7, 3.19 * 1.1, 7.41),
    ("WE_74437636356203_62uH_metal_alloy", 62.0, 56.1, 5.22 * 1.1, 6.19),
    ("WE_7443763540470_47uH_MnZn", 47.0, 46.6, 6.38, 6.0),
    ("WE_74437636353703_37uH_metal_alloy", 37.0, 34.8, 3.19 * 1.1, 8.87),
    ("WE_7443763540330_33uH_MnZn", 33.0, 32.9, 6.38, 7.0),
    ("CC_AGP4233-333ME_33uH_ferrite_10pct_bound", 33.0, 33.0 * 0.9, 2.95, 10.0),
    ("VI_IHTH1500TZEB330M5A_33uH_composite", 33.2, 30.6, 5.1, 2.6),
    ("VI_IHB-6_47uH_no_curve", 47.0, None, 8.0, None),
]


def cases():
    c = {"CTL_B0_s19b_nominal_LNEW41": {},
         "CTL_D22_as_specified_LNEW0": {"LNEW": 0.0}}
    for name, l0, l21, dcr, srf in PARTS:
        c_p = cp(srf * 1e6, l0 * 1e-6) if srf else 30e-12
        base = {"RNEW": dcr * 1e-3, "CPNEW": c_p}
        if l21 is not None:
            c[f"{name}@21A"] = {**base, "LNEW": l21 * 1e-6}
        c[f"{name}@0A"] = {**base, "LNEW": l0 * 1e-6}
    # threshold sweep on the same D-22 basis (generic part: 5 mohm, 15 pF): which per-leg L at 21 A keeps 6 dB in
    # every sensitivity?  Any derated value (hot core, tolerance) can be read off this sweep.
    for ln in (38, 40, 42, 44):
        c[f"SWEEP_LNEW_{ln}uH_5mohm_15pF"] = {"LNEW": ln * 1e-6, "RNEW": 5e-3, "CPNEW": 15e-12}
    return c


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
    worst = min(r["nominal"]["margin_dB"], r["nominal_0p5kHz"]["margin_dB"], r["sens_min_dB"])
    r["verdict_6dB"] = "PASS" if worst >= 6 else ("FAIL" if r["nominal"]["margin_dB"] < 0 else "INCONCLUSIVE")
    return name, r


def main():
    procs = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 4
    w0 = g.margin({}, fs_list=list(np.arange(35000, 60001, 2000.0)))
    assert abs(w0["margin_dB"] - 10.479) < 0.01, w0
    print(f"control: s19b nominal reproduced {w0['margin_dB']:.3f} dB at {w0['f_hz']/1e3:.0f} kHz", flush=True)
    path = HERE / "dm_emi_check.json"
    c = cases()
    out = {}
    if "--only" in sys.argv:   # re-run a subset (name prefixes) and merge into the existing JSON
        keys = sys.argv[sys.argv.index("--only") + 1].split(",")
        c = {k: v for k, v in c.items() if any(k.startswith(x) for x in keys)}
        out = json.load(open(path)) if path.exists() else {}
    with Pool(procs) as p:
        for name, r in p.imap_unordered(run_full, list(c.items())):
            out[name] = r
            n = r["nominal"]
            print(f"{name:52s} nom {n['margin_dB']:6.2f} ({n['band']} {n['f_hz']/1e3:.0f}k {n['cfg']}) "
                  f"0.5k {r['nominal_0p5kHz']['margin_dB']:6.2f}  sens_min {r['sens_min_dB']:6.2f} [{r['sens_min_case']}]  "
                  f"panE {r['INFO_pan_earthed_91pF']['margin_dB']:5.1f}  {r['verdict_6dB']}", flush=True)
            json.dump(dict(sorted(out.items())), open(path, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
