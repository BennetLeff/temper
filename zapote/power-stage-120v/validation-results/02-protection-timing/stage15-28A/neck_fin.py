#!/usr/bin/env python3
"""Stage 15: 1-D fin estimate of the local copper rise in each narrow tank-path span (ESTIMATE).

Reads out/sw_widths.json (sw_widths.py). A span is a run of cuts narrower than the IPC 20 K width,
extended to the first cut on each side that meets it. Model: steady 1-D conduction along the copper,
-d/dx(k t w dT/dx) = I^2 rho / (t w), with T = 0 at both span ends (the wide copper there is taken as
isothermal) and NO heat loss to FR-4 or air inside the span. The no-loss assumption overstates the
excess; isothermal ends understate it if the wide sections themselves are hot. So this is an
estimate of the excess over the neighbouring wide copper, not a bound. B3 (task 04) is the gate.
Currents: tank RMS I; the SW_A leg-A link carries only the Q3 half: I / sqrt(2).
usage: python3 neck_fin.py   -> out/neck_fin.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
K, T = 390.0, 70e-6
RHO = 1.72e-8 * (1 + 0.00393 * 75)          # copper at 100 C
SHARE = {"SW_A B.Cu leg-A link, Q3 to Q2": 1 / math.sqrt(2)}


def fin(xs, ws, i):
    n = len(xs)
    if n < 3:
        return 0.0
    x = np.array(xs) * 1e-3
    w = np.array(ws) * 1e-3
    h = x[1] - x[0]
    g = K * T * w                                  # conductance per length
    q = i * i * RHO / (T * w)                      # W/m
    a = np.zeros((n, n)); b = np.zeros(n)
    a[0, 0] = a[-1, -1] = 1.0
    for j in range(1, n - 1):
        gl, gr = 0.5 * (g[j - 1] + g[j]), 0.5 * (g[j] + g[j + 1])
        a[j, j - 1], a[j, j], a[j, j + 1] = -gl / h ** 2, (gl + gr) / h ** 2, -gr / h ** 2
        b[j] = q[j]
    return float(np.linalg.solve(a, b).max())


def main():
    r = json.loads((HERE / "out/sw_widths.json").read_text())
    out = []
    for run in r["runs"]:
        cuts = run["cuts"]
        share = SHARE.get(run["run"], 1.0)
        j = 0
        while j < len(cuts):
            need = lambda c: c["need_mm"] * share ** (1 / 0.725)
            if cuts[j]["width_mm"] >= need(cuts[j]) or cuts[j]["width_mm"] == 0:
                j += 1
                continue
            k = j
            while k < len(cuts) and 0 < cuts[k]["width_mm"] < need(cuts[k]):
                k += 1
            lo, hi = max(j - 1, 0), min(k, len(cuts) - 1)
            seg = cuts[lo:hi + 1]
            xs = [c["at"] for c in seg]
            ws = [max(c["width_mm"], 0.1) for c in seg]
            fr = [c["I_frac"] for c in seg]
            row = {"run": run["run"], "span": [xs[0], xs[-1]], "length_mm": round(xs[-1] - xs[0], 1),
                   "w_min_mm": min(ws), "current_share": round(share, 3)}
            for itank in (22.0, 28.0):
                row[f"excess_{int(itank)}A_K"] = round(fin(xs, ws, itank * share * min(fr)), 1)
            out.append(row)
            j = k + 1
    (HERE / "out/neck_fin.json").write_text(json.dumps(out, indent=1) + "\n")
    for o in out:
        print(o)


if __name__ == "__main__":
    main()
