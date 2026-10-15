#!/usr/bin/env python3
"""Tests for the B3 airflow region and the HF film-cap body-to-air path (b3-ratings/jet-2026-10-15). No board solves.

    python3 validation-results/04-board-current-thermal/round5-native21/b3-ratings/test_b3_airflow.py
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / "b3-convergence"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(UNIT / "native-21/layout/gates"))
import thermal_body as tb  # noqa: E402
import b3_ratings_gate as gate  # noqa: E402
import run_basis as rb  # noqa: E402
import jet_strip_height as jsh  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


# ---- film-cap body-to-air conductance
area = tb.film_body_area_mm2() * 1e-6
ok(abs(tb.film_body_area_mm2() - (9.0 * 18.0 + 2 * 17.5 * 18.0 + 2 * 9.0 * 17.5)) < 1e-9,
   "exposed area = top + two sides + two ends of the p.14 9.0 x 17.5 x 18.0 mm box (1107 mm^2)")
hs = [1, 5, 10, 35, 60, 100, 150]
gs = [tb.film_body_g_air(h) for h in hs]
ok(all(b > a for a, b in zip(gs, gs[1:])), "g_air rises with h")
ok(all(g <= h * area + 1e-15 for h, g in zip(hs, gs)), "g_air never exceeds the bare-area h A (fin efficiency <= 1)")
ok(abs(tb.film_body_g_air(1e-6) / (1e-6 * area) - 1) < 1e-3, "g_air -> h A as h -> 0 (isothermal body)")
ok(0.80 < tb.film_body_g_air(10) / (10 * area) < 0.83, f"h 10: {tb.film_body_g_air(10) / (10 * area):.3f} of h A")
ok(tb.film_body_g_air(0) == 0.0, "no air path at h 0")
# TDK's own rating: 5.4 A at 100 kHz, ESR typ 14.0 mOhm, self-heating <= 20 K (p.14) => >= 0.0204 W/K body-to-ambient
ok(tb.film_body_g_air(10) < 5.4 ** 2 * 0.014 / 20.0, "h-10 path is below the conductance implied by TDK's 20 K rating")

g_s = tb.film_strong_coupling_g()
ok(g_s > 50 * tb.film_body_g_air(10), f"strong tie {g_s:.3f} W/K >> body-to-air {tb.film_body_g_air(10):.4f} W/K")
b = tb.film_top_bound_rise(60.0, 0.05, tb.film_body_g_air(10))
ok(60.0 - 1.0 < b < 60.0, f"strong-tie bound sits within 1 K of the hot pad (60 K rise -> {b:.2f} K)")
ok(abs(tb.film_top_bound_rise(60.0, 0.05, 0.0) - (60.0 + 0.05 / g_s)) < 1e-12, "no air path: hot pad + P / g_strong")

# ---- region solve: h_top == h with air at the bay is the still-air model, bit for bit; energy closes with a region
nx = ny = 40
board = np.ones((nx, ny), bool)
k = np.full((2, nx, ny), tb.K_CU)
thk = np.array([70e-6, 70e-6])
heat = np.zeros((2, nx, ny))
heat[0, 20, 20] = 0.5
pitch_m = 0.5e-3
part = tb.NetPart("P", 0.2, "test")
part.groups.append((np.array([10 * ny + 10]), np.array([1.0]), 0.05, "pad"))
part.g_air = 0.01
links = [(0, 5, 5, 1, 0.3)]
r0, j0, rec0 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part])
mask = np.zeros((nx, ny), bool)
mask[15:30, 15:30] = True
r1, j1, rec1 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part], top_region=(mask, 10.0, 0.0))
ok(np.array_equal(r0, r1) and np.array_equal(j0, j1), "region at h_top = h, air at the bay: identical solution")
r2, j2, rec2 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part], top_region=(mask, 100.0, 0.0))
ok(r2[0][20, 20] < r0[0][20, 20] and abs(rec2["balance_rel"]) < 1e-8, f"h_top 100 cools the region; balance "
   f"{rec2['balance_rel']:.1e}")
part.t_air = -5.0
r3, j3, rec3 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part], top_region=(mask, 100.0, -5.0))
ok(r3[0][20, 20] < r2[0][20, 20] and abs(rec3["balance_rel"]) < 1e-8, f"cooler jet air cools further; balance "
   f"{rec3['balance_rel']:.1e}")
reg = tb.TopRegion(rb.JET_REGION, 60.0)
ok(reg.contains(38.5, 12.6) and not reg.contains(31.7, 28.2), "R5 is centred in the jet region, C40 is not")

# ---- case grammar and roles
ok(gate.case_ceiling_h("c18_h10") == (18.0, 10) and gate.case_jet("c18_h10") is None, "still-air case parses")
ok(gate.case_ceiling_h("c28_h10_jet100") == (28.0, 10) and gate.case_jet("c28_h10_jet100") == {"h_top": 100.0,
   "air_c": None}, "jet case parses")
ok(gate.case_jet("c26_h10_jet35a50") == {"h_top": 35.0, "air_c": 50.0}, "jet case with its own air temperature")
try:
    gate.case_ceiling_h("c28_jet100")
    ok(False, "a malformed case is refused")
except SystemExit:
    ok(True, "a malformed case is refused")
try:
    gate.run(HERE, ["c28_h10_jet100@61"], None, ["c28_h10_jet100"])
    ok(False, "an airflow case cannot be a release case")
except SystemExit as e:
    ok("cannot be release" in str(e), "an airflow case cannot be a release case")
try:
    gate.parse_cases("c28_h10_jet35@55,c28_h10_jet35@61", None)
    ok(False, "one case at two bays is refused (its run files would collide)")
except SystemExit:
    ok(True, "one case at two bays is refused (its run files would collide)")
ok(all(b["role"] != "airflow" and gate.case_jet(c) is None for c, b in gate.BASIS.items()),
   "the default BASIS has no airflow case")

# ---- one region definition, and the jet-strip keep-out covers it
x0, x1, y0, y1 = rb.JET_REGION
g0, g1, h0, h1 = jsh.REGION
ok(g0 <= x0 and x1 <= g1 and h0 <= y0 and y1 <= h1, f"jet_strip_height keep-out {jsh.REGION} contains the B3 jet "
   f"region {rb.JET_REGION}")

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
