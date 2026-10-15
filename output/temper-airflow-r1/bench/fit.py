#!/usr/bin/env python3
"""Jet bench fit: board-face h of the R45 jet box from guarded-plate runs, carried to the product, mapped to the ceiling.

Commands (bench.json; bench.example.json if absent)
  python fit.py --selftest              synthetic rig day -> the whole pipeline -> selftest.json (no hardware)
  python fit.py zero runs/zero.csv      overnight isothermal soak -> tc_offsets_K in bench.json
  python fit.py gap runs/d055_*.csv runs/gap_*.csv    guard-offset runs at one flow -> G_gap_W_K in bench.json
  python fit.py run runs/d055_r1.csv    one run: steady values, h, Re
  python fit.py report runs/            every run -> results.json and the verdict
  python fit.py transient runs/transient_d055.csv     power-step run -> h from the plate time constant (cross-check)

Steady state (per run): the last 5 min must hold |d(dT)/dt| <= 0.02 K/min, else dT is extrapolated with a single-
exponential fit over the last 40 min (flagged); the guard null T_p - T_g = -guard_offset_K within 0.1 K is flagged
if missed (the balance corrects any residual with G_gap either way). Heat balance:
    h = (P - G_gap (T_p - T_g) - eps sigma A (T_s^4 - T_ref^4)) / (A (T_s - T_ref))
P = V I - I^2 R_lead; T_s = plate thermocouple mean less the conduction drop over their 1 mm depth; T_ref = jet-air
thermocouple in the manifold (jet runs), hood Pt100 (still air).
Transfer to the product (setpoints.py): each jet run's manifold pressure is mapped to the product pressure with the
same Reynolds number, dp_eq = dp (rho_p/rho_r)(nu_p/nu_r)^2, and Nu = h D / k. ln Nu = a + b ln dp_eq is fitted over
the jet runs and evaluated at delivery.py's jet pressure for each drive; h_prod = Nu k_p / D (Pr^0.42 corrected).
Uncertainty: Monte Carlo over every systematic in bench.json (1 sigma, shared across runs: G_gap, emissivity, area,
power gain, per-channel offsets, thermocouple gain, pressure gain, 3-thermocouple isothermality bias from
plate-design.json, property reference temperature anywhere between jet and film, product strip temperature, real Cd
through delivery's network, jet height x Martin's height sensitivity) plus each run's statistical noise, inflated by
the Birge ratio when repeats scatter more than their noise. U95 = 2.5-97.5 percentile.
Verdict at drive 0.55 for each board-h-sweep case: PASS if the 2.5 % bound >= required h_top, MARGINAL if the
median is but the bound is not, FAIL if the median is below. Ceiling = board-h-sweep ceiling_by_h, linear in h,
held flat above h 150 (the sweep's top); the 28 A Kconfig cap still applies.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
AIRFLOW = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(AIRFLOW))
from air import SIGMA, props  # noqa: E402
from jet_logger import COLS, GuardPI, load_bench, write_csv  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import delivery as dl  # noqa: E402  (read-only; functions only)

SETP = json.loads((HERE / "setpoints.json").read_text())
SWEEP = json.loads((AIRFLOW / "board-h-sweep.json").read_text())
PD = json.loads((HERE / "plate-design.json").read_text())
JET_CONDITIONS = ("floor", "d055", "full", "sweep", "gap", "height", "transient")
WIN_S, SLOPE_LIM, NULL_LIM = 300, 0.02 / 60, 0.1
CFM = 0.000471947
N_MC = 4000


# ------------------------------------------------------------------ I/O
def read_run(path: Path) -> tuple[dict, dict]:
    meta, rows, header = {}, [], None
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            k, _, v = line[1:].partition(":")
            meta[k.strip()] = v.strip()
        elif header is None:
            header = line.split(",")
        elif line.strip():
            rows.append([float(x) if x else np.nan for x in line.split(",")])
    arr = np.array(rows)
    return meta, {c: arr[:, i] for i, c in enumerate(header)}


def chan(cols, cfg, name):
    return cols[f"tc{cfg['tc_channels'][name]}"] - cfg["tc_offsets_K"].get(name, 0.0)


def mean_chans(cols, cfg, names):
    return np.mean([chan(cols, cfg, n) for n in names], axis=0)


def save_bench(cfg: dict, path: Path):
    path.write_text(json.dumps(cfg, indent=1) + "\n")


# ------------------------------------------------------------------ per-run steady values
def _exp(t, a, b, tau):
    return a + b * np.exp(-t / tau)


def steady(t, y):
    """Value of y at steady state, its statistical sigma, and how it was obtained."""
    w = t >= t[-1] - WIN_S
    tw, yw = t[w], y[w]
    slope = np.polyfit(tw, yw, 1)[0]
    resid = yw - np.polyval(np.polyfit(tw, yw, 1), tw)
    sig = float(np.std(resid) / math.sqrt(max(len(yw) / 10, 1)))      # ~10 s correlation of the 1 Hz rows
    if abs(slope) <= SLOPE_LIM:
        return float(np.mean(yw)), sig, "steady"
    m = t >= max(t[0], t[-1] - 2400)
    tt, yy = t[m] - t[m][0], y[m]
    try:
        p, cov = curve_fit(_exp, tt, yy, p0=(yy[-1], yy[0] - yy[-1], 300.0), maxfev=20000)
        if p[2] <= 0 or not np.all(np.isfinite(cov)):
            raise RuntimeError
        return float(p[0]), float(math.hypot(math.sqrt(cov[0, 0]), sig)), f"extrapolated (tau {p[2]:.0f} s)"
    except Exception:
        return float(np.mean(yw)), float(math.hypot(sig, abs(slope) * 600)), "NOT STEADY"


def run_values(path: Path, cfg: dict) -> dict:
    meta, c = read_run(path)
    cond = meta.get("condition", "")
    t = c["t_s"]
    if cond == "flowcal":                      # flow meter in line, heaters off: only dp, air temperature and flow
        w = t >= t[-1] - min(WIN_S, t[-1] / 2)
        return {"run": meta.get("run", path.stem), "file": path.name, "condition": cond, "jet": False, "how": "steady",
                "null_ok": True, "spread_K": 0.0, "dT": 0.0, "P": 0.0, "h_central": None, "gap": 0.0, "guard_offset_K": 0.0,
                "Tref": float(np.mean(c["pt100_C"][w])), "dp": float(np.nanmean(c["dp_Pa"][w])),
                "flow_slpm": float(meta["flow_slpm"]) if meta.get("flow_slpm") else None}
    tp = mean_chans(c, cfg, cfg["plate_tcs"])
    tg = mean_chans(c, cfg, cfg["guard_tcs"])
    jet = cond in JET_CONDITIONS
    tref = chan(c, cfg, cfg["jet_air_tc"]) if jet else c["pt100_C"]
    p = c["v_bus_V"] * c["i_A"] - c["i_A"] ** 2 * cfg["r_lead_ohm"]
    dT, s_dT, how = steady(t, tp - tref)
    w = t >= t[-1] - WIN_S
    off = float(meta.get("guard_offset_K", 0) or 0)
    null = float(np.mean((tp - tg)[w]))
    P, s_P = float(np.mean(p[w])), float(np.std(p[w]) / math.sqrt(max(w.sum() / 10, 1)))
    out = {"run": meta.get("run", path.stem), "file": path.name, "condition": cond, "jet": jet,
           "H_mm": float(meta.get("H_mm", 6.0) or 6.0), "guard_offset_K": off,
           "dT": dT, "s_dT": s_dT, "how": how, "gap": null, "null_ok": bool(abs(null + off) <= NULL_LIM),
           "P": P, "s_P": s_P, "Tp": float(np.mean(tp[w])), "Tref": float(np.mean(tref[w])),
           "dp": float(np.nanmean(c["dp_Pa"][w])) if jet else 0.0,
           "plate_ch": [cfg["plate_tcs"]], "ref": cfg["jet_air_tc"] if jet else "pt100",
           "flow_slpm": float(meta["flow_slpm"]) if meta.get("flow_slpm") else None,
           "spread_K": float(np.ptp([np.mean(chan(c, cfg, n)[w]) for n in cfg["plate_tcs"]]))}
    if "exit_air_tc" in cfg and jet:
        out["T_exit"] = float(np.mean(chan(c, cfg, cfg["exit_air_tc"])[w]))
    out["h_central"] = h_from(out, cfg)
    return out


def h_from(r, cfg, P=None, dT=None, gap=None, g_gap=None, eps=None, area=None):
    P = r["P"] if P is None else P
    dT = r["dT"] if dT is None else dT
    gap = r["gap"] if gap is None else gap
    g_gap = cfg["G_gap_W_K"] if g_gap is None else g_gap
    eps = cfg["eps_plate"] if eps is None else eps
    area = cfg["plate"]["area_m2"] if area is None else area
    drop = P / area * cfg["plate"]["tc_depth_m"] / cfg["plate"]["k_W_mK"]
    ts = r["Tref"] + dT - drop
    q_rad = eps * SIGMA * area * ((ts + 273.15) ** 4 - (r["Tref"] + 273.15) ** 4)
    return (P - g_gap * gap - q_rad) / (area * (dT - drop))


# ------------------------------------------------------------------ zero, gap, transient
def cmd_zero(path: Path, cfg: dict, cfg_path: Path | None, quiet=False) -> dict:
    meta, c = read_run(path)
    t = c["t_s"]
    w = t >= t[-1] - 3600
    rate = abs(np.polyfit(t[w], c["pt100_C"][w], 1)[0]) * 3600
    offs = {}
    for name, ch in cfg["tc_channels"].items():
        k = f"tc{ch}"
        if k in c and np.isfinite(c[k][w]).all():
            offs[name] = round(float(np.mean(c[k][w] - c["pt100_C"][w])), 4)
    ok = rate <= 0.1 and t[-1] >= 5400
    res = {"room_drift_K_per_h": round(rate, 3), "duration_min": round(t[-1] / 60, 1), "offsets_K": offs, "accepted": ok,
           "rule": "last 60 min of a >= 90 min soak, heaters and blower off, Pt100 drift <= 0.1 K/h"}
    if ok:
        cfg["tc_offsets_K"] = offs
        if cfg_path:
            save_bench(cfg, cfg_path)
    if not quiet:
        print(json.dumps(res, indent=1))
    return res


def cmd_gap(paths: list[Path], cfg: dict, cfg_path: Path | None, quiet=False) -> dict:
    rs = [run_values(p, cfg) for p in paths]
    # P - q_rad = hA * dT' + G_gap * gap  (one flow): least squares for hA and G_gap
    rows, rhs = [], []
    for r in rs:
        drop = r["P"] / cfg["plate"]["area_m2"] * cfg["plate"]["tc_depth_m"] / cfg["plate"]["k_W_mK"]
        ts = r["Tref"] + r["dT"] - drop
        q_rad = cfg["eps_plate"] * SIGMA * cfg["plate"]["area_m2"] * ((ts + 273.15) ** 4 - (r["Tref"] + 273.15) ** 4)
        rows.append([r["dT"] - drop, r["gap"]])
        rhs.append(r["P"] - q_rad)
    X, y = np.array(rows), np.array(rhs)
    sol, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ sol
    dof = max(len(y) - 2, 1)
    s2 = float(resid @ resid / dof) if len(y) > 2 else (0.003 * float(np.mean(y))) ** 2
    cov = s2 * np.linalg.inv(X.T @ X)
    g, sg = float(sol[1]), float(math.sqrt(cov[1, 1]))
    span = float(np.ptp(X[:, 1]))
    ok = span >= 2.0 and g > 0
    res = {"runs": [r["run"] for r in rs], "guard_offsets_K": [round(r["gap"], 3) for r in rs], "G_gap_W_K": round(g, 4),
           "G_gap_u_W_K": round(sg, 4), "hA_W_K": round(float(sol[0]), 4), "accepted": ok,
           "rule": "same flow, guard offsets spanning >= 2 K (0 and +3, +6 K)"}
    if ok:
        cfg["G_gap_W_K"], cfg["G_gap_u_rel"] = round(g, 4), round(max(sg / g, 0.05), 3)
        if cfg_path:
            save_bench(cfg, cfg_path)
    if not quiet:
        print(json.dumps(res, indent=1))
    return res


def cmd_transient(path: Path, cfg: dict, quiet=False) -> dict:
    """Plate-power step at the last marker. With theta = rise of (T_p - T_jet) and theta_g = rise of (T_p - T_g) since
    the step, C dtheta/dt = dP - G theta - G_gap theta_g. Integrated, theta + (G_gap/C) int(theta_g) = (dP/C) t - (G/C) int(theta):
    linear in the unknowns dP/C and G/C, so the step size (and the power meter) drops out; the lagging guard is
    corrected with G_gap. h = (G - G_rad) / A rests on the plate heat capacity C (weighed parts x cp)."""
    meta, c = read_run(path)
    t = c["t_s"]
    i0 = int(np.argmax(c["marker"] >= np.nanmax(c["marker"]))) if np.nanmax(c["marker"]) > 0 else 0
    tp = mean_chans(c, cfg, cfg["plate_tcs"])
    ta = chan(c, cfg, cfg["jet_air_tc"])
    tg = mean_chans(c, cfg, cfg["guard_tcs"])
    pre = slice(max(i0 - 60, 0), i0)
    th = (tp - ta)[i0:] - np.mean((tp - ta)[pre])
    thg = (tp - tg)[i0:] - np.mean((tp - tg)[pre])
    tt = t[i0:] - t[i0]
    A, C = cfg["plate"]["area_m2"], cfg["plate"]["C_J_K"]
    cum = lambda y: np.concatenate([[0.0], np.cumsum((y[1:] + y[:-1]) / 2 * np.diff(tt))])
    y = th + cfg["G_gap_W_K"] / C * cum(thg)
    X = np.column_stack([tt, -cum(th)])
    sol, res_, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ sol
    cov = float(resid @ resid) / max(len(y) - 2, 1) * np.linalg.inv(X.T @ X)
    G = sol[1] * C
    tm = float(np.mean(ta[i0:] + (tp - ta)[i0:])) + 273.15
    g_rad = 4 * cfg["eps_plate"] * SIGMA * A * tm ** 3
    h = (G - g_rad) / A
    u = h * math.hypot(cfg["plate"]["C_u_rel"], math.sqrt(cov[1, 1]) / sol[1])
    res = {"run": meta.get("run"), "G_W_K": round(float(G), 4), "tau_s": round(float(1 / sol[1]), 2),
           "h_transient": round(float(h), 2), "u_1sigma": round(float(u), 2),
           "note": "independent of the power measurement; rests on the plate heat capacity C"}
    if not quiet:
        print(json.dumps(res, indent=1))
    return res


# ------------------------------------------------------------------ transfer, Monte Carlo, verdict
def martin_dlnh_dH():
    q = SETP["named"]["drive_0.55"]["board_cfm"] * dl.CFM
    hi = dl.h_board(q, dict(dl.JET, H_mm=6.1))["h_est"]
    lo = dl.h_board(q, dict(dl.JET, H_mm=5.9))["h_est"]
    return (math.log(hi) - math.log(lo)) / 0.2


def cd_slope(row):
    s = row["Cd_sensitivity"]
    return (math.log(s["Cd0.72"]["jet_dp_Pa"]) - math.log(s["Cd0.58"]["jet_dp_Pa"])) / 0.14


def iso_bias(h):
    pts = {}
    for r in PD["A_isothermality"]["Al6061_3mm"]["cases"]:
        pts[r["h_bar"]] = max(pts.get(r["h_bar"], 0.0), abs(r["h_from_3TC_over_isothermal_h"] - 1))
    hs = sorted(pts)
    return np.interp(h, hs, [pts[k] for k in hs])


def ceiling_tables():
    tab = {}
    for k, v in SWEEP["ceiling_by_h"].items():
        bay, h = k.split("_h")
        tab.setdefault(bay, []).append((float(h), v["all_gated_ceiling_A"]))
    return {b: sorted(v) for b, v in tab.items()}


def ceiling_at(bay_rows, h):
    hs, a = zip(*bay_rows)
    return float(np.interp(h, hs, a))


def status(h_med, h_lo, need):
    return "PASS" if h_lo >= need else ("MARGINAL" if h_med >= need else "FAIL")


def monte_carlo(runs: list[dict], cfg: dict, rng, n=N_MC) -> dict:
    A0, D = cfg["plate"]["area_m2"], cfg["jet"]["D_m"]
    jets = [r for r in runs if r["jet"] and r["condition"] not in ("gap", "transient", "height")]
    still = [r for r in runs if r["condition"] == "still"]
    chans = sorted(cfg["tc_channels"])
    off = {c: rng.normal(0, cfg["tc_offset_u_K"], n) for c in chans} | {"pt100": np.zeros(n)}
    g_gap = cfg["G_gap_W_K"] * (1 + cfg["G_gap_u_rel"] * rng.standard_normal(n))
    eps = np.clip(cfg["eps_plate"] + cfg["eps_u"] * rng.standard_normal(n), 0.0, 1.0)
    area = A0 * (1 + cfg["plate"]["area_u_rel"] * rng.standard_normal(n))
    pgain = 1 + cfg["power_u_rel"] * rng.standard_normal(n)
    tgain = 1 + cfg["tc_gain_u_rel"] * rng.standard_normal(n)
    dpg = 1 + cfg["dp_u_rel"] * rng.standard_normal(n)
    iso = rng.uniform(-1, 1, n)
    f_ref = rng.uniform(0, 1, n)
    prod = SETP["product"]
    t_s_prod = prod["strip_C"] + cfg["product_strip_u_K"] * rng.standard_normal(n)
    cd_mean, cd_u = cfg["jet"]["Cd"], cfg["jet"]["Cd_u"]
    flows = [r for r in runs if r.get("flow_slpm") and r["dp"] > 0]
    cd_meas = None
    if flows:
        cds = []
        for r in flows:
            pr = props(r["Tref"])
            q = r["flow_slpm"] / 60000 * (r["Tref"] + 273.15) / 273.15    # slpm (0 C, 1 atm) -> m3/s at jet temperature
            cds.append(q / (cfg["jet"]["N"] * math.pi / 4 * D ** 2 * math.sqrt(2 * r["dp"] / pr["rho"])))
        cd_meas = {"mean": float(np.mean(cds)), "sd": float(np.std(cds)), "n": len(cds)}
        cd_mean, cd_u = cd_meas["mean"], math.hypot(cd_meas["sd"], cfg["flow_u_rel"] * cd_meas["mean"])
    cd = cd_mean + cd_u * rng.standard_normal(n)
    dH = cfg["H_u_mm"] * rng.standard_normal(n)
    sH = sH_martin = martin_dlnh_dH()
    heights = [r for r in runs if r["condition"] == "height" and abs(r["H_mm"] - 6.0) >= 0.2]
    sH_meas = None

    def h_draw(r, zscale=1.0):
        mp = np.mean([off[c] for c in cfg["plate_tcs"]], axis=0)
        mg = np.mean([off[c] for c in cfg["guard_tcs"]], axis=0)
        dT = (r["dT"] + mp - off[r["ref"]] + zscale * r["s_dT"] * rng.standard_normal(n)) * tgain
        gap = r["gap"] + mp - mg
        P = (r["P"] + zscale * r["s_P"] * rng.standard_normal(n)) * pgain
        drop = P / area * cfg["plate"]["tc_depth_m"] / cfg["plate"]["k_W_mK"]
        ts = r["Tref"] + dT - drop
        q_rad = eps * SIGMA * area * ((ts + 273.15) ** 4 - (r["Tref"] + 273.15) ** 4)
        h = (P - g_gap * gap - q_rad) / (area * (dT - drop))
        return h * (1 + iso * iso_bias(r["h_central"])), ts

    def nu_dp(r, h, ts):
        tr = r["Tref"] + f_ref * (ts - r["Tref"]) / 2
        pr = props(tr)
        tpr = prod["jet_air_C"] + f_ref * (t_s_prod - prod["jet_air_C"]) / 2
        pp = props(tpr)
        dp_eq = r["dp"] * dpg * (pp["rho"] / pr["rho"]) * (pp["nu"] / pr["nu"]) ** 2
        nu = h * D / pr["k"] * (pp["Pr"] / pr["Pr"]) ** 0.42
        return nu, dp_eq, pp

    out = {"n_draws": n, "cd_measured": cd_meas, "martin_dlnh_dH_per_mm": round(sH_martin, 4)}
    if jets:
        # central fit to get the Birge ratio of the repeats
        x0 = np.log([r["dp"] for r in jets])
        y0 = np.log([r["h_central"] for r in jets])
        sig = np.array([math.hypot(r["s_dT"] / r["dT"], r["s_P"] / r["P"]) for r in jets])
        if len(set(np.round(x0, 3))) >= 2:
            b0, a0 = np.polyfit(x0, y0, 1)
            chi2 = float(np.sum(((y0 - (a0 + b0 * x0)) / np.maximum(sig, 1e-4)) ** 2) / max(len(jets) - 2, 1))
        else:
            chi2 = float(np.var(y0) / max(np.mean(sig ** 2), 1e-8)) if len(jets) > 1 else 1.0
        birge = max(1.0, math.sqrt(chi2))
        if heights and len(set(np.round(x0, 3))) >= 2:
            sl = [math.log(r["h_central"] / math.exp(a0 + b0 * math.log(r["dp"]))) / (r["H_mm"] - 6.0) for r in heights]
            sH_meas = {"per_mm": round(float(np.mean(sl)), 4), "runs": [r["run"] for r in heights]}
            sH = sH_meas["per_mm"]
        X, Y = [], []
        for r in jets:
            h, ts = h_draw(r, birge)
            nu, dp_eq, pp = nu_dp(r, h, ts)
            X.append(np.log(dp_eq))
            Y.append(np.log(nu))
        X, Y = np.array(X), np.array(Y)
        if len(set(np.round(x0, 3))) >= 2:
            xm, ym = X.mean(0), Y.mean(0)
            b = ((X - xm) * (Y - ym)).sum(0) / ((X - xm) ** 2).sum(0)
            a = ym - b * xm
        else:
            b = 1 / 3 + 0.1 * rng.standard_normal(n)          # Martin's Re^(2/3) is dp^(1/3)
            a = Y.mean(0) - b * X.mean(0)
        pp = props(prod["jet_air_C"] + f_ref * (t_s_prod - prod["jet_air_C"]) / 2)
        x_lo, x_hi = float(np.exp(np.median(X, axis=1)).min()), float(np.exp(np.median(X, axis=1)).max())
        drives = {}
        for row in SETP["rows"]:
            dp_p = row["jet_dp_Pa"] * np.exp(cd_slope(row) * (cd - SETP["jet"]["Cd"]))
            h = np.exp(a + b * np.log(dp_p)) * pp["k"] / D * (1 + sH * dH)
            q = np.percentile(h, [2.5, 50, 97.5])
            inside = x_lo / 1.1 <= row["jet_dp_Pa"] <= x_hi * 1.1
            drives[f"{row['drive']}"] = {"h_med": round(float(q[1]), 1), "h_lo95": round(float(q[0]), 1),
                                         "h_hi95": round(float(q[2]), 1),
                                         "u95_rel": round(float((q[2] - q[0]) / 2 / q[1]), 4),
                                         "product_jet_dp_Pa": row["jet_dp_Pa"], "within_measured_range": inside,
                                         "delivery_h_est": row["h_est_delivery"], "delivery_h_design": row["h_design_delivery"],
                                         "martin_factor_med": round(float(q[1]) / row["h_est_delivery"], 3)}
        out |= {"measured_dlnh_dH": sH_meas, "birge_ratio": round(birge, 3), "exponent_b": [round(float(np.percentile(b, p)), 3) for p in (2.5, 50, 97.5)],
                "measured_dp_eq_range_Pa": [round(x_lo, 2), round(x_hi, 2)], "drives": drives}
    if still:
        hs = np.concatenate([h_draw(r)[0] for r in still])
        q = np.percentile(hs, [2.5, 50, 97.5])
        out["still_air"] = {"h_med": round(float(q[1]), 2), "h_lo95": round(float(q[0]), 2), "h_hi95": round(float(q[2]), 2),
                            "model_floor": 10.0}
    return out


def verdict(mc: dict) -> dict:
    tabs = ceiling_tables()
    d = mc["drives"]
    key055 = "0.55"
    res = {"drive": {}, "cases": {}}
    for dk, v in d.items():
        res["drive"][dk] = {"h_med": v["h_med"], "h_lo95": v["h_lo95"],
                            "ceiling_A_at_lo95": {b: round(ceiling_at(tabs[b], v["h_lo95"]), 1) for b in tabs},
                            "ceiling_A_at_med": {b: round(ceiling_at(tabs[b], v["h_med"]), 1) for b in tabs},
                            "within_measured_range": v["within_measured_range"]}
    for case, req in SWEEP["required_h_top"].items():
        need = req["h_top_required"]
        v = d[key055]
        min_drive = next((float(k) for k, x in sorted(d.items(), key=lambda kv: float(kv[0]))
                          if x["h_lo95"] >= need and x["within_measured_range"]), None)
        res["cases"][case] = {"need": need, "at_0.55": status(v["h_med"], v["h_lo95"], need), "min_drive_lo95": min_drive}
    v = d[key055]
    s = res["cases"]["c28_bay61"]["at_0.55"]
    res["raise_ceiling"] = {"status": s, "basis": "c28_bay61 (28 A, 61 C bay) at board-floor drive 0.55",
                            "supported_ceiling_A_bay61_lo95": res["drive"][key055]["ceiling_A_at_lo95"]["bay61"],
                            "supported_ceiling_A_bay55_lo95": res["drive"][key055]["ceiling_A_at_lo95"]["bay55"],
                            "caps": "sweep held flat above h 150; firmware Kconfig cap 28 A; jet air taken at bay temperature "
                                    "in the sweep (conservative, D4)"}
    if not v["within_measured_range"]:
        res["raise_ceiling"]["status"] += " (EXTRAPOLATED: drive 0.55 pressure outside the measured range)"
    return res


def cmd_report(paths: list[Path], cfg: dict, out_file: Path | None = HERE / "results.json", seed=1, quiet=False) -> dict:
    runs = [run_values(p, cfg) for p in paths]
    runs = [r for r in runs if r["condition"] not in ("zero",)]
    rng = np.random.default_rng(seed)
    mc = monte_carlo(runs, cfg, rng)
    res = {"runs": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k not in ("plate_ch",)}
                    for r in runs], "mc": mc}
    for r in res["runs"]:
        if r["jet"] and r["dp"] > 0 and r["dT"] > 0:
            pr = props(r["Tref"] + r["dT"] / 2)
            v = cfg["jet"]["Cd"] * math.sqrt(2 * r["dp"] / pr["rho"])
            r["Re_film_Cd"] = round(v * cfg["jet"]["D_m"] / pr["nu"])
            r["cfm_Cd"] = round(cfg["jet"]["N"] * math.pi / 4 * cfg["jet"]["D_m"] ** 2 * v / CFM, 3)
            if "T_exit" in r:
                mcp = r["cfm_Cd"] * CFM * pr["rho"] * pr["cp"]
                r["exit_air_energy_ratio"] = round(mcp * (r["T_exit"] - r["Tref"]) / r["P"], 3) if r["P"] > 0 else None
    if "cd_measured" in mc and mc["cd_measured"]:
        res["cd_measured"] = mc["cd_measured"]
    flags = [f"{r['run']}: {r['how']}" for r in runs if r["how"] != "steady"]
    flags += [f"{r['run']}: guard null T_p - T_g {r['gap']:+.3f} K, wanted {-r['guard_offset_K']:+.1f}" for r in runs if not r["null_ok"]]
    flags += [f"{r['run']}: plate TC spread {r['spread_K']:.2f} K" for r in runs if r["spread_K"] > 0.25 * max(r["dT"], 1)]
    res["flags"] = flags
    if "drives" in mc:
        res["verdict"] = verdict(mc)
    if out_file:
        out_file.write_text(json.dumps(res, indent=1) + "\n")
    if not quiet:
        print_report(res)
    return res


def print_report(res):
    mc = res["mc"]
    print("run              cond   dp_Pa  dT_K    P_W     h      how")
    for r in res["runs"]:
        if r["condition"] == "flowcal":
            print(f"{r['run']:<16} flowcal {r['dp']:6.2f} Pa  {r['flow_slpm']} slpm")
            continue
        print(f"{r['run']:<16} {r['condition']:<6} {r['dp']:6.2f} {r['dT']:6.2f} {r['P']:7.3f} {r['h_central']:7.2f}  {r['how']}")
    if "still_air" in mc:
        s = mc["still_air"]
        print(f"\nstill air under the jet box: h {s['h_med']} (95 % {s['h_lo95']}..{s['h_hi95']}) W/m2K convective; "
              f"the model floor is {s['model_floor']}")
    if "drives" not in mc:
        return
    print(f"\nNu ~ dp^b, b = {mc['exponent_b'][1]} (95 % {mc['exponent_b'][0]}..{mc['exponent_b'][2]}); Birge {mc['birge_ratio']}")
    print("drive  h_med  95 %         Martin x   delivery est/design   in range")
    for k, v in mc["drives"].items():
        print(f"{k:<6} {v['h_med']:6.1f} {v['h_lo95']:6.1f}..{v['h_hi95']:<6.1f} {v['martin_factor_med']:<8} "
              f"{v['delivery_h_est']:>6}/{v['delivery_h_design']:<6}        {v['within_measured_range']}")
    vd = res["verdict"]
    print("\ncase        need   at drive 0.55   lowest drive with h_lo95 >= need")
    for c, v in vd["cases"].items():
        print(f"{c:<11} {v['need']:<6} {v['at_0.55']:<15} {v['min_drive_lo95']}")
    rc = vd["raise_ceiling"]
    print(f"\nRAISE TANK CEILING ABOVE 18 A: {rc['status']}  ({rc['basis']})")
    print(f"ceiling the measured h supports at drive 0.55 (95 % lower bound): bay 61 C {rc['supported_ceiling_A_bay61_lo95']} A, "
          f"bay 55 C {rc['supported_ceiling_A_bay55_lo95']} A; {rc['caps']}")
    for f in res["flags"]:
        print("FLAG", f)


# ------------------------------------------------------------------ synthetic rig day (self-test)
def nu_truth_factory(h055):
    """True law Nu = c dp_eq^0.38, scaled so the product h at drive 0.55 is h055 (film reference)."""
    pp = props(SETP["product"]["film_C"])
    dp055 = SETP["named"]["drive_0.55"]["jet_dp_Pa"]
    b = 0.38
    c = h055 * 0.003 / pp["k"] / dp055 ** b
    return lambda dp_eq: c * dp_eq ** b, b


def simulate_day(tmp: Path, cfg_bench: dict, h055: float, rng) -> dict:
    """Lumped plate + guard thermal model with the logger's own guard loop; writes runs as jet_logger.py would."""
    nu_true, b_true = nu_truth_factory(h055)
    A, D = cfg_bench["plate"]["area_m2"], 0.003
    truth = {"C_p": cfg_bench["plate"]["C_J_K"] * 1.02, "C_g": 45.0, "G_env": 0.06, "A_rim": 3e-4, "G_gap": 0.11,
             "eps": 0.06, "h_still": 4.0, "dlnh_dH": -0.06, "blower_rise": 0.8, "dp_gain": 1 + 0.01 * rng.standard_normal(),
             "v_gain": 1 + 0.002 * rng.standard_normal(), "i_gain": 1 + 0.002 * rng.standard_normal()}
    offs = {n: float(rng.normal(0, 0.4)) for n in cfg_bench["tc_channels"]}
    truth["tc_offsets"] = offs
    pt_off = 0.02
    prod = SETP["product"]
    state = {"t": 0.0, "Tp": 22.9, "Tg": 22.9}
    pi = GuardPI(cfg_bench)
    t_day = [0.0]

    def room(t):
        return 22.9 + 0.03 * t / 3600 + (0.0 if t < 9000 else 0.15 * math.sin(2 * math.pi * (t - 9000) / 5400))

    def h_true(dp, tp, tj, H=6.0):
        if dp <= 0:
            return truth["h_still"]
        if H != 6.0:
            return h_true(dp, tp, tj) * (1 + truth["dlnh_dH"] * (H - 6.0))
        tf = (tp + tj) / 2
        pr = props(tf)
        pp = props(prod["film_C"])
        dp_eq = dp * (pp["rho"] / pr["rho"]) * (pp["nu"] / pr["nu"]) ** 2
        return nu_true(dp_eq) * pr["k"] / D * (pr["Pr"] / pp["Pr"]) ** 0.42

    def run(name, cond, minutes, dp_set=0.0, blower=True, guard=True, power=None, dT_target=25.0, offset=0.0, step=None,
            flow=False, H=6.0):
        rows = []
        tj0 = room(t_day[0]) + (truth["blower_rise"] if blower else 0.0)
        h0 = h_true(dp_set, tj0 + dT_target, tj0, H)
        g_rad = 4 * truth["eps"] * SIGMA * A * (tj0 + dT_target / 2 + 273.15) ** 3
        P = (h0 * A + g_rad) * dT_target if power is None else power
        marker, duty = 0, 0
        n = int(minutes * 60)
        for k in range(n):
            t = t_day[0]
            tr = room(t)
            th = tr + (truth["blower_rise"] if blower else 0.0)
            if step and k == n // 2:
                P *= step
                marker = 1
            dp = dp_set if blower else 0.0
            tj = th + (0.02 * (state["Tp"] - th) if dp > 0 else 0.0)
            h = h_true(dp, state["Tp"], tj, H)
            ts = state["Tp"] - P / A * cfg_bench["plate"]["tc_depth_m"] / cfg_bench["plate"]["k_W_mK"]
            tref = tj if dp > 0 else tr
            q_conv = h * A * (ts - tref)
            q_rad = truth["eps"] * SIGMA * A * ((ts + 273.15) ** 4 - (tref + 273.15) ** 4)
            pg = duty / 1023 * pi.pmax
            dtp = (P - q_conv - q_rad - truth["G_gap"] * (state["Tp"] - state["Tg"])) / truth["C_p"]
            dtg = (pg - truth["G_gap"] * (state["Tg"] - state["Tp"]) - truth["G_env"] * (state["Tg"] - tr)
                   - (h if dp > 0 else truth["h_still"]) * truth["A_rim"] * (state["Tg"] - tref)) / truth["C_g"]
            state["Tp"] += dtp
            state["Tg"] += dtg
            t_day[0] += 1.0
            tc = {}
            for nme in cfg_bench["plate_tcs"]:
                tc[nme] = state["Tp"]
            for nme in cfg_bench["guard_tcs"]:
                tc[nme] = state["Tg"]
            tc[cfg_bench["jet_air_tc"]] = tj
            tc[cfg_bench["exit_air_tc"]] = tj + (0.4 * P / max(dp_set, 1) if dp > 0 else 0.0)
            row = {"t_s": float(k)}
            for nme, ch in cfg_bench["tc_channels"].items():
                row[f"tc{ch}"] = tc[nme] + offs[nme] + rng.normal(0, 0.03)
            row["cj_C"] = tr + 1.0
            row["pt100_C"] = th + pt_off + rng.normal(0, 0.01)
            r_heat = 20.0 * (1 + 0.0002 * (state["Tp"] - 25))
            i = math.sqrt(P / r_heat) if P > 0 else 0.0
            row["i_A"] = round(i * truth["i_gain"] / 2.5e-5) * 2.5e-5
            row["v_bus_V"] = round((i * (r_heat + cfg_bench["r_lead_ohm"])) * truth["v_gain"] / 1.25e-3) * 1.25e-3
            row["dp_Pa"] = dp * truth["dp_gain"] + rng.normal(0, 0.05) if blower else rng.normal(0, 0.05)
            if guard:
                tpm = np.mean([row[f"tc{cfg_bench['tc_channels'][x]}"] - cfg_bench["tc_offsets_K"].get(x, 0.0)
                               for x in cfg_bench["plate_tcs"]])
                tgm = np.mean([row[f"tc{cfg_bench['tc_channels'][x]}"] - cfg_bench["tc_offsets_K"].get(x, 0.0)
                               for x in cfg_bench["guard_tcs"]])
                duty, pgw = pi.step(tpm + offset - tgm, 1.0)
            else:
                duty, pgw = 0, 0.0
            row.update(duty=duty, p_guard_W=pgw, marker=marker)
            rows.append(row)
        meta = {"run": name, "condition": cond, "H_mm": H, "guard_offset_K": offset, "room_C": round(room(t_day[0]), 2),
                "flow_slpm": "", "notes": "synthetic"}
        if flow and dp_set > 0:
            pr = props(th)
            q = truth_cd * cfg_bench["jet"]["N"] * math.pi / 4 * D ** 2 * math.sqrt(2 * dp_set / pr["rho"])
            meta["flow_slpm"] = round(q * 60000 * 273.15 / (th + 273.15) * (1 + 0.01 * rng.standard_normal()), 3)
        write_csv(tmp / f"{name}.csv", meta, rows)
        return tmp / f"{name}.csv"

    truth_cd = 0.68
    dp_rig = {row["drive"]: row["rig_dp_Pa_by_room_C"]["24"] for row in SETP["rows"]}
    files = {"zero": run("zero", "zero", 150, blower=False, guard=False, power=0.0)}
    truth["files"] = files
    return {"truth": truth, "run": run, "dp_rig": dp_rig, "nu_true": nu_true, "b_true": b_true, "truth_cd": truth_cd,
            "h_true": h_true, "state": state}


def selftest():
    tmp = HERE / "_selftest_runs"
    out = {"scope": "fit.py --selftest: a synthetic rig day per scenario (lumped plate + guard thermal model driven by "
                    "jet_logger.GuardPI, thermocouple offsets +-0.4 K and noise, INA226 quantisation, room drift, pressure "
                    "and power gain errors, blower heating, true G_gap / emissivity / heat capacity different from "
                    "bench.example.json) -> zero -> gap -> report -> transient; checks recovery against the truth. The "
                    "generator's truth uses film-temperature properties; fit.py spans jet..film, which shows here as a "
                    "~-0.8 % offset inside the stated U95",
           "scenarios": {}}
    ok_all = True
    for label, h055, expect, fl in (("pass_h125", 125.0, "PASS", "inline"), ("near_h100", 100.0, None, "inline"),
                                    ("fail_h88", 88.0, "FAIL", "flowcal"), ("near_h100_no_flowmeter", 100.0, None, None)):
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir()
        rng = np.random.default_rng(7)
        cfg = json.loads((HERE / "bench.example.json").read_text())
        sim = simulate_day(tmp, cfg, h055, rng)
        z = cmd_zero(sim["truth"]["files"]["zero"], cfg, None, quiet=True)
        off_err = max(abs(z["offsets_K"][n] - (sim["truth"]["tc_offsets"][n] - 0.02)) for n in cfg["tc_channels"])
        run, dp = sim["run"], sim["dp_rig"]
        files = [run("still_r1", "still", 45, blower=False), run("still_r2", "still", 180, blower=False)]
        files += [run("d055_r1", "d055", 25, dp[0.55], flow=fl == "inline")]
        gap_files = [files[-1], run("gap_p3", "gap", 30, dp[0.55], offset=3.0), run("gap_p6", "gap", 30, dp[0.55], offset=6.0)]
        g = cmd_gap(gap_files, cfg, None, quiet=True)
        files += [run(f"floor_r{i}", "floor", 25, dp[0.458], flow=fl == "inline" and i == 1) for i in (1, 2)]
        files += [run(f"d055_r{i}", "d055", 25, dp[0.55]) for i in (2, 3)]
        files += [run(f"full_r{i}", "full", 20, dp[1.0], flow=fl == "inline" and i == 1) for i in (1, 2)]
        if fl == "flowcal":
            files += [run(f"flowcal_{d}", "flowcal", 5, dp[d], power=0.0, guard=False, flow=True) for d in (0.458, 0.55, 1.0)]
        if label == "pass_h125":
            files += [run("height_5p5", "height", 25, dp[0.55], H=5.5), run("height_6p5", "height", 25, dp[0.55], H=6.5)]
        files += [run(f"sweep_{d}", "sweep", 25, dp[d]) for d in (0.5, 0.7, 0.8)]
        tr_file = run("transient_d055", "transient", 30, dp[0.55], step=1.5)
        rep = cmd_report(files + gap_files[1:], cfg, out_file=None, quiet=True)
        tr = cmd_transient(tr_file, cfg, quiet=True)

        # truth at the product for each drive (film reference, as the generator defines it)
        pp = props(SETP["product"]["film_C"])
        h_true_prod = {f"{r['drive']}": sim["nu_true"](r["jet_dp_Pa"]) * pp["k"] / 0.003 for r in SETP["rows"]}
        d = rep["mc"]["drives"]
        err = {k: round(d[k]["h_med"] / h_true_prod[k] - 1, 4) for k in d}
        cover = {k: d[k]["h_lo95"] <= h_true_prod[k] <= d[k]["h_hi95"] for k in d}
        run_err = []
        for r in rep["runs"]:
            if r["jet"] and r["condition"] not in ("gap", "transient"):
                ht = sim["h_true"](r["dp"] / sim["truth"]["dp_gain"], r["Tref"] + r["dT"], r["Tref"], r["H_mm"])
                run_err.append(abs(r["h_central"] / ht - 1))
        still = rep["mc"]["still_air"]
        h_tr_ref = np.median([r["h_central"] for r in rep["runs"] if r["condition"] == "d055"])
        vd = rep["verdict"]
        st = vd["cases"]["c28_bay61"]["at_0.55"]
        checks = {
            "zero_offsets_within_0.03K": off_err <= 0.03,
            "G_gap_within_15pct": abs(g["G_gap_W_K"] / sim["truth"]["G_gap"] - 1) <= 0.15,
            "per_run_h_within_1.5pct": max(run_err) <= 0.015,
            "still_air_within_10pct": abs(still["h_med"] / sim["truth"]["h_still"] - 1) <= 0.10,
            "product_h_0.55_within_2pct": abs(err["0.55"]) <= 0.02,
            "truth_inside_U95_all_drives": all(cover.values()),
            "transient_within_5pct_of_steady": abs(tr["h_transient"] / h_tr_ref - 1) <= 0.05,
            "height_slope_within_0.02_per_mm": label != "pass_h125" or (
                rep["mc"]["measured_dlnh_dH"] is not None
                and abs(rep["mc"]["measured_dlnh_dH"]["per_mm"] - sim["truth"]["dlnh_dH"]) <= 0.02),
            "cd_measured_within_3pct": (not fl) or (rep["mc"]["cd_measured"] is not None
                                                  and abs(rep["mc"]["cd_measured"]["mean"] / sim["truth_cd"] - 1) <= 0.03),
            "verdict_as_expected": expect is None or st == expect,
            "near_threshold_not_FAIL": expect is not None or st in ("PASS", "MARGINAL"),
        }
        checks = {k: bool(v) for k, v in checks.items()}
        cover = {k: bool(v) for k, v in cover.items()}
        ok = all(checks.values())
        ok_all &= ok
        out["scenarios"][label] = {
            "h_true_0.55": round(h_true_prod["0.55"], 2), "h_med_0.55": d["0.55"]["h_med"],
            "h95_0.55": [d["0.55"]["h_lo95"], d["0.55"]["h_hi95"]], "u95_rel_0.55": d["0.55"]["u95_rel"],
            "rel_error_by_drive": err, "truth_covered": cover, "zero_max_offset_error_K": round(off_err, 4),
            "G_gap_fit": g["G_gap_W_K"], "G_gap_true": sim["truth"]["G_gap"], "worst_run_h_error": round(max(run_err), 4),
            "still_air": still, "h_still_true": sim["truth"]["h_still"], "transient": tr, "transient_ref_h": round(float(h_tr_ref), 2),
            "cd_measured": rep["mc"]["cd_measured"], "cd_true": sim["truth_cd"], "exponent_b": rep["mc"]["exponent_b"],
            "b_true": sim["b_true"], "birge": rep["mc"]["birge_ratio"], "flow": fl,
            "measured_dlnh_dH": rep["mc"]["measured_dlnh_dH"], "martin_dlnh_dH": rep["mc"]["martin_dlnh_dH_per_mm"], "c28_bay61_at_0.55": st,
            "raise_ceiling": vd["raise_ceiling"], "flags": rep["flags"], "checks": checks, "pass": ok,
            "c28_bay61_pass_needs_h_ge": round(SWEEP["required_h_top"]["c28_bay61"]["h_top_required"] / (1 - d["0.55"]["u95_rel"]), 1),
            "as_martin_factor_at_0.55": round(SWEEP["required_h_top"]["c28_bay61"]["h_top_required"] / (1 - d["0.55"]["u95_rel"])
                                              / d["0.55"]["delivery_h_est"], 3)}
        print(f"{label}: h(0.55) true {h_true_prod['0.55']:.1f}  fit {d['0.55']['h_med']} "
              f"[{d['0.55']['h_lo95']}, {d['0.55']['h_hi95']}]  U95 {d['0.55']['u95_rel']:.1%}  c28_bay61 {st}  "
              f"{'PASS' if ok else 'FAIL'} {[k for k, v in checks.items() if not v]}")
    shutil.rmtree(tmp, ignore_errors=True)
    out["pass"] = ok_all
    (HERE / "selftest.json").write_text(json.dumps(out, indent=1) + "\n")
    print("SELFTEST", "PASS" if ok_all else "FAIL")
    return ok_all


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("cmd", nargs="?", choices=["zero", "gap", "run", "report", "transient"])
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    cfg_path = HERE / "bench.json"
    if not cfg_path.exists():
        shutil.copy(HERE / "bench.example.json", cfg_path)
    cfg = load_bench(cfg_path)
    paths = [Path(p) for p in a.paths]
    if a.cmd == "report" and len(paths) == 1 and paths[0].is_dir():
        paths = sorted(paths[0].glob("*.csv"))
    if a.cmd == "zero":
        cmd_zero(paths[0], cfg, cfg_path)
    elif a.cmd == "gap":
        cmd_gap(paths, cfg, cfg_path)
    elif a.cmd == "run":
        r = run_values(paths[0], cfg)
        print(json.dumps({k: v for k, v in r.items() if k != "plate_ch"}, indent=1))
    elif a.cmd == "report":
        cmd_report(paths, cfg)
    elif a.cmd == "transient":
        cmd_transient(paths[0], cfg)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
