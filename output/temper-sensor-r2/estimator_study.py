"""temper-sensor-r2: route-1 (coil-as-stimulus) estimator on the passive R16 cartridge.

Question: with no heater in the cartridge, can firmware that knows the coil
power remove the passive Pt100's lag and contact error well enough to meet the
DECISIONS.md bar? (A1: |estimate - T_c| <= 3 K after 10 s; A2: closed-loop
overshoot of true T_c <= 5 K; Pt100 noise 0.2 K rms; h_c 300..3000 W/m2K.)

Truth plant (richer than any estimator):
  - pan base as N radial rings (finite difference), wall mass lumped on the rim
    ring, heat input over the coil annulus r 20..114 mm with a half-sine
    profile, convective + radiative loss, optional water node that boils at
    100 C;
  - cartridge from evidence/sensor-r16/thermal_screen.py (R15 alumina design):
    cap node on the centre ring through h_c over the contact disc, Pt100 chip on
    a bond under the cap, silicone-boot leak to a sink that warms during the run;
  - rim NTC reads the sink with a +3 K error; Pt100 adds white noise.

Feedback variants, each in its own closed PI loop (same gains):
  perfect     feedback on true T_c (shows what the controller alone does)
  raw         Pt100 reading
  kf_nopower  Kalman filter, constant-velocity pan, nominal h_c (no power info)
  kf_oracle_h the same filter told the true h_c: the ceiling for any scheme
              that could measure contact (not realisable passively)
  ekf_power   route 1: EKF with pan driven by a*P + d, estimating T_pan, h_c (as
              G_c), a = eta/C_pan and an unmodelled-heat drift d online

Run: python estimator_study.py   (writes results.json, prints the gate table)
"""
from __future__ import annotations

import json
import os
from math import exp, log, pi, sqrt
from multiprocessing import Pool
from pathlib import Path

import numpy as np

# ---- cartridge (R15/R16 alumina design, values from thermal_screen.py) ------
C_CAP = 3720 * 880 * (pi * 5.0e-3**2 * 0.6e-3 + 2 * pi * 5.0e-3 * 0.6e-3 * 3.6e-3)
C_EL = 3970 * 880 * (1.8e-3 * 2.0e-3 * 0.65e-3)
G_BOND = 1.5 * (1.8e-3 * 2.0e-3) / 0.2e-3
G_LEAK = 0.25 * (2 * pi * 5.3e-3 * 0.4e-3) / 3.0e-3
A_CONTACT = pi * 4.5e-3**2
H_NOMINAL = 1000.0

# ---- coil, power, environment ---------------------------------------------
R_IN, R_OUT = 0.020, 0.114     # heated annulus: coil eye >= 40 (spec row 14), OD 228
P_MAX = 1800.0                 # input W
T_AMB = 25.0
SIGMA_SB = 5.670e-8
NTC_BIAS = 3.0                 # rim-NTC error vs true sink, K
DT_CTRL = 0.1                  # controller / estimator / sample period, s
DT_SIM = 0.02                  # truth integration step, s
T_END = 600.0
N_RINGS = 24

# Pans. kt = sum(k*t) and rct = sum(rho*cp*t) per m2 of base, from the layer stack.
PANS = {
    "cast_iron_26": dict(R=0.105, kt=50 * 5e-3, rct=7200 * 460 * 5e-3, eps=0.8,
                         wall_H=0.05, wall_rct=7200 * 460 * 4.5e-3, water_kg=0.0, sp=(200, 230)),
    "carbon_steel_28": dict(R=0.100, kt=50 * 2e-3, rct=7850 * 470 * 2e-3, eps=0.7,
                            wall_H=0.05, wall_rct=7850 * 470 * 2e-3, water_kg=0.0, sp=(200, 230)),
    "triply_clad_24": dict(R=0.090, kt=16 * 1.0e-3 + 200 * 1.6e-3, rct=4.0e6 * 1.0e-3 + 2.43e6 * 1.6e-3,
                           eps=0.15, wall_H=0.06, wall_rct=4.0e6 * 1.0e-3 + 2.43e6 * 1.6e-3,
                           water_kg=0.0, sp=(180, 210)),
    "disc_pot_water_1l5": dict(R=0.080, kt=16 * 1.2e-3 + 200 * 4e-3, rct=4.0e6 * 1.2e-3 + 2.43e6 * 4e-3,
                               eps=0.15, wall_H=0.12, wall_rct=4.0e6 * 0.6e-3, water_kg=1.5, sp=(90, 100)),
}
H_SWEEP = (300.0, 1000.0, 3000.0)
ETA_SWEEP = (0.82, 0.92)
NOISE_SWEEP = (0.05, 0.2)
SP_STEP_T = 360.0


class Truth:
    def __init__(self, pan, h_c, eta, seed):
        self.p, self.h_c, self.eta = pan, h_c, eta
        dr = pan["R"] / N_RINGS
        r_lo = np.arange(N_RINGS) * dr
        r_hi = r_lo + dr
        area = pi * (r_hi**2 - r_lo**2)
        self.area = area
        self.C = pan["rct"] * area
        wall_area = 2 * pi * pan["R"] * pan["wall_H"]
        self.C[-1] += pan["wall_rct"] * wall_area
        self.loss_area = area.copy()
        self.loss_area[-1] += 2 * wall_area           # inside + outside of the wall
        self.G = 2 * pi * pan["kt"] * r_hi[:-1] / dr  # ring i <-> i+1
        rm = 0.5 * (r_lo + r_hi)
        prof = np.where((rm > R_IN) & (rm < R_OUT), np.sin(pi * (rm - R_IN) / (R_OUT - R_IN)), 0.0) * area
        self.heat_frac = prof / prof.sum()
        self.T = np.full(N_RINGS, T_AMB)
        self.Tcap = self.Tel = T_AMB
        self.Cw = pan["water_kg"] * 4186.0
        self.Tw = T_AMB
        self.t = 0.0
        self.rng = np.random.default_rng(seed)

    def sink(self):
        rise = 35.0 if self.Cw else 50.0
        return T_AMB + rise * (1 - exp(-self.t / 300.0))

    def step(self, P_in, h_c):
        p = self.p
        Ts = self.sink()
        g_c = h_c * A_CONTACT
        q = self.eta * P_in * self.heat_frac
        T = self.T
        cond = np.zeros(N_RINGS)
        flow = self.G * (T[1:] - T[:-1])
        cond[:-1] += flow
        cond[1:] -= flow
        # bottom: through the glass to the sink-ish glass temperature
        loss = 15.0 * self.area * (T - Ts)
        if self.Cw:
            hw = 2000.0
            to_water = hw * self.area * (T - self.Tw)
            loss = loss + to_water
            wall_rad = self.loss_area - self.area
            loss += wall_rad * (10.0 * (T - T_AMB) + p["eps"] * SIGMA_SB * ((T + 273.15)**4 - (T_AMB + 273.15)**4))
            dTw = (to_water.sum() - 20.0 * pi * p["R"]**2 * (self.Tw - T_AMB)) / self.Cw
        else:
            loss += self.loss_area * (10.0 * (T - T_AMB)
                                      + p["eps"] * SIGMA_SB * ((T + 273.15)**4 - (T_AMB + 273.15)**4))
        sens = g_c * (T[0] - self.Tcap)
        dT = (q + cond - loss) / self.C
        dT[0] -= sens / self.C[0]
        dcap = (sens - G_LEAK * (self.Tcap - Ts) - G_BOND * (self.Tcap - self.Tel)) / C_CAP
        del_ = G_BOND * (self.Tcap - self.Tel) / C_EL
        self.T = T + DT_SIM * dT
        self.Tcap += DT_SIM * dcap
        self.Tel += DT_SIM * del_
        if self.Cw:
            self.Tw = min(100.0, self.Tw + DT_SIM * dTw)   # surplus boils off
        self.t += DT_SIM

    def T_c(self):
        return float(self.T[0])

    def T_mean(self):
        w = self.area * ((np.arange(N_RINGS) + 0.5) * self.p["R"] / N_RINGS > R_IN)
        return float((self.T * w).sum() / w.sum())


# ---- estimators -------------------------------------------------------------
def sensor_deriv(Tp, Tcap, Tel, Gc, Ts):
    dcap = (Gc * (Tp - Tcap) - G_LEAK * (Tcap - Ts) - G_BOND * (Tcap - Tel)) / C_CAP
    return dcap, G_BOND * (Tcap - Tel) / C_EL


class EKF:
    """Generic EKF over a pure-python discrete map with a numeric Jacobian."""
    SUB = 5

    def __init__(self, x0, P0, Q, r_meas, meas_idx):
        self.x = np.array(x0, float)
        self.P = np.diag(P0).astype(float)
        self.Q = np.diag(Q) * DT_CTRL
        self.R = r_meas**2
        self.mi = meas_idx

    def fmap(self, x, u):
        raise NotImplementedError

    def step(self, y, u):
        x = self.x
        fx = np.array(self.fmap(list(x), u))
        F = np.empty((len(x), len(x)))
        for j in range(len(x)):
            e = 1e-5 if j >= 3 else 1e-3
            xp = list(x)
            xp[j] += e
            F[:, j] = (np.array(self.fmap(xp, u)) - fx) / e
        P = F @ self.P @ F.T + self.Q
        S = P[self.mi, self.mi] + self.R
        K = P[:, self.mi] / S
        self.x = fx + K * (y - fx[self.mi])
        self.P = P - np.outer(K, P[self.mi, :])
        self.P = 0.5 * (self.P + self.P.T)
        self.clamp()
        return self.estimate()

    def clamp(self):
        pass


class EKFPower(EKF):
    """x = [T_pan, T_cap, T_el, ln G_c, ln a, d]; T_pan' = a P + d."""

    def __init__(self, y0, noise):
        a0 = 0.88 / 900.0
        super().__init__([y0, y0, y0, log(H_NOMINAL * A_CONTACT), log(a0), 0.0],
                         [1.0, 1.0, 1.0, 1.2**2, 0.8**2, 0.05**2],
                         [0.02, 1e-4, 1e-4, 0.01, 2e-4, 2e-4], noise, 2)

    def fmap(self, x, u):
        Tp, Tcap, Tel, lg, la, d = x
        P_in, Ts = u
        Gc, a = exp(lg), exp(la)
        h = DT_CTRL / self.SUB
        for _ in range(self.SUB):
            dcap, dele = sensor_deriv(Tp, Tcap, Tel, Gc, Ts)
            Tp += h * (a * P_in + d)
            Tcap += h * dcap
            Tel += h * dele
        return [Tp, Tcap, Tel, lg, la, d]

    def clamp(self):
        self.x[3] = min(max(self.x[3], log(100 * A_CONTACT)), log(10000 * A_CONTACT))
        self.x[4] = min(max(self.x[4], log(0.5 / 20000)), log(1.0 / 200))

    def estimate(self):
        return float(self.x[0])


class KFNoPower(EKF):
    """x = [T_pan, v, T_cap, T_el]; constant-velocity pan, nominal G_c, no power."""

    def __init__(self, y0, noise, h_c=H_NOMINAL):
        super().__init__([y0, 0.0, y0, y0], [1.0, 0.5**2, 1.0, 1.0], [0.02, 0.05, 1e-4, 1e-4], noise, 3)
        self.Gc = h_c * A_CONTACT

    def fmap(self, x, u):
        Tp, v, Tcap, Tel = x
        _, Ts = u
        Gc = self.Gc
        h = DT_CTRL / self.SUB
        for _ in range(self.SUB):
            dcap, dele = sensor_deriv(Tp, Tcap, Tel, Gc, Ts)
            Tp += h * v
            Tcap += h * dcap
            Tel += h * dele
        return [Tp, v, Tcap, Tel]

    def estimate(self):
        return float(self.x[0])


# ---- closed loop ------------------------------------------------------------
# Gain-scheduled PID in the rate domain: rate_cmd [K/s] = KP e + KI int(e) - KD dT/dt,
# P = rate_cmd / a, where a = eta / C_total is the pan's lumped heating gain.
# Every feedback variant gets the TRUE a, so A2 compares sensing, not plant ID.
# Frozen from a sweep on perfect feedback (DECISIONS.md section 5) before any
# estimator was compared: worst perfect-feedback overshoot 2.06 K.
KP, KI, KD, I_BAND = 0.1, 0.002, 1.0, 10.0      # 1/s, 1/s2, -, K
SP_RATE = 1.0                  # setpoint ramp limit, K/s


def run(pan_name, h_c, eta, noise, mode, h_step=None, seed=0, h_factor=1.0):
    """One closed-loop run. The noise seed is per case, shared by every mode.

    h_factor scales the h_c given to kf_oracle_h (1.0 = told the truth)."""
    pan = PANS[pan_name]
    tr = Truth(pan, h_c, eta, seed)
    rng = np.random.default_rng(seed + 1)
    sp1, sp2 = pan["sp"]
    est = {"ekf_power": EKFPower, "kf_nopower": KFNoPower, "kf_oracle_h": KFNoPower}.get(mode)
    est = est(T_AMB, noise) if est else None
    integ, P_cmd = 0.0, 0.0
    a_true = eta / (tr.C.sum() + tr.Cw)
    sp_eff, T_prev, dT_f = T_AMB, T_AMB, 0.0
    n_sub = round(DT_CTRL / DT_SIM)
    log_ = []
    h_now = h_c
    for k in range(int(T_END / DT_CTRL)):
        t = k * DT_CTRL
        if h_step and t >= h_step[0]:
            h_now = h_step[1]
        for _ in range(n_sub):
            tr.step(P_cmd, h_now)
        y = tr.Tel + noise * rng.standard_normal()
        ntc = tr.sink() + NTC_BIAS
        if mode == "perfect":
            T_hat = tr.T_c()
        elif mode == "raw":
            T_hat = y
        else:
            if mode == "kf_oracle_h":
                est.Gc = h_factor * h_now * A_CONTACT   # told the contact, including any step
            T_hat = est.step(y, (P_cmd, ntc))
        sp = sp1 if t + DT_CTRL < SP_STEP_T else sp2
        sp_eff = min(sp, sp_eff + SP_RATE * DT_CTRL) if sp > sp_eff else sp
        dT_f += (DT_CTRL / 2.0) * ((T_hat - T_prev) / DT_CTRL - dT_f)   # 2 s filter
        T_prev = T_hat
        e = sp_eff - T_hat
        if abs(e) < I_BAND:
            integ = min(max(integ + KI * e * DT_CTRL, 0.0), P_MAX * a_true)
        P_cmd = min(max((KP * e + integ - KD * dT_f) / a_true, 0.0), P_MAX)
        log_.append((t + DT_CTRL, sp, T_hat, tr.T_c(), tr.T_mean(), y, P_cmd, h_now,
                     exp(est.x[3]) / A_CONTACT if mode == "ekf_power" else float("nan")))
    return np.array(log_)


def metrics(L):
    t, sp, That, Tc, Tm, y, P, h, h_hat = L.T
    m = t >= 10.0
    err_c = That - Tc
    seg1 = (t < SP_STEP_T)
    seg2 = ~seg1
    hold1 = (t > SP_STEP_T - 60) & seg1
    hold2 = t > T_END - 60
    return {
        "est_err_c_max_K": round(float(np.abs(err_c[m]).max()), 2),
        "est_err_mean_max_K": round(float(np.abs((That - Tm)[m]).max()), 2),
        "centre_lag_max_K": round(float((Tm - Tc).max()), 2),
        "overshoot_K": round(float(max((Tc - sp)[seg1].max(), (Tc - sp)[seg2].max())), 2),
        "hold_err_c_K": [round(float((Tc - sp)[hold1].mean()), 2), round(float((Tc - sp)[hold2].mean()), 2)],
        "t_reach_sp1_minus2K_s": round(float(t[np.argmax(Tc >= sp[0] - 2)]) if (Tc >= sp[0] - 2).any() else float("nan"), 1),
        "h_hat_end": round(float(h_hat[-1]), 0) if np.isfinite(h_hat[-1]) else None,
    }


def commuting_lags_check():
    """Exact check of the identifiability argument on the estimator-class model.

    Pan heat content -> first-order centre lag tau_r -> T_c -> first-order
    contact lag tau_s -> reading. Swap the two lags: the reading for the same
    power history is identical (series LTI lags commute), but T_c is not. So
    power plus reading cannot say how much lag is contact and how much is pan.
    """
    rng = np.random.default_rng(7)
    P = np.repeat(rng.uniform(0, P_MAX, 60), 50)          # 300 s of random steps at 0.1 s
    a = 0.85 / 600.0
    out = {}
    for tau_r, tau_s in ((4.0, 15.0), (15.0, 4.0)):
        bulk = tc = y = T_AMB
        Tc, Y = [], []
        for p in P:
            bulk += DT_CTRL * a * p
            tc += DT_CTRL * (bulk - tc) / tau_r
            y += DT_CTRL * (tc - y) / tau_s
            Tc.append(tc)
            Y.append(y)
        out[(tau_r, tau_s)] = (np.array(Tc), np.array(Y))
    (c1, y1), (c2, y2) = out.values()
    return {"reading_max_diff_K": float(np.abs(y1 - y2).max()),
            "T_c_max_diff_K": round(float(np.abs(c1 - c2).max()), 1)}


def band_sweep():
    """How well must h_c be known? Filter given h_c x factor, against true h_c."""
    trues = (300.0, 500.0, 1000.0, 2000.0, 3000.0)
    factors = (0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 2.0)
    jobs = [(p, h, 0.82, 0.2, "kf_oracle_h", None, 100 + i, f)
            for i, (p, h, f) in enumerate((p, h, f) for p in PANS for h in trues for f in factors)]
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        logs = pool.starmap(run, jobs)
    grid = {}
    for (p, h, _, _, _, _, _, f), L in zip(jobs, logs):
        m = metrics(L)
        g = grid.setdefault(f"{h:.0f}", {}).setdefault(f"{f:g}", {"err": 0.0, "os": -99.0})
        g["err"] = max(g["err"], m["est_err_c_max_K"])
        g["os"] = max(g["os"], m["overshoot_K"])
    return {"note": "worst over the four pans, eta 0.82, noise 0.2 K; err = max |T_hat - T_c| after 10 s, "
                    "os = overshoot of true T_c", "true_h_by_factor": grid}


def main():
    modes = ("perfect", "raw", "kf_nopower", "kf_oracle_h", "ekf_power")
    rows = []
    cases = [(p, h, eta, n, None) for p in PANS for h in H_SWEEP for eta in ETA_SWEEP for n in NOISE_SWEEP]
    # mid-run contact change during the first hold: pan shifts / oil film dries.
    for p in ("carbon_steel_28", "triply_clad_24"):
        cases.append((p, 1000.0, 0.88, 0.2, (250.0, 300.0)))
        cases.append((p, 300.0, 0.88, 0.2, (250.0, 3000.0)))
    traces = {}
    jobs = [(p, h, eta, n, mode, hs, i) for i, (p, h, eta, n, hs) in enumerate(cases) for mode in modes]
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        logs = iter(pool.starmap(run, jobs))
    for i, (p, h, eta, n, hs) in enumerate(cases):
        for mode in modes:
            L = next(logs)
            met = metrics(L)
            row = {"pan": p, "h_c": h, "eta": eta, "noise_K": n,
                   "h_step": list(hs) if hs else None, "mode": mode, **met}
            gated = n == 0.2
            row["A1"] = met["est_err_c_max_K"] <= 3.0 if gated and mode != "perfect" else None
            row["A2"] = met["overshoot_K"] <= 5.0 if gated else None
            rows.append(row)
            if eta == 0.82 and n == 0.2 and hs is None and h in (300.0, 3000.0):
                traces[f"{p}|{h:.0f}|{mode}"] = L[::10].round(3).tolist()
        print(f"{p:20s} h={h:6.0f} eta={eta:.2f} n={n:.2f} step={hs}  " + "  ".join(
            f"{r['mode']}: e={r['est_err_c_max_K']:5.1f} os={r['overshoot_K']:5.1f}"
            for r in rows[-len(modes):]))

    summary = {}
    for mode in modes:
        g = [r for r in rows if r["mode"] == mode and r["noise_K"] == 0.2]
        summary[mode] = {
            "cases": len(g),
            "A1_pass": sum(bool(r["A1"]) for r in g) if mode != "perfect" else None,
            "A2_pass": sum(bool(r["A2"]) for r in g),
            "worst_est_err_c_K": max(r["est_err_c_max_K"] for r in g),
            "worst_overshoot_K": max(r["overshoot_K"] for r in g),
            "worst_est_err_mean_K": max(r["est_err_mean_max_K"] for r in g),
        }
    out = {"scope": __doc__.strip(),
           "cartridge": {"C_cap_mJ_per_K": round(C_CAP * 1e3, 1), "C_el_mJ_per_K": round(C_EL * 1e3, 3),
                         "G_bond_W_per_K": round(G_BOND, 4), "G_leak_mW_per_K": round(G_LEAK * 1e3, 3),
                         "tau63_s_by_h": {f"{h:.0f}": round(C_CAP / (h * A_CONTACT + G_LEAK) + C_EL / G_BOND, 2)
                                          for h in H_SWEEP}},
           "controller": {"Kp_per_s": KP, "Ki_per_s2": KI, "Kd": KD, "integrate_within_K": I_BAND,
                          "setpoint_ramp_K_per_s": SP_RATE, "P_max_W": P_MAX, "gain_schedule": "P = rate / (eta/C_total), true value"},
           "summary_noise_0.2K": summary,
           "commuting_lags_check": commuting_lags_check(),
           "contact_knowledge_band": band_sweep(),
           "rows": rows}
    here = Path(__file__).parent
    (here / "results.json").write_text(json.dumps(out, indent=1) + "\n")
    (here / "traces.json").write_text(json.dumps(
        {"columns": ["t", "sp", "T_hat", "T_c", "T_mean", "pt100", "P_W", "h_c", "h_hat"], "traces": traces}) + "\n")
    print()
    for mode, s in summary.items():
        print(f"{mode:11s} {s}")
    print("commuting lags:", out["commuting_lags_check"])
    band = out["contact_knowledge_band"]["true_h_by_factor"]
    print("filter given h_c x factor -> worst err / overshoot (K)")
    print("true h   " + "".join(f"{f:>13s}" for f in next(iter(band.values()))))
    for h, row in band.items():
        print(f"{h:>6s}   " + "".join(f"{v['err']:6.1f}/{v['os']:5.1f} " for v in row.values()))


if __name__ == "__main__":
    main()
