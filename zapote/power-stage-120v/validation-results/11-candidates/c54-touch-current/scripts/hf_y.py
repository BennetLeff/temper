#!/usr/bin/env python3
"""c54: switching-frequency (35-60 kHz harmonics) touch current in the open-PE test, versus board Y (C3/C4).

Not part of the committed 60 Hz rule. Re-uses the committed co-design estimator
(07-conducted-emi/leakage/co-design-2026-10-15/hf_touch.py: s19b network with the LISN sense / PE bond replaced by a
meter from PE to earth; IEC 60990 Fig. 4 weighted, and a UL-style 1500 ohm || 0.15 uF reading) but points it at the
CURRENT committed s19b model (emi_s19b.py, MODULE_S38) with the board-of-record L1 / module patch of emi_y.py.
Sources at the line crest (overstates a line-cycle RMS by up to ~1.41x); HF adds to the 60 Hz value in quadrature.

Usage: python3 -I hf_y.py   -> ../results/hf_touch.json
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
S19B = PS / "validation-results/07-conducted-emi/s19b/emi_s19b.py"
CODESIGN = PS / "validation-results/07-conducted-emi/leakage/co-design-2026-10-15"
FIT = PS / "validation-results/11-candidates/b15-proto-alternates/results/b82726_fit.json"
OUT = HERE.parent / "results/hf_touch.json"

sys.argv = [str(S19B), "--no-plots"]
spec = importlib.util.spec_from_file_location("emi_s19b_c54", S19B)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.HERE = HERE.parent / "results"

sys.path.insert(0, str(CODESIGN))
import hf_touch as HT  # noqa: E402  (imports emi_core, which loads its own byte copy; we swap in the current model)

HT.m = m

f = json.loads(FIT.read_text())["parts"]["B82726S2243A020"]["fit"]["10k_10M"]
BOR = dict(LCM=0.75e-3, LDM=8e-6, RCH=3.2e-3, CCH=f["per_winding_C_pF"] * 1e-12, RLOSSCH=f["per_winding_R_ohm"],
           LNEW=100e-6)


def main() -> int:
    cm = m.cm_capacitances()
    nom = {**m.nominal_params(cm), **BOR}
    mc = HT.control_meter()
    assert max(abs(list(r.values())[1] - r["closed_form"]) for r in mc) < 1e-9, mc
    out = {"note": __doc__.strip().splitlines()[0], "meter_control": mc, "options": {}}
    for cy in (2.2, 1.5, 1.0):
        p = {**m.BASE, **nom, "CY": cy * 1e-9}
        corners = {"nominal": {}, "chokes -30 % (L1 + module)": {"LCM": p["LCM"] * 0.7, "LCMADD": p["LCMADD"] * 0.7},
                   "Y -20 %": {"CY": p["CY"] * 0.8}, "Y +20 %": {"CY": p["CY"] * 1.2},
                   "coil + board 51 pF": {"CCOILA": 25.7e-12, "CCOILB": 25.3e-12}}
        res = {}
        for name, ov in corners.items():
            r = HT.hf_touch({"CY": cy * 1e-9, **ov}, nom)
            res[name] = r
            print(f"Y {cy} nF {name:28s} IEC60990 {r['lisn_mains_iec60990']['weighted_mA']:.4f}  "
                  f"stiff {r['stiff_mains_iec60990']['weighted_mA']:.4f}  UL-style {r['lisn_mains_ul101']['weighted_mA']:.4f} mA",
                  flush=True)
        worst = max(v["weighted_mA"] for r in res.values() for v in r.values())
        out["options"][f"Y{cy}"] = {"CY_nF": cy, "corners": res, "worst_weighted_mA_any_meter_any_corner": worst}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
