#!/usr/bin/env python3 -I
"""S1: sensitivity of the committed s19b conducted-EMI margin to the board Y-cap path inductance (ESLY) that
moving C3/C4 to the inlet module changes (F11: PE path 75-81 mm, ~125 nH today; module Y caps sit at the inlet PE
stud, 10-25 mm). Calls the unmodified s19b model like g01-mains/emi_g01.py. Read-only on 07-conducted-emi/s19b.
    python3 -I emi_s1.py [--step 1] -> ../results/emi_s1.json
The model has no harness element: the harness inductance (computed in conn_inductance.py) is 3-4 orders below the
1.6 mH choke and is not modelled."""
import importlib.util, json, sys
sys.dont_write_bytecode = True
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
S19B = HERE.parents[2]/"07-conducted-emi/s19b/emi_s19b.py"
spec = importlib.util.spec_from_file_location("emi_s19b", S19B); m = importlib.util.module_from_spec(spec)
sys.modules["emi_s19b"] = m; spec.loader.exec_module(m)
m.COPPER = Path("/nonexistent")
STEP = float(sys.argv[sys.argv.index("--step")+1]) if "--step" in sys.argv else 2.0
REP = [(170.0, "pan_22A"), (198.0, "pan_28A"), (198.0, "nopan_22A")]
FS = list(np.arange(35000, 60001, STEP*1000.0))
cm = m.cm_capacitances(); NOM = m.nominal_params(cm)
def margin(over):
    p = {**NOM, **over}; worst = None
    for vc, cn in REP:
        trs = {}
        for fs in FS:
            h = np.arange(1, int(30e6/fs)+1)
            t = m.transfers({**p, **m.tank_for(vc, m.case_at(vc, m.CASES[cn], fs), fs)}, True, h*fs); t["h"] = h; trs[fs] = t
        rows = m.aggregate(trs, None, vc, m.CASES[cn], FS, 1.0, 1.0)
        for tag in ("lo", "hi"):
            w = m.worst(rows, "terminal", tag)
            if w and (worst is None or w["margin_dB"] < worst["margin_dB"]): worst = dict(w, band=tag, cfg=f"{int(vc)}V/{cn}")
    return worst
out = {"NOM_ESLY_nH": NOM.get("ESLY", 0)*1e9, "NOM_LPE_nH": NOM.get("LPE", 0)*1e9}
for name, ov in (("baseline_nominal", {}), ("ESLY_15nH", {"ESLY": 15e-9}), ("ESLY_45nH", {"ESLY": 45e-9}),
                 ("ESLY_125nH_F11", {"ESLY": 125e-9}), ("ESLY_125nH_and_module_Y_ESL_x3", {"ESLY": 125e-9, "ESLYADD": 45e-9, "ESLYHF": 30e-9})):
    w = margin(ov); out[name] = {k: w[k] for k in ("margin_dB", "band", "cfg") if k in w}
    print(name, out[name], flush=True)
json.dump(out, open(HERE.parent/"results/emi_s1.json", "w"), indent=1)
