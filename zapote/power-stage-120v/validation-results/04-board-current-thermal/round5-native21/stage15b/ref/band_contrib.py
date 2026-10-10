#!/usr/bin/env python3
"""Stage 15: what sets the shunt-OCP band width (so we know what a tighter band would cost).

Re-runs task-02 round-3 thresholds.exact_corners (read-only import) for one divider with individual
error sources switched off: comparator offset scaled, resistor tolerances zeroed per group, R5 drift zeroed.
usage: python3 band_contrib.py [UNIT] [R34] [R35]   -> out/band_contrib.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
UNIT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
R34 = float(sys.argv[2]) if len(sys.argv) > 2 else 12.6e3
R35 = float(sys.argv[3]) if len(sys.argv) > 3 else 11.7e3
spec = importlib.util.spec_from_file_location("thr", UNIT / "validation-results/02-protection-timing/round3/thresholds.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE = dict(m.PARTS)
ORIG_THRESH = m.thresholds
RT = (0.001, 25e-6)


def run(over, vos_scale=1.0):
    def th(p, ref, vos, v3v3=3.3, clamp_v=0.0):
        return ORIG_THRESH(p, ref, vos * vos_scale, v3v3, clamp_v)
    m.thresholds = th
    m.PARTS.clear(); m.PARTS.update(BASE); m.PARTS.update(over)
    res = [m.exact_corners(t, 50.0)["shunt_a"] for t in (-10.0, 85.0)]
    m.thresholds = ORIG_THRESH
    m.PARTS.clear(); m.PARTS.update(BASE)
    return round(min(r["min"] for r in res), 2), round(max(r["max"] for r in res), 2)


def main():
    div = {"R34": (R34, *RT), "R35": (R35, *RT)}
    cases = {
        "all (committed method)": (div, 1.0),
        "comparator offset+bias x0 (ideal comparator)": (div, 0.0),
        "comparator offset x0.25 (1 mV-class part)": (div, 0.25),
        "R32/R33 ideal": ({**div, "R32": (10e3, 0, 0), "R33": (10e3, 0, 0)}, 1.0),
        "R34/R35 ideal": ({"R34": (R34, 0, 0), "R35": (R35, 0, 0)}, 1.0),
        "R5 ideal (no tol, no TCR)": ({**div, "R5": (0.001, 0, 0)}, 1.0),
        "R32-R35 0.05 % 10 ppm": ({"R34": (R34, 5e-4, 10e-6), "R35": (R35, 5e-4, 10e-6),
                                   "R32": (10e3, 5e-4, 10e-6), "R33": (10e3, 5e-4, 10e-6)}, 1.0),
    }
    out = {}
    for name, (over, vs) in cases.items():
        lo, hi = run(over, vs)
        out[name] = {"band_A": [lo, hi], "width_A": round(hi - lo, 2)}
        print(f"{name:46s} {lo:7.2f} {hi:7.2f}  width {hi - lo:6.2f}")
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/band_contrib.json").write_text(json.dumps({"R34": R34, "R35": R35, "cases": out}, indent=1) + "\n")


if __name__ == "__main__":
    main()
