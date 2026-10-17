#!/usr/bin/env python3
"""Tests for the B3 hot-copper fixed point (OPEN-ITEMS S17). No board solves.

    python3 validation-results/04-board-current-thermal/round5-native21/b3-ratings/test_b3_hot_copper.py
"""
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "b3-convergence"))
sys.path.insert(0, str(HERE.parent / "b3"))
sys.path.insert(0, str(HERE))
import thermal_body as tb  # noqa: E402
import thermal as T  # noqa: E402
import b3_ratings_gate as gate  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


ok(tb.ALPHA_CU == T.ALPHA_CU == 0.00393, "one alpha: thermal / thermal_body = sheet_solver.ALPHA_CU 0.00393 /K")

# ---- closed form: a uniformly heated sheet, convection only (no lateral gradient)
n, pitch_m, h, t0 = 12, 1e-3, 10.0, 61.0
board = np.ones((n, n), bool)
k = np.full((1, n, n), 390.0)
thk = np.array([35e-6])
q20 = np.full((1, n, n), 2e-3)                    # W per cell
g = 2 * h * pitch_m ** 2
a = tb.ALPHA_CU
exact = q20[0, 0, 0] * (1 + a * (t0 - 20)) / (g - a * q20[0, 0, 0])
rise, _, rec = tb.solve_system(board, k, thk, q20.copy(), h, pitch_m, [], tcr={"q20": q20, "alpha": a, "t_abs0_c": t0})
ok(abs(rise.mean() - exact) < 1e-6 and np.ptp(rise) < 1e-6, f"uniform sheet: {rise.mean():.6f} K = closed form "
   f"{exact:.6f} K")
ok(abs(rec["balance_rel"]) < 1e-9 and abs(rec["tcr"]["q_hot_w"] - rec["source_w"]) < 1e-12,
   f"energy closes on the hot loss (balance {rec['balance_rel']:.1e})")
cold, _, _ = tb.solve_system(board, k, thk, q20.copy(), h, pitch_m, [])
ok(abs(cold.mean() - q20[0, 0, 0] / g) < 1e-6, "no tcr: the 20 C model")

# ---- a non-uniform case against a naive Picard loop on the plain operator
heat = np.zeros((1, n, n))
heat[0, 3:6, 4:8] = 0.05
part = tb.NetPart("P", 0.1, "test")
part.groups.append((np.array([8 * n + 8]), np.array([1.0]), 0.05, "pad"))
part.g_air = 0.004
r_fix, j_fix, rec_fix = tb.solve_system(board, k, thk, heat.copy(), h, pitch_m, [], [part],
                                        tcr={"q20": heat, "alpha": a, "t_abs0_c": t0})
x = None
r_it = np.zeros_like(heat)
for _ in range(200):
    q = heat * (1 + a * (t0 + r_it - 20))
    r_new, j_it, _ = tb.solve_system(board, k, thk, q, h, pitch_m, [], [part])
    d = np.abs(r_new - r_it).max()
    r_it = r_new
    if d < 1e-9:
        break
ok(np.abs(r_fix - r_it).max() < 1e-4 and abs(j_fix[0] - j_it[0]) < 1e-4,
   f"fixed point = naive Picard loop (max diff {np.abs(r_fix - r_it).max():.1e} K)")
ok(rec_fix["tcr"]["picard_steps"] >= 1 and rec_fix["tcr"]["max_dT_k"] < tb.TCR_TOL_K, "Picard check recorded and settled")

# ---- runaway: dq/dT above the convective conductance
big = np.full((1, n, n), 1.2 * g / a)
try:
    tb.solve_system(board, k, thk, big.copy(), h, pitch_m, [], tcr={"q20": big, "alpha": a, "t_abs0_c": t0})
    ok(False, "thermal runaway is refused")
except RuntimeError as e:
    ok("runaway" in str(e), "thermal runaway is refused")

# ---- legacy solve_stack gives the same uniform-sheet fixed point
r_leg, rec_leg = T.solve_stack(board, k, thk, q20.copy(), h, pitch_m, tcr=(q20, a, t0))
ok(abs(r_leg.mean() - exact) < 1e-5, f"legacy thermal.solve_stack hot copper = closed form ({r_leg.mean():.6f} K)")

# ---- gate: copper basis of run files
hot = {"model": "hot-iterated", "alpha_per_k": a, "air_c": 61.0, "max_heated_copper_c": 120.0, "loss_multiplier": 1.3,
       "max_dT_k": 1e-5}
r_hot, r_cold, r_old = {"copper_temp_model": hot}, {"copper_temp_model": {"model": "cold-20C", "alpha_per_k": 0.0}}, {}
ok(gate.copper_check("c", r_hot, r_hot, 61.0, False)["model"] == "hot-iterated", "hot runs at the case bay are accepted")
for name, r in (("cold-20C", r_cold), ("unrecorded", r_old)):
    try:
        gate.copper_check("c", r, r, 61.0, False)
        ok(False, f"{name} copper refused without --allow-cold-copper")
    except SystemExit:
        ok(True, f"{name} copper refused without --allow-cold-copper")
    ok(gate.copper_check("c", r, r, 61.0, True) is None, f"{name} copper accepted with --allow-cold-copper")
try:
    gate.copper_check("c", r_hot, r_hot, 55.0, False)
    ok(False, "a hot run solved at another bay is refused")
except SystemExit:
    ok(True, "a hot run solved at another bay is refused (no shift)")
try:
    gate.copper_check("c", r_hot, r_cold, 61.0, True)
    ok(False, "mixed hot / cold meshes refused")
except SystemExit:
    ok(True, "mixed hot / cold meshes refused")

# ---- rail-monitor probe rows (OPEN-ITEMS S16)
def probe(t, nets):
    return {"layer": "F.Cu", "pad_max_cell_c": t, "pad_mean_c": t, "pad_max_padmean_c": t, "cells": 4, "nets": nets}


nets = {"U17": ["monitor_ls-ref", "n_ls"], "U19": ["bias_ha.monitor-ref", "n_ha"], "U21": ["bias_hb.monitor-ref", "n_hb"],
        "U29": ["monitor_ls-good", "n_ls", "v15_ls"], "U30": ["bias_ha.monitor-good", "n_ha", "p_ha"],
        "U31": ["bias_hb.monitor-good", "n_hb", "p_hb"], "U16": ["bias_ls-fb", "leg_ret", "n_ls"],
        "U18": ["bias_ha.split-fb", "n_ha", "sw_a"], "U20": ["bias_hb.split-fb", "n_hb", "sw_b"],
        "R59": ["monitor_ls-ref", "v15_ls"], "R80": ["monitor_ls-halfref", "n_ls"], "R5": ["leg_ret", "x"],
        "U5": ["ocp_kelvin_p", "ref25", "u_ref-nc"], "U3": ["v15_ls", "ocp_kelvin_p", "hot5_en", "u_ldo-nc", "hot5"],
        "R138": ["v15_ls", "monitor_ls-ldo_en"], "R139": ["monitor_ls-ldo_en", "n_ls"]}
pr = {r: probe(70.0, n) for r, n in nets.items()}
S42 = {**{r: "TL431AIDBZR" for r in ("U17", "U19", "U21")}, **{r: "LM339BIDR" for r in ("U29", "U30", "U31")},
       **{r: "TLVH431BQDBZR" for r in ("U16", "U18", "U20")}, "U5": "LM4040A25IDBZR", "U3": "TPS70950QDBVRQ1"}
S46 = {**S42, **{r: "TL431BQDBZR" for r in ("U17", "U19", "U21")}, **{r: "LM2901BIDR" for r in ("U29", "U30", "U31")}}
S47 = {**S46, "U5": "LM4050AEM3-2.5/NOPB"}
rows = gate.probe_rows("c", {"probes": pr}, {"probes": pr}, 61.0, mpns=S42)
byref = {r["item"].split(":")[0]: r for r in rows}
ok(all(byref[r]["gated"] for r in gate.MONITORS) and len(gate.MONITORS) == 11, "eleven gated rows (U5 from stage 47, U3 from 48)")
ok(abs(byref["U17"]["est_c"] - (70.0 + 11.0 + gate.MONITOR_SELF["tl431"] * 206.0)) < 1e-9 and byref["U17"]["limit_c"] == 85.0,
   f"TL431 row = pad + bay shift + P RthJA ({byref['U17']['self_heat_k']} K), limit 85 C")
ok(byref["U16"]["limit_c"] == 125.0 and byref["U29"]["limit_c"] == 85.0, "TLVH431BQ 125 C, LM339B 85 C")
# stage 46: the limit follows the MPN's grade (the 125 C grades of the same pinouts), the estimate does not move
rows46 = {r["item"].split(":")[0]: r for r in gate.probe_rows("c", {"probes": pr}, {"probes": pr}, 61.0, mpns=S46)}
ok(all(rows46[r]["limit_c"] == 125.0 for r in ("U17", "U19", "U21", "U29", "U30", "U31")) and
   all(rows46[r]["est_c"] == byref[r]["est_c"] for r in gate.MONITORS) and "LM2901BIDR" in rows46["U29"]["item"],
   "TL431BQ / LM2901B rows: limit 125 C from the MPN grade, same estimate")
# stage 47 (c47-ref25-grade): U5 (REF25) is a gated row; LM4040A25I 85 C, LM4050AEM3-2.5 125 C, self-heat at the
# 0.24 mA operating maximum through 326 K/W (SNOS455H p.11 note 1)
ok(byref["U5"]["limit_c"] == 85.0 and "LM4040A25IDBZR" in byref["U5"]["item"] and
   abs(byref["U5"]["est_c"] - (70.0 + 11.0 + gate.MONITOR_SELF["ref25"] * 326.0)) < 1e-9 and 0.1 < byref["U5"]["self_heat_k"] < 0.3,
   f"U5 LM4040A25I row: pad + bay shift + P RthJA ({byref['U5']['self_heat_k']} K), limit 85 C")
rows47 = {r["item"].split(":")[0]: r for r in gate.probe_rows("c", {"probes": pr}, {"probes": pr}, 61.0, mpns=S47)}
ok(rows47["U5"]["limit_c"] == 125.0 and rows47["U5"]["est_c"] == byref["U5"]["est_c"] and "LM4050AEM3" in rows47["U5"]["item"],
   "U5 LM4050AEM3-2.5 row: limit 125 C from the MPN grade, same estimate")
ok(abs(gate.MONITOR_SELF["ref25"] - 0.2382e-3 * 2.5162) < 2e-6, "U5 self-heat power = 0.238 mA x 2.5162 V")
bom46 = gate.bom_mpns()
ok(all(bom46[r] == S47[r] for r in gate.MONITORS), "the frozen native-21 BOM carries the stage-46 / 47 / 48 grades at the eleven refs")
# stage 48 (c48-ldo-en-ref-watch): U3 (HOT5 LDO) is a gated TJ row, pad copper + its 0.160 W bound x psi_JB 40.7 K/W
ok(byref["U3"]["limit_c"] == 125.0 and "TPS70950QDBVRQ1" in byref["U3"]["item"] and
   abs(byref["U3"]["est_c"] - (70.0 + 11.0 + 0.160 * 40.7)) < 1e-9, f"U3 TPS70950-Q1 row: pad + bay shift + 0.160 W psi_JB, TJ 125 C")
# ... and its heat goes into its connected pads only: pin 4 is NC, "No internal connection" (SLVSCE6D Table 4-1 p.3)
import json  # noqa: E402
hs = {r["ref"]: r for r in json.loads((HERE.parent / "b3/inputs/native21-board-heat-sources.json").read_text())["parts"]}
ok(hs["U3"]["watts_nominal"] == 0.160 and hs["U3"].get("pad_numbers") == ["1", "2", "3", "5"],
   "U3 heat source: 0.160 W on pads 1 / 2 / 3 / 5, none on the NC pin 4")
ok(not byref["R138"]["gated"] and not byref["R139"]["gated"] and
   abs(byref["R138"]["limit_c"] - (155 - 85 * (gate.V_PN * 100 / 127) ** 2 / 100e3 / 0.08)) < 1e-9,
   "LDO EN divider R138 / R139 advisory rows (100 k / 27 k, terminal derating line)")
for name, bad in (("unknown MPN", {**S47, "U29": "LM339DR"}), ("MPN of another kind", {**S47, "U17": "LM2901BIDR"}),
                  ("ref missing from the BOM", {k: v for k, v in S47.items() if k != "U30"}),
                  ("U5 on the industrial LM4050AIM3 (no grade row)", {**S47, "U5": "LM4050AIM3-2.5/NOPB"}),
                  ("U5 on a TL431 (another kind)", {**S47, "U5": "TL431BQDBZR"}),
                  ("U3 on the commercial TPS70950DBVR (no grade row)", {**S47, "U3": "TPS70950DBVR"})):
    try:
        gate.probe_rows("c", {"probes": pr}, {"probes": pr}, 61.0, mpns=bad)
        ok(False, f"probe rows refuse: {name}")
    except SystemExit:
        ok(True, f"probe rows refuse: {name}")
ok(not byref["R59"]["gated"] and abs(byref["R59"]["limit_c"] - (155 - 85 * (gate.V_PN - gate.VREF_TL431) ** 2 / 2200 / 0.2)) < 1e-9,
   "R59 (2.2 k reference feed) advisory, derating line at its power")
ok("R5" not in byref, "resistors off the monitor nets are not probe rows")
for name, bad in (("no probes", {}), ("moved ref", {"probes": {**pr, "U17": probe(70.0, ["n_ls", "x"])}}),
                  ("unknown divider", {"probes": {**pr, "R200": probe(70.0, ["monitor_ls-uv", "v15_ls"])}}),
                  ("U5 moved off ref25", {"probes": {**pr, "U5": probe(70.0, ["ocp_kelvin_p", "hot5"])}}),
                  ("U3 EN back on IN", {"probes": {**pr, "U3": probe(70.0, ["v15_ls", "ocp_kelvin_p", "hot5"])}})):
    try:
        gate.probe_rows("c", bad, bad, 61.0, mpns=S47)
        ok(False, f"probe rows refuse: {name}")
    except SystemExit:
        ok(True, f"probe rows refuse: {name}")

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
