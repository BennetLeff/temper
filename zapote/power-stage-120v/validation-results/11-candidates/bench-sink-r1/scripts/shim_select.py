#!/usr/bin/env python3
"""Bench heatsink r1: choose each FET's shim and FR-4 pad from the measured gaps, and check the lean (README section 5).

    python3 -I scripts/shim_select.py gaps.csv     (from bench-sink-r1/)  -> prints the fit sheet; exit 1 on any reject

gaps.csv columns: ref,g_low,g_up  (mm; feeler gap between the BARE sink face and each package back, clamp OFF, sink pushed
lightly onto the row, at the two gauge heights bench_tolerance.py prints). Optional row 'BR1,g,' for the BR1 dry fit (gap
between the strip face and BR1's back with BR1 standing vertical, leads centred in its holes).
The gap is extrapolated to the board line (the device's pivot); the most-proud device gets no shim; shims are rounded to
the nearest SHIM_STEP. Example input (not a measurement): example-gaps.csv.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402
import bench_mech as M  # noqa: E402
import bench_thermal as BT  # noqa: E402
import bench_tolerance as TOL  # noqa: E402


def main(path):
    rows = {r["ref"].strip(): r for r in csv.DictReader(open(path))}
    cl = BT.clamp(P.PAD_CHOICE)
    mech = M.elastic_limits()
    theta_acc, *_ = TOL.lean_limit(cl, mech, TOL.lean_terms())
    win = TOL.pad_windows(cl)
    z_lo, z_up = TOL.gauge_z()
    fets = [r for r in P.FET_X if r in rows]
    g0, lean = {}, {}
    for r in fets:
        lo, up = float(rows[r]["g_low"]), float(rows[r]["g_up"])
        lean[r] = (up - lo) / (z_up - z_lo)                       # + = top further from the sink
        g0[r] = lo - lean[r] * (z_lo - P.Z_PIVOT)
    mean_lean = sum(lean.values()) / len(lean)
    gmin = min(g0.values())
    ok = True
    print(f"gauge heights z {z_lo:.2f} / {z_up:.2f}; lean limit vs row mean {theta_acc:.4f} rad; shim step {P.SHIM_STEP} mm")
    print("| ref | g0 at board mm | shim mm | pad | spring N | lean vs mean rad | lean ok |")
    print("|---|---|---|---|---|---|---|")
    for r in fets:
        shim = round((g0[r] - gmin) / P.SHIM_STEP) * P.SHIM_STEP
        pad = next((k for k, w in win.items() if w["shim_from"] <= shim <= w["shim_to"]), None)
        if pad is None:
            ok = False
            f = "no window"
        else:
            d = {"FR-4 1.6": (0.0, 0.0), "FR-4 0.8": (P.FR4_T[0] - P.FR4_THIN_T[1], P.FR4_T[1] - P.FR4_THIN_T[0]),
                 "no pad": (P.FR4_T[0], P.FR4_T[1])}[pad]
            f = f"{cl['F_min'] - P.SPRING['k'] * d[1] + P.SPRING['k'] * shim:.1f}-{cl['F_max'] - P.SPRING['k'] * d[0] + P.SPRING['k'] * shim:.1f}"
        dl = lean[r] - mean_lean
        lok = abs(dl) <= theta_acc
        ok &= lok
        print(f"| {r} | {g0[r]:.3f} | {shim:.3f} | {pad} | {f} | {dl:+.4f} | {lok} |")
    if "BR1" in rows:
        g = float(rows["BR1"]["g_low"])
        print(f"BR1 shim {max(0.0, math.floor(g / P.SHIM_STEP) * P.SHIM_STEP):.3f} mm (rounded down: BR1's screw pulls it onto the strip)")
    print("RESULT:", "fit" if ok else "REJECT: a device leans past the limit or no pad window fits (README section 5)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
