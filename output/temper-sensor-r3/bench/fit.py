"""sensor-r3 bench: fit dry contact tau63 per pan from survey logs, and gate C1.

The quantity the bench decides (DECISIONS.md section 5): C1's dry contact lag
    tau63_C1(h) = C_cap/(h A + G_leak) + C_el/G_bond      (screen.tau63, C1 constants)
must be <= 1.2 s on every pan; > 1.35 s on any pan is the stop rule.

The surrogate probe (RIG.md) does not have to match C1's heat capacity: each run
is fitted for the effective contact conductance per area h_c (a property of the
pan base, the face finish and the tilt-following mount, which the surrogate
copies), and C1's tau63 is then computed from h_c with C1's own constants.

Fit model (per set-down): two lumped nodes, cap (disc + bond, C_cap_s) and Pt100
element (C_el, G_bond = C_el / tau_int from the paste calibration), a leak G_leak
to the probe body at the pre-contact reading, and contact h_c * A to the pan,
switched on at t0. The pan target is the reference thermocouple (slowly cooling
pan) plus a constant offset dT that absorbs thermocouple error. Free: t0, ln h_c,
dT. Uncertainty: Jacobian covariance scaled by the residual variance.

Commands
  python fit.py --selftest              synthetic end-to-end test (writes selftest.json)
  python fit.py --selftest --selftest-probe probe.lean.json   same, for the lean probe
                                        (writes selftest-lean.json)
  python fit.py calibrate RUN.csv       paste-on-copper run -> tau_int into probe.json
  python fit.py run RUN.csv             fit one set-down log, print the result
  python fit.py survey RUNS_DIR         fit every *.csv, per-pan verdicts -> survey-results.json

Log format (logger.py writes it): '# key: value' header lines (pan, pan_class,
condition, repeat, probe), then rows 'R,t_us,rtd_reg', 'T,t_us,tc_counts,cj_counts',
'M,t_us,n', 'F,t_us,fault'.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import pi, sqrt
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import screen  # noqa: E402  (C1 constants and the tau63 definition the bar uses)

C1 = screen.CANDS["C1"]
TAU_BAR, TAU_STOP = 1.2, 1.35
A_CVD, B_CVD = 3.9083e-3, -5.775e-7          # IEC 60751 coefficients, T >= 0 C
PRE_S, WIN_S = 1.0, 8.0                        # fit window around the detected rise


# ---------------------------------------------------------------- probe constants
def load_probe(path: Path) -> dict:
    p = json.loads(path.read_text())
    d = p["disc"]
    c_disc = d["mass_mg"] * 1e-6 * d["cp_J_kgK"]
    p["C_cap_s"] = c_disc + p["bond"]["C_extra_J_K"]
    p["A_s"] = pi * (p["disc"]["contact_d_mm"] * 1e-3 / 2) ** 2
    p["C_el"] = p["element"]["C_el_J_K"]
    return p


def c1_tau63(h: float) -> float:
    return screen.tau63(C1, h)


# ---------------------------------------------------------------- log parsing
def rtd_reg_to_C(reg: np.ndarray, rref: float, r0: float = 100.0) -> np.ndarray:
    code = (reg.astype(np.int64) >> 1) & 0x7FFF
    r = code * rref / 32768.0
    return (-A_CVD + np.sqrt(A_CVD**2 - 4 * B_CVD * (1 - r / r0))) / (2 * B_CVD)


def tc_counts_to_C(counts: np.ndarray) -> np.ndarray:
    return counts.astype(float) / 128.0           # MAX31856 LTC: 19-bit signed, LSB 2^-7 C


def read_log(path: Path, rref: float) -> dict:
    meta, R, T, M = {}, [], [], []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            if ":" in line:
                k, v = line[1:].split(":", 1)
                meta[k.strip()] = v.strip()
            continue
        f = line.strip().split(",")
        if not f or not f[0]:
            continue
        if f[0] == "R":
            R.append((int(f[1]), int(f[2])))
        elif f[0] == "T":
            T.append((int(f[1]), int(f[2])))
        elif f[0] == "M":
            M.append(int(f[1]))
    R, T = np.array(R), np.array(T)
    out = {"meta": meta,
           "t_r": R[:, 0] * 1e-6, "y": rtd_reg_to_C(R[:, 1], rref),
           "t_tc": T[:, 0] * 1e-6 if len(T) else np.array([]),
           "tc": tc_counts_to_C(T[:, 1]) if len(T) else np.array([]),
           "marks": np.array(M) * 1e-6}
    t_origin = out["t_r"][0]
    for k in ("t_r", "t_tc", "marks"):
        out[k] = out[k] - t_origin
    return out


# ---------------------------------------------------------------- model
def model_matrices(C_cap, C_el, G_bond, G_leak, G_c):
    # states [T_cap, T_el]; inputs: target (pan) and body (probe body, at the pre-contact reading)
    A = np.array([[-(G_c + G_bond + G_leak) / C_cap, G_bond / C_cap],
                  [G_bond / C_el, -G_bond / C_el]])
    Bt = np.array([G_c / C_cap, 0.0])
    Bb = np.array([G_leak / C_cap, 0.0])
    return A, Bt, Bb


def response(ts, x0, a0, a1, body, C_cap, C_el, G_bond, G_leak, G_c):
    """Exact state at times ts >= 0 for target(t) = a0 + a1 t and a constant body temperature.

    x(t) = p0 + p1 t + expm(A t) (x0 - p0), with p1 = -A^-1 Bt a1 and A p0 + Bt a0 + Bb body = p1.
    A has real negative eigenvalues (a passive RC network), so expm is done by eigendecomposition.
    """
    A, Bt, Bb = model_matrices(C_cap, C_el, G_bond, G_leak, G_c)
    Ainv = np.linalg.inv(A)
    p1 = -Ainv @ (Bt * a1)
    p0 = Ainv @ (p1 - Bt * a0 - Bb * body)
    lam, V = np.linalg.eig(A)
    lam, V = lam.real, V.real
    c = np.linalg.solve(V, np.asarray(x0, float) - p0)
    h = V @ (c[:, None] * np.exp(np.outer(lam, ts)))
    return (p0[:, None] + np.outer(p1, ts) + h).T


def fit_setdown(t, y, t_ref, T_ref, probe, tau_int=None, h_guess=2000.0):
    """Fit one set-down. Returns dict with t0, h_c, dT, sigmas, residual, tau63 values."""
    tau_int = probe["tau_int_s"] if tau_int is None else tau_int
    C_cap, C_el, G_leak, A = probe["C_cap_s"], probe["C_el"], probe["G_leak_W_K"], probe["A_s"]
    G_bond = C_el / tau_int
    # detect the rise: first sample > baseline + 1 K (baseline from the first 0.5 s)
    base = np.median(y[t < t[0] + 0.5])
    i_rise = int(np.argmax(y > base + 1.0))
    t_rise = t[i_rise]
    w = (t >= t_rise - PRE_S) & (t <= t_rise + WIN_S)
    tw, yw = t[w], y[w]
    y0 = np.median(y[(t >= t_rise - PRE_S) & (t < t_rise - 0.2)]) if np.any(
        (t >= t_rise - PRE_S) & (t < t_rise - 0.2)) else yw[0]
    # reference: linear fit of the pan thermocouple over the window +-2 s
    rw = (t_ref >= tw[0] - 2) & (t_ref <= tw[-1] + 2)
    pc = np.polyfit(t_ref[rw], T_ref[rw], 1) if rw.sum() >= 3 else np.array([0.0, np.median(T_ref)])

    def pred(p):
        t0, lnh, dT = p
        h = np.exp(lnh)
        out = np.full(len(tw), y0)
        after = tw >= t0
        if after.any():
            a0 = np.polyval(pc, t0) + dT
            x = response(tw[after] - t0, [y0, y0], a0, pc[0], y0, C_cap, C_el, G_bond, G_leak, h * A)
            out[after] = x[:, 1]
        return out

    def res(p):
        return pred(p) - yw

    best = None
    for h0 in (h_guess / 4, h_guess, h_guess * 4):
        s = least_squares(res, [t_rise - 0.05, np.log(h0), 0.0], x_scale=[0.05, 0.3, 1.0],
                          bounds=([tw[0], np.log(50), -30], [t_rise + 0.2, np.log(2e6), 30]))
        if best is None or s.cost < best.cost:
            best = s
    J = best.jac
    dof = max(1, len(yw) - 3)
    s2 = 2 * best.cost / dof
    try:
        cov = np.linalg.inv(J.T @ J) * s2
        sig = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        sig = np.array([np.nan] * 3)
    t0, lnh, dT = best.x
    h = float(np.exp(lnh))
    # propagate ln h sigma to tau63 (derivative by finite difference)
    dtau = (c1_tau63(h * 1.01) - c1_tau63(h / 1.01)) / (2 * np.log(1.01))
    tau_s = C_cap / (h * A + G_leak) + tau_int
    return {"t0_s": round(float(t0), 4), "h_c_W_m2K": round(h, 1), "ln_h_sigma": round(float(sig[1]), 4),
            "dT_K": round(float(dT), 3), "rms_K": round(float(np.sqrt(s2)), 4),
            "tau63_surrogate_s": round(tau_s, 4), "tau63_C1_s": round(c1_tau63(h), 4),
            "tau63_C1_sigma_s": round(abs(dtau) * float(sig[1]), 4),
            "ref_slope_K_s": round(float(pc[0]), 3), "y0_C": round(float(y0), 3), "n": int(len(yw))}


# probe-constant uncertainties (1-sigma-ish, stated in DECISIONS.md D6)
SYS = {"C_cap_s": 0.04, "C_el": 0.30, "G_leak_W_K": 0.50, "tau_int_s": 0.015}


def systematic_band(t, y, t_ref, T_ref, probe, base):
    """Refit with each probe constant perturbed (+ and -); RSS of the largest tau63_C1 shift per constant."""
    shifts = {}
    for k, rel in {**SYS, **probe.get("sys", {})}.items():
        worst = 0.0
        for sgn in (+1, -1):
            q = dict(probe)
            if k == "tau_int_s":
                q[k] = max(0.01, probe[k] + sgn * rel)
            else:
                q[k] = probe[k] * (1 + sgn * rel)
            r = fit_setdown(t, y, t_ref, T_ref, q, h_guess=base["h_c_W_m2K"])
            worst = max(worst, abs(r["tau63_C1_s"] - base["tau63_C1_s"]))
        shifts[k] = round(worst, 4)
    return round(sqrt(sum(v * v for v in shifts.values())), 4), shifts


def verdict(tau, sys_s=0.0):
    """PASS if tau + sys <= bar; STOP if tau - sys > stop line; otherwise MARGINAL."""
    if tau + sys_s <= TAU_BAR:
        return "PASS"
    if tau - sys_s > TAU_STOP:
        return "STOP"
    return "MARGINAL"


def fit_calibration(t, y, t_ref, T_ref):
    """Paste-on-copper run: first-order fit gives tau_int (+ the tiny paste-joint lag)."""
    base = np.median(y[t < t[0] + 0.5])
    i_rise = int(np.argmax(y > base + 1.0))
    tr = t[i_rise]
    w = (t >= tr - PRE_S) & (t <= tr + 3.0)
    tw, yw = t[w], y[w]
    y0 = np.median(yw[tw < tr - 0.2]) if np.any(tw < tr - 0.2) else yw[0]
    T_fin = np.median(T_ref[(t_ref > tr + 1) & (t_ref < tr + 5)]) if len(T_ref) else yw[-1]

    def res(p):
        t0, tau, dT = p
        s = np.clip(tw - t0, 0, None)
        return y0 + (T_fin + dT - y0) * (1 - np.exp(-s / tau)) - yw

    s = least_squares(res, [tr - 0.02, 0.15, 0.0], bounds=([tw[0], 0.005, -30], [tr + 0.2, 3.0, 30]))
    return {"tau_int_s": round(float(s.x[1]), 4), "t0_s": round(float(s.x[0]), 4), "dT_K": round(float(s.x[2]), 3)}


# ---------------------------------------------------------------- synthetic truth for the self-test
def synth_log(path: Path, probe_true: dict, h_true: float, rng, *, paste=False, rref=430.0,
              T_pan0=150.0, cool=0.25, settle_s=None, tc_offset=1.5, n_layers=6, ref_extra_cool=0.0):
    """Higher-fidelity generator than the fit model: disc conducted through n_layers
    (Biot effects), bond + element nodes, contact that ramps on over a settling time,
    cooling pan, thermocouple with lag/offset/noise, MAX31865 codes with quantisation,
    noise and 60 Hz sampling jitter. Writes a log in the logger.py format.
    ref_extra_cool (K/s): after set-down the reference location cools this much faster
    than the contact point (plate-induced gradient; plate_check.py)."""
    d = probe_true
    A = d["A_s"]
    n = n_layers
    C_layer = d["C_disc_true"] / n
    G_z = d["k_disc"] * pi * (d["disc_d_m"] / 2) ** 2 / (d["t_disc_m"] / n)
    C_bond, C_el, G_bond, G_leak = d["C_bond_true"], d["C_el_true"], d["G_bond_true"], d["G_leak_true"]
    settle = rng.uniform(0.03, 0.15) if settle_s is None else settle_s
    t_contact = 2.0 + rng.uniform(0, 0.5)
    t_end = t_contact + 12.0
    dt = 2e-4
    nodes = n + 1  # disc layers + element; bond C lumped into the bottom layer
    C = np.array([C_layer] * n + [C_el])
    C[n - 1] += C_bond
    T = np.full(nodes, 25.0)
    T_body = 25.0
    K0 = np.zeros((nodes, nodes))
    for i in range(n - 1):
        K0[i, i] += G_z
        K0[i + 1, i + 1] += G_z
        K0[i, i + 1] -= G_z
        K0[i + 1, i] -= G_z
    K0[n - 1, n - 1] += G_bond + G_leak
    K0[n, n] += G_bond
    K0[n - 1, n] -= G_bond
    K0[n, n - 1] -= G_bond
    bvec = np.zeros(nodes)
    bvec[n - 1] = G_leak * T_body
    out = []
    t_next_r = rng.uniform(0, 0.0167)
    t_next_tc = rng.uniform(0, 0.1)
    tc_state = T_pan0
    tt = 0.0
    while tt < t_end:
        T_pan = T_pan0 - cool * tt
        if tt >= t_contact:
            ramp = min(1.0, (tt - t_contact) / settle)
            Gc = h_true * A * ramp
        else:
            Gc = 0.0
        # backward Euler (the layer modes are ~0.1 ms, far below dt): (C/dt + K) T' = C/dt T + b
        K = K0.copy()
        K[0, 0] += Gc
        rhs = C / dt * T + bvec
        rhs[0] += Gc * T_pan
        T = np.linalg.solve(np.diag(C / dt) + K, rhs)
        T_ref_loc = T_pan - ref_extra_cool * max(0.0, tt - t_contact)
        tc_state += dt * (T_ref_loc - tc_state) / 0.25    # bead lag 0.25 s
        if tt >= t_next_r:
            Tel = T[n] + rng.normal(0, 0.02)
            r = 100.0 * (1 + A_CVD * Tel + B_CVD * Tel**2)
            code = int(round(r / rref * 32768))
            out.append(f"R,{int(tt * 1e6)},{code << 1}")
            t_next_r += 0.0167 + rng.normal(0, 0.0003)
        if tt >= t_next_tc:
            tc = tc_state + tc_offset + rng.normal(0, 0.08)
            out.append(f"T,{int(tt * 1e6)},{int(round(tc * 128))},{int(25 * 64)}")
            t_next_tc += 0.1
        tt += dt
    hdr = [f"# pan: synth_h{h_true:.0f}", "# pan_class: synthetic", f"# condition: {'paste' if paste else 'dry_nominal'}",
           "# repeat: 1", f"# h_true: {h_true}", f"# settle_s: {settle:.3f}"]
    path.write_text("\n".join(hdr + out) + "\n")
    return settle


def selftest(probe_file: Path = HERE / "probe.example.json", out_file: Path = HERE / "selftest.json"):
    """End-to-end: synth logs -> calibrate -> fit -> tau63_C1 vs truth."""
    rng = np.random.default_rng(20261015)
    tmp = HERE / "_selftest_logs"
    tmp.mkdir(exist_ok=True)
    probe = load_probe(probe_file)
    # truth deliberately differs from the fit's nominal constants: element C +30 %,
    # bond thinner than nominal, disc conducted in layers, leak x1.5.
    t_d = probe["disc"]["t_mm"] * 1e-3
    d_d = probe["disc"]["d_mm"] * 1e-3
    truth = {"A_s": probe["A_s"], "C_disc_true": probe["C_cap_s"] - probe["bond"]["C_extra_J_K"],
             "C_bond_true": probe["bond"]["C_extra_J_K"], "k_disc": probe["disc"]["k_W_mK"],
             "t_disc_m": t_d, "disc_d_m": d_d, "C_el_true": probe["C_el"] * 1.3,
             "G_bond_true": 0.07, "G_leak_true": probe["G_leak_W_K"] * 1.5}
    # 1) calibration run (thermal paste on a copper block: joint ~ 80,000 W/m2K)
    cal_path = tmp / "cal.csv"
    synth_log(cal_path, truth, 8.0e4, rng, paste=True, settle_s=0.01)
    L = read_log(cal_path, 430.0)
    cal = fit_calibration(L["t_r"], L["y"], L["t_tc"], L["tc"])
    tau_int_true = truth["C_el_true"] / truth["G_bond_true"]
    rows = []
    for h in (500.0, 700.0, 888.0, 1100.0, 1300.0, 2000.0, 4000.0, 13000.0):
        for rep in range(3):
            p = tmp / f"h{h:.0f}_{rep}.csv"
            settle = synth_log(p, truth, h, rng)
            L = read_log(p, 430.0)
            probe_cal = {**probe, "tau_int_s": cal["tau_int_s"]}
            r = fit_setdown(L["t_r"], L["y"], L["t_tc"], L["tc"], probe_cal)
            sys_s = systematic_band(L["t_r"], L["y"], L["t_tc"], L["tc"], probe_cal, r)[0] if rep == 0 else None
            tau_true = c1_tau63(h)
            err = r["tau63_C1_s"] - tau_true
            tol = max(0.05, 0.05 * tau_true)
            verdict_true = "PASS" if tau_true <= TAU_BAR else ("MARGINAL" if tau_true <= TAU_STOP else "STOP")
            verdict_fit = "PASS" if r["tau63_C1_s"] <= TAU_BAR else ("MARGINAL" if r["tau63_C1_s"] <= TAU_STOP else "STOP")
            near_bar = abs(tau_true - TAU_BAR) <= tol or abs(tau_true - TAU_STOP) <= tol
            ok = (abs(err) <= tol if h <= 4000 else r["tau63_C1_s"] <= TAU_BAR) and (verdict_fit == verdict_true or near_bar)
            rows.append({"h_true": h, "rep": rep, "settle_s": round(settle, 3), "h_fit": r["h_c_W_m2K"],
                         "tau63_C1_true_s": round(tau_true, 4), "tau63_C1_fit_s": r["tau63_C1_s"],
                         "tau63_C1_sigma_s": r["tau63_C1_sigma_s"], "tau63_C1_sys_s": sys_s,
                         "err_s": round(err, 4), "tol_s": round(tol, 4),
                         "verdict_true": verdict_true, "verdict_fit": verdict_fit, "ok": bool(ok)})
    for f in tmp.glob("*.csv"):
        f.unlink()
    # survey aggregation check: three synthetic pans, one rep each, dry_nominal
    surv_dir = tmp / "survey"
    surv_dir.mkdir()
    expect = {"pan_A": (3000.0, "PASS"), "pan_B": (600.0, "STOP"), "pan_C": (1300.0, "PASS")}
    for name, (h, _) in expect.items():
        f = surv_dir / f"{name}.csv"
        synth_log(f, truth, h, rng)
        txt = f.read_text().replace(f"# pan: synth_h{h:.0f}", f"# pan: {name}").replace(
            "# pan_class: synthetic", f"# pan_class: class_{name}")
        f.write_text(txt)
    probe_path = tmp / "probe.json"
    raw = json.loads(probe_file.read_text())
    raw["tau_int_s"] = cal["tau_int_s"]
    probe_path.write_text(json.dumps(raw))
    cmd_survey(surv_dir, load_probe(probe_path))
    sres = json.loads((surv_dir / "survey-results.json").read_text())
    got = {x["pan"]: x["verdict"] for x in sres["summary"]}
    survey_ok = all(got.get(k) == v for k, (_, v) in expect.items()) and sres["overall"] == "STOP"
    for f in surv_dir.iterdir():
        f.unlink()
    surv_dir.rmdir()
    probe_path.unlink()
    tmp.rmdir()
    passed = all(r["ok"] for r in rows) and survey_ok
    out = {"scope": "fit.py --selftest: synthetic set-downs from a layered-disc generator with contact settling, "
                    "pan cooling, thermocouple lag/offset and MAX31865 quantisation; the fit uses the 2-node model "
                    "with nominal constants (element C 30 % low, leak 33 % low vs truth) and tau_int from a synthetic "
                    "paste calibration.",
           "tolerance": "|tau63_C1 fit - truth| <= max(0.05 s, 5 %) for h <= 4000; above that tau63_C1 fit <= 1.2 s; "
                        "verdict must match except within the tolerance of 1.2 or 1.35 s",
           "calibration": {**cal, "tau_int_true_s": round(tau_int_true, 4)},
           "max_abs_err_s_h_le_4000": round(max(abs(r["err_s"]) for r in rows if r["h_true"] <= 4000), 4),
           "survey_check": {"expected": {k: v for k, (_, v) in expect.items()}, "got": got,
                            "overall": sres["overall"], "ok": survey_ok},
           "rows": rows, "passed": passed}
    out["probe_file"] = probe_file.name
    out_file.write_text(json.dumps(out, indent=1) + "\n")
    print(f"calibration tau_int fit {cal['tau_int_s']} s (true {tau_int_true:.4f} s)")
    for r in rows:
        print(f"h {r['h_true']:7.0f} rep {r['rep']} settle {r['settle_s']:.3f}  h_fit {r['h_fit']:8.0f}  "
              f"tau63_C1 {r['tau63_C1_fit_s']:.3f} sys {r['tau63_C1_sys_s'] if r['tau63_C1_sys_s'] is not None else '-'} "
              f"(true {r['tau63_C1_true_s']:.3f})  "
              f"{r['verdict_fit']:8s} {'ok' if r['ok'] else 'FAIL'}")
    print("survey check:", out["survey_check"])
    print("SELFTEST", "PASS" if passed else "FAIL", "max |err| (h<=4000):", out["max_abs_err_s_h_le_4000"], "s")
    return 0 if passed else 1


# ---------------------------------------------------------------- CLI
def cmd_run(path: Path, probe: dict):
    L = read_log(path, probe["Rref_ohm"])
    r = fit_setdown(L["t_r"], L["y"], L["t_tc"], L["tc"], probe)
    sys_s, shifts = systematic_band(L["t_r"], L["y"], L["t_tc"], L["tc"], probe, r)
    return {**L["meta"], "file": path.name, **r, "tau63_C1_sys_s": sys_s, "sys_by_constant_s": shifts,
            "verdict": verdict(r["tau63_C1_s"], sys_s)}


def cmd_survey(d: Path, probe: dict):
    rows = []
    for p in sorted(d.glob("*.csv")):
        try:
            rows.append(cmd_run(p, probe))
        except Exception as e:  # keep going; record the failure
            rows.append({"file": p.name, "error": repr(e)})
    groups = {}
    for r in rows:
        if "error" in r:
            continue
        groups.setdefault((r.get("pan", "?"), r.get("pan_class", "?"), r.get("condition", "?")), []).append(r)
    summary = []
    for (pan, cls, cond), rs in sorted(groups.items()):
        taus = np.array([r["tau63_C1_s"] for r in rs])
        hs = np.array([r["h_c_W_m2K"] for r in rs])
        i_w = int(np.argmax(taus))
        worst, worst_sys = float(taus[i_w]), float(rs[i_w]["tau63_C1_sys_s"])
        summary.append({"pan": pan, "class": cls, "condition": cond, "n": len(rs),
                        "h_c_median": round(float(np.median(hs)), 0), "h_c_min": round(float(hs.min()), 0),
                        "tau63_C1_median_s": round(float(np.median(taus)), 3), "tau63_C1_worst_s": round(worst, 3),
                        "tau63_C1_worst_sys_s": round(worst_sys, 3),
                        "verdict": verdict(worst, worst_sys), "gated": cond == "dry_nominal"})
    gated = [s for s in summary if s["gated"]]
    overall = ("NO DATA" if not gated else "STOP" if any(s["verdict"] == "STOP" for s in gated)
               else "MARGINAL" if any(s["verdict"] == "MARGINAL" for s in gated) else "PASS")
    n_pans = len({s["pan"] for s in gated})
    classes = sorted({s["class"] for s in gated})
    out = {"bar_s": TAU_BAR, "stop_s": TAU_STOP, "overall": overall, "pans_gated": n_pans,
           "classes_gated": classes, "coverage_ok": n_pans >= 12 and len(classes) >= 6,
           "summary": summary, "runs": rows}
    (d / "survey-results.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{'pan':24s} {'class':20s} {'condition':14s} {'n':>2s} {'h_med':>7s} {'tau_med':>7s} {'tau_worst':>9s}  verdict")
    for s in summary:
        print(f"{s['pan']:24s} {s['class']:20s} {s['condition']:14s} {s['n']:2d} {s['h_c_median']:7.0f} "
              f"{s['tau63_C1_median_s']:7.3f} {s['tau63_C1_worst_s']:6.3f}+-{s['tau63_C1_worst_sys_s']:.3f}  {s['verdict']}{'' if s['gated'] else ' (not gated)'}")
    print(f"OVERALL {overall}; gated pans {n_pans}, classes {len(classes)}; coverage {'ok' if out['coverage_ok'] else 'INCOMPLETE (need >= 12 pans, 6 classes)'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--selftest-probe", default=None,
                    help="probe JSON for the self-test (default probe.example.json); "
                         "writes selftest-<name>.json instead of selftest.json")
    ap.add_argument("--probe", default=str(HERE / "probe.json"))
    ap.add_argument("cmd", nargs="?", choices=["calibrate", "run", "survey"])
    ap.add_argument("path", nargs="?")
    a = ap.parse_args()
    if a.selftest:
        if a.selftest_probe:
            pf = Path(a.selftest_probe)
            pf = pf if pf.is_absolute() else HERE / pf
            sys.exit(selftest(pf, HERE / f"selftest-{pf.stem.replace('probe.', '')}.json"))
        sys.exit(selftest())
    probe_path = Path(a.probe)
    probe = load_probe(probe_path)
    if a.cmd == "calibrate":
        L = read_log(Path(a.path), probe["Rref_ohm"])
        cal = fit_calibration(L["t_r"], L["y"], L["t_tc"], L["tc"])
        raw = json.loads(probe_path.read_text())
        raw["tau_int_s"] = cal["tau_int_s"]
        raw.setdefault("calibration_runs", []).append({"file": Path(a.path).name, **cal})
        probe_path.write_text(json.dumps(raw, indent=1) + "\n")
        print(json.dumps(cal))
    elif a.cmd == "run":
        print(json.dumps(cmd_run(Path(a.path), probe), indent=1))
    elif a.cmd == "survey":
        cmd_survey(Path(a.path), probe)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
