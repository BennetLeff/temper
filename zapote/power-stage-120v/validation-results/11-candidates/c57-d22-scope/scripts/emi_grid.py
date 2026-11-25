#!/usr/bin/env python3
"""D-22 EMI margin against DM inductance and the SCF31X choke's unpublished DM leakage (07-conducted-emi/s19b, unchanged).

    python3 -I emi_grid.py VARIANT OUTDIR     VARIANT = proto|prod : DM_uH : leak_pct     e.g. proto:100:0.3
proto = board L1 B82726S2243A020 (b15 fit), prod = the model's fitted B82726S2203A020. LDMADD = leak_pct of 5.68 mH (the model
uses 1 % = 56.8 uH; it is the loop total, so it compares with 2 x the per-line DM inductance). Every assert in the model still runs.
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PS = Path(__file__).resolve().parents[4]
S = PS / "validation-results/07-conducted-emi/s19b/emi_s19b.py"
FIT = PS / "validation-results/11-candidates/b15-proto-alternates/results/b82726_fit.json"
kind, dm, leak = sys.argv[1].split(":")
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
sys.argv = [str(S), "--no-plots"]
sp = importlib.util.spec_from_file_location("emi_s19b", S)
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)
m.HERE = out
patch = {"LNEW": float(dm) * 1e-6, "LDMADD": float(leak) / 100 * 5.68e-3}
if kind == "proto":
    f = json.loads(FIT.read_text())["parts"]["B82726S2243A020"]["fit"]["10k_10M"]
    patch.update(LCM=0.75e-3, LDM=8e-6, RCH=3.2e-3, CCH=f["per_winding_C_pF"] * 1e-12, RLOSSCH=f["per_winding_R_ohm"])
else:
    assert kind == "prod"
orig = m.nominal_params
m.nominal_params = lambda cm: {**orig(cm), **patch}
m.main()
