#!/usr/bin/env python3
"""D-31 part 1 (decision B): R34 retune for the shunt OCP band.

Imports the round-3 threshold model unchanged
(`validation-results/02-protection-timing/round3/thresholds.py`) and reruns
its exhaustive corner search (every resistor vertex, reference ±20 mV,
comparator offset ±4 mV and input bias, at -10 and +85 C board temperature
with the assumed +50 C R5 self-heating) for candidate R34 values in the same
Yageo RT0603BRD07 ±0.1 % / 25 ppm/C family (E192 values). Raising R34 lowers
the threshold voltage and raises the whole band:

    Itrip = [Vref*R33/R32 - (Vref*R35/(R34+R35) + Vos)*(1 + R33/R32)] / R5

Criterion (task 02 round 3): shunt OCP minimum >= 44 A at both temperatures.
Reported alongside: the band maximum, which sets the current at gate-off for
a CT-failed (backup) shunt trip; survival.py shows die VDS <= 350 V for
turn-off up to 330 A, and T1 (CST3015-100ED) is rated 88 A (round 3).

    python3 retune.py  ->  retune.json, retune.md
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R3 = HERE.parents[3] / "02-protection-timing" / "round3" / "thresholds.py"
E192 = [10.5, 10.6, 10.7, 10.9, 11.0, 11.1, 11.3, 11.4, 11.5, 11.7, 11.8, 12.0, 12.1]   # kOhm


def load():
    spec = importlib.util.spec_from_file_location("r3_thresholds", R3)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    m = load()
    base = m.PARTS["R34"]
    rows = []
    for k in E192:
        m.PARTS["R34"] = (k * 1e3, *base[1:])
        band = {t: m.exact_corners(t, 50.0)["shunt_a"] for t in (-10.0, 85.0)}
        lo = min(b["min"] for b in band.values())
        hi = max(b["max"] for b in band.values())
        rows.append({"R34_kohm": k, "min_A": round(lo, 2), "max_A": round(hi, 2),
                     "meets_44A_min": lo >= 44.0, "max_vs_T1_88A": hi <= 88.0})
    m.PARTS["R34"] = base
    first = next((r for r in rows if r["meets_44A_min"]), None)
    res = {"model": str(R3.relative_to(HERE.parents[4])), "criterion": "min >= 44 A at -10 and +85 C (R5 +50 C)",
           "baseline_R34_kohm": base[0] / 1e3, "rows": rows,
           "smallest_R34_meeting_min": first}
    (HERE / "retune.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = ["| R34 kΩ (RT0603BRD07) | band min A | band max A | min ≥ 44 A | max ≤ 88 A (T1) |",
             "| ---: | ---: | ---: | --- | --- |"]
    lines += [f"| {r['R34_kohm']} | {r['min_A']} | {r['max_A']} | {r['meets_44A_min']} | {r['max_vs_T1_88A']} |" for r in rows]
    (HERE / "retune.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("smallest meeting min:", first)


if __name__ == "__main__":
    main()
