"""Tune-to-inductance helper (BUILD-AND-MEASURE.md step T). Bench numbers in, the next move out.

Given the MEASURED free-air L at 40 kHz of the coil as it is wound now (outer turns 7.46 = with the spare turn, 6.46 = R1,
5.96, ...), it scales the model's trim curve (results/free_air.json R1 states) by measured / model at that state and
lists every reachable state with its predicted L, the model's loaded L on cast iron / 430 and the rim heating share
(results/trim_heating.json). Rules (README D2):
  - target window 76-86 uH free-air (R1 81 uH +/- ~6 %; the system check holds across it), first choice nearest 81;
  - never trim below 5.46 outer turns: at 4.96 the cast-iron loaded L (39.8 uH) falls under the spec row-3 floor 41.5;
  - if the scaled curve misses the window at every allowed state, do NOT force it: the model is off by > ~5 %; record
    the ratio, keep the coil for measurement, and re-split the next former (L_fit in free_air.json, ratio applied).
Usage: .venv/bin/python model/tune.py --L 88.4 --outer 7.46 [--target 81]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FREE = json.loads((HERE / "results" / "free_air.json").read_text())
TRIM = json.loads((HERE / "results" / "trim_heating.json").read_text())["rows"]
STATES = ["R1_plus_spare", "R1", "R1_trim-0.5", "R1_trim-1", "R1_trim-1.5", "R1_trim-2"]
WINDOW, MIN_OUTER = (76.0, 86.0), 5.46


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--L", type=float, required=True, help="measured free-air L at 40 kHz, uH (coil + bars, leads dressed)")
    ap.add_argument("--outer", type=float, required=True, help="outer turns wound now (7.46 with the spare turn)")
    ap.add_argument("--target", type=float, default=81.0)
    a = ap.parse_args()
    c = FREE["candidates"]
    model = {s: c[s]["L_free_uH"] for s in STATES}
    outer = {s: c[s]["sections"][1]["turns"] for s in STATES}
    now = min(STATES, key=lambda s: abs(outer[s] - a.outer))
    if abs(outer[now] - a.outer) > 0.05:
        raise SystemExit(f"outer turns {a.outer} is not a modelled state ({sorted(outer.values())})")
    k = a.L / model[now]
    print(f"state now {now}: model {model[now]:.1f} uH, measured {a.L:.1f} uH -> ratio {k:.3f} ({(k - 1) * 100:+.1f} %)")
    ok = []
    for s in STATES:
        pred = k * model[s]
        th = {r["pan"]: r for r in TRIM if r["state"] == s}
        allowed = outer[s] >= MIN_OUTER - 1e-6 and outer[s] <= outer[now] + 1e-6
        flag = "" if allowed else ("  (needs turns added: not reachable)" if outer[s] > outer[now] else "  (below 5.46 outer: not allowed)")
        inwin = WINDOW[0] <= pred <= WINDOW[1]
        print(f"  {s:14s} outer {outer[s]:.2f}: predicted {pred:5.1f} uH {'in window' if inwin else 'outside':10s} "
              f"loaded CI {th['cast_iron']['L_loaded_uH'] * k:4.1f} / 430 {th['ss430']['L_loaded_uH'] * k:4.1f} uH, rim {th['ss430']['rim_share'] * 100:.0f} %{flag}")
        if allowed and inwin:
            ok.append((abs(pred - a.target), s, pred))
    if ok:
        _, s, pred = min(ok)
        n = round((outer[now] - outer[s]) * 2)
        print(f"-> go to {s}: unwind {n} half-turn(s) from the outer end ({n * 180} deg), dress the lead, re-measure (expect {pred:.1f} uH)")
    else:
        print("-> no allowed state lands in 76-86 uH: keep the coil as wound, record the ratio, re-split the next former")
    print("note: loaded-L values are the model's scaled by the free-air ratio; measure them on your pans (step M3)")


if __name__ == "__main__":
    main()
