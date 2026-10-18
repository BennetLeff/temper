"""temper-sensor-r3 in-the-box screen of sensor architectures against DECISIONS.md section 1.

Reuses the sensor-r2 truth plant, filters and frozen controller
(../temper-sensor-r2/estimator_study.py, imported read-only) and the contact model
(contact_model.py) for each design's own h_c spread.

Candidates (numeric):
  C0  R16 cartridge as built: alumina cap 376 mJ/K, passive, fixed contact model
  C1  sensor-r3: lapped Si3N4 disc 8 x 0.32 mm on a PEEK post, thin bondline,
      passive, fixed contact model, power-step contact-loss probe (detector D1)
  C2  R16 cap + in-situ contact measurement: 40 mW Pt100 self-heating pulses
      (4 s every 12 s) and an EKF that estimates G_c (active; patent-flagged)
C3 (dual-element passive heat-flux) is rejected analytically in README.md.

Run: python screen.py   -> screen-results.json (about a minute on 10 cores)
"""
from __future__ import annotations

import json
import os
import sys
from math import exp, log, pi
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "temper-sensor-r2"))
sys.path.insert(0, str(HERE))
import contact_model as cm  # noqa: E402
import estimator_study as es  # noqa: E402

# ---- candidates ---------------------------------------------------------------
SI3N4_RHO_CP = 3250 * 690            # J/m3K (Si3N4 substrate grade, k 85-90)
C_DISC = SI3N4_RHO_CP * pi * 4.0e-3**2 * 0.32e-3
CANDS = {
    "C0": dict(label="R16 alumina cap, passive", C_CAP=es.C_CAP, G_BOND=es.G_BOND, G_LEAK=es.G_LEAK,
               A_CONTACT=pi * 4.5e-3**2, face="R16 alumina cap (ground)", pulse=False),
    "C1": dict(label="Si3N4 8x0.32 disc on PEEK post, passive", C_CAP=1.1 * C_DISC,   # +10 % bond/rim
               G_BOND=1.7 * (1.8e-3 * 2.0e-3) / 0.10e-3,                            # 0.10 mm EPO-TEK 930-4
               G_LEAK=0.8e-3,          # design cap (HANDOFF CAD gate G4): 0.3 mm PEEK neck >= 3 mm long,
                                       # wiper on the neck, 4-wire leads in low-k alloy for the first 20 mm
               A_CONTACT=pi * 3.8e-3**2, face="sensor-r3 Si3N4 disc (lapped)", pulse=False,
               h_nom=1300.0),       # chosen by hnom_sweep.py (tau-midpoint rule gives 1722)
    "C2": dict(label="R16 alumina cap + Pt100 self-heating pulses", C_CAP=es.C_CAP, G_BOND=es.G_BOND,
               G_LEAK=es.G_LEAK, A_CONTACT=pi * 4.5e-3**2, face="R16 alumina cap (ground)", pulse=True),
}
PULSE_W, PULSE_ON, PULSE_PERIOD = 0.040, 4.0, 12.0   # a 1 s pulse only sees the bond (tau 0.3 s)
STRESS_H = (300.0, 1000.0, 3000.0)
NOISE = 0.2


def apply(c):
    es.C_CAP, es.G_BOND, es.G_LEAK, es.A_CONTACT = c["C_CAP"], c["G_BOND"], c["G_LEAK"], c["A_CONTACT"]


def tau63(c, h):
    return c["C_CAP"] / (h * c["A_CONTACT"] + c["G_LEAK"]) + es.C_EL / c["G_BOND"]


def h_spread(c):
    """Per thermal pan: (h_min, h_max) over the cookware classes and tilts in contact_model."""
    tab = cm.table()[c["face"]]
    out = {}
    for row in tab.values():
        hs = list(row["h_c_by_tilt"].values())
        lo, hi = out.get(row["thermal_pan"], (1e9, 0))
        out[row["thermal_pan"]] = (min(lo, min(hs)), max(hi, max(hs)))
    return out


def h_nominal(c, spread):
    """Fixed-model h: c["h_nom"] if set, else the h whose tau63 sits mid-way in the design's tau range."""
    if c.get("h_nom"):
        return c["h_nom"]
    lo = min(v[0] for v in spread.values())
    hi = max(v[1] for v in spread.values())
    t_mid = 0.5 * (tau63(c, lo) + tau63(c, hi))
    g = c["C_CAP"] / (t_mid - es.C_EL / c["G_BOND"]) - c["G_LEAK"]
    return g / c["A_CONTACT"]


# ---- truth with element heater and a food drop ------------------------------------
class Truth(es.Truth):
    food_C, food_T0, food_h = 0.5 * 3500.0, 5.0, 600.0

    def __init__(self, *a, food_at=None, **k):
        super().__init__(*a, **k)
        self.food_at, self.Tf = food_at, None
        r_mid = (np.arange(es.N_RINGS) + 0.5) * self.p["R"] / es.N_RINGS
        self.food_mask = r_mid < 0.7 * self.p["R"]

    def step(self, P_in, h_c, P_h=0.0):
        super().step(P_in, h_c)
        self.Tel += es.DT_SIM * P_h / es.C_EL
        if self.food_at is not None and self.t >= self.food_at:
            if self.Tf is None:
                self.Tf = self.food_T0
            q = self.food_h * self.area * self.food_mask * (self.T - self.Tf)
            self.T = self.T - es.DT_SIM * q / self.C
            self.Tf += es.DT_SIM * q.sum() / self.food_C


class KFPulse(es.EKF):
    """x = [T_pan, v, T_cap, T_el, ln G_c]; known element heat pulses make G_c observable."""

    def __init__(self, y0, noise, h0):
        super().__init__([y0, 0.0, y0, y0, log(h0 * es.A_CONTACT)], [1.0, 0.25, 1.0, 1.0, 1.5**2],
                         [0.02, 0.05, 1e-4, 1e-4, 2e-3], noise, 3)

    def fmap(self, x, u):
        Tp, v, Tcap, Tel, lg = x
        _, Ts, P_h = u
        Gc = exp(lg)
        h = es.DT_CTRL / self.SUB
        for _ in range(self.SUB):
            dcap, dele = es.sensor_deriv(Tp, Tcap, Tel, Gc, Ts)
            Tp += h * v
            Tcap += h * dcap
            Tel += h * (dele + P_h / es.C_EL)
        return [Tp, v, Tcap, Tel, lg]

    def clamp(self):
        self.x[4] = min(max(self.x[4], log(50 * es.A_CONTACT)), log(50000 * es.A_CONTACT))

    def estimate(self):
        return float(self.x[0])


# ---- contact-loss detector D1 ------------------------------------------------------
TRIG_RATE, TRIG_HOLD_S, TRIG_PMIN = -0.8, 1.0, 0.4    # K/s over 2 s, s, fraction of P_MAX
PROBE_OFF, PROBE_ON, PROBE_P = 5.0, 8.0, 0.5           # off / on / off, on at 50 %
PROBE_TAU, PROBE_FRAC, RETRY_S = 3.0, 0.25, 20.0       # lag of the energy regressor, s
DECAY_RMS_K, HOLDOFF_S = 0.5, 30.0                     # free-decay fit tolerance; re-trigger hold-off


def slope(t, y):
    t = np.asarray(t)
    return float(np.polyfit(t - t.mean(), np.asarray(y), 1)[0])


def free_decay_rms(t, y, T_rim, tau_off):
    """RMS misfit of y to a free decay toward the rim temperature: the lost-contact
    hypothesis. Free parameters: the asymptote offset and tau within +-40 %."""
    best = 1e9
    for f in np.linspace(0.6, 1.4, 17):
        z = np.exp(-t / (f * tau_off))
        X = np.column_stack([np.ones_like(t), z])
        coef, res, *_ = np.linalg.lstsq(X, y, rcond=None)
        r = y - X @ coef
        # asymptote must be near the rim reading (within 25 K) for the hypothesis to hold
        if abs(coef[0] - T_rim) <= 25.0:
            best = min(best, float(np.sqrt(np.mean(r**2))))
    return best


def probe_says_contact(hist_t, hist_y, hist_P, t0, a, T_rim=None, tau_off=None):
    """Regress the reading on [1, t, t^2, E_lag(t)] over the probe; E = coil energy (kJ)
    passed through a first-order lag PROBE_TAU (pan-centre diffusion + sensor).

    A quadratic background absorbs a decaying heat draw (food) or the free decay
    toward the sink (lost contact); the coil-energy coefficient d is K/kJ seen at
    the sensor. Intact contact gives d ~ a (attenuated by the sensor lag); lost
    contact gives d ~ 0.
    """
    ts, ys, Ps = np.array(hist_t), np.array(hist_y), np.array(hist_P)
    w = ts >= t0
    t = ts[w] - t0
    E = np.cumsum(Ps[w]) * es.DT_CTRL / 1000.0
    E_lag = np.zeros_like(E)
    for i in range(1, len(E)):
        E_lag[i] = E_lag[i - 1] + es.DT_CTRL / PROBE_TAU * (E[i - 1] - E_lag[i - 1])
    X = np.column_stack([np.ones_like(t), t, t**2, E_lag])
    coef = np.linalg.lstsq(X, ys[w], rcond=None)[0]
    d_exp = a * 1000.0
    responds = coef[3] >= PROBE_FRAC * d_exp
    decays = free_decay_rms(t, ys[w], T_rim, tau_off) <= DECAY_RMS_K
    return responds or not decays, float(coef[3]), d_exp


def run(cid, pan_name, h_c, eta, mode, seed, h_nom, loss_at=None, food_at=None, detector=False):
    c = CANDS[cid]
    apply(c)
    pan = es.PANS[pan_name]
    tr = Truth(pan, h_c, eta, seed, food_at=food_at)
    rng = np.random.default_rng(seed + 1)
    sp1, sp2 = pan["sp"]
    a_true = eta / (tr.C.sum() + tr.Cw)
    if mode == "kf_fixed":
        est = es.KFNoPower(es.T_AMB, NOISE, h_c=h_nom)
    elif mode == "kf_pulse":
        est = KFPulse(es.T_AMB, NOISE, h_nom)
    else:
        est = None
    integ, P_cmd, sp_eff, T_prev, dT_f = 0.0, 0.0, es.T_AMB, es.T_AMB, 0.0
    n_sub = round(es.DT_CTRL / es.DT_SIM)
    hist_t, hist_hat, hist_y, hist_P = [], [], [], []
    state, t_state, trig_since, detected_at, probes = "normal", 0.0, None, None, 0
    probe_log, holdoff_until, suspect_at = [], 0.0, None
    log_ = []
    h_now = h_c
    for k in range(int(es.T_END / es.DT_CTRL)):
        t = k * es.DT_CTRL
        if loss_at is not None and t >= loss_at:
            h_now = 2.0                                   # tip off the pan / stuck down
        P_h = PULSE_W if (mode == "kf_pulse" and (t % PULSE_PERIOD) < PULSE_ON) else 0.0
        for _ in range(n_sub):
            tr.step(P_cmd, h_now, P_h)
        y = tr.Tel + NOISE * rng.standard_normal()
        ntc = tr.sink() + es.NTC_BIAS
        if mode == "perfect":
            T_hat = tr.T_c()
        elif mode == "raw":
            T_hat = y
        else:
            T_hat = est.step(y, (P_cmd, ntc, P_h) if mode == "kf_pulse" else (P_cmd, ntc))
        sp = sp1 if t + es.DT_CTRL < es.SP_STEP_T else sp2
        sp_eff = min(sp, sp_eff + es.SP_RATE * es.DT_CTRL) if sp > sp_eff else sp
        dT_f += (es.DT_CTRL / 2.0) * ((T_hat - T_prev) / es.DT_CTRL - dT_f)
        T_prev = T_hat
        e = sp_eff - T_hat
        if abs(e) < es.I_BAND:
            integ = min(max(integ + es.KI * e * es.DT_CTRL, 0.0), es.P_MAX * a_true)
        P_pid = min(max((es.KP * e + integ - es.KD * dT_f) / a_true, 0.0), es.P_MAX)
        hist_t.append(t)
        hist_hat.append(T_hat)
        hist_y.append(y)
        hist_P.append(P_cmd)
        # --- D1 state machine
        P_next = P_pid
        if detector:
            if state == "normal" and t >= holdoff_until:
                if len(hist_t) > 20:
                    s = slope(hist_t[-20:], hist_hat[-20:])
                    if s < TRIG_RATE and np.mean(hist_P[-20:]) >= TRIG_PMIN * es.P_MAX:
                        trig_since = t if trig_since is None else trig_since
                        if t - trig_since >= TRIG_HOLD_S:
                            state, t_state, probes = "probe", t, probes + 1
                            suspect_at = suspect_at if suspect_at is not None else t
                    else:
                        trig_since = None
            if state in ("probe", "retry"):
                dt = t - t_state
                if dt < 2 * PROBE_OFF + PROBE_ON:
                    P_next = PROBE_P * es.P_MAX if PROBE_OFF <= dt < PROBE_OFF + PROBE_ON else 0.0
                else:
                    ok, d, d_exp = probe_says_contact(hist_t, hist_y, hist_P, t_state, a_true,
                                                      ntc, c["C_CAP"] / c["G_LEAK"])
                    probe_log.append((round(t, 1), round(d, 3), round(d_exp, 3), bool(ok)))
                    if not ok:
                        state, t_state = "lost", t
                        detected_at = detected_at if detected_at is not None else t
                    else:
                        state, trig_since, holdoff_until = "normal", None, t + HOLDOFF_S
                        integ = 0.0
            if state == "lost":
                P_next = 0.0
                if t - t_state >= RETRY_S:
                    state, t_state = "retry", t
            if state in ("probe", "retry", "lost"):
                integ = 0.0
        P_cmd = P_next
        log_.append((t + es.DT_CTRL, sp, T_hat, tr.T_c(), tr.T_mean(), y, P_cmd, h_now,
                     exp(est.x[-1]) / es.A_CONTACT if mode == "kf_pulse" else float("nan")))
    L = np.array(log_)
    return L, {"probes": probes, "suspect_at": suspect_at, "detected_at": detected_at,
               "probe_log": probe_log[:6]}


def metrics(L, loss_at=None):
    m = es.metrics(L)
    t, sp, That, Tc, Tm = L[:, 0], L[:, 1], L[:, 2], L[:, 3], L[:, 4]
    m["T_mean_overshoot_K"] = round(float(max((Tm - sp)[t < es.SP_STEP_T].max(), (Tm - sp)[t >= es.SP_STEP_T].max())), 2)
    if loss_at is not None:
        after = t >= loss_at
        m["Tc_max_over_sp_after_loss_K"] = round(float((Tc - sp)[after].max()), 2)
        m["est_err_c_max_K"] = round(float(np.abs(That - Tc)[(t >= 10) & (t < loss_at)].max()), 2)
        m["overshoot_K"] = round(float((Tc - sp)[(t < loss_at)].max()), 2)
    return m


def job(args):
    cid, pan, h, eta, mode, seed, h_nom, kind, loss_at, food_at, det = args
    L, info = run(cid, pan, h, eta, mode, seed, h_nom, loss_at, food_at, det)
    return args, metrics(L, loss_at), info


def main():
    jobs = []
    meta = {}
    for cid, c in CANDS.items():
        apply(c)
        spread = h_spread(c)
        h_nom = h_nominal(c, spread)
        meta[cid] = {"label": c["label"], "C_cap_mJ_per_K": round(c["C_CAP"] * 1e3, 1),
                     "G_bond_W_per_K": round(c["G_BOND"], 4), "G_leak_mW_per_K": round(c["G_LEAK"] * 1e3, 2),
                     "contact_area_mm2": round(c["A_CONTACT"] * 1e6, 1),
                     "h_spread_by_pan": spread, "h_nominal": round(h_nom, 0),
                     "tau63_s_by_pan": {p: [round(tau63(c, lo), 2), round(tau63(c, hi), 2)]
                                        for p, (lo, hi) in spread.items()},
                     "tau63_s_stress": {f"{h:.0f}": round(tau63(c, h), 2) for h in STRESS_H},
                     "tau_off_s": round(c["C_CAP"] / c["G_LEAK"], 1)}
        modes = ["perfect", "raw", "kf_pulse" if c["pulse"] else "kf_fixed"]
        i = 0
        for pan, (lo, hi) in spread.items():
            for h in (lo, hi):
                for eta in es.ETA_SWEEP:
                    for mode in modes:
                        jobs.append((cid, pan, h, eta, mode, 100 + i, h_nom, "design", None, None, False))
                    i += 1
        for pan in es.PANS:
            for h in STRESS_H:
                for mode in modes[1:]:
                    jobs.append((cid, pan, h, 0.82, mode, 300 + i, h_nom, "stress", None, None, False))
                i += 1
        if not c["pulse"]:
            # B5 contact loss at t = 250 s (during the first hold), with D1; food-drop false positives.
            for pan, (lo, hi) in spread.items():
                h_mid = (lo * hi) ** 0.5
                jobs.append((cid, pan, h_mid, 0.82, "kf_fixed", 500 + i, h_nom, "loss", 250.0, None, True))
                jobs.append((cid, pan, h_mid, 0.82, "kf_fixed", 500 + i, h_nom, "loss_nodet", 250.0, None, False))
                jobs.append((cid, pan, h_mid, 0.82, "kf_fixed", 500 + i, h_nom, "nominal_det", None, None, True))
                if pan != "disc_pot_water_1l5":
                    jobs.append((cid, pan, h_mid, 0.82, "kf_fixed", 500 + i, h_nom, "food", None, 250.0, True))
                i += 1
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        res = pool.map(job, jobs)
    rows = []
    for (cid, pan, h, eta, mode, seed, h_nom, kind, loss_at, food_at, det), m, info in res:
        sp_hi = es.PANS[pan]["sp"][1]
        b3_lim = 1.5 if sp_hi <= 100 else 3.0
        row = {"cand": cid, "kind": kind, "pan": pan, "h_c": round(h, 0), "eta": eta, "mode": mode, **m, **info}
        if kind in ("design", "stress") and mode != "perfect":
            row["B1"] = m["est_err_c_max_K"] <= 3.0
        if kind in ("design", "stress"):
            row["B2"] = m["overshoot_K"] <= 5.0
            row["B3"] = max(abs(x) for x in m["hold_err_c_K"]) <= b3_lim
        if kind == "loss":
            row["B5"] = (info["detected_at"] is not None and info["detected_at"] - 250.0 <= 15.0
                         and m["Tc_max_over_sp_after_loss_K"] <= 15.0)
        rows.append(row)
    summary = {}
    for cid in CANDS:
        s = {}
        for kind in ("design", "stress"):
            for mode in ("perfect", "raw", "kf_fixed", "kf_pulse"):
                g = [r for r in rows if r["cand"] == cid and r["kind"] == kind and r["mode"] == mode]
                if not g:
                    continue
                s[f"{kind}/{mode}"] = {
                    "cases": len(g),
                    "B1_pass": sum(bool(r.get("B1")) for r in g) if mode != "perfect" else None,
                    "B2_pass": sum(bool(r["B2"]) for r in g), "B3_pass": sum(bool(r["B3"]) for r in g),
                    "worst_est_err_K": max(r["est_err_c_max_K"] for r in g),
                    "worst_overshoot_K": max(r["overshoot_K"] for r in g),
                    "worst_T_mean_overshoot_K": max(r["T_mean_overshoot_K"] for r in g)}
        for kind in ("loss", "loss_nodet", "nominal_det", "food"):
            g = [r for r in rows if r["cand"] == cid and r["kind"] == kind]
            if g:
                s[kind] = [{k: r.get(k) for k in ("pan", "h_c", "suspect_at", "detected_at", "probes", "Tc_max_over_sp_after_loss_K",
                                                  "overshoot_K", "hold_err_c_K", "B5")} for r in g]
        summary[cid] = s
    out = {"scope": __doc__.strip(), "candidates": meta, "noise_K": NOISE,
           "pulse": {"W": PULSE_W, "on_s": PULSE_ON, "period_s": PULSE_PERIOD},
           "detector_D1": {"decay_fit_rms_K": DECAY_RMS_K, "holdoff_s": HOLDOFF_S,"trigger_rate_K_s_over_2s": TRIG_RATE, "trigger_hold_s": TRIG_HOLD_S,
                           "trigger_Pmin_frac": TRIG_PMIN, "probe": "off/on/off", "probe_off_s": PROBE_OFF, "probe_on_s": PROBE_ON,
                           "energy_lag_s": PROBE_TAU,
                           "probe_P_frac": PROBE_P, "lost_if_energy_coef_below_frac_of_a": PROBE_FRAC,
                           "retry_s": RETRY_S},
           "summary": summary, "rows": rows}
    (HERE / "screen-results.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for cid, s in summary.items():
        print(f"== {cid} {meta[cid]['label']}  h_nom={meta[cid]['h_nominal']}  tau by pan {meta[cid]['tau63_s_by_pan']}")
        for k, v in s.items():
            print("  ", k, v)


if __name__ == "__main__":
    main()
