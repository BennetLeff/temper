#!/usr/bin/env python3
"""Summarise the D6-D9 diode-swap re-runs (c39_diode_rerun.py) with the study's own analyzer (gate-network-2026-10-15
scripts/analyze.py summarize(), imported read-only, SIMS pointed at ../results/c39-sims), and compare with the committed
full-grid row of split68_1_cgs4p7_tt125 (results/full.md line 15). Usage: python3 -I c39_summary.py OUT.json"""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
GNDIR = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-results/"
             "01-switching-parasitics/gate-network-2026-10-15")
spec = importlib.util.spec_from_file_location("an", GNDIR / "scripts/analyze.py")
an = importlib.util.module_from_spec(spec)
spec.loader.exec_module(an)
an.SIMS = Path(__file__).resolve().parents[1] / "results/c39-sims"

COMMITTED = {"S1_worst_t_trans_ns": 190.2, "S1_zvs": "80/80", "S1_off": -1.718, "S2_vds": 435.0, "S2_off": -2.567,
             "S4_slew_esl10": 49.7, "S4_slew_esl1.06": 49.15, "S4_difdt": 244.0, "S4_irr": 50.8, "S4_vds": 347.2,
             "S4_off": 0.497, "S5_slew_esl10": 22.1, "S5_slew_esl1.06": 20.63, "S5_vds": 360.3, "S5_off": -0.219,
             "off_all": 0.497, "pass": "640/640"}
SCREEN = {"off_gate_V": 1.9, "S4_slew_Vns": 56.0, "S4_difdt_Apus": 1040.0, "dead_time_ns": 340.0}


def flat(s):
    a, b, f4, f5 = s["S1"], s["S2"], s["S4"], s["S5"]
    return {"S1_worst_t_trans_ns": a["worst_t_trans_ns"], "S1_zvs": a["zvs"], "S1_off": a["max_off_V"],
            "S2_vds": b["max_vds"], "S2_off": b["max_off_V"], "S4_slew_esl10": f4.get("max_slew2080_esl10"),
            "S4_slew_esl1.06": f4.get("max_slew2080_esl1.06"), "S4_difdt": f4["max_difdt_75_25"], "S4_irr": f4["max_irr_A"],
            "S4_vds": f4["max_vds"], "S4_off": f4["max_off_V"], "S5_slew_esl10": f5.get("max_slew2080_esl10"),
            "S5_slew_esl1.06": f5.get("max_slew2080_esl1.06"), "S5_vds": f5["max_vds"], "S5_off": f5["max_off_V"],
            "off_all": round(max(a["max_off_V"], b["max_off_V"], f4["max_off_V"], f5["max_off_V"]), 3),
            "pass": f"{s['pass']}/{s['complete']}", "runs": s["runs"]}


out = {"committed_split68_1_cgs4p7_tt125": COMMITTED, "screens": SCREEN, "runs": {}, "loss": {}}
for m in ("pmeg", "vfhi", "cjhi"):
    cfg = f"split68_1_cgs4p7_tt125_D{m}"
    s = an.summarize(cfg, "full")
    if s:
        f = flat(s)
        f["miller_clamp_margin_V"] = round(SCREEN["off_gate_V"] - f["off_all"], 3)
        f["S4_slew_margin_Vns"] = round(SCREEN["S4_slew_Vns"] - max(f["S4_slew_esl10"], f["S4_slew_esl1.06"]), 2)
        f["turnoff_margin_340_ns"] = round(SCREEN["dead_time_ns"] - f["S1_worst_t_trans_ns"], 1)
        out["runs"][m] = f
    try:
        ls = an.loss_summary(cfg)
        if ls:
            out["loss"][m] = ls
    except Exception as e:  # loss grid not run yet
        out["loss"][m] = f"n/a ({type(e).__name__})"
if "pmeg" in out["runs"]:
    p = out["runs"]["pmeg"]
    out["control_max_abs_delta"] = max(abs(p[k] - v) for k, v in COMMITTED.items() if isinstance(v, float))
json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
keys = list(COMMITTED) + ["miller_clamp_margin_V", "S4_slew_margin_Vns", "turnoff_margin_340_ns"]
print(f"{'metric':22s} {'committed':>10s} " + " ".join(f"{m:>10s}" for m in out["runs"]))
for k in keys:
    print(f"{k:22s} {str(COMMITTED.get(k, '')):>10s} " + " ".join(f"{str(out['runs'][m].get(k)):>10s}" for m in out["runs"]))
print("control max |delta| vs committed:", out.get("control_max_abs_delta"))
print("loss:", json.dumps(out["loss"], default=str)[:1500])
