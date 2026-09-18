#!/usr/bin/env python3
"""Assemble the N-DPT final numbers from ngspice logs + Coss tables.

No device physics here: it only reads the .meas values and the Coss(v) tables
produced by ngspice and applies the campaign's frequency weighting.
"""
import json
import math
import re

F_HZ = 129107.39198576905
ANALYTIC_OVERLAP_W = 37.36824064736847  # zapote-erc::pfc_switching at case[1]
ANALYTIC_EOSS_W = 1.5106
ANALYTIC_TOTAL_W = 45.502337474982966

LOGS = {
    "IPW65R045C7@25C":  ("logs/dpt_ipw65r045c7_L0_25c.log",  "derived/coss_ipw65r045c7_L0_25c.json"),
    "IPW65R045C7@125C": ("logs/dpt_ipw65r045c7_L0_125c.log", "derived/coss_ipw65r045c7_L0_125c.json"),
    "IPZ60R040C7@25C":  ("logs/dpt_ipz60r040c7_L0_25c.log",  "derived/coss_ipz60r040c7_L0_25c.json"),
    "IPZ60R040C7@125C": ("logs/dpt_ipz60r040c7_L0_125c.log", "derived/coss_ipz60r040c7_L0_125c.json"),
}
MEAS = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([-+0-9.eE]+)\s*(?:from=.*)?$")


def meas(path):
    out = {}
    for line in open(path, errors="replace"):
        m = MEAS.match(line)
        if m and not line.strip().startswith("Error"):
            try:
                out[m.group(1)] = float(m.group(2))
            except ValueError:
                pass
    return out


def main():
    res = {}
    for name, (log, coss_json) in LOGS.items():
        m = meas(log)
        c = json.load(open(coss_json))
        eon, eoff = m["eon"], m["eoff"]
        eoss = c["eoss_j"]
        p_on_off = (eon + eoff) * F_HZ
        p_overlap_only = (eon - eoss + eoff) * F_HZ
        res[name] = {
            "eon_j": eon, "eoff_j": eoff, "eoss_j": eoss,
            "turn_on_current_a": m["il_eon"], "turn_off_current_a": m["il_eoff"],
            "p_switch_on_off_w": p_on_off,
            "ratio_vs_analytic_overlap": p_on_off / ANALYTIC_OVERLAP_W,
            "p_overlap_only_w": p_overlap_only,
            "ratio_overlap_only_vs_analytic": p_overlap_only / ANALYTIC_OVERLAP_W,
            "p_eoss_w": eoss * F_HZ,
            "ratio_total_vs_analytic_total": (p_on_off + eoss * F_HZ) / ANALYTIC_TOTAL_W,
        }
    out = {"f_hz": F_HZ, "analytic_overlap_w": ANALYTIC_OVERLAP_W,
           "analytic_eoss_w": ANALYTIC_EOSS_W, "analytic_total_switch_gate_w": ANALYTIC_TOTAL_W,
           "devices": res}
    print(json.dumps(out, indent=2))
    open("derived/final_numbers.json", "w").write(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
