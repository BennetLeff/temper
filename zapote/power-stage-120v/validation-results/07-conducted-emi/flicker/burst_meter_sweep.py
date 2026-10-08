#!/usr/bin/env python3
"""Reproducible burst screen; grid minimum, not an installation guarantee.

Period grid divides each 600 s observation exactly. Whole half-cycle bursts
repeat indefinitely, so twelve identical Pst windows give Plt=Pst. Sweep duty
as well as period; minimum is conservative over the declared duty grid only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from flickermeter import pinst, plt, pst
from burst_flicker import min_period

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "01-switching-parasitics/round17/delegation/out-D35"
POWERS = (160, 200, 250, 300)
PERIODS = (2, 2.5, 3, 4, 5, 6, 7.5, 8, 10, 12, 15, 20, 24, 25, 30, 40, 50, 60)
DUTIES = (.05, .1, .25, .5, .75, .9, .95)
# NA illustrative service + branch: 30 m copper loop, 3.31 mm2 (#12 AWG),
# rho20=1.7241e-8 ohm m; upstream R=.03, total assumed X=.03 ohm.
# This is a documented circuit scenario, not a claimed population percentile.
NA_R = 30 * 1.7241e-8 / 3.31e-6 + .03
IMPEDANCES = {"iec_proxy": (.4, .25), "na_illustrative": (NA_R, .03)}


def burst(depth_pct: float, period: float, duty: float, fs: int = 2400) -> float:
    # Settled repetition, with whole-half-cycle duty rounded down as firmware.
    halfcycles = round(period * 120)
    on = max(1, math.floor(duty * halfcycles))
    samples = np.arange(780 * fs)
    halfindex = samples // (fs // 120)
    amplitude = 1 - depth_pct / 100 * ((halfindex % halfcycles) < on)
    voltage = 120 * math.sqrt(2) * amplitude * np.sin(2 * np.pi * 60 * samples / fs)
    return pst(pinst(voltage, fs)[180 * fs:])


def main() -> None:
    rows = []
    for label, (r, x) in IMPEDANCES.items():
        for power in POWERS:
            depth = 100 * power / (120**2 * .95) * (r * .95 + x * math.sqrt(1 - .95**2))
            sweep = []
            for period in PERIODS:
                values = [burst(depth, period, duty) for duty in DUTIES]
                worst = max(values)
                sweep.append({"period_s": period, "worst_duty": DUTIES[values.index(worst)], "Pst_max": worst, "Plt": plt([worst] * 12), "pass": worst <= .65, "by_duty": dict(zip(map(str, DUTIES), values))})
            eligible = [s["period_s"] for s in sweep if s["pass"]]
            twenty = next(s for s in sweep if s["period_s"] == 20)
            refined = burst(depth, 20, twenty["worst_duty"], fs=4800)
            row = {"case": label, "power_w": power, "R_ohm": r, "X_ohm": x, "PF": .95,
                   "depth_pct": depth, "minimum_tested_period_s": min(eligible) if eligible else None,
                   "analytical_min_s": min_period(depth), "Pst_20s_4800Hz": refined,
                   "fs_refinement_relative": abs(refined - twenty["Pst_max"]) / refined, "sweep": sweep}
            rows.append(row)
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "burst-sweep.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(label, power, row["minimum_tested_period_s"], refined, flush=True)


if __name__ == "__main__":
    main()
