"""Refine the >=2s burst grid to 0.1s and check actual two-hour rule records.

Only the declared duty grid and synthetic impedance cases are covered.
The two-hour test uses twelve measured windows, not Plt=Pst by assumption.
"""
from __future__ import annotations

import json
import math

import numpy as np

from burst_meter_sweep import DUTIES, OUT, burst
from flickermeter import pinst, plt, pst


def two_hour(depth: float, period: float, duty: float) -> dict:
    fs = 2400
    halfcycles = math.ceil(period * 120)
    on = math.floor(duty * halfcycles)
    sample = np.arange((180+7200)*fs)
    amplitude = 1-depth/100*((sample//(fs//120) % halfcycles) < on)
    voltage = 120*math.sqrt(2)*amplitude*np.sin(2*np.pi*60*sample/fs)
    inst = pinst(voltage, fs)[180*fs:]
    values = [pst(inst[i*600*fs:(i+1)*600*fs]) for i in range(12)]
    return {"period_s": halfcycles/120, "duty": duty, "Pst_windows": values,
            "Pst_max": max(values), "Plt": plt(values),
            "pass": max(values) <= 1 and plt(values) <= .65}


def main() -> None:
    rows = []
    for original in json.loads((OUT / "burst-sweep.json").read_text()):
        first = next(i for i, s in enumerate(original["sweep"]) if s["pass"])
        upper = original["sweep"][first]["period_s"]
        lower = original["sweep"][first-1]["period_s"] if first else 2
        refined = []
        for tenth in range(math.ceil(lower*10), math.floor(upper*10)+1):
            period = tenth/10
            values = [burst(original["depth_pct"], period, duty) for duty in DUTIES]
            refined.append({"period_s": period, "worst_duty": DUTIES[values.index(max(values))],
                            "Pst_max": max(values), "pass_Pst_0p65": max(values) <= .65})
        chosen = next(r for r in refined if r["pass_Pst_0p65"])
        rule_period = math.ceil(original["analytical_min_s"]*120)/120
        rule_values = [burst(original["depth_pct"], rule_period, d) for d in DUTIES]
        worst_duty = DUTIES[rule_values.index(max(rule_values))]
        candidates = []
        period = chosen["period_s"]
        while True:
            checks = [two_hour(original["depth_pct"], period, d) for d in DUTIES]
            item = {"period_s": period, "by_duty": checks, "pass": all(c["pass"] for c in checks)}
            candidates.append(item)
            if item["pass"]:
                break
            period = round(period+.1, 1)
        if period > 2:
            previous = round(period-.1, 1)
            checks = [two_hour(original["depth_pct"], previous, d) for d in DUTIES]
            candidates.append({"period_s": previous, "by_duty": checks, "pass": all(c["pass"] for c in checks)})
        rule_checks = [two_hour(original["depth_pct"], rule_period, d) for d in DUTIES]
        row = {"case": original["case"], "power_w": original["power_w"],
               "short_window_candidate_s": chosen["period_s"],
               "minimum_verified_tested_s": period,
               "minimum_grid_two_hour": two_hour(original["depth_pct"], chosen["period_s"], chosen["worst_duty"]),
               "analytical_rule_two_hour": two_hour(original["depth_pct"], rule_period, worst_duty),
               "two_hour_duty_checks": candidates, "two_hour_rule_duty_checks": rule_checks,
               "refinement": refined}
        rows.append(row)
        (OUT / "refined-burst.json").write_text(json.dumps(rows, indent=2)+"\n")
        print(row["case"], row["power_w"], row["minimum_verified_tested_s"],
              row["minimum_grid_two_hour"]["Plt"], row["analytical_rule_two_hour"]["Plt"], flush=True)


if __name__ == "__main__":
    main()
