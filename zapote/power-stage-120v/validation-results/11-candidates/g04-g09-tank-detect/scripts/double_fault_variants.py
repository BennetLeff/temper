#!/usr/bin/env python3
"""G04/F3: rerun the committed CT-blind double-fault study (02-protection-timing/bank-ov-double-fault) with
bank variants, WITHOUT editing it. The study module is imported read-only; its module constants are
overridden for each variant (C corners, rated voltage, firmware floor) after its own controls have passed
at the committed +-10 % basis.

Variants
  base         committed basis: C 0.45-0.55 uF (5 x 100 nF K), floor 35 kHz in the fw rows
  J_tol        5 x 100 nF J (+-5 %): C 0.475-0.525 uF
  J_tol+L5     J bank and coil L +-5 % (a measured, binned coil; NOT a committed assumption, sensitivity only)
Reported per variant: governing no-floor quasi-steady peak (the 1702 V figure), time-domain F1/F2, 35 kHz floor, and
ratios against 1600 V (the sheet's only continuous peak rating) and 2000 V (B32654A2104 sibling).
Run: python3 -I double_fault_variants.py   -> ../results/double_fault_variants.json
"""
import importlib.util, json, math, sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
VR = HERE.parents[2]
SRC = VR / "02-protection-timing/bank-ov-double-fault/bank_ov_double_fault.py"
spec = importlib.util.spec_from_file_location("bodf", SRC)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

CTL = M.controls()                      # asserts the committed numbers at the committed basis
M.controls = lambda: CTL                # study() calls controls(); keep the verified result for variants


def run(name, ctol, ltol):
    M.C_MIN, M.C_MAX = M.C_NOM * (1 - ctol), M.C_NOM * (1 + ctol)
    M.L_MIN, M.L_MAX = M.L_NOM * (1 - ltol), M.L_NOM * (1 + ltol)
    M.CORNERS = {"Lmax_Cmin (max Z0)": (M.L_MAX, M.C_MIN), "Lmax_Cmax": (M.L_MAX, M.C_MAX), "nominal": (M.L_NOM, M.C_NOM),
                 "Lmin_Cmin": (M.L_MIN, M.C_MIN), "Lmin_Cmax": (M.L_MIN, M.C_MAX)}
    r = M.study()
    td = r["time_domain_worst"]
    ss = r["quasi_steady_just_under_trip_worst"]
    out = {"variant": name, "C_tol": ctol, "L_tol": ltol,
           "steady_no_floor_V": round(ss["no_floor"]["Vc_pk_V"], 1),
           "steady_35k_floor_V": round(ss["fw_floor_35k"]["Vc_pk_V"], 1),
           "td_F1_runaway_V": round(td["F1_runaway"]["Vc_peak_V"], 1),
           "td_F2_loop_intact_V": round(td["F2_pan_removal"]["Vc_peak_V"], 1)}
    out["gov_V"] = max(out["steady_no_floor_V"], out["td_F1_runaway_V"], out["td_F2_loop_intact_V"])
    out["gov_over_1600"] = round(out["gov_V"] / 1600, 3)
    out["gov_over_2000"] = round(out["gov_V"] / 2000, 3)
    out["floor_table"] = r.get("frequency_floor_table") or r.get("floor_table")
    return out


res = {"controls_ok": True, "source": str(SRC.relative_to(VR)),
       "variants": [run("base", 0.10, 0.10), run("J_tol", 0.05, 0.10), run("J_tol+L5", 0.05, 0.05)]}
# control: base must reproduce the committed governing figure
committed = json.loads((SRC.parent / "results.json").read_text())
assert abs(res["variants"][0]["steady_no_floor_V"] - committed["quasi_steady_just_under_trip_worst"]["no_floor"]["Vc_pk_V"]) < 0.2
(HERE.parent / "results" / "double_fault_variants.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
for v in res["variants"]:
    print({k: v[k] for k in v if k != "floor_table"})
