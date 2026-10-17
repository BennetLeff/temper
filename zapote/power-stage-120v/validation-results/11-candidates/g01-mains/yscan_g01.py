#!/usr/bin/env python3 -I
"""Cliff check for proposal M2 (L1 and module CM choke both Kemet SC-20-201): nominal margin vs board Y (C3/C4) with module HF Y 2.2 nF.
Shows how close the 4.4 nF choice is to the low-Y resonance cliff (CM resonance moving into 50-60 kHz)."""
import importlib.util, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("emi_g01", HERE / "emi_g01.py")
g = importlib.util.module_from_spec(spec); sys.modules["emi_g01"] = g; spec.loader.exec_module(g)
sc201 = {"LCM": 2.0e-3, "LDM": 20e-6, "RCH": 10e-3}
mod = {"LCMADD": 2.0e-3, "LDMADD": 20e-6, "RCMADD": 10e-3, "LNEW": 41e-6, "CYADD": 1e-15}
out = {}
for cy in (0.5, 1.0, 1.5, 1.8, 2.2, 2.7, 3.3):
    r = g.margin({**mod, **sc201, "CY": cy * 1e-9})
    out[cy] = r["margin_dB"]
    print(f"board Y {cy:3.1f} nF + module 2.2 nF: nominal {r['margin_dB']:6.1f} dB ({r['band']}, {r['f_hz']/1e3:.0f} kHz, CM {r['CM_dBuV']:.0f})", flush=True)
json.dump(out, open(HERE / "yscan_g01_results.json", "w"), indent=1)
