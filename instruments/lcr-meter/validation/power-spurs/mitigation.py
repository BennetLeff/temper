#!/usr/bin/env python3
"""Task 5 support: quantify host-side mitigations of the 1 kHz combs (USB SOF,
host clock; and a hypothetical board-clock 1 kHz comb) and of DDS-harmonic
collisions, for the Temper grid.

"board" below is a hypothetical board-clock 1 kHz comb (no such periodic task
runs in this build; see alias_map.py); "SOF" is the real host frame comb.
Options:
  current   : 1000, 35000, 40000, 50000, 60000 Hz, 16384-sample record
  shift     : +500 Hz (1500, 35500, ...), 16384 samples
  shift+T   : +500 Hz, 16000 samples, so the record is exactly 16*N ms and
              every half-integer-kHz comb offset is an integer number of bins
For each: worst fit response to any comb line h*1 kHz (h <= 300) with the
host-clock offset swept over +-560 ppm (SOF) or exactly 0 (board task), and
the lowest DDS harmonic order folding into the main lobe.
Writes mitigation.json.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

import common as c
from alias_map import dds_collision_order

HERE = pathlib.Path(__file__).resolve().parent
EPS = c.USB_SOF_TOL + c.XTAL_TOL


def comb_worst(f, fs, count, eps_list, hmax=300, window=None):
    fit = c.Fit(f, fs, count, window)
    worst = 0.0
    arg = None
    for h in range(1, hmax + 1):
        lines = h * 1000.0 * (1 + np.asarray(eps_list))
        r = fit.response(c.alias(lines, fs))
        k = int(np.argmax(r))
        if r[k] > worst:
            worst, arg = float(r[k]), (h, float(eps_list[k]))
    return worst, arg


def best_divider(hz, kcap=200):
    """Divider (1..20, >= 8 samples/cycle, >= 10 cycles in 16384 samples) that
    maximises the lowest DDS harmonic order folding into the fit main lobe."""
    a = c.acquisition(hz)
    f = a["f_dds_hz"]
    best = None
    for n in range(1, c.MAX_DIVIDER + 1):
        fs = c.CONVERSION_RATE_HZ / n
        if fs < 8 * f or c.DEFAULT_COUNT * f / fs < 10:
            continue
        k = dds_collision_order(f, fs, c.DEFAULT_COUNT / fs) or kcap + 1
        if best is None or k > best[1]:
            best = (n, k)
    return best


def divider_study():
    """For every integer frequency where divider_for leaves a DDS harmonic
    k <= 20 in the main lobe, find the best alternative divider."""
    import numpy as np_
    rows = []
    for hz in range(100, 100001):
        a = c.acquisition(hz)
        k0 = dds_collision_order(a["f_dds_hz"], a["fs_hz"], a["record_s"], kmax=20)
        if k0 is None:
            continue
        n, k = best_divider(hz)
        rows.append({"hz": hz, "host_divider": a["divider"], "host_k": k0, "best_divider": n, "best_k": k})
    ks = np_.array([r["best_k"] for r in rows])
    return {"frequencies_with_k_le_20": len(rows), "fixed_to_k_ge_50": int(np_.sum(ks >= 50)),
            "fixed_to_k_gt_200": int(np_.sum(ks > 200)), "worst_after": int(ks.min()) if ks.size else None,
            "examples": rows[:6] + [r for r in rows if r["hz"] in (5000, 10000, 50000, 100000)]}


def main():
    options = {"current": (c.TEMPER_GRID, c.DEFAULT_COUNT, None),
               "shift": ([x + 500 for x in c.TEMPER_GRID], c.DEFAULT_COUNT, None),
               "shift+T": ([x + 500 for x in c.TEMPER_GRID], 16000, None),
               "shift+Hann": ([x + 500 for x in c.TEMPER_GRID], c.DEFAULT_COUNT, "hann")}
    sof_eps = np.linspace(-EPS, EPS, 113)
    realistic = np.linspace(-150e-6, 150e-6, 31)   # typical host + board crystals
    out = {}
    for name, (grid, count, window) in options.items():
        rows = []
        for hz in grid:
            a = c.acquisition(hz)
            f, fs = a["f_dds_hz"], a["fs_hz"]
            board, barg = comb_worst(f, fs, count, [0.0], window=window)
            sof, sarg = comb_worst(f, fs, count, sof_eps, window=window)
            sof_r, _ = comb_worst(f, fs, count, realistic, window=window)
            rows.append({"hz": hz, "divider": a["divider"], "count": count, "window": window or "none",
                         "record_ms": count / fs * 1e3,
                         "board_1khz_comb_worst": board, "board_at": barg,
                         "sof_worst_560ppm": sof, "sof_at": sarg, "sof_worst_150ppm": sof_r,
                         "dds_lowest_collision_k": dds_collision_order(f, fs, count / fs)})
        out[name] = rows
    out["divider_study"] = divider_study()
    out["temper_grid_best_divider"] = {str(int(hz)): best_divider(hz) for hz in c.TEMPER_GRID}
    (HERE / "mitigation.json").write_text(json.dumps(out, indent=1))
    print("divider study:", json.dumps(out["divider_study"]))
    print("best divider on the Temper grid (N, lowest k):", out["temper_grid_best_divider"])
    for name, rows in out.items():
        if not isinstance(rows, list):
            continue
        print(f"== {name}")
        for r in rows:
            print(f"  {r['hz']:>7.0f} Hz N={r['divider']:>2} T={r['record_ms']:7.2f} ms | board 1 kHz comb (hypothetical) worst {c.db(r['board_1khz_comb_worst']):7.1f} dB "
                  f"| SOF worst +-560ppm {c.db(r['sof_worst_560ppm']):6.1f} dB (h,eps={r['sof_at']}) +-150ppm {c.db(r['sof_worst_150ppm']):6.1f} dB "
                  f"| DDS lowest k in lobe: {r['dds_lowest_collision_k']}")


if __name__ == "__main__":
    main()
