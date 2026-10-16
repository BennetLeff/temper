"""Problem B: contaminated contact between the C1 disc and the pan (oil, water, crud).

Extends contact_model.py (Yovanovich light-load gap conductance, same face, pans,
tilts) with a fluid in the gap, a solid film in series, a sticky post that no
longer follows the pan, and a boiling water pocket around the post. Writes the
contact values to contaminants.json and provides truth plants for the closed loop
(pyloop.py, hc_cosim.py).

Property values (each an ASSUMPTION with a source; the bench replaces them):
  air k at 150 C          0.0349 W/m K   contact_model.K_AIR_150C (as r3)
  edible oil k            0.15-0.17 W/m K (0.17 at 25 C falling ~0.0002 /K; used
                          0.155 at 150 C). Turgut, Tavman & Tavman, Int. J. Food Prop.
                          12 (2009) 741 (hot wire, olive / sunflower / corn, 25-80 C);
                          Coupland & McClements, JAOCS 74 (1997) 1559.
  oil viscosity           canola 0.060 Pa s at 25 C, 0.0055 at 150 C, 0.004 at 180 C.
                          Fasina & Colley, Int. J. Food Prop. 11 (2008) 738 (35-180 C;
                          the 25 C value extrapolated).
  polymerised oil film    k 0.15-0.25 W/m K: crosslinked amorphous polymer range
  ("varnish")             (Mark (ed.), Physical Properties of Polymers Handbook, 2007,
                          ch. 10). Thickness 0-100 um is a sweep, not a measurement.
  water, 100 C            k_l 0.680, k_v 0.0248 W/m K, cp 4217 J/kg K, h_fg 2.257 MJ/kg:
                          Incropera & DeWitt, Fundamentals of Heat and Mass Transfer
                          6th ed., Table A.6.
  boiling curve, water,   free convection below dT_e 5 K (h 1000 W/m2 K); nucleate
  1 atm                   q'' = q''_max (dT_e/30)^3 to q''_max = 1.26 MW/m2 at 30 K;
                          transition log-linear to the Leidenfrost q''_min = 1.8e4 W/m2
                          at 120 K; film boiling q''_min dT_e/120 above. Incropera 6th ed.
                          section 10.4, Fig. 10.4 and Example 10.1. A confined pocket may
                          dry out earlier: boil_scale 0.3 is run as a sensitivity.
  pocket geometry         from cad/cartridge_r3.py: glass bore r 9.0, neck r 4.0, collar
                          r 8.0 (top 0.2 mm under the glass top), relief r 5.5 down to
                          the wiper 2.8 mm below: pan-bottom area over the pocket
                          pi (9^2 - 4^2) = 204 mm2, liquid volume above the wiper and in
                          the collar annulus 0.05-0.35 ml. Wetted disc edge pi 8 x 0.32
                          = 8 mm2.
  wiper and spring        cad/tilt-follow.json: friction 0.056 N (mu 0.3) / 0.185 N
                          (dry mu 1.0); spring 1.21-1.79 N.
  pan bow when hot        0-0.3 mm rise of the base centre at 230 C, linear in the pan
                          mean temperature: an ASSUMPTION (no measured value found);
                          the bench measures it with a dial gauge on a hot pan.

Run: python contaminants.py  -> contaminants.json
"""
from __future__ import annotations

import json
import sys
from math import cos, exp, log, pi
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "temper-sensor-r2"))
sys.path.insert(0, str(HERE.parent))
import contact_model as cm  # noqa: E402
import estimator_study as es  # noqa: E402
import screen  # noqa: E402

FACE = cm.FACES["sensor-r3 Si3N4 disc (lapped)"]
K_AIR = cm.K_AIR_150C
K_OIL = 0.155
K_OIL_RANGE = (0.15, 0.17)
MU_OIL = {25: 0.060, 150: 0.0055, 180: 0.0040}
K_VARNISH = (0.15, 0.25)
K_WATER, K_VAPOUR, CP_W, H_FG = 0.680, 0.0248, 4217.0, 2.257e6
Q_MAX, Q_MIN, DT_NB, DT_LEID, H_NC = 1.26e6, 1.8e4, 30.0, 120.0, 1000.0
A_POCKET = pi * (9.0e-3**2 - 4.0e-3**2)       # pan bottom over the bore pocket, m2
R_POCKET = (4.0e-3, 9.0e-3)
A_EDGE = pi * 8.0e-3 * 0.32e-3                 # wetted disc edge, m2
H_SUB = 1360.0                                  # conduction across a ~0.5 mm water layer, k/delta
WIPER_F = (0.056, 0.185)
SPRING_F = (1.21, 1.79)
TILT_FOLLOW, TILT_PAN = 0.002, 0.005


def h_face(pan, tilt, force, k_fluid, m_gas, extra=0.0, n_r=24, n_t=36):
    """Area-mean conductance of a fluid-filled gap over the C1 face (contact_model's
    Yovanovich mean-plane separation Y at force, plus the tilt wedge, plus an extra
    uniform separation), plus linearised radiation. W/m2 K."""
    p = cm.PANS[pan]
    sigma = 1.25e-6 * (FACE["Ra"] ** 2 + p["Ra"] ** 2) ** 0.5
    area = pi * FACE["R_face"] ** 2
    p_over_h = max(force, 1e-4) / area / (p["H"] * 1e9)
    Y = sigma * 1.184 * (-log(3.132 * p_over_h)) ** 0.547
    h_rad = 4 * cm.EPS_RAD * 5.67e-8 * cm.T_RAD ** 3
    tot = 0.0
    for i in range(n_r):
        r = (i + 0.5) / n_r * FACE["R_face"]
        for j in range(n_t):
            th = 2 * pi * (j + 0.5) / n_t
            g = tilt * (FACE["R_face"] + r * cos(th))
            tot += k_fluid / (Y + m_gas + g + extra) * r
    return tot / (n_r * n_t) * 2.0 / FACE["R_face"] + h_rad


def h_dry(pan, tilt=TILT_FOLLOW, force=SPRING_F[0]):
    return h_face(pan, tilt, force, K_AIR, cm.M_GAS)


def squeeze_time(mu, h0, h1, force=SPRING_F[0], R=None):
    """Reynolds squeeze-film time for the sprung disc to thin a film from h0 to h1 (s)."""
    R = R or FACE["R_face"]
    return 3 * pi * mu * R**4 / (4 * force) * (1.0 / h1**2 - 1.0 / h0**2)


def q_boil(dT, scale=1.0):
    """Heat flux (W/m2) from a wall dT above saturated water (boiling curve, see header)."""
    if dT <= DT_NB / 6.0:
        return H_NC * dT
    if dT <= DT_NB:
        return max(H_NC * dT, scale * Q_MAX * (dT / DT_NB) ** 3)
    if dT <= DT_LEID:
        f = (dT - DT_NB) / (DT_LEID - DT_NB)
        return scale * exp(log(Q_MAX) + f * (log(Q_MIN) - log(Q_MAX)))
    return scale * Q_MIN * dT / DT_LEID


# ---- contact tables -----------------------------------------------------------------
def oil_table():
    rows = {}
    for pan in cm.PANS:
        dry = h_dry(pan)
        r = {"dry": round(dry)}
        for kk in K_OIL_RANGE:
            r[f"oil_wet_k{kk}"] = round(h_face(pan, TILT_FOLLOW, SPRING_F[0], kk, 0.0))
        for ex in (2e-6, 5e-6, 20e-6, 100e-6):
            r[f"oil_film_{ex * 1e6:.0f}um"] = round(h_face(pan, TILT_FOLLOW, SPRING_F[0], K_OIL, 0.0, ex))
        for kv in K_VARNISH:
            for tv in (10e-6, 30e-6, 60e-6, 100e-6):
                r[f"varnish_{tv * 1e6:.0f}um_k{kv}"] = round(1.0 / (1.0 / dry + tv / kv))
        rows[pan] = r
    squeeze = {f"{T}C": {f"{h0 * 1e6:.0f}->{h1 * 1e6:.0f}um_s": round(squeeze_time(MU_OIL[T], h0, h1), 3)
                         for h0, h1 in ((100e-6, 20e-6), (100e-6, 5e-6), (20e-6, 2e-6))} for T in MU_OIL}
    return rows, squeeze


def water_table():
    rows = {}
    for pan in cm.PANS:
        rows[pan] = {"dry": round(h_dry(pan)),
                     "liquid_gap": round(h_face(pan, TILT_FOLLOW, SPRING_F[0], K_WATER, 0.0)),
                     "vapour_gap": round(h_face(pan, TILT_FOLLOW, SPRING_F[0], K_VAPOUR, cm.M_GAS))}
    return rows


def crud_table():
    """Sticky post. Partial (friction < spring): force F_s - F_f and the pan's tilt not
    followed. Stuck (friction >= spring): no load, a uniform separation from pan bow."""
    rows = {}
    for pan in cm.PANS:
        r = {"dry": round(h_dry(pan))}
        for ff in (0.5, 1.0, 1.1):
            r[f"partial_Ff{ff}N_tilt5mrad"] = round(h_face(pan, TILT_PAN, SPRING_F[0] - ff, K_AIR, cm.M_GAS))
        for d in (0.0, 10e-6, 25e-6, 50e-6, 100e-6, 200e-6, 300e-6, 500e-6):
            r[f"stuck_gap_{d * 1e6:.0f}um"] = round(h_face(pan, TILT_PAN, 1e-3, K_AIR, cm.M_GAS, d))
        rows[pan] = r
    return rows


def h_gap_fn(pan, tilt=TILT_PAN):
    """h(separation in m) for a stuck post (no load), as an interpolation table."""
    ds = np.array([0.0, 5e-6, 10e-6, 25e-6, 50e-6, 100e-6, 200e-6, 300e-6, 500e-6, 1e-3])
    hs = np.array([h_face(pan, tilt, 1e-3, K_AIR, cm.M_GAS, d) for d in ds])
    return lambda d: float(np.interp(d, ds, hs))


# ---- truth plants for the closed loop ----------------------------------------------
class ContactTruth(screen.Truth):
    """screen.Truth whose contact is set by h_fn(truth, h_dry) each step (h_dry is the
    loop's own h_c(t)); optional extra heat exchange via exchange()."""

    def __init__(self, pan, h0, eta, seed, food_at=None, h_fn=None):
        super().__init__(pan, h0, eta, seed, food_at=food_at)
        self.h_fn = h_fn
        self.h_eff = h0

    def step(self, P_in, h_c, P_h=0.0):
        """One DT_SIM step, sub-cycled so that explicit Euler stays stable for a stiff
        contact (a liquid-filled gap) or a boiling pocket."""
        self.h_eff = self.h_fn(self, h_c) if self.h_fn else h_c
        dt = es.DT_SIM
        g_cap = self.h_eff * es.A_CONTACT + self.g_exchange_cap()
        rate = max(g_cap / es.C_CAP, self.g_exchange_pan())
        n = max(1, int(np.ceil(rate * dt / 0.4)))
        try:
            es.DT_SIM = dt / n
            for _ in range(n):
                super().step(P_in, self.h_eff, P_h)
                self.exchange()
        finally:
            es.DT_SIM = dt

    def exchange(self):
        pass

    def g_exchange_cap(self):
        """Linearised extra conductance on the cap node (W/K), for the sub-cycle count."""
        return 0.0

    def g_exchange_pan(self):
        """Largest extra conductance / heat capacity on a pan ring (1/s)."""
        return 0.0


class StickyTruth(ContactTruth):
    """Post stuck from t_stick: the gap opens as the pan bows (rise delta_max at 230 C,
    linear in T_mean above the temperature at the stick), plus an optional step gap."""

    def __init__(self, pan, h0, eta, seed, food_at=None, cls="cast_iron_as_cast", delta_max=0.2e-3,
                 t_stick=0.0, gap_step=None):
        super().__init__(pan, h0, eta, seed, food_at=food_at)
        self.hg = h_gap_fn(cls)
        self.delta_max, self.t_stick, self.gap_step = delta_max, t_stick, gap_step
        self.T_stick = None
        self.h_fn = self._h

    def _h(self, tr, h_dry):
        if self.t < self.t_stick:
            return h_dry
        if self.T_stick is None:
            self.T_stick = self.T_mean()
        d = self.delta_max * min(max((self.T_mean() - self.T_stick) / (230.0 - es.T_AMB), 0.0), 1.0)
        if self.gap_step and self.t >= self.gap_step[0]:
            d += self.gap_step[1]
        return min(h_dry, self.hg(d))


class WaterTruth(ContactTruth):
    """A water pocket around the post: m_w0 kg arriving at t_in at T_in (t_in 0: a wet pan
    placed cold). While water is present the gap is liquid-filled below 100 C at the
    contact (h_liq) and vapour-filled above (h_vap); the pocket takes heat from the pan
    bottom over A_POCKET and from the disc edge on the boiling curve; at 100 C it boils
    off at h_fg."""

    def __init__(self, pan, h0, eta, seed, food_at=None, m_w0=0.15e-3, t_in=0.0, T_in=20.0,
                 h_liq=20000.0, h_vap=None, boil_scale=1.0):
        super().__init__(pan, h0, eta, seed, food_at=food_at)
        self.m_w0, self.t_in, self.T_in = m_w0, t_in, T_in
        self.h_liq, self.h_vap, self.boil_scale = h_liq, h_vap, boil_scale
        self.m_w, self.T_w = 0.0, T_in
        self.arrived = False
        dr = self.p["R"] / es.N_RINGS
        lo = np.arange(es.N_RINGS) * dr
        hi = lo + dr
        ov = np.clip(np.minimum(hi, R_POCKET[1]) ** 2 - np.maximum(lo, R_POCKET[0]) ** 2, 0, None) * pi
        self.w_ring = ov / ov.sum()
        self.boiled_s = 0.0
        self.h_fn = self._h

    def _h(self, tr, h_dry):
        if not self.arrived and self.t >= self.t_in:
            self.arrived, self.m_w, self.T_w = True, self.m_w0, self.T_in
        if self.m_w <= 0.0:
            return h_dry
        if self.T_c() < 100.0:
            return max(h_dry, self.h_liq)
        return self.h_vap if self.h_vap is not None else h_dry * K_VAPOUR / K_AIR

    def _g_lin(self, dT):
        """dq''/dT of the boiling curve (or the subcooled conduction), W/m2 K."""
        if self.T_w < 100.0:
            return H_SUB
        d = max(abs(dT), 0.5)
        return max(H_NC, abs(q_boil(d + 0.5, self.boil_scale) - q_boil(max(d - 0.5, 0.0), self.boil_scale)))

    def g_exchange_cap(self):
        if self.m_w <= 0.0:
            return 0.0
        return A_EDGE * self._g_lin(self.Tcap - self.T_w)

    def g_exchange_pan(self):
        if self.m_w <= 0.0:
            return 0.0
        Tp = float((self.T * self.w_ring).sum())
        return float((A_POCKET * self._g_lin(Tp - self.T_w) * self.w_ring / self.C).max())

    def exchange(self):
        if self.m_w <= 0.0:
            return
        dt = es.DT_SIM
        Tp = float((self.T * self.w_ring).sum())
        if self.T_w < 100.0:
            q_pan = A_POCKET * H_SUB * (Tp - self.T_w)
            q_disc = A_EDGE * H_SUB * (self.Tcap - self.T_w)
        else:
            q_pan = A_POCKET * q_boil(Tp - 100.0, self.boil_scale)
            q_disc = A_EDGE * q_boil(self.Tcap - 100.0, self.boil_scale)
        self.T = self.T - dt * q_pan * self.w_ring / self.C
        self.Tcap -= dt * q_disc / es.C_CAP
        if self.T_w < 100.0:
            self.T_w = min(100.0, self.T_w + dt * (q_pan + q_disc) / (self.m_w * CP_W))
        else:
            self.m_w -= dt * max(q_pan + q_disc, 0.0) / H_FG
            self.boiled_s += dt
            if self.m_w <= 0.0:
                self.m_w = 0.0


def main():
    oil, squeeze = oil_table()
    out = {"scope": __doc__.strip(),
           "constants": {"k_air": round(K_AIR, 4), "k_oil": K_OIL, "k_oil_range": K_OIL_RANGE, "mu_oil_Pa_s": MU_OIL,
                         "k_varnish_range": K_VARNISH, "k_water": K_WATER, "k_vapour": K_VAPOUR, "h_fg": H_FG,
                         "q_max": Q_MAX, "q_min": Q_MIN, "A_pocket_mm2": round(A_POCKET * 1e6, 1),
                         "A_edge_mm2": round(A_EDGE * 1e6, 1), "wiper_friction_N": WIPER_F, "spring_N": SPRING_F},
           "oil_h_W_m2K": oil, "oil_squeeze_film_s": squeeze,
           "water_h_W_m2K": water_table(),
           "crud_h_W_m2K": crud_table(),
           "boiling_curve_W_m2": {f"{d}": round(q_boil(d)) for d in (2, 5, 10, 20, 30, 60, 100, 120, 150, 200)},
           "crud_friction_margin": {"stick_needs_friction_rise_x": round(SPRING_F[0] / WIPER_F[1], 1)}}
    (HERE / "contaminants.json").write_text(json.dumps(out, indent=1) + "\n")
    for k in ("oil_h_W_m2K", "water_h_W_m2K", "crud_h_W_m2K"):
        print("==", k)
        for p, r in out[k].items():
            print("  ", p, r)
    print("squeeze", squeeze)
    print("boil", out["boiling_curve_W_m2"])


if __name__ == "__main__":
    main()
