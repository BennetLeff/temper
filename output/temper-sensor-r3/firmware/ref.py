"""Python double-precision references for the sensor-r3 firmware port.

- KFRef: the sensor-r2 KFNoPower filter (es.EKF machinery, numeric Jacobian,
  double precision) with the cartridge constants passed explicitly instead of
  read from estimator_study's module globals, so it can shadow a C filter whose
  constants differ from the truth plant's. check_kfref() proves KFRef equals
  es.KFNoPower when the constants agree.
- d1_replay: screen.py's detector-D1 block run open-loop over recorded
  sequences, using screen.slope / screen.probe_says_contact unchanged.
- HotTruth: screen.Truth with the pan (and water) starting hot and the
  cartridge and glass cold: a preheated pan placed on the hob.

Imports ../screen.py and ../../temper-sensor-r2/estimator_study.py read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R3 = HERE.parent
sys.path.insert(0, str(R3.parent / "temper-sensor-r2"))
sys.path.insert(0, str(R3))
import estimator_study as es  # noqa: E402
import screen  # noqa: E402

C1 = screen.CANDS["C1"]


def c1_constants():
    """The C1 cartridge exactly as screen.py models it (truth and reference KF)."""
    return dict(c_cap=C1["C_CAP"], c_el=es.C_EL, g_bond=C1["G_BOND"], g_leak=C1["G_LEAK"],
                area=C1["A_CONTACT"], h_nom=C1["h_nom"])


class KFRef(es.EKF):
    """x = [T_pan, v, T_cap, T_el]; constant-velocity pan, fixed G_c, no power."""

    def __init__(self, y0, noise, k):
        super().__init__([y0, 0.0, y0, y0], [1.0, 0.5**2, 1.0, 1.0], [0.02, 0.05, 1e-4, 1e-4], noise, 3)
        self.k = dict(k)
        self.Gc = k["h_nom"] * k["area"]

    def fmap(self, x, u):
        Tp, v, Tcap, Tel = x
        _, Ts = u
        k, Gc = self.k, self.Gc
        h = es.DT_CTRL / self.SUB
        for _ in range(self.SUB):
            dcap = (Gc * (Tp - Tcap) - k["g_leak"] * (Tcap - Ts) - k["g_bond"] * (Tcap - Tel)) / k["c_cap"]
            dele = k["g_bond"] * (Tcap - Tel) / k["c_el"]
            Tp += h * v
            Tcap += h * dcap
            Tel += h * dele
        return [Tp, v, Tcap, Tel]

    def estimate(self):
        return float(self.x[0])


def check_kfref(n=600, seed=3):
    """max |KFRef - es.KFNoPower| on a noisy sequence with screen's C1 constants."""
    screen.apply(C1)
    rng = np.random.default_rng(seed)
    a = es.KFNoPower(es.T_AMB, screen.NOISE, h_c=C1["h_nom"])
    b = KFRef(es.T_AMB, screen.NOISE, c1_constants())
    worst = 0.0
    for i in range(n):
        y = 25.0 + 0.3 * i + 0.2 * rng.standard_normal()
        ntc = 28.0 + 0.01 * i
        worst = max(worst, abs(a.step(y, (0.0, ntc)) - b.step(y, (0.0, ntc))))
    return worst


class HotTruth(screen.Truth):
    def __init__(self, *a, T_hot=None, **k):
        super().__init__(*a, **k)
        if T_hot is not None:
            self.T[:] = T_hot
            if self.Cw:
                self.Tw = min(T_hot, 100.0)


def d1_replay(y, th, p, ntc, a, tau_off, probe_off=screen.PROBE_OFF, probe_on=screen.PROBE_ON):
    """screen.run()'s D1 block over recorded sequences (index k <-> t = k*dt).

    p[k] is the power applied during the period that ended at sample k (the
    reference's hist_P). Returns suspect/lost sample indices, probe count and
    the probe log (index, d, d_exp, ok)."""
    dt = es.DT_CTRL
    hist_t, hist_hat, hist_y, hist_P = [], [], [], []
    state, t_state, trig_since, holdoff_until = "normal", 0.0, None, 0.0
    suspect, lost, probes, plog = None, None, 0, []
    off, on = probe_off, probe_on
    for k in range(len(y)):
        t = k * dt
        hist_t.append(t)
        hist_hat.append(th[k])
        hist_y.append(y[k])
        hist_P.append(p[k])
        if state == "normal" and t >= holdoff_until:
            if len(hist_t) > 20:
                s = screen.slope(hist_t[-20:], hist_hat[-20:])
                if s < screen.TRIG_RATE and np.mean(hist_P[-20:]) >= screen.TRIG_PMIN * es.P_MAX:
                    trig_since = t if trig_since is None else trig_since
                    if t - trig_since >= screen.TRIG_HOLD_S - 1e-9:
                        state, t_state, probes = "probe", t, probes + 1
                        suspect = suspect if suspect is not None else k
                else:
                    trig_since = None
        if state in ("probe", "retry"):
            if t - t_state >= 2 * off + on - 1e-9:
                ok, d, d_exp = screen.probe_says_contact(hist_t, hist_y, hist_P, t_state - 1e-9, a,
                                                         ntc[k], tau_off)
                plog.append((k, float(d), float(d_exp), bool(ok)))
                if not ok:
                    state, t_state = "lost", t
                    lost = lost if lost is not None else k
                else:
                    state, trig_since, holdoff_until = "normal", None, t + screen.HOLDOFF_S - 1e-9
        if state == "lost" and t - t_state >= screen.RETRY_S - 1e-9:
            state, t_state = "retry", t
    return {"suspect_k": suspect, "lost_k": lost, "probes": probes, "probe_log": plog}
