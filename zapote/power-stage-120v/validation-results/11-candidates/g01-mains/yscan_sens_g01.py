#!/usr/bin/env python3 -I
"""M2 with board Y 1.5 and 1.8 nF: full one-at-a-time sensitivity set (same set as emi_g01.py)."""
import importlib.util, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("emi_g01", HERE / "emi_g01.py")
g = importlib.util.module_from_spec(spec); sys.modules["emi_g01"] = g; spec.loader.exec_module(g)
sc201 = {"LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3}
mod = {"LCMADD": 2.0e-3, "LDMADD": 20e-6, "RCMADD": 10e-3, "LNEW": 41e-6, "CYADD": 1e-15}
out = {}
for cy in (1.5, 1.8):
    over = {**mod, **sc201, "CY": cy * 1e-9}
    s = {n: g.margin({**over, **so})["margin_dB"] for n, so in g.sens_set(over).items()}
    out[cy] = s
    print(f"board Y {cy} nF (Y total {cy+2.2:.1f}): sens min {min(s.values()):.1f}  {({k: round(v,1) for k,v in s.items()})}", flush=True)
json.dump(out, open(HERE / "yscan_sens_g01_results.json", "w"), indent=1)
