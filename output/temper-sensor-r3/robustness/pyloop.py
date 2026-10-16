"""Python closed loop for the h_c-robustness screen (sensor-r3 robustness study).

A copy of screen.py run() (C1, kf_fixed, detector D1 in screen mode, frozen
rate PID with the true a), with:
  - a time-varying true contact h_c(t) (steps, ramps) and the contaminant
    truth plants of contaminants.py (oil film, water film, sticky post);
  - the firmware's cartridge constants in the filter (FW_K, 1.8 % C_cap
    mismatch as in the co-sim);
  - the h_c-step candidates compared in hc_candidates.py:
      V0  baseline (fixed contact model)
      V1  residual detector -> cap power at the pre-event level for cap_s
      V2  residual detector -> request a D1 probe at once
      V3  residual detector -> contact-shift window (shift_kf.ShiftKF):
          bounded ln G adaptation, only downward, D1 probe on escalation
Imports screen.py / estimator_study.py read-only.
"""
from __future__ import annotations

import sys
from math import exp
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R3 = HERE.parent
sys.path.insert(0, str(R3.parent / "temper-sensor-r2"))
sys.path.insert(0, str(R3))
sys.path.insert(0, str(HERE))
import estimator_study as es  # noqa: E402
import screen  # noqa: E402
from shift_kf import ShiftKF  # noqa: E402

FW_K = dict(c_cap=0.0404, c_el=0.008175, g_bond=0.0612, g_leak=0.0008, area=45.4e-6, h_nom=1300.0)
C1 = screen.CANDS["C1"]
LPG_N, LPG_SLOPE, LPG_BAND, LPG_MARGIN, LPG_RATE = 100, 0.15, (95.0, 118.0), 5.0, 0.2
STEADY_S, STEADY_BAND_K = 10.0, 3.0   # setpoint reached and held within 3 K this long = steady


def h_profile(spec):
    """spec: None (constant), ("step", t, h1), ("ramp", t0, t1, h1), or a list of those (applied in order)."""
    if spec is None:
        return lambda t, h0: h0
    specs = spec if isinstance(spec[0], (list, tuple)) else [spec]

    def f(t, h0):
        h = h0
        for s in specs:
            if s[0] == "step" and t >= s[1]:
                h = s[2]
            elif s[0] == "ramp" and t >= s[1]:
                fr = min(1.0, (t - s[1]) / (s[2] - s[1]))
                h = h * (s[3] / h) ** fr       # log-linear
        return h
    return f


def run(pan_name, h0, eta, seed, variant="V0", h_spec=None, food_at=None, loss_at=None,
        truth_factory=None, cand_opt=None, T_END=None):
    """One closed-loop run. Returns (log array, info dict).

    log columns: t, sp, T_hat, T_c, T_mean, y, P, h_true, h_model.
    """
    screen.apply(C1)
    opt = dict(cand_opt or {})
    pan = es.PANS[pan_name]
    tr = truth_factory(pan, h0, eta, seed, food_at) if truth_factory else screen.Truth(pan, h0, eta, seed, food_at=food_at)
    rng = np.random.default_rng(seed + 1)
    sp1, sp2 = pan["sp"]
    a_true = eta / (tr.C.sum() + tr.Cw)
    use_cs = variant in ("V3", "V3f", "V3L", "V3Lc")
    use_lpg = variant in ("V3L", "V3Lc")
    lpg_budget = variant == "V3L"     # V3Lc: the cap without the energy budget (rejected)
    lpg_on = 0.0
    lpg_e = 0.0                       # PID energy delivered during the current plateau (J)
    freeze = variant == "V3f"
    escalated = False
    est = ShiftKF(es.T_AMB, FW_K, cs_enable=use_cs, **opt.get("kf", {}))
    # V1/V2 use the same trigger, from the same filter, with no window
    det = ShiftKF(es.T_AMB, FW_K, cs_enable=False) if variant in ("V1", "V2") else None
    hf = h_profile(h_spec)
    t_end = T_END or es.T_END
    integ, P_cmd, sp_eff, T_prev, dT_f = 0.0, 0.0, es.T_AMB, es.T_AMB, 0.0
    n_sub = round(es.DT_CTRL / es.DT_SIM)
    hist_t, hist_hat, hist_y, hist_P = [], [], [], []
    state, t_state, trig_since, detected_at, probes = "normal", 0.0, None, None, 0
    holdoff_until, suspect_at = 0.0, None
    cap_until, cap_w, det_hold = -1.0, None, 30.0
    lost_events = 0
    cs_events = []
    stat_log = []
    settled_k = 0                 # last step not steady at the setpoint (integer, as the C loop)
    probe_req = False
    log_ = []
    for k in range(int(t_end / es.DT_CTRL)):
        t = k * es.DT_CTRL
        h_now = hf(t, h0)
        if loss_at is not None and t >= loss_at:
            h_now = 2.0
        if hasattr(tr, "set_time"):
            tr.set_time(t)
        for _ in range(n_sub):
            tr.step(P_cmd, h_now)
        y = tr.reading() if hasattr(tr, "reading") else tr.Tel
        y = y + screen.NOISE * rng.standard_normal()
        ntc = tr.sink() + es.NTC_BIAS
        steady = k - settled_k >= round(STEADY_S / es.DT_CTRL)
        T_hat, ev = est.step(y, ntc, P_cmd, allow=(state == "normal"), steady=steady, a=a_true)
        if ev:
            cs_events.append((round(t, 1), ev, round(est.h_model)))
        if ev == "escalate":
            probe_req = True
            escalated = True
        if opt.get("log_stat"):
            st = est.stat()
            if st is not None:
                stat_log.append((t, st[0], st[1], st[2], P_cmd))
        if det is not None:
            det.step(y, ntc, P_cmd)
            if state == "normal" and t >= det_hold and det.triggered() > 0:
                det_hold = t + 20.0
                cs_events.append((round(t, 1), "trig", None))
                if variant == "V1":
                    cap_w = float(np.mean(det.phist[-2 * det.nlag:-det.nlag]))
                    cap_until = t + opt.get("cap_s", 30.0)
                else:
                    probe_req = True
        sp = sp1 if t + es.DT_CTRL < es.SP_STEP_T else sp2
        sp_eff = min(sp, sp_eff + es.SP_RATE * es.DT_CTRL) if sp > sp_eff else sp
        dT_f += (es.DT_CTRL / 2.0) * ((T_hat - T_prev) / es.DT_CTRL - dT_f)
        T_prev = T_hat
        e = sp_eff - T_hat
        if abs(e) < es.I_BAND:
            integ = min(max(integ + es.KI * e * es.DT_CTRL, 0.0), es.P_MAX * a_true)
        P_pid = min(max((es.KP * e + integ - es.KD * dT_f) / a_true, 0.0), es.P_MAX)
        if use_lpg and len(hist_hat) >= LPG_N:
            # latent-plateau guard: the estimate sits in the boiling band, flat, well below
            # the setpoint while the loop asks for heat. A wet pocket under the pan centre
            # pins the centre near 100 C while the annulus heats: limit the heating rate.
            # The budget: while T_hat is in the band, the PID may deliver the energy that
            # would take the whole pan from T_hat to the setpoint (a * E <= sp - T_hat; losses
            # make the true rise smaller). That boils off a wet pocket by heating the pan
            # around it and keeps the pan mean at or below the setpoint; then the cap applies
            # while the plateau lasts. E counts from entering the band from below, and resets on
            # leaving it. Entering from above (the reading fell into the band: the pan was hotter
            # than T_hat) has no budget.
            in_band = LPG_BAND[0] <= T_hat <= LPG_BAND[1]
            if in_band and hist_hat[-1] > LPG_BAND[1]:
                lpg_e = float("inf")
            flat = abs(screen.slope(hist_t[-LPG_N:], hist_hat[-LPG_N:])) < LPG_SLOPE
            if in_band and flat and sp - T_hat > LPG_MARGIN:
                if not lpg_budget or a_true * lpg_e >= sp - T_hat:
                    P_pid = min(P_pid, LPG_RATE / a_true)
                    lpg_on += es.DT_CTRL
            lpg_e = lpg_e + P_pid * es.DT_CTRL if in_band else 0.0
        if t < cap_until:
            P_pid = min(P_pid, cap_w)
        if freeze and est.win is not None and T_hat < sp_eff:
            # hold the pre-event power while the window measures the contact
            P_pid = est.win["p_ref"]
        hist_t.append(t)
        hist_hat.append(T_hat)
        hist_y.append(y)
        hist_P.append(P_cmd)
        P_next = P_pid
        if not (sp_eff >= sp and abs(T_hat - sp) < STEADY_BAND_K):
            settled_k = k
        # --- D1 (screen.py block) + external probe request
        if state == "normal" and t >= holdoff_until:
            start = False
            if probe_req:
                start = True
            elif len(hist_t) > 20:
                s = screen.slope(hist_t[-20:], hist_hat[-20:])
                if s < screen.TRIG_RATE and np.mean(hist_P[-20:]) >= screen.TRIG_PMIN * es.P_MAX:
                    trig_since = t if trig_since is None else trig_since
                    if t - trig_since >= screen.TRIG_HOLD_S:
                        start = True
                else:
                    trig_since = None
            if start:
                probe_req = False
                state, t_state, probes = "probe", t, probes + 1
                suspect_at = suspect_at if suspect_at is not None else t
        elif state != "normal":
            probe_req = False
        if state in ("probe", "retry"):
            dt = t - t_state
            if dt < 2 * screen.PROBE_OFF + screen.PROBE_ON:
                P_next = screen.PROBE_P * es.P_MAX if screen.PROBE_OFF <= dt < screen.PROBE_OFF + screen.PROBE_ON else 0.0
            else:
                ok, d, d_exp = screen.probe_says_contact(hist_t, hist_y, hist_P, t_state, a_true, ntc,
                                                         FW_K["c_cap"] / FW_K["g_leak"])
                cs_events.append((round(t, 1), "probe", round(d / d_exp, 3), bool(ok)))
                if not ok:
                    if state == "probe":
                        lost_events += 1
                    state, t_state = "lost", t
                    detected_at = detected_at if detected_at is not None else t
                else:
                    if state == "retry":
                        est.reset_contact()
                    state, trig_since, holdoff_until = "normal", None, t + screen.HOLDOFF_S
                    integ = 0.0
        if state == "lost":
            P_next = 0.0
            if t - t_state >= screen.RETRY_S:
                state, t_state = "retry", t
        if state in ("probe", "retry", "lost"):
            integ = 0.0
        if state == "normal":
            escalated = escalated and est.win is not None
        P_cmd = P_next
        log_.append((t + es.DT_CTRL, sp, T_hat, tr.T_c(), tr.T_mean(), y, P_cmd, h_now, est.h_model))
    return np.array(log_), {"probes": probes, "suspect_at": suspect_at, "detected_at": detected_at,
                            "lost_events": lost_events, "cs_events": cs_events[:12], "lpg_s": round(lpg_on, 1),
                            **({"stat": np.array(stat_log)} if opt.get("log_stat") else {})}


def metrics(L, loss_at=None, ev_at=None, settle_s=20.0):
    """screen.metrics, plus for contact events at times ev_at: B1 evaluated outside
    [ev, ev + settle_s) of each event, and the worst error inside those windows."""
    m = screen.metrics(L, loss_at)
    if ev_at:
        t, That, Tc = L[:, 0], L[:, 2], L[:, 3]
        inside = np.zeros(len(t), bool)
        for ev in ev_at:
            inside |= (t >= ev) & (t < ev + settle_s)
        err = np.abs(That - Tc)
        m["est_err_c_max_K"] = round(float(err[(t >= 10) & ~inside].max()), 2)
        m["est_err_in_transient_K"] = round(float(err[inside].max()), 2)
    m["h_model_end"] = round(float(L[-1, 8]), 0)
    m["h_model_min"] = round(float(L[:, 8].min()), 0)
    return m
