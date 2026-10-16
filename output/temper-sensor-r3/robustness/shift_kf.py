"""Python reference of the C1 contact-shift window (firmware candidate V3).

The base filter is the firmware's fixed-contact KF (x = [T_pan, v, T_cap, T_el],
pan_temp_estimator.c), written as its exact affine map x' = F(G) x + g(G) T_sink
with F, g composed from 5 Euler substeps in double, as pte_init does.

Why a window can identify a contact CHANGE when sensor-r2 showed G_c cannot be
identified: over a run, a slow contact and a slow pan centre produce the same
reading (the two lags commute), so coil power cannot tell them apart. A contact
change is different: it is a step in the cartridge, which settles in 0.2-3.5 s,
while the pan cannot change its rate unless the power changes. If the pan's
temperature and rate are pinned to their values just before the step, the only
way the model can explain the reading's fall is a lower G. The window measures G
relative to the model before the step; the absolute h_c stays unknown.

  1. Trigger (outside a window, after start_holdoff_s and holdoff_s): the
     reading's slope over the last n_recent samples is below its slope over the
     n_before samples before that by more than dv_trig (down) or above it by
     more than dv_trig (up, only while G < G_nom), and the mean power over the
     last p_recent_s has not fallen (down) / risen (up) by more than dp_frac of
     P_max against the p_recent_s before. A power change explains a change of
     rate; a contact change does not.
  2. The filter is rewound trig_lag_s and replayed as a 5-state EKF with ln G as
     a state. The pan is pinned: T_pan from the snapshot (sd p0_t_win), v from
     the reading slope over v_ref_s before the snapshot (sd p0_v_win), and their
     process noise near zero. ln G starts at the old value with sd p0_lng and is
     clamped to [ln G_floor, ln G_old] (down) or [ln G_old, ln G_nom] (up): the
     assumed contact can only go down, or come back up to nominal.
  3. The window closes:
       - escalate (down): ln G reaches the floor. The fall is faster than any
         partial contact gives (contact loss, or real pan cooling such as food):
         the window is replayed with the old G and the caller requests a D1 probe;
       - accept: at least win_min_s after the trigger, ln G has moved less than
         settle_dlng over settle_s, the change is >= min_drop and the posterior
         sd of ln G <= max_sd_lng. The contact taken is exp(ln G - accept_bias_sd
         sd): the lower side, because a contact assumed too good over-heats;
       - revert: otherwise, at win_max_s, or when the caller's gate drops
         (D1 left NORMAL, sensor fault).
The caller resets G to nominal when D1 restores contact after a loss.
"""
from __future__ import annotations

from math import exp, log

import numpy as np


def affine_map(k, gc, dt=0.1, sub=5):
    """F (4x4) and g (4,) of the 5-substep Euler map for contact conductance gc (W/K)."""
    h = dt / sub

    def step(x, u):
        tp, v, tcap, tel = x
        dcap = (gc * (tp - tcap) - k["g_leak"] * (tcap - u) - k["g_bond"] * (tcap - tel)) / k["c_cap"]
        dele = k["g_bond"] * (tcap - tel) / k["c_el"]
        return np.array([tp + h * v, v, tcap + h * dcap, tel + h * dele])

    F = np.zeros((4, 4))
    for j in range(4):
        e = np.zeros(4)
        e[j] = 1.0
        for _ in range(sub):
            e = step(e, 0.0)
        F[:, j] = e
    z = np.zeros(4)
    for _ in range(sub):
        z = step(z, 1.0)
    return F, z


DEFAULTS = dict(
    q=(0.02, 0.05, 1e-4, 1e-4), p0=(1.0, 0.25, 1.0, 1.0), sigma=0.2, dt=0.1, p_max=1800.0,
    cs_enable=True, cs_up=True,
    # trigger
    n_recent=15, n_before=30, dv_trig=0.6, p_recent_s=8.0, dp_frac=0.10,
    start_holdoff_s=30.0, holdoff_s=20.0,
    # window
    trig_lag_s=2.5, v_ref_s=5.0, p0_t_win=0.1, p0_v_win=0.03, q_t_win=1e-4, q_v_win=1e-4,
    p0_lng=1.0, q_lng=0.002, h_floor=150.0, h_deg=100.0, pin_power=False, tau_c=3.0,
    win_min_s=4.0, win_min_hold_s=8.0, win_max_s=12.0, settle_s=2.0, settle_dlng=0.04, min_drop=0.25, max_sd_lng=0.2,
    accept_bias_sd=1.0, v_mode="slope",
)


class ShiftKF:
    """Fixed-contact KF plus the contact-shift window. step() returns (T_hat, event)."""

    def __init__(self, y0, k, **opt):
        self.k = dict(k)
        self.o = o = {**DEFAULTS, **opt}
        self.g_nom = k["h_nom"] * k["area"]
        self._set_g(self.g_nom)
        self.x = np.array([y0, 0.0, y0, y0], float)
        self.P = np.diag(o["p0"]).astype(float)
        self.Q = np.diag(o["q"]) * o["dt"]
        self.R = o["sigma"] ** 2
        self.nlag = int(round(o["trig_lag_s"] / o["dt"]))
        self.npw = int(round(o["p_recent_s"] / o["dt"]))
        self.nref = int(round(o["v_ref_s"] / o["dt"]))
        self.nkeep = max(o["n_recent"] + o["n_before"], 2 * self.npw, self.nlag + 1 + self.nref)
        self.snap = []          # (x, P) before each of the last nlag + 1 steps
        self.yhist, self.thist, self.phist, self.lhist = [], [], [], []
        self.pl = 0.0           # coil power through the pan-centre lag (W)
        self.a = 0.0            # plant gain from the caller (K/J)
        self.win = None
        self.holdoff = 0
        self.t = 0
        self.events = []

    def _set_g(self, g):
        self.g = g
        self.F, self.gs = affine_map(self.k, g, self.o["dt"])

    @property
    def h_model(self):
        return self.g / self.k["area"]

    def _kf(self, x, P, y, ts):
        x = self.F @ x + self.gs * ts
        P = self.F @ P @ self.F.T + self.Q
        S = P[3, 3] + self.R
        K = P[:, 3] / S
        x = x + K * (y - x[3])
        P = P - np.outer(K, P[3, :])
        return x, 0.5 * (P + P.T)

    def _ekf(self, z, Pz, y, ts, dpl=0.0):
        o, w = self.o, self.win
        g = exp(z[4])
        F, gs = affine_map(self.k, g, o["dt"])
        eps = 1e-4
        F2, gs2 = affine_map(self.k, g * exp(eps), o["dt"])
        x = z[:4]
        fx = F @ x + gs * ts
        J = np.zeros((5, 5))
        J[:4, :4] = F
        J[:4, 4] = ((F2 @ x + gs2 * ts) - fx) / eps
        J[4, 4] = 1.0
        q = list(o["q"])
        q[0], q[1] = o["q_t_win"], o["q_v_win"]
        Qz = np.diag(q + [o["q_lng"]]) * o["dt"]
        zp = np.append(fx, z[4])
        if o["pin_power"] and not w["steady"]:
            zp[1] += self.a * dpl          # the pinned pan follows the lagged coil power
        Pp = J @ Pz @ J.T + Qz
        S = Pp[3, 3] + self.R
        K = Pp[:, 3] / S
        zn = zp + K * (y - zp[3])
        Pn = Pp - np.outer(K, Pp[3, :])
        Pn = 0.5 * (Pn + Pn.T)
        zn[4] = min(max(zn[4], w["lo"]), w["hi"])
        return zn, Pn

    # ---- trigger statistic
    def stat(self):
        """(reading slope change K/s, lowest and highest 1 s power block of the last p_recent_s
        minus the mean power of the p_recent_s before, W) or None until the history is full."""
        o = self.o
        n1, n2 = o["n_recent"], o["n_before"]
        if len(self.yhist) < self.nkeep:
            return None
        y = np.asarray(self.yhist[-(n1 + n2):])
        tt = np.arange(n1 + n2) * o["dt"]
        s_rec = np.polyfit(tt[n2:], y[n2:], 1)[0]
        s_bef = np.polyfit(tt[:n2], y[:n2], 1)[0]
        p = np.asarray(self.phist[-2 * self.npw:])
        base = p[:self.npw].mean()
        blocks = p[self.npw:].reshape(-1, 10).mean(axis=1)
        return s_rec - s_bef, blocks.min() - base, blocks.max() - base

    def triggered(self):
        """+1 (down window), -1 (up window) or 0."""
        st = self.stat()
        if st is None:
            return 0
        dv, dp_lo, dp_hi = st
        lim = self.o["dp_frac"] * self.o["p_max"]
        if dv < -self.o["dv_trig"] and dp_lo >= -lim:
            return 1
        if self.o["cs_up"] and dv > self.o["dv_trig"] and dp_hi <= lim and self.g < 0.95 * self.g_nom:
            return -1
        return 0

    # ---- one period
    def step(self, y, ts, p_applied, allow=True, steady=False, a=0.0):
        """allow: the caller's gate (D1 NORMAL, no fault); steady: the loop has held its
        setpoint (no ramp) for a while, so a pinned pan stays valid for win_min_hold_s.
        Returns (T_hat, event or None)."""
        o = self.o
        self.t += 1
        self.snap.append((self.x.copy(), self.P.copy()))
        if len(self.snap) > self.nlag + 1:
            self.snap.pop(0)
        self.yhist.append(y)
        self.thist.append(ts)
        self.phist.append(p_applied)
        self.pl += o["dt"] / o["tau_c"] * (p_applied - self.pl)
        self.lhist.append(self.pl)
        self.a = a
        if len(self.yhist) > self.nkeep:
            self.yhist.pop(0)
            self.thist.pop(0)
            self.phist.pop(0)
            self.lhist.pop(0)
        event = None
        if self.win is None:
            self.x, self.P = self._kf(self.x, self.P, y, ts)
        else:
            event = self._win_step(y, ts, self.lhist[-1] - self.lhist[-2], allow)
        if (self.win is None and event is None and o["cs_enable"] and allow and self.t > self.holdoff
                and self.t * o["dt"] >= o["start_holdoff_s"]):
            d = self.triggered()
            if d:
                self._open(d, steady)
                event = "open_down" if d > 0 else "open_up"
        return float(self.x[0]), event

    def _open(self, direction, steady=False):
        o = self.o
        x0, P0 = self.snap[0]
        n = len(self.snap)                       # samples since the snapshot (incl. this one)
        dl = np.diff(np.asarray(self.lhist[-(n + 1):]))
        replay = list(zip(self.yhist[-n:], self.thist[-n:], dl))
        z = np.append(x0, log(self.g))
        yref = np.asarray(self.yhist[-(n + self.nref):-n])
        tref = np.arange(len(yref)) * o["dt"]
        if o.get("v_steady_zero") and steady:
            z[1] = 0.0
        elif o["v_mode"] == "kf":          # alternatives kept for vpin_variants.py
            z[1] = x0[1]
        elif o.get("v_mode") == "quad":
            c2 = np.polyfit(tref, yref, 2)
            z[1] = 2 * c2[0] * tref[-1] + c2[1]
        elif o.get("v_mode") == "short":
            m = int(round(o.get("v_short_s", 2.0) / o["dt"]))
            z[1] = np.polyfit(tref[-m:], yref[-m:], 1)[0]
        else:
            z[1] = np.polyfit(tref, yref, 1)[0]
        if o["pin_power"] and not steady:
            # the reference slope is the mean rate over the reference window; move it to the
            # snapshot with the lagged-power change since then
            lref = np.asarray(self.lhist[-(n + self.nref):-n])
            z[1] += self.a * (self.lhist[-n - 1] - lref.mean())
        Pz = np.zeros((5, 5))
        Pz[2:4, 2:4] = P0[2:4, 2:4]
        Pz[0, 0] = o["p0_t_win"] ** 2
        Pz[1, 1] = o["p0_v_win"] ** 2
        Pz[4, 4] = o["p0_lng"] ** 2
        lg = log(self.g)
        if direction > 0:
            lo, hi = log(o["h_floor"] * self.k["area"]), lg
        else:
            lo, hi = lg, log(self.g_nom)
        p_ref = float(np.mean(self.phist[-(n + self.nref):-n]))
        self.win = dict(dir=direction, z=z, P=Pz, lo=lo, hi=hi, g_before=self.g, x0=x0.copy(), P0=P0.copy(), p_ref=p_ref, steady=steady,
                        samples=list(replay), n=0, n_replay=n, lng_log=[])
        for y, ts, d in replay:
            self._advance(y, ts, d)
        self.events.append((self.t, "open", self.h_model))

    def _advance(self, y, ts, dpl):
        w = self.win
        w["z"], w["P"] = self._ekf(w["z"], w["P"], y, ts, dpl)
        w["n"] += 1
        w["lng_log"].append(w["z"][4])
        self.x = w["z"][:4].copy()
        self.P = w["P"][:4, :4].copy()

    def _close(self, kind):
        w, o = self.win, self.o
        if kind == "accept":
            # safety bias: take the lower side of the ln G posterior (a contact assumed too
            # good reads low and over-heats the pan); never past the window's own clamp
            lng = w["z"][4] - o["accept_bias_sd"] * w["P"][4, 4] ** 0.5
            self._set_g(exp(max(lng, w["lo"]) if w["dir"] > 0 else max(lng, log(w["g_before"]))))
            self.x = w["z"][:4].copy()
            self.P = w["P"][:4, :4].copy()
        else:                                   # revert / escalate: replay with the old contact
            self._set_g(w["g_before"])
            x, P = w["x0"], w["P0"]
            for y, ts, _ in w["samples"]:
                x, P = self._kf(x, P, y, ts)
            self.x, self.P = x, P
        self.events.append((self.t, kind, self.h_model))
        self.win = None
        self.holdoff = self.t + int(round(o["holdoff_s"] / o["dt"]))
        return kind

    def _win_step(self, y, ts, dpl, allow):
        o, w = self.o, self.win
        w["samples"].append((y, ts, dpl))
        self._advance(y, ts, dpl)
        if not allow:
            return self._close("revert")
        lng = w["z"][4]
        if w["dir"] > 0 and lng <= w["lo"] + 1e-6:
            return self._close("escalate")
        dur = (w["n"] - w["n_replay"]) * o["dt"]
        ns = int(round(o["settle_s"] / o["dt"]))
        moved = lng < w["hi"] - 1e-6 if w["dir"] > 0 else lng > w["lo"] + 1e-6
        settled = moved and len(w["lng_log"]) > ns and abs(lng - w["lng_log"][-1 - ns]) < o["settle_dlng"]
        big = abs(lng - log(w["g_before"])) >= -log(1.0 - o["min_drop"]) or (w["dir"] < 0 and lng >= w["hi"] - 1e-6)
        at_nominal = w["dir"] < 0 and lng >= w["hi"] - 1e-6     # back at the nominal clamp
        good = settled and big and (w["P"][4, 4] ** 0.5 <= o["max_sd_lng"] or at_nominal)
        # a pinned constant-rate pan is valid for longer in a hold than in a ramp
        win_min = o["win_min_hold_s"] if w["steady"] else o["win_min_s"]
        if dur >= win_min and good:
            return self._close("accept")
        if dur >= o["win_max_s"]:
            return self._close("revert")
        return None

    def set_contact(self, h):
        """Contact degraded below the floor (escalated window + D1 probe with no power
        response): assume h (never above the current model)."""
        if self.win is not None:
            self._close("revert")
        self._set_g(min(self.g, h * self.k["area"]))

    def reset_contact(self):
        """D1 restored contact after a loss: a new seating, back to the nominal model."""
        if self.win is not None:
            self._close("revert")
        self._set_g(self.g_nom)
