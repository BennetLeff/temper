#!/usr/bin/env python3
"""Re-run the stage-38 conducted-EMI model of record (07-conducted-emi/s19b/emi_s19b.py, MODULE_S38) with board L1
swapped to an alternate choke. The repo script is imported read-only; only its BASE L1 parameters and its output
directory are patched. Every control the script asserts (D-22 9.28 dB, round-3 peaks, closed form, ngspice parity)
still runs.

Usage: python3 -I run_emi_l1.py <variant> <outdir>
  variant: s38_control      unchanged (must reproduce nominal 12.37 / sensitivity min 8.19 dB)
           B82726S2243A020  TDK p.4: 0.75 mH, Lstray 8 uH, 3.2 mOhm; winding C / loss from the p.5 vector fit
                            (fit_b82726_curves.py, 10 kHz-10 MHz band, the round-3 convention)
           B82726S2243A020_fit3M  same, winding C / loss from the 10 kHz-3 MHz band fit (larger C)
           <any of the above>_moduleDM49p7  plus the module DM inductors at 49.7 uH (DECISIONS 32 part at 21 A)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
SCRIPT = REPO / "validation-results/07-conducted-emi/s19b/emi_s19b.py"
HERE = Path(__file__).resolve().parent
FIT = HERE.parent / "results/b82726_fit.json"

variant, outdir = sys.argv[1], Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
sys.argv = [str(SCRIPT), "--no-plots"]

spec = importlib.util.spec_from_file_location("emi_s19b", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.HERE = outdir  # results.json (and the copper summary cache) go to outdir, never the repo

patch = {}
if variant.startswith("B82726S2243A020"):
    fit = json.loads(FIT.read_text())["parts"]["B82726S2243A020"]["fit"]
    f = fit["10k_3M" if "fit3M" in variant else "10k_10M"]
    patch = dict(LCM=0.75e-3, LDM=8e-6, RCH=3.2e-3,
                 CCH=f["per_winding_C_pF"] * 1e-12, RLOSSCH=f["per_winding_R_ohm"])
elif not variant.startswith("s38_control"):
    raise SystemExit(f"unknown variant {variant}")
if variant.endswith("_moduleDM49p7"):
    # off-board D-22 module DM inductors at the DECISIONS 32 part (Wurth WE-HCFT 74437636355602, 56 uH, 49.7 uH at
    # 21 A) instead of s19b's 41 uH placeholder; information: MODULE-REQUEST.md still lists 2 x 41 uH without an MPN
    patch["LNEW"] = 49.7e-6
elif variant.endswith("_LDM8u"):
    # attribution: fitted L1 with only its stray (DM) inductance changed 18 -> 8 uH
    patch["LDM"] = 8e-6
elif "_moduleDM" in variant:
    # what-if: module DM inductors at <N> uH each (e.g. _moduleDM100u), to size the module for this L1
    patch["LNEW"] = float(variant.split("_moduleDM")[1].rstrip("u")) * 1e-6
# board L1 only, through the nominal parameter set (not BASE): the controls (D-22, round 3) build the native-15
# network from BASE and must keep the fitted part. scenarios() takes P = {**BASE, **nom}, so the relative part-value
# sensitivities (L1 -30 %, winding C x2) apply to the alternate. The module choke keys (LCMADD...) are untouched.
_orig_nominal = m.nominal_params
m.nominal_params = lambda cm: {**_orig_nominal(cm), **patch}
(outdir / "patch.json").write_text(json.dumps({"variant": variant, "board_L1_patch": patch,
                                               "script": str(SCRIPT)}, indent=1) + "\n")
print("variant", variant, "patch", patch, flush=True)
m.main()
