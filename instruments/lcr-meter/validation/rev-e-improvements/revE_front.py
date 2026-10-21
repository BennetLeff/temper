"""Rev E front end as a phasor network, for the improvements study.

The analog core is reduced to what survives calibration plus what can change after it:
  - source: SOURCE amplitude VS behind R_SRC (100 Ohm RG + 47 Ohm R104 on the 100 Ohm range);
  - fixture: 2-terminal J3 (followers sense J3 HI / J3 LO on the board) or 4-terminal (Kelvin)
    with four coax leads, followers on Hpot / Lpot, 1 kOhm CUR->POT on the board;
  - DUT_LO 100 pF C0G to ground, R_iso 22 Ohm to the TIA summing node (ideal virtual ground),
    TIA feedback Z_f = RF || CF;
  - four codec input legs (1k/1k divider, 560 pF, 1 uF X7R, 470 Ohm, codec R_in), CH1 = HIGH - LOW,
    CH2 = LOW - TIA (docs/rev-e-front-end.md);
  - codec ADC noise from the TAC5112 wideband SNR (91 dB to 85 kHz re 2 Vrms, -3 dB for CM_TOL = 01),
    exactly as ../rev-e-codec/noise_codec.py.
Followers are ideal (no input current); the TIA is an ideal virtual ground.  Fixed non-idealities of
the real core are linear and removed by the three-standard calibration (VI README section 2.5); this
model only has to carry what changes between calibration and measurement.  Cross-checks against the
SPICE-derived virtual instrument are in validate.py.
All arrays are batched over draws: every parameter is an array of shape (N,) (legs: (N, 4)).
"""
from __future__ import annotations

import math

import numpy as np

VS = 1.7                 # V peak, firmware cap (docs/rev-e-front-end.md "Level")
R_SRC = 147.0            # 100 Ohm RG + 47 Ohm R104 (rev-e-plan 2026-10-21)
R_CP = 1e3               # 4T: on-board CUR->POT resistor
R_LEAD_2T = 0.03         # ESTIMATE: one loose test lead, ohm
R_LEAD_COAX = 0.035      # ESTIMATE: 1 m RG-58 centre conductor + BNC, ohm
NOM = dict(Rin=44e3,     # TAC5112 p10: 44 kOhm typical in the "40 kOhm" mode
           Cc=1e-6, R1=1e3, R2=1e3, Caa=560e-12, Rser=470.0,
           RF=100.0, CF=100e-12, Riso=22.0, C100=100e-12)
# codec ADC noise (noise_codec.py): 2 Vrms differential full scale, SNR 91 dB over 85 kHz, CM_TOL 3 dB
ADC_SNR_DB = 91.0
CM_TOL_DB = 3.0
S_ADC = (2.0 / 10 ** ((ADC_SNR_DB - CM_TOL_DB) / 20)) ** 2 / 85e3   # V^2/Hz at the codec pins


def leg_gain(w, Rin, Cc, R1, R2, Caa, Rser=NOM["Rser"]):
    """Op-amp output -> codec sampled signal for one input leg (current into R_in times R_in)."""
    zbr = 1 / (1j * w * Cc) + Rser + Rin
    yx = 1 / R1 + 1 / R2 + 1j * w * Caa + 1 / zbr
    return (1 / R1) / yx * Rin / zbr


def nominal_drift(n):
    d = {k: np.full((n, 4), NOM[k], float) for k in ("Rin", "Cc", "R1", "R2", "Caa")}
    d.update({k: np.full(n, NOM[k], float) for k in ("RF", "CF", "Riso", "C100")})
    d["phi_cc"] = np.zeros(n)        # codec inter-channel phase drift (rad), sensitivity runs only
    d["rref_scale"] = np.ones(n)     # reference resistor TCR x dT
    return d


class Net:
    def __init__(self, n, nodes):
        self.n = n
        self.idx = {k: i for i, k in enumerate(nodes)}
        self.Y = np.zeros((n, len(nodes), len(nodes)), complex)
        self.I = np.zeros((n, len(nodes)), complex)

    def add(self, a, b, y):
        y = np.broadcast_to(np.asarray(y, complex), (self.n,))
        ia = self.idx.get(a)
        ib = self.idx.get(b)
        if ia is not None:
            self.Y[:, ia, ia] += y
        if ib is not None:
            self.Y[:, ib, ib] += y
        if ia is not None and ib is not None:
            self.Y[:, ia, ib] -= y
            self.Y[:, ib, ia] -= y

    def inject(self, a, i):
        self.I[:, self.idx[a]] += i

    def solve(self):
        v = np.linalg.solve(self.Y, self.I[..., None])[..., 0]
        return {k: v[:, i] for k, i in self.idx.items()}


def measure(f, kelvin, zdut, p, drift, rsrc=R_SRC, ref=None, rcp=R_CP, bypass=False):
    """Return codec phasors (A, B) for one capture per draw.

    zdut : (N,) complex DUT impedance, or None for open jacks (reference check).
    p    : fixture draws: 'rc' (N,4) contact R [2T uses rc[:,0] as the total per insertion;
           4T: Hcur, Hpot, Lpot, Lcur], 'c2t' (N,2) lead C hi/lo (2T), 'cx' (N,4) coax C
           (Hcur, Hpot, Lpot, Lcur), 'lser' (N,) series loop L (2T) or current->pot mutual (4T).
    ref  : (N,) complex reference branch impedance across the board CUR nodes (Rref + relay contact).
    bypass: 4T reference check with the relay's second pole shorting Hcur->Hpot on the board.
    """
    w = 2 * math.pi * f
    n = p["rc"].shape[0]
    d = drift
    zf = 1 / (1 / d["RF"] + 1j * w * d["CF"])
    gnd = None
    if not kelvin:
        net = Net(n, ["HB", "DH", "DL", "LB"])
        net.add("HB", gnd, 1 / rsrc)
        net.inject("HB", VS / rsrc)
        net.add("HB", "DH", 1 / (R_LEAD_2T + p["rc"][:, 0]))
        net.add("DH", gnd, 1j * w * p["c2t"][:, 0])
        net.add("DL", gnd, 1j * w * p["c2t"][:, 1])
        net.add("DL", "LB", 1 / R_LEAD_2T)
        net.add("LB", gnd, 1j * w * d["C100"] + 1 / d["Riso"])
        if zdut is not None:
            net.add("DH", "DL", 1 / (zdut + 1j * w * p["lser"]))
        if ref is not None:
            net.add("HB", "LB", 1 / ref)
        v = net.solve()
        vhp, vlp, vlc = v["HB"], v["LB"], v["LB"]
    else:
        cx = p["cx"]
        rc = p["rc"]
        if zdut is None:
            # Open jacks (reference check, DUT removed): Kelvin-clip jaws are insulated from each other,
            # so each coax is an open stub hanging on its own board node (lead R negligible).
            net = Net(n, ["HC", "HP", "LP", "LC"])
            net.add("HC", gnd, 1 / rsrc + 1j * w * cx[:, 0])
            net.inject("HC", VS / rsrc)
            net.add("HC", "HP", 1 / (1e-1 if bypass else rcp))
            net.add("HP", gnd, 1j * w * cx[:, 1])
            net.add("LP", gnd, 1j * w * cx[:, 2])
            net.add("LP", "LC", 1 / rcp)
            net.add("LC", gnd, 1j * w * (cx[:, 3] + d["C100"]) + 1 / d["Riso"])
            if ref is not None:
                net.add("HC", "LC", 1 / ref)
            v = net.solve()
            vhp, vlp, vlc = v["HP"], v["LP"], v["LC"]
            return _codec(w, vhp, vlp, vlc, d, zf)
        net = Net(n, ["HC", "HP", "DH", "DL", "LP", "LC"])
        net.add("HC", gnd, 1 / rsrc + 1j * w * cx[:, 0] / 2)
        net.inject("HC", VS / rsrc)
        net.add("HC", "DH", 1 / (R_LEAD_COAX + rc[:, 0]))
        net.add("DH", gnd, 1j * w * (cx[:, 0] + cx[:, 1]) / 2)
        net.add("HC", "HP", 1 / (1e-1 if bypass else rcp))
        net.add("HP", "DH", 1 / (R_LEAD_COAX + rc[:, 1]))
        net.add("HP", gnd, 1j * w * cx[:, 1] / 2)
        net.add("DL", "LP", 1 / (R_LEAD_COAX + rc[:, 2]))
        net.add("LP", gnd, 1j * w * cx[:, 2] / 2)
        net.add("DL", gnd, 1j * w * (cx[:, 2] + cx[:, 3]) / 2)
        net.add("DL", "LC", 1 / (R_LEAD_COAX + rc[:, 3]))
        net.add("LC", gnd, 1j * w * (cx[:, 3] / 2 + d["C100"]) + 1 / d["Riso"])
        net.add("LP", "LC", 1 / rcp)
        if zdut is not None:
            net.add("DH", "DL", 1 / (zdut + 1j * w * p["lser"]))
        if ref is not None:
            net.add("HC", "LC", 1 / ref)
        v = net.solve()
        vhp, vlp, vlc = v["HP"], v["LP"], v["LC"]
    return _codec(w, vhp, vlp, vlc, d, zf)


def _codec(w, vhp, vlp, vlc, d, zf):
    vtia = -(vlc / d["Riso"]) * zf
    g = [leg_gain(w, d["Rin"][:, k], d["Cc"][:, k], d["R1"][:, k], d["R2"][:, k], d["Caa"][:, k]) for k in range(4)]
    a = g[0] * vhp - g[1] * vlp
    b = (g[2] * vlp - g[3] * vtia) * np.exp(1j * d["phi_cc"])
    return a, b


def phasor_sigma(T, mult=1.0):
    """1-sigma of each real component of a fitted codec phasor (E|dP|^2 = 2 S / T)."""
    return math.sqrt(S_ADC / T) * mult


M_SCALE = NOM["Riso"] + NOM["RF"]   # raw ratio scale so that m ~ Z in ohms


def raw(a, b, rng=None, sigma=0.0):
    if rng is not None and sigma > 0:
        n = a.shape[0]
        a = a + sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
        b = b + sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return M_SCALE * a / b
