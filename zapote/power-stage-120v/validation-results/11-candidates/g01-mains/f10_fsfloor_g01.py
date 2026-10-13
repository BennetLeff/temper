#!/usr/bin/env python3 -I
"""F10 side question: how much DM inductance does the module need if the controller's lowest fs is raised?
Nominal margin (no sensitivities) of config K2 (3.2 mH module choke, Y 4.4 nF) vs module DM inductor LNEW and fs floor."""
import importlib.util, json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("emi_g01", HERE / "emi_g01.py")
g = importlib.util.module_from_spec(spec); sys.modules["emi_g01"] = g; spec.loader.exec_module(g)
big = {"LCMADD": 3.2e-3, "LDMADD": 36e-6, "CYADD": 1e-15}
out = {}
for floor in (35, 38, 40, 45):
    fs = list(np.arange(floor * 1e3, 60001, 1000.0))
    for ln in (0, 10, 20, 32):
        r = g.margin({**big, "LNEW": ln * 1e-6}, fs_list=fs)
        out[f"floor{floor}_LNEW{ln}"] = r["margin_dB"]
        print(f"fs floor {floor} kHz, LNEW {ln:2d} uH: nominal {r['margin_dB']:5.1f} dB ({r['band']}, f={r['f_hz']/1e3:.0f} kHz)", flush=True)
json.dump(out, open(HERE / "f10_fsfloor_g01_results.json", "w"), indent=1)
