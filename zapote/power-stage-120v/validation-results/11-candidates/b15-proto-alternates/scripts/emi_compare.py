#!/usr/bin/env python3
"""Compare the L1-alternate EMI runs (run_emi_l1.py) with the control and the committed stage-38 results.json.
Usage: python3 -I emi_compare.py <results dir> <out.json>"""
import json
import sys
from pathlib import Path

R = Path(sys.argv[1])
COMMITTED = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/"
                 "validation-results/07-conducted-emi/s19b/results.json")
runs = {"committed_s38": json.loads(COMMITTED.read_text())}
for v in ("s38_control", "B82726S2243A020", "B82726S2243A020_fit3M", "s38_control_moduleDM49p7",
          "B82726S2243A020_moduleDM49p7", "B82726S2243A020_moduleDM82u", "B82726S2243A020_moduleDM100u", "B82726S2243A020_moduleDM120u", "s38_control_LDM8u"):
    p = R / f"emi-{v}" / "results.json"
    if p.exists():
        runs[v] = json.loads(p.read_text())


def scen_min(res, s):
    t = res["scenarios"][s]
    best = None
    for k, row in t.items():
        if "nopan_28A" in k:
            continue
        for band in ("hi_150k_30M", "lo_9k_150k"):
            r = row.get(band)
            if r and (best is None or r["margin_dB"] < best[0]):
                best = (r["margin_dB"], k, band, r.get("f_hz") or r.get("freq_hz"), r.get("mode") or r.get("detector"))
    return best


KEY = ["nominal", "coil_PE_study16_plus_board_51pF", "X_caps_minus20pct", "Y_caps_minus20pct",
       "L1_minus30pct_and_module_choke_minus30pct", "L1_winding_C_x2", "module_DM_80uH",
       "INFO_pan_earthed_91pF", "board_only_no_module", "module_DM_18uH_only (D-22 as specified)"]
out = {"verdicts": {}, "scenarios": {}, "controls": {}}
for name, res in runs.items():
    out["verdicts"][name] = res["verdict"]
    out["controls"][name] = res.get("controls", {}).get("asserts")
    out["scenarios"][name] = {s: scen_min(res, s) for s in KEY if s in res["scenarios"]}
    # the worst sensitivity (the one that sets sensitivity_min_margin_all_dB)
excl = ("module_DM_18uH", "board_only", "Y_caps_board_only", "STACKED", "REC", "thin_pad_and", "insulator_swap",
        "edge_x4", "coil_PE_100pF_one_sided", "INFO_")
for name, res in runs.items():
    sens = [(scen_min(res, s)[0], s) for s in res["scenarios"] if s != "nominal" and not s.startswith(excl)]
    out.setdefault("worst_sensitivities", {})[name] = sorted(sens)[:5]
# aux bound
for name, res in runs.items():
    out.setdefault("aux_bound", {})[name] = res.get("aux_supplies_at_limit_bound")
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n")
print("verdicts")
for n, v in out["verdicts"].items():
    print(f"  {n:24s} nominal {v['nominal_min_margin_dB']:.3f}  sens_min {v['sensitivity_min_margin_all_dB']:.3f}  "
          f"sens22 {v['sensitivity_min_margin_22A_dB']:.3f}  {v['verdict']}")
print("controls", json.dumps(out["controls"].get("B82726S2243A020")))
for s in KEY:
    print(s)
    for n in runs:
        print(f"   {n:24s} {out['scenarios'][n].get(s)}")
print("worst sensitivities")
for n, w in out["worst_sensitivities"].items():
    print("  ", n, [(round(a, 2), b) for a, b in w])
for n, a in out["aux_bound"].items():
    print("  aux", n, json.dumps(a))
