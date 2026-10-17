#!/usr/bin/env python3
"""DECISIONS item 14 "Still open": blower stall at the 28 A ceiling, h 10. Regenerates results.json.

    python3 h10_stall.py          (about 3-5 minutes; needs numpy, scipy, shapely, matplotlib)

Needs the A4 heat arrays outputs/*-heat.npz (gitignored; written by ../run_cases.py) next to the committed
A4 case json files, exactly as b3/run_study.py does.

(a) steady state at h 10 at the derated tank current, by the committed b3/thermal.py (the scripts the
    stage-15b ceiling sweep uses);
(b) the transient: a lumped sink / junction bound and a finite-volume board transient on the same matrix as
    thermal.py with heat capacities added (adiabatic during the window, so it is an upper bound on the
    window), driven by the firmware timeline of firmware/components/control/thermal_mgmt.[ch].

The controls at the top reproduce the committed 28 A h 25 peak (134.1 C, README stage 15b) and the 198 C
h 10 figure (DECISIONS item 14) and assert them within 0.5 K.
"""
import csv
import shutil
import gzip
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import LinearOperator, cg

HERE = Path(__file__).resolve().parent
R5 = HERE.parent
UNIT = HERE.parents[3]
B3 = R5 / "b3"
sys.path.insert(0, str(B3))
import run_study as rs  # noqa: E402
import thermal as th  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="h10stall_"))
RESULTS = {"inputs": {}, "controls": {}, "assumptions": {}}

# ------------------------------------------------------------------ inputs and limits (all cited in README)
CEILING_A = 28.0                    # commissioned ceiling, DECISIONS item 14
CAP_PCT = 25                        # BLOWER_STALL_POWER_CAP_PCT (thermal_mgmt.h:278)
STALL_RISE_K = 2.0                  # BLOWER_STALL_RISE_K (thermal_mgmt.h:279)
STALL_TIME_S = 1.0                  # BLOWER_STALL_TIME_MS
TACH_WINDOW_S = 0.25                # BLOWER_TACH_WINDOW_MS
TICK_S = 0.1                        # BLOWER_TICK_S (main/thermal_io.c:52)
APPLY_S = 0.5                       # ASSUMED: cap -> tank power loop settled (not in the committed firmware)
T_DET_S = TACH_WINDOW_S + STALL_TIME_S + 2 * TICK_S      # 1.45 s: worst-case tach window + >1 s + two ticks
T_DER_S = T_DET_S + APPLY_S                              # derate in force
FW_SINK_TRIP_C = 95.0               # OVER_TEMP_THRESHOLD, DECISIONS 14-16
HW_SINK_TRIP_C = {"low": 98.3, "nom": 101.4, "high": 104.6}
TJ_MAX_C, TJ_TARGET_C = 150.0, 125.0     # IPW65R018CFD7 maximum; design target (trip-ladder doc)
BOARD_TG_C = 150.0                  # NP-155F Tg, native-17/stackup.json
BOARD_TIERS_C = {"gate_105": 105.0, "fr4_class_130": 130.0, "accepted_h25_28A_134p1": 134.1}
I_FACTOR = 1.05                     # run_study.py convention: sustained current = 1.05 x ceiling (firmware RMS trip)
I_DER_A = CEILING_A * math.sqrt(CAP_PCT / 100.0)         # tank power ~ I^2 -> 14 A
R_SA, R_PED = 0.29, 0.0161          # board_side.py docstring: R_SA 0.29 + 0.0161 pedestal (C/W)
R_TOT = R_SA + R_PED
R_JS = 0.28 + 0.634                 # theta_jc + theta_cs, trip-ladder doc
H_FORCED, H_STILL = 25.0, 10.0
T_AMB = 50.0

# ------------------------------------------------------------------ B3 wrapper
HEAT_C28 = json.loads(rs.HEAT_C28.read_text())
TANK_ROWS = {"R5", "R39", "C21", "C22", "C23", "C151", "C152", "C5", "C6"}   # rows that scale with I_t^2


def b3_solve(tag, i_t, h, keep_npz=True):
    """thermal.py at tank RMS i_t [A]; tank-current rows of the c28 heat file scaled by (i_t/29.4)^2."""
    heat = json.loads(json.dumps(HEAT_C28))
    k = (i_t / 29.4) ** 2
    for p in heat["parts"]:
        if p["ref"] in TANK_ROWS:
            p["watts_nominal"] *= k
            p["watts_worst"] *= k
    hp = TMP / f"heat_{tag}.json"
    hp.write_text(json.dumps(heat))
    rs.OPS[tag] = {"I_t": i_t, "I_line": 11.1, "parts": "nominal", "heat": "c28"}   # line current held (conservative)
    out = TMP / f"{tag}.json"
    subprocess.run([sys.executable, str(B3 / "thermal.py"), "--geometry", str(rs.GEOM), "--case", rs.cases(tag),
                    "--pitch-mm", "1.0", "--h", str(h), "--a6-heat", str(hp), "--a6-mode", "nominal",
                    "--output", str(out)], check=True, stdout=subprocess.DEVNULL)
    r = json.loads(out.read_text())
    z = np.load(out.with_suffix(".npz"))
    x, y, rise = z["x_mm"], z["y_mm"], z["rise_k"]
    ix, iy = x <= 80, y <= 12.5
    fet_row = float(T_AMB + rise[:, ix][:, :, iy].max())
    parts = sorted(r["a6_parts_applied"], key=lambda q: -q["conditional_pad_cell_max_c"])[:4]
    row = {"I_t_A": i_t, "h": h, "peak_c": r["peak"]["temperature_c"], "peak_x_mm": r["peak"]["x_mm"],
           "peak_y_mm": r["peak"]["y_mm"], "peak_layer": r["peak"]["layer"], "fet_row_max_c": fet_row,
           "source_w": r["balance"]["source_w"], "balance_w": r["balance"]["balance_w"],
           "hottest_part_pad_cells": [(q["ref"], round(q["conditional_pad_cell_max_c"], 1)) for q in parts]}
    return row, z, r


# ------------------------------------------------------------------ controls
RESULTS["inputs"] = {
    "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip(),
    "geometry": str(rs.GEOM.relative_to(UNIT)), "heat_file": str(rs.HEAT_C28.relative_to(UNIT)),
    "ceiling_sweep_committed": "validation-results/04-board-current-thermal/round5-native21/b3/outputs/ceiling_sweep.json"}
ctrl25, z25, _ = b3_solve("ctl_c28_h25", 1.05 * CEILING_A, 25)
ctrl10, z10, _ = b3_solve("ctl_c28_h10", 1.05 * CEILING_A, 10)
committed_sweep = json.loads((B3 / "outputs/ceiling_sweep.json").read_text())
c28_committed = [e for e in committed_sweep if e["ceiling_A"] == 28.0][0]["peak"]["temperature_c"]
RESULTS["controls"] = {
    "h25_28A_peak_c": ctrl25["peak_c"], "h25_28A_target_c": 134.1, "h25_28A_committed_sweep_json_c": c28_committed,
    "h10_28A_peak_c": ctrl10["peak_c"], "h10_28A_target_c": 198.0,
    "h25_peak_location": (ctrl25["peak_x_mm"], ctrl25["peak_y_mm"], ctrl25["peak_layer"]),
    "h10_peak_location": (ctrl10["peak_x_mm"], ctrl10["peak_y_mm"], ctrl10["peak_layer"]),
    "note": "README stage 15b quotes 134.1 (board 9a9c43c6); stage 16 (board e9481ed6) re-ran the committed sweep to "
            "133.9, which is the committed outputs/ceiling_sweep.json value."}
assert abs(ctrl25["peak_c"] - 134.1) <= 0.5, ctrl25
assert abs(ctrl25["peak_c"] - c28_committed) <= 1e-6 + 0.01, (ctrl25["peak_c"], c28_committed)
assert abs(ctrl10["peak_c"] - 198.0) <= 0.5, ctrl10
print("controls OK:", round(ctrl25["peak_c"], 2), round(ctrl10["peak_c"], 2), flush=True)

# ------------------------------------------------------------------ (a) derated steady state at h 10
sweep = {}
for label, i_c in (("tank_stopped_0A", 0.0), ("cap_as_current_7A", CEILING_A * CAP_PCT / 100.0),
                   ("cap_5pct_6p3A", CEILING_A * math.sqrt(0.05)), ("cap_10pct_8p9A", CEILING_A * math.sqrt(0.10)),
                   ("cap_15pct_10p8A", CEILING_A * math.sqrt(0.15)),
                   ("cap_as_power_14A", I_DER_A), ("21A", 21.0), ("ceiling_28A", CEILING_A)):
    row, zz, _ = b3_solve("sw_" + label, I_FACTOR * i_c, 10)
    row["ceiling_equiv_A"] = i_c
    sweep[label] = row
    if label == "cap_as_power_14A":
        z14 = zz
    if label == "tank_stopped_0A":
        z0 = zz
    print("h10", label, round(row["peak_c"], 1), row["hottest_part_pad_cells"][:2], flush=True)
row14h25, _, _ = b3_solve("sw_14A_h25", I_FACTOR * I_DER_A, 25)
RESULTS["a_steady_h10"] = {"cap_pct": CAP_PCT, "derated_ceiling_A": I_DER_A, "I_t_used_A": I_FACTOR * I_DER_A,
                           "sweep": sweep, "derated_14A_at_h25_reference": row14h25}

# ------------------------------------------------------------------ (b) lumped sink / junction bound
rows = [r for r in csv.DictReader(open(UNIT / "validation-results/05-resonant-tank-envelope/round6-full-power/outputs/board-side-fets.csv"))
        if float(r["line_V"]) == 120.0]


def fet_table(f_khz):
    r = sorted([q for q in rows if float(q["f_kHz"]) == f_khz], key=lambda q: float(q["I_tank_A"]))
    i = np.array([float(q["I_tank_A"]) for q in r])
    p = np.array([float(q["A_sink_W"]) for q in r])
    d = np.array([float(q["A_tj_max_C"]) for q in r]) - (T_AMB + R_TOT * p)       # Tj - T_sink_base, worst FET
    return i, p, d


S8 = {"base_mm": 8.0, "stack_mm": 67.5, "length_mm": 117.0, "fins": 15, "fin_t_mm": 1.5, "fin_h_mm": 40.0}   # m11 SINK-DRAWING-NOTES
RHO_AL, CP_AL = 2700.0, 900.0        # 6063 handbook values (not in the repo)
v_base = S8["base_mm"] * S8["stack_mm"] * S8["length_mm"] * 1e-9
v_fins = S8["fins"] * S8["fin_t_mm"] * S8["fin_h_mm"] * S8["length_mm"] * 1e-9
C_BASE, C_FULL = RHO_AL * CP_AL * v_base, RHO_AL * CP_AL * (v_base + v_fins)
fin_area = S8["fins"] * 2 * S8["fin_h_mm"] * S8["length_mm"] * 1e-6 + S8["stack_mm"] * S8["length_mm"] * 1e-6
G_STILL = (H_STILL / H_FORCED) / R_TOT          # forced-air conductance scaled by h10/h25 (indicative, assumed)
RESULTS["assumptions"]["sink"] = {"C_base_only_J_per_K": C_BASE, "C_full_J_per_K": C_FULL, "fin_plus_base_area_m2": fin_area,
                                  "G_still_W_per_K_indicative": G_STILL, "t_det_s": T_DET_S, "t_derate_s": T_DER_S}


def sink_sim(f_khz, c_sink, tau_ntc, g, derate_power, protections=("c28", "fw", "hw"), hw_corner="low", dt=0.005):
    """Explicit sink model. Tank at the 28 A point until T_DER_S, derated until switched off. derate_power:
    'bound' = values at the lowest committed current (22 A; P and Tj-Tsink increase with I), 'fit' = quadratic fit."""
    i, p, d = fet_table(f_khz)
    p28, d28 = float(np.interp(28.0, i, p)), float(np.interp(28.0, i, d))
    if derate_power == "bound":
        pder, dder = float(p[0]), float(d[0])
    else:
        pder = float(np.polyval(np.polyfit(i, p, 2), I_DER_A))
        dder = float(np.polyval(np.polyfit(i, d, 2), I_DER_A))
    t0 = T_AMB + R_TOT * p28
    t, ts, tm = 0.0, t0, t0
    snap, flag_t, off_t, cause = None, None, None, None
    nxt_tick, tl = 0.0, []
    tj_peak, ts_peak = -1e9, -1e9
    while t < 120.0:
        on = off_t is None or t < off_t
        pw = (p28 if t < T_DER_S else pder) if on else 0.0
        dj = (d28 if t < T_DER_S else dder) if on else 0.0
        ts += dt * (pw - g * (ts - T_AMB)) / c_sink
        tm += dt * (ts - tm) / tau_ntc if tau_ntc > 0 else (ts - tm)
        t += dt
        if tau_ntc == 0:
            tm = ts
        if on:
            tj_peak = max(tj_peak, ts + dj)
        ts_peak = max(ts_peak, ts)
        if t >= nxt_tick:
            nxt_tick += TICK_S
            if snap is None and t >= T_DET_S:
                snap = tm
            if off_t is None:
                if "c28" in protections and snap is not None and tm > snap + STALL_RISE_K:
                    off_t, cause = t + APPLY_S, "C28 sink rise > 2 K"
                if "fw" in protections and tm >= FW_SINK_TRIP_C and (off_t is None or t + APPLY_S < off_t):
                    off_t, cause = t + APPLY_S, "firmware 95 C trip"
                if "hw" in protections and ts >= HW_SINK_TRIP_C[hw_corner] and (off_t is None or t + 0.01 < off_t):
                    off_t, cause = t + 0.01, f"hardware sink trip ({hw_corner} corner)"
        if off_t is not None and t > off_t + 1.0:
            break
    return {"f_kHz": f_khz, "C_sink_J_per_K": c_sink, "tau_ntc_s": tau_ntc, "G_W_per_K": g, "derate_power": derate_power,
            "protections": list(protections), "P28_W": p28, "Pder_W": pder, "dTj_sink_28A_K": d28, "dTj_sink_der_K": dder,
            "T_sink_start_c": t0, "Tj_start_c": t0 + d28, "t_switch_off_s": off_t, "cause": cause,
            "T_sink_peak_true_c": ts_peak, "Tj_peak_c": tj_peak,
            "T_sink_meas_at_snapshot_c": snap}


sink_runs = {}
PRIMARY = dict(f_khz=40.0, c_sink=C_BASE, tau_ntc=7.0, g=0.0, derate_power="bound")
sink_runs["primary_conservative_all_protections"] = sink_sim(**PRIMARY)
sink_runs["primary_C28_only"] = sink_sim(**PRIMARY, protections=("c28",))
sink_runs["primary_no_protection_until_hw_high_corner"] = sink_sim(**PRIMARY, protections=("hw",), hw_corner="high")
sink_runs["central_full_sink_G_still_fit"] = sink_sim(40.0, C_FULL, 3.0, G_STILL, "fit")
sink_runs["central_full_sink_G_still_fit_C28_only"] = sink_sim(40.0, C_FULL, 3.0, G_STILL, "fit", protections=("c28",))
sens = []
for f in (40.0, 45.0, 50.0):
    for c in (C_BASE, C_FULL):
        for tau in (0.0, 7.0, 15.0):
            for dp in ("bound", "fit"):
                s = sink_sim(f, c, tau, 0.0, dp)
                s["case"] = f"f{f:g}_C{'base' if c == C_BASE else 'full'}_tau{tau:g}_{dp}"
                sens.append(s)
RESULTS["b_sink_junction"] = {"runs": sink_runs, "sensitivity_all_protections_G0": sens,
                              "sensitivity_max_Tj_peak_c": max(s["Tj_peak_c"] for s in sens),
                              "sensitivity_max_T_sink_peak_c": max(s["T_sink_peak_true_c"] for s in sens)}
print("sink primary:", {k: sink_runs["primary_conservative_all_protections"][k] for k in
                        ("t_switch_off_s", "cause", "T_sink_peak_true_c", "Tj_peak_c")}, flush=True)

# ------------------------------------------------------------------ (b) finite-volume board transient
data = json.loads(gzip.open(rs.GEOM, "rt").read())
x, y, board, copper, pads, barrels = th.grid_geometry(data, 1.0)
nz, nx, ny = len(th.LAYER_NAMES), len(x), len(y)
k = np.full((nz, nx, ny), th.K_FR4)
for layer, zi in th.CU_INDEX.items():
    k[zi][copper[layer]] = th.K_CU
links = th.barrel_edges(barrels, x, y, board)
thick = th.THICK_MM * 1e-3
RHO_CP = {"cu": 8960.0 * 385.0, "fr4": 1850.0 * 1100.0}    # handbook; FR-4 value is the low end -> faster heating
cap = np.where(k == th.K_CU, RHO_CP["cu"], RHO_CP["fr4"]) * thick[:, None, None] * (1e-3 ** 2)   # J/K per node
ids = np.arange(nz * nx * ny).reshape(nz, nx, ny)
inactive = ~np.broadcast_to(board, (nz, nx, ny))


def assemble(h):
    """Same conductance matrix as thermal.solve_stack (copied), with outer-face convection h."""
    area, pitch_m = (1e-3) ** 2, 1e-3
    diag = np.zeros(nz * nx * ny)
    rr, cc, vv = [], [], []
    for zi in range(nz):
        sheet = k[zi] * thick[zi]
        for axis in (0, 1):
            if axis == 0:
                a, b, ka, kb, valid = ids[zi, :-1, :], ids[zi, 1:, :], sheet[:-1, :], sheet[1:, :], board[:-1, :] & board[1:, :]
            else:
                a, b, ka, kb, valid = ids[zi, :, :-1], ids[zi, :, 1:], sheet[:, :-1], sheet[:, 1:], board[:, :-1] & board[:, 1:]
            g = 2 * ka * kb / (ka + kb)
            th.add_edge(rr, cc, vv, diag, a[valid], b[valid], g[valid])
    for zi in range(nz - 1):
        g = area / (thick[zi] / (2 * k[zi]) + thick[zi + 1] / (2 * k[zi + 1]))
        th.add_edge(rr, cc, vv, diag, ids[zi][board], ids[zi + 1][board], g[board])
    for zi, i, j, z2, cond in links:
        if board[i, j]:
            th.add_edge(rr, cc, vv, diag, [ids[zi, i, j]], [ids[z2, i, j]], [cond])
    for zi in (0, nz - 1):
        np.add.at(diag, ids[zi][board], h * area)
    return rr, cc, vv, diag


def step_solver(h, dt):
    rr, cc, vv, diag = assemble(h)
    diag = diag + (cap / dt).ravel() * (~inactive).ravel()
    diag[ids[inactive]] = 1.0
    m = coo_matrix((np.concatenate(vv + [diag]), (np.concatenate(rr + [np.arange(diag.size)]),
                                                  np.concatenate(cc + [np.arange(diag.size)]))), shape=(diag.size,) * 2).tocsr()
    pre = LinearOperator(m.shape, matvec=lambda v: v / diag)
    return m, pre


def run_transient(rise0, schedule, h_of_t, t_end, dts):
    """schedule: list of (t_from, heat_w array [nz,nx,ny]); h_of_t(t) -> h. Implicit Euler, nodes relative to ambient."""
    t, rise, hist = 0.0, rise0.copy(), []
    cache = {}
    for dt in dts:
        if t >= t_end:
            break
        h = h_of_t(t)
        key = (h, dt)
        if key not in cache:
            cache[key] = step_solver(h, dt)
        m, pre = cache[key]
        heat = [q for tf, q in schedule if tf <= t + 1e-9][-1]
        rhs = (cap / dt * rise).ravel() + heat.ravel()
        rhs[ids[inactive]] = 0.0
        sol, info = cg(m, rhs, x0=rise.ravel(), rtol=1e-10, atol=1e-12, M=pre, maxiter=5000)
        assert info == 0, info
        rise = sol.reshape(rise.shape)
        t += dt
        e = np.where(np.broadcast_to(board, rise.shape), rise, -np.inf)
        ix, iy = x <= 80, y <= 12.5
        hist.append({"t_s": round(t, 4), "board_peak_c": float(T_AMB + e.max()),
                     "fet_row_max_c": float(T_AMB + e[:, ix][:, :, iy].max()),
                     "u26_cell_c": float(T_AMB + rise[0, np.argmin(abs(x - 109.5)), np.argmin(abs(y - 77.5))])})
    return hist, rise


# control: the assembled matrix reproduces thermal.py's steady state at h 25 / 28 A
m25, _ = step_solver(25.0, 1e12)
rhs = z25["heat_w"].ravel().copy()
rhs[ids[inactive]] = 0.0
chk, info = cg(m25, rhs, rtol=1e-10, atol=1e-12, M=LinearOperator(m25.shape, matvec=lambda v: v / m25.diagonal()), maxiter=12000)
dmax = float(np.abs(chk.reshape(z25["rise_k"].shape) - z25["rise_k"])[~inactive].max())
RESULTS["controls"]["fv_matrix_vs_thermal_py_max_abs_K"] = dmax
assert dmax < 0.01, dmax
print("FV matrix control OK", dmax, flush=True)

# windows: blower stop -> tank switch-off. "conservative corner" = the lumped bound's primary run; "longest" = the
# longest switch-off over every lumped run in which the C28 path acts (primary, central, and the 36-run sensitivity set).
c28_runs = [sink_runs[k_] for k_ in ("primary_conservative_all_protections", "primary_C28_only",
                                     "central_full_sink_G_still_fit", "central_full_sink_G_still_fit_C28_only")] + sens
WIN_CONS = sink_runs["primary_conservative_all_protections"]["t_switch_off_s"]
WIN_LONG = max(s_["t_switch_off_s"] for s_ in c28_runs if s_["t_switch_off_s"] is not None)
WIN_HWONLY = sink_runs["primary_no_protection_until_hw_high_corner"]["t_switch_off_s"]
T_WIN = max(WIN_LONG, WIN_HWONLY)
dts_win = [0.25] * int(math.ceil(T_WIN / 0.25))
t_off_grid = len(dts_win) * 0.25
Q28, Q14, Q0 = z25["heat_w"], z14["heat_w"], z0["heat_w"]
rise0 = z25["rise_k"]
board_tr = {}
for name, sched in (("derate_in_force", [(0.0, Q28), (T_DER_S, Q14), (t_off_grid, Q0)]),
                    ("derate_never_applies_until_stop", [(0.0, Q28), (t_off_grid, Q0)])):
    hist, riseN = run_transient(rise0, sched, lambda t: 0.0, t_off_grid, dts_win)       # adiabatic window = bound
    # after the window: natural convection h 10, tank stopped, to 900 s
    dts_post = [1.0] * 20 + [5.0] * 20 + [20.0] * 35 + [50.0] * 12
    post_hist, _ = run_transient(riseN, [(0.0, Q0)], lambda t: H_STILL, 900.0, dts_post)
    for p in post_hist:
        p["t_s"] = round(p["t_s"] + t_off_grid, 2)
    def pk(key, tmax):
        return max(p[key] for p in hist if p["t_s"] <= tmax + 1e-9)
    board_tr[name] = {"window_end_s": t_off_grid, "window": hist, "after_window_h10_tank_stopped": post_hist,
                      "windows_s": {"conservative_corner": WIN_CONS, "longest_c28_path": WIN_LONG, "hw_backstop_only": WIN_HWONLY},
                      "peak_c": {w: pk("board_peak_c", t_) for w, t_ in (("conservative_corner", WIN_CONS), ("longest_c28_path", WIN_LONG), ("hw_backstop_only", WIN_HWONLY))},
                      "fet_row_peak_c": {w: pk("fet_row_max_c", t_) for w, t_ in (("conservative_corner", WIN_CONS), ("longest_c28_path", WIN_LONG), ("hw_backstop_only", WIN_HWONLY))},
                      "peak_after_window_900s_c": max(p["board_peak_c"] for p in post_hist),
                      "board_peak_at_900s_c": post_hist[-1]["board_peak_c"],
                      "fet_row_max_at_900s_c": post_hist[-1]["fet_row_max_c"]}
RESULTS["b_board_transient"] = board_tr
RESULTS["assumptions"]["board"] = {
    "rho_cp_J_per_m3K": RHO_CP, "capacity": "copper and FR-4 sheets of the thermal.py stack only; no components, mask or solder",
    "air_side": "h = 0 during the window (upper bound), h 10 after it",
    "total_board_capacity_J_per_K": float(cap[~inactive].sum()), "window_s": T_WIN}
RESULTS["assumptions"]["windows_s"] = {"conservative_corner": WIN_CONS, "longest_c28_path": WIN_LONG, "hw_backstop_only": WIN_HWONLY}

# ------------------------------------------------------------------ verdicts against the criterion in README.md
prim = sink_runs["primary_conservative_all_protections"]
c28only = sink_runs["primary_C28_only"]
hv = {
    "L1_tj_max_over_window_c": max(s["Tj_peak_c"] for s in sens + list(sink_runs.values())),
    "L1_limit_c": TJ_MAX_C,
    "L2_true_sink_peak_with_c28_only_c": c28only["T_sink_peak_true_c"], "L2_limit_c": HW_SINK_TRIP_C["high"],
    "L3_board_peak_in_window_c": board_tr["derate_in_force"]["peak_c"]["longest_c28_path"], "L3_limit_c": BOARD_TG_C,
    "L3_board_peak_if_cap_never_applies_c": board_tr["derate_never_applies_until_stop"]["peak_c"]["longest_c28_path"],
    "L3_board_peak_hw_backstop_only_window_c": board_tr["derate_in_force"]["peak_c"]["hw_backstop_only"],
    "L4_board_peak_derated_h10_c": sweep["cap_as_power_14A"]["peak_c"], "L4_limit_c": BOARD_TG_C,
    "L4_board_peak_tank_stopped_h10_c": sweep["tank_stopped_0A"]["peak_c"],
    "tank_attributable_at_14A_K": sweep["cap_as_power_14A"]["peak_c"] - sweep["tank_stopped_0A"]["peak_c"],
}
hv["L1_pass"] = hv["L1_tj_max_over_window_c"] <= TJ_MAX_C
hv["L2_pass"] = hv["L2_true_sink_peak_with_c28_only_c"] <= HW_SINK_TRIP_C["high"]
hv["L3_pass"] = hv["L3_board_peak_in_window_c"] <= BOARD_TG_C
hv["L4_pass"] = hv["L4_board_peak_derated_h10_c"] <= BOARD_TG_C and sweep["cap_as_power_14A"]["fet_row_max_c"] <= BOARD_TG_C
hv["informational_tj_over_125_target"] = hv["L1_tj_max_over_window_c"] > TJ_TARGET_C
hv["informational_board_tiers_exceeded_in_window"] = {n: hv["L3_board_peak_in_window_c"] > v for n, v in BOARD_TIERS_C.items()}
hv["informational_board_tiers_exceeded_derated_h10"] = {n: hv["L4_board_peak_derated_h10_c"] > v for n, v in BOARD_TIERS_C.items()}
hv["verdict"] = "PASS" if all(hv[k_] for k_ in ("L1_pass", "L2_pass", "L3_pass", "L4_pass")) else "FAIL"
RESULTS["verdict"] = hv
(HERE / "results.json").write_text(json.dumps(RESULTS, indent=1, default=float) + "\n")
print(json.dumps(hv, indent=1, default=float))
shutil.rmtree(TMP, ignore_errors=True)
