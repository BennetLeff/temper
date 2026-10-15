#!/usr/bin/env python3
"""Stage-19b conducted-EMI margin study (task: EMC1 follow-up).  numpy/scipy only (+matplotlib for PNGs).

Deterministic.  Usage:  python3 emi_s19b.py [--no-plots] [--quick]
Writes results.json and spectrum_*.png next to this file.

Layout of this file
  1. limits (47 CFR 18.307(a) induction-cooking table, as transcribed in ../sources/ecfr-47cfr18.307-table.json)
  2. a small complex MNA solver (replaces ngspice; validated against D-22's saved ngspice transfers)
  3. network builders: the native-15 / D-22 receiver (control) and the stage-19b receiver
  4. sources: analytic full-bridge (trapezoid sw-node + rectified-tank bus current), checked against D-22 FFTs
  5. controls (asserted), the stage-19b run, sensitivities, bounds for PS2 / PS3, verdict
Stage 38 (candidate 23, DECISIONS 47): the nominal inlet module is the stage-38 one (Y removed, SCF31X 5.68 mH CM
choke; MODULE_S38) and the part-value sensitivities are relative to it.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "3")  # rule: <= 3 CPU workers

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PS = HERE.parents[2]  # zapote/power-stage-120v
D22 = PS / "validation-results/01-switching-parasitics/round17/delegation/out-D22"
R3 = PS / "validation-results/07-conducted-emi/round3/outputs"
COPPER = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/s19/s19b/copper-dump.json")
COPPER_FALLBACK = HERE / "inputs/copper-dump-s19b-summary.json"  # reduced numbers, committed (dump is 2.6 MB)
EPS0 = 8.8541878128e-12
QUICK = "--quick" in sys.argv

# ----------------------------------------------------------------------------------------------
# 1. limits
# ----------------------------------------------------------------------------------------------


def limits(f):
    """Return (qp, av, regulated) dBuV.  150k-30M per 47 CFR 18.307(a) (tighter value at a boundary);
    9-150 kHz: QP only (110 dBuV to 50 kHz, 90->80 dBuV log decrease 50-150 kHz), AV = NaN (none).
    18.307(e)/18.301 ISM exclusions applied above 150 kHz (6.78 MHz +-15 kHz, 13.56 +-7 kHz, 27.12 +-163 kHz)."""
    f = np.asarray(f, float)
    qp = np.where(f < 50e3, 110.0, 90.0 - 10.0 * np.log(f / 50e3) / np.log(3.0))
    hi = f >= 150e3
    qp_hi = np.where(f < 500e3, 66 - 10 * np.log(np.maximum(f, 1) / 150e3) / np.log(500 / 150),
                     np.where(f <= 5e6, 56.0, 60.0))
    qp = np.where(hi, qp_hi, qp)
    av = np.where(hi, qp_hi - 10.0, np.nan)
    reg = (f >= 9e3) & (f <= 30e6)
    for c, w in ((6.78e6, 15e3), (13.56e6, 7e3), (27.12e6, 163e3)):
        reg &= np.abs(f - c) > w
    return qp, av, reg


def d22_limits(f):
    """Exactly D-22's (150 kHz-30 MHz) limits() for the control."""
    qp, av, reg = limits(f)
    return qp, av, reg & (np.asarray(f) >= 150e3)


# ----------------------------------------------------------------------------------------------
# 2. MNA solver
# ----------------------------------------------------------------------------------------------


class Net:
    """Linear AC network.  Elements: R, C, L (named, couplable), K, V (named, ideal), I (named)."""

    def __init__(self):
        self.el = []

    def R(self, a, b, v):
        self.el.append(("R", a, b, float(v)))

    def C(self, a, b, v):
        self.el.append(("C", a, b, float(v)))

    def L(self, name, a, b, v):
        self.el.append(("L", name, a, b, float(v)))

    def K(self, l1, l2, k):
        self.el.append(("K", l1, l2, float(k)))

    def V(self, name, a, b):
        self.el.append(("V", name, a, b))

    def I(self, name, a, b):  # current flows a -> (through source) -> b
        self.el.append(("I", name, a, b))

    def series_rlc(self, a, b, tag, l=0.0, r=0.0, c=None):
        """a --L-- --R-- --C-- b (skips zero parts)."""
        nodes = [a]
        parts = []
        if l:
            parts.append(("L", l))
        if r:
            parts.append(("R", r))
        if c:
            parts.append(("C", c))
        for i, (k, v) in enumerate(parts):
            nxt = b if i == len(parts) - 1 else f"{tag}_{i}"
            if k == "L":
                self.L(f"L_{tag}_{i}", nodes[-1], nxt, v)
            elif k == "R":
                self.R(nodes[-1], nxt, v)
            else:
                self.C(nodes[-1], nxt, v)
            nodes.append(nxt)

    def compile(self):
        nodes = {"0": -1}
        for e in self.el:
            for n in (e[1], e[2]) if e[0] in "RC" else ((e[2], e[3]) if e[0] in "LVI" else ()):
                if n not in nodes:
                    nodes[n] = len(nodes) - 1
        nn = len(nodes) - 1
        branches = [e for e in self.el if e[0] in "LV"]
        bidx = {e[1]: nn + i for i, e in enumerate(branches)}
        N = nn + len(branches)
        A0 = np.zeros((N, N), complex)
        A1 = np.zeros((N, N), complex)  # multiplied by j*omega

        def stamp(M, i, j, v):
            if i >= 0 and j >= 0:
                M[i, j] += v

        for e in self.el:
            k = e[0]
            if k in "RC":
                a, b = nodes[e[1]], nodes[e[2]]
                M, val = (A0, 1.0 / e[3]) if k == "R" else (A1, e[3])
                for (i, j, s) in ((a, a, 1), (b, b, 1), (a, b, -1), (b, a, -1)):
                    stamp(M, i, j, s * val)
            elif k in "LV":
                a, b = nodes[e[2]], nodes[e[3]]
                bi = bidx[e[1]]
                stamp(A0, a, bi, 1)
                stamp(A0, b, bi, -1)
                stamp(A0, bi, a, 1)
                stamp(A0, bi, b, -1)
                if k == "L":
                    A1[bi, bi] += -e[4]
        for e in self.el:
            if e[0] == "K":
                l1 = next(x for x in self.el if x[0] == "L" and x[1] == e[1])
                l2 = next(x for x in self.el if x[0] == "L" and x[1] == e[2])
                m = e[3] * np.sqrt(l1[4] * l2[4])
                A1[bidx[e[1]], bidx[e[2]]] += -m
                A1[bidx[e[2]], bidx[e[1]]] += -m
        return nodes, bidx, A0, A1, N

    def solve(self, freqs, excitations, outputs, chunk=3000):
        """excitations: {name: {source_name: amplitude}}; outputs: {name: (node_a, node_b)} -> V(a)-V(b).
        Returns {exc: {out: complex array over freqs}}."""
        nodes, bidx, A0, A1, N = self.compile()
        isrc = {e[1]: (nodes[e[2]], nodes[e[3]]) for e in self.el if e[0] == "I"}
        names = list(excitations)
        B = np.zeros((N, len(names)), complex)
        for c, nm in enumerate(names):
            for s, amp in excitations[nm].items():
                if s in bidx:
                    B[bidx[s], c] += amp
                else:
                    a, b = isrc[s]
                    if a >= 0:
                        B[a, c] -= amp
                    if b >= 0:
                        B[b, c] += amp
        freqs = np.asarray(freqs, float)
        res = {nm: {o: np.zeros(len(freqs), complex) for o in outputs} for nm in names}
        for s in range(0, len(freqs), chunk):
            w = 2 * np.pi * freqs[s:s + chunk]
            A = A0[None] + 1j * w[:, None, None] * A1[None]
            X = np.linalg.solve(A, np.broadcast_to(B, (len(w), N, len(names))).copy())
            for c, nm in enumerate(names):
                for o, (na, nb) in outputs.items():
                    va = X[:, nodes[na], c] if nodes[na] >= 0 else 0
                    vb = X[:, nodes[nb], c] if nodes[nb] >= 0 else 0
                    res[nm][o][s:s + chunk] = va - vb
        return res


# ----------------------------------------------------------------------------------------------
# 3. networks
# ----------------------------------------------------------------------------------------------

BASE = dict(  # round-3 / D-22 deck defaults (emi_topology.cir)
    LCM=1.6e-3, LDM=18e-6, RCH=4.5e-3, CCH=11.078e-12, RLOSSCH=12.691e3,
    CX=1e-6, ESLX=12.2e-9, ESRX=35e-3, CY=2.2e-9, ESLY=0.0, CMOV=1.4e-9,
    CBRJ=85e-12, CBRP=10e-12, CBRN=10e-12,
    CBULK=5.4e-6, CLOCAL=0.4e-6, LBULK=20e-9, LLOCAL=5e-9, RBULK=20e-3, RLOCAL=10e-3,
    CTABA=42e-12, CTABB=42e-12, CTABH=42e-12, CCOILA=15.7e-12, CCOILB=15.3e-12,  # enclosure study 16 (R43 Laplace solve), pan floating: 31.0 pF, J5 15.7 / J2 15.3
   
    CPOURA=0.0, CPOURB=0.0, CBUSPE_X=0.0, CBUSN_X=0.0, COIL_SHIELD_FRAC=0.0,
    LPE=100e-9, RPE=10e-3, RLISN_SERIES=0.0,
    RPAN=2.0, LCOIL=70e-6, CRES=0.54e-6,
    # D-22 added-stage defaults (filter_stage.py / qualify_filter.py NOMINAL)
    LNEW=18e-6, RNEW=8e-3, CPNEW=30e-12, CXNEW=4.7e-6, CDAMP=4.7e-6, RDAMP=3.9, ESLC=20e-9, ESRC=35e-3,
    LRDAMP=500e-9, LCMADD=1.6e-3, LDMADD=18e-6, RCMADD=4.5e-3, CCMADD=11.078e-12, RLCMADD=12.691e3,
    CXIN=2.2e-6, CYHF=2.2e-9, ESLYHF=10e-9, ESRYHF=0.1, CYADD=4.7e-9, ESLYADD=15e-9, ESRYADD=0.1,
)


def build(p0: dict, module: bool, aux: bool = False) -> Net:
    """Round-3 receiver, optional D-22/19b inlet module, tank, and noise ports.
    Sources: VlegA/VlegB (switch-node voltage vs bus_n), Idm (bus current), and, if aux, Iauxdm / Iauxcm."""
    p = {**BASE, **p0}
    n = Net()
    # LISN: mains side shorted (RF-quiet), 50 uH (+ optional 5 ohm), 0.1 uF to a 50 ohm sense resistor to PE.
    for s, t, ln in (("L", "mains_l", "line_in"), ("N", "mains_n", "neut_in")):
        n.L(f"Llisn{s}", "0", ln, 50e-6) if not p["RLISN_SERIES"] else (
            n.R("0", f"lisnr{s}", p["RLISN_SERIES"]), n.L(f"Llisn{s}", f"lisnr{s}", ln, 50e-6))
        n.C(ln, f"lisn_{s.lower()}", 0.1e-6)
        n.R(f"lisn_{s.lower()}", "pe", 50.0)
    n.R("pe", "pe_l", p["RPE"])
    n.L("Lbond", "pe_l", "0", p["LPE"])
    if module:
        # inlet module: input X, coupled CM choke (+ leakage DM), discrete DM inductors, X, damping branch,
        # bleed, Y caps (D-22 PARTS.md topology; DM L raised per DECISIONS "EMI below 150 kHz" item 4)
        n.series_rlc("line_in", "neut_in", "xin", p["ESLC"], p["ESRC"], p["CXIN"])
        for s, ln, ch in (("L", "line_in", "add_l"), ("N", "neut_in", "add_n")):
            n.R(ln, f"cm_{s}a", p["RCMADD"])
            n.L(f"LcmAdd{s}", f"cm_{s}a", ch, p["LCMADD"])
            n.C(ln, ch, p["CCMADD"])
            n.R(ln, ch, p["RLCMADD"])
        n.K("LcmAddL", "LcmAddN", 1 - p["LDMADD"] / (2 * p["LCMADD"]))
        if p["LNEW"] > 0:
            for s, a, b in (("L", "add_l", "lm"), ("N", "add_n", "nm")):
                n.R(a, f"new_{s}a", p["RNEW"])
                n.L(f"Lnew{s}", f"new_{s}a", b, p["LNEW"])
                n.C(a, b, p["CPNEW"])
        else:
            n.R("add_l", "lm", 1e-6)
            n.R("add_n", "nm", 1e-6)
        LM, NM = "lm", "nm"
        n.series_rlc(LM, NM, "xnew", p["ESLC"], p["ESRC"], p["CXNEW"])
        n.series_rlc(LM, NM, "damp", p["ESLC"] + p["LRDAMP"], p["RDAMP"], p["CDAMP"])
        n.R(LM, NM, 30e3)
        for s, ln in (("L", LM), ("N", NM)):
            n.series_rlc(ln, "pe", f"yadd{s}", p["ESLYADD"], p["ESRYADD"], p["CYADD"])
            n.series_rlc(ln, "pe", f"yhf{s}", p["ESLYHF"], p["ESRYHF"], p["CYHF"])
    else:
        LM, NM = "line_in", "neut_in"
        n.R("add_l", "line_in", 1e12)  # dangling guard (unused nodes would be singular)
        n.R("add_n", "neut_in", 1e12)
        n.R("lm", "line_in", 1e12)
        n.R("nm", "neut_in", 1e12)
    # board filter: C1, MOV, L1, C2, Y caps (native-21 ato: cx1/rv1 on L_F, l1 Cmc20A, cx2, cy1/cy2 2.2 nF)
    n.series_rlc(LM, NM, "x1", p["ESLX"], p["ESRX"], p["CX"])
    n.C(LM, NM, p["CMOV"])
    for s, a, b, ch in (("L", LM, "line_f", "ch_l"), ("N", NM, "neut_f", "ch_n")):
        n.R(a, ch, p["RCH"])
        n.L(f"LchL" if s == "L" else "LchN", ch, b, p["LCM"])
        n.C(a, b, p["CCH"])
        n.R(a, b, p["RLOSSCH"])
    n.K("LchL", "LchN", 1 - p["LDM"] / (2 * p["LCM"]))
    n.series_rlc("line_f", "neut_f", "x2", p["ESLX"], p["ESRX"], p["CX"])
    n.series_rlc("line_f", "pe", "yl", p["ESLY"], 0.0, p["CY"])
    n.series_rlc("neut_f", "pe", "yn", p["ESLY"], 0.0, p["CY"])
    # rectifier conducting pair at line crest + junction caps + case coupling
    n.R("line_f", "bus_p", 0.05)
    n.R("neut_f", "bus_n", 0.05)
    for a in ("line_f", "neut_f"):
        n.C(a, "bus_p", p["CBRJ"])
        n.C(a, "bus_n", p["CBRJ"])
    n.C("bus_p", "pe", p["CBRP"] + p["CBUSPE_X"])
    n.C("bus_n", "pe", p["CBRN"] + p["CBUSN_X"])
    # DC link groups
    n.series_rlc("bus_p", "bus_n", "bulk", p["LBULK"], p["RBULK"], p["CBULK"])
    n.series_rlc("bus_p", "bus_n", "local", p["LLOCAL"], p["RLOCAL"], p["CLOCAL"])
    n.I("Idm", "bus_p", "bus_n")
    # bridge: switch nodes (ideal sources vs bus_n), tabs and pours to PE, tank
    n.V("VlegA", "sw_a", "bus_n")
    n.V("VlegB", "sw_b", "bus_n")
    n.C("bus_p", "pe", 2 * p["CTABH"])  # Q2 and Q5 tabs
    n.C("sw_a", "pe", p["CTABA"] + p["CPOURA"])
    n.C("sw_b", "pe", p["CTABB"] + p["CPOURB"])
    n.R("sw_a", "tank_a", p["RPAN"])
    n.L("Lcoil", "tank_a", "tank_b", p["LCOIL"])
    n.C("tank_b", "sw_b", p["CRES"])
    ca, cb = ("tank_a", "tank_b") if p.get("COIL_AT_TANK") else ("sw_a", "sw_b")
    fr = p["COIL_SHIELD_FRAC"]  # fraction of the coil capacitance returned to bus_n (coil-side electrostatic shield)
    n.C(ca, "pe", p["CCOILA"] * (1 - fr))
    n.C(cb, "pe", p["CCOILB"] * (1 - fr))
    if fr:
        n.C(ca, "bus_n", p["CCOILA"] * fr)
        n.C(cb, "bus_n", p["CCOILB"] * fr)
    if aux:  # auxiliary-supply noise ports on the filtered side (PS1-PS3 sit on L_FILT / N_FILT)
        n.I("Iauxdm", "line_f", "neut_f")
        n.I("Iauxcl", "line_f", "pe")
        n.I("Iauxcn", "neut_f", "pe")
    return n


OUT = {"l_pe": ("lisn_l", "pe"), "n_pe": ("lisn_n", "pe"), "l_gnd": ("lisn_l", "0"), "n_gnd": ("lisn_n", "0")}
EXC = {"A": {"VlegA": 1}, "B": {"VlegB": 1}, "DM": {"Idm": 1}}
EXC_AUX = {"AUXDM": {"Iauxdm": 1}, "AUXCM": {"Iauxcl": 1, "Iauxcn": 1}}


def transfers(p, module, freqs, aux=False):
    net = build(p, module, aux)
    exc = {**EXC, **(EXC_AUX if aux else {})}
    return net.solve(freqs, exc, OUT)


def levels(v_l, v_n):
    """dBuV rms of complex peak phasors (peak/sqrt2)."""
    f = lambda z: 20 * np.log10(np.maximum(np.abs(z), 1e-30) / np.sqrt(2) / 1e-6)
    return {"L": f(v_l), "N": f(v_n), "CM": f((v_l + v_n) / 2), "DM": f((v_l - v_n) / 2),
            "terminal": np.maximum(f(v_l), f(v_n))}


# ----------------------------------------------------------------------------------------------
# 4. sources
# ----------------------------------------------------------------------------------------------


def v_leg(n, fs, vc, tr, tf, leg):
    """Peak phasor of harmonic n of a 0..vc, 50 % duty leg with linear edges centred on t=0 (A rises at
    t=0; B is A delayed by T/2).  a_n = vc/(j n w T) [sinc(n fs tr) - (-1)^n sinc(n fs tf)]."""
    n = np.asarray(n, float)
    w = 2 * np.pi * n * fs
    T = 1 / fs
    s = lambda t: np.sinc(n * fs * t)  # numpy sinc is sin(pi x)/(pi x)
    a = vc / (1j * w * T) * (s(tr) - np.where(n % 2 == 0, 1.0, -1.0) * s(tf))
    a = 2 * a
    if leg == "B":
        a = a * np.exp(-1j * w * T / 2)
    return a


def i_bus(n, ipk, phi, tc):
    """Peak phasor at harmonic n of fs of the bridge input current |-rectified| i = Ipk sin(wt-phi) sgn(sin wt):
    only even n; c_k = Ipk/pi [e^{-j phi}/(1-2k) + e^{j phi}/(1+2k)], n=2k, smoothed by sinc(n fs tc)."""
    n = np.asarray(n)
    out = np.zeros(n.shape, complex)
    even = (n % 2 == 0) & (n > 0)
    k = n[even] // 2
    out[even] = 2 * ipk / np.pi * (np.exp(-1j * phi) / (1 - 2 * k) + np.exp(1j * phi) / (1 + 2 * k))
    return out


# ----------------------------------------------------------------------------------------------
# 5a. controls
# ----------------------------------------------------------------------------------------------


def control_d22(results):
    """Reproduce D-22's committed numbers (native-15 receiver, ngspice -> MNA)."""
    qm = json.load(open(D22 / "qualified-margin-results.json"))
    scen = json.load(open(D22 / "filter-scenarios.json"))
    out = {"transfer_parity": [], "margins": []}
    # (i) transfer parity against ngspice exact-harmonic AC arrays
    for name, fs in (("original_nominal", 35000), ("original_nominal", 60000),
                     ("proposed_nominal", 35000), ("proposed_nominal", 60000), ("old_low_leakage", 60000)):
        added, params = scen[name]
        f = np.arange(1, int(30e6 / fs) + 1) * fs
        mine = transfers(params, added, f)
        for src in ("A", "B", "DM"):
            ref = np.load(D22 / "harmonic-transfer-v3" / f"{name}-f{fs}-{src}.npz")
            rl = ref["v(lisn_l)"] - ref["v(pe)"]
            rn = ref["v(lisn_n)"] - ref["v(pe)"]
            err = max(np.max(np.abs(mine[src]["l_pe"] - rl) / np.maximum(np.abs(rl), 1e-30)),
                      np.max(np.abs(mine[src]["n_pe"] - rn) / np.maximum(np.abs(rn), 1e-30)))
            out["transfer_parity"].append({"scenario": name, "fs_hz": fs, "source": src,
                                           "max_rel_err_vs_ngspice": float(err)})
    # (ii) committed D-22 margins from its own source FFTs
    def margin(case_npz, name, fs):
        added, params = scen[name]
        with np.load(case_npz) as d:
            sig = {k: d[k] for k in d.files}
        sel = sig["frequency_Hz"] > 0
        f = sig["frequency_Hz"][sel]
        tr = transfers(params, added, f)
        vl = sum(tr[s]["l_pe"] * sig[k][sel] for s, k in (("A", "v(swa)"), ("B", "v(swb)"), ("DM", "bus_current_A")))
        vn = sum(tr[s]["n_pe"] * sig[k][sel] for s, k in (("A", "v(swa)"), ("B", "v(swb)"), ("DM", "bus_current_A")))
        lv = levels(vl, vn)["terminal"]
        qp, av, reg = d22_limits(f)
        i = np.flatnonzero(reg)[np.argmin((av - lv)[reg])]
        return float((av - lv)[i]), float(f[i])

    jobs = [("d19-v170-r2-e1.06-f35000-s0.5-c24", "v170-r2-e1.06-f35000-s0.5-c24-full-fft.npz", 35000),
            ("d19-v170-r2-e1.06-f60000-s0.5-c48", "v170-r2-e1.06-f60000-s0.5-c48-full-fft.npz", 60000)]
    for case, npz, fs in jobs:
        for name in ("original_nominal", "proposed_nominal"):
            ref = next(r for r in qm if r["case"] == case and r["scenario"] == name and r["mode"] == "terminal")
            av, fz = margin(D22 / npz, name, fs)
            out["margins"].append({"case": case, "scenario": name, "committed_AV_dB": ref["AV_dB"], "committed_Hz": ref["Hz"],
                                   "repro_AV_dB": av, "repro_Hz": fz, "delta_dB": av - ref["AV_dB"]})
    # (iii) the headline: worst proposed-filter margin 9.28 dB (198 V, 60 kHz, old_low_leakage)
    case = "envelope-v198-f60000-r100-e1.06-s0.5"
    ref = next(r for r in qm if r["case"] == case and r["scenario"] == "old_low_leakage" and r["mode"] == "terminal")
    av, fz = margin(D22 / "periodic-runs" / case / "fft.npz", "old_low_leakage", 60000)
    out["margins"].append({"case": case, "scenario": "old_low_leakage", "committed_AV_dB": ref["AV_dB"],
                           "committed_Hz": ref["Hz"], "repro_AV_dB": av, "repro_Hz": fz, "delta_dB": av - ref["AV_dB"]})
    out["headline_D22_worst_margin_committed_dB"] = 9.28
    out["headline_D22_worst_margin_repro_dB"] = av
    return out


def trapezoid_round3(h, fs, vbus, edge_s, shift):
    period = 1 / fs
    w = 2 * np.pi * h * fs
    ramp = (1 - np.exp(-1j * w * edge_s)) / (1j * w * edge_s)
    return 2 * (vbus * ramp * (1 - np.exp(-1j * w * period / 2)) / (1j * w * period)) * np.exp(-1j * w * shift)


def control_round3():
    """native-15 round-3 'both_mismatches' assumed-spectrum peak CM lines (committed 59.97 / 64.19 dBuV)."""
    summ = json.load(open(R3 / "assumed_spectrum_summary.json"))
    res = []
    scen = {"both_mismatches": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12}, 5.0, 1.2),
            "balanced": ({"CTABA": 42e-12, "CTABB": 42e-12}, 5.0, 1.0),
            "choke_l_minus_30pct": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12, "LCM": 1.12e-3}, 5.0, 1.2),
            "coil_pe_100pf": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12, "CCOILA": 50e-12, "CCOILB": 50e-12}, 5.0, 1.2)}
    for name, (par, slope, bf) in scen.items():
        for fs in (35e3, 60e3):
            h = np.arange(int(np.ceil(150e3 / fs)), int(np.floor(30e6 / fs)) + 1)
            f = h * fs
            tr = transfers({**par, "LNEW": 0}, False, f)
            va = trapezoid_round3(h, fs, 170.0, 170.0 / (slope * 1e9), 0.0)
            vb = trapezoid_round3(h, fs, 170.0, 170.0 / (slope * 1e9) * bf, 0.5 / fs)
            l = tr["A"]["l_gnd"] * va + tr["B"]["l_gnd"] * vb
            n_ = tr["A"]["n_gnd"] * va + tr["B"]["n_gnd"] * vb
            cm = np.abs((l + n_) / 2)
            pk = 20 * np.log10(np.maximum(cm, 1e-30) / 1e-6)
            i = int(np.argmax(pk))
            ref = next(s for s in summ if s["scenario"] == name and s["switching_hz"] == fs)
            res.append({"scenario": name, "fs_hz": fs, "committed_dBuV": ref["max_cm_peak_dbuv"], "committed_Hz": ref["at_hz"],
                        "repro_dBuV": float(pk[i]), "repro_Hz": float(f[i]), "delta_dB": float(pk[i] - ref["max_cm_peak_dbuv"])})
    return res


def control_closed_form():
    """Closed-form checks of the MNA + LISN stack (two frequencies each), independent formulas.
    (a) DM: ideal source -> series L -> shunt C -> R (LISN 50 ohm):  H = 1/(1 - w^2 L C + j w L / R).
    (b) CM: capacitive injection Ccm into the two 50-ohm LISN sense resistors in parallel (25 ohm) with
        the LISN 50 uH in series with 0.1 uF acting as ~short: V = I*25, I = jwC V0, transfer magnitude
        |jwC*25/(1 + jwC*25)| exactly for this one-pole network (LISN coupling caps/inductors included below)."""
    res = []
    L, C, R = 100e-6, 4.7e-6, 50.0
    for f in (20e3, 200e3):
        n = Net()
        n.V("Vs", "a", "0")
        n.L("L1", "a", "b", L)
        n.C("b", "0", C)
        n.R("b", "0", R)
        mine = n.solve([f], {"s": {"Vs": 1}}, {"o": ("b", "0")})["s"]["o"][0]
        w = 2 * np.pi * f
        ref = 1 / (1 - w * w * L * C + 1j * w * L / R)
        res.append({"case": "series-L shunt-C 50 ohm", "f_hz": f, "mna_dB": 20 * np.log10(abs(mine)),
                    "closed_form_dB": 20 * np.log10(abs(ref)), "delta_dB": 20 * np.log10(abs(mine)) - 20 * np.log10(abs(ref))})
    # (b) full LISN network of build(): a voltage source V0 in series with Ccm from the (otherwise floating
    # DUT-free) line_in/neut_in to PE.  Closed form: both LISN branches are 50 uH || (0.1uF + 50 ohm) from the
    # EUT port to ground; sense voltage relative to PE (pe has Rbond+Lbond to ground, ~0 here).
    for f in (150e3, 2e6):
        Ccm = 100e-12
        n = Net()
        for s, ln in (("L", "line_in"), ("N", "neut_in")):
            n.L(f"Llisn{s}", "0", ln, 50e-6)
            n.C(ln, f"lisn_{s.lower()}", 0.1e-6)
            n.R(f"lisn_{s.lower()}", "pe", 50.0)
            n.C("x", ln, Ccm)
        n.V("V0", "x", "pe")
        n.R("pe", "0", 1e-9)
        mine = n.solve([f], {"s": {"V0": 1}}, {"o": ("lisn_l", "pe")})["s"]["o"][0]
        w = 2 * np.pi * f
        zl = 1 / (1 / (1j * w * 50e-6) + 1 / (1 / (1j * w * 0.1e-6) + 50))  # EUT-port impedance to ground
        z2 = zl / 2  # two ports in parallel
        i = 1 / (1 / (1j * w * Ccm) / 2 + z2)  # V0 -> two Ccm in parallel -> z2
        vport = i * z2
        ref = vport * 50 / (50 + 1 / (1j * w * 0.1e-6))
        res.append({"case": "CM injection via 100 pF into LISN pair", "f_hz": f, "mna_dB": 20 * np.log10(abs(mine)),
                    "closed_form_dB": 20 * np.log10(abs(ref)), "delta_dB": 20 * np.log10(abs(mine)) - 20 * np.log10(abs(ref))})
    return res


def control_sources():
    """Validate the analytic full-bridge source against D-22's ngspice FFT of the actual device-level run
    (170 V, 35 kHz, R=2): fit tank (Ipk, phi) from bus-current harmonics 0/4..20, compare the rest and v_swa."""
    from scipy.optimize import least_squares
    with np.load(D22 / "v170-r2-e1.06-f35000-s0.5-c24-full-fft.npz") as d:
        isim = np.abs(d["bus_current_A"][:22:2])
        vsim = np.abs(d["v(swa)"][1:600:2])
        fr = d["frequency_Hz"]
    ks = np.arange(0, 11)

    def mod(x):
        a = np.abs(i_bus(2 * ks, x[0], x[1], 0.0))
        a[0] = 2 * x[0] * np.cos(x[1]) / np.pi
        return a

    idx = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    fit = least_squares(lambda x: np.log(mod(x)[idx] / isim[idx]), [30.0, 1.0])
    ipk, phi = fit.x
    err = 20 * np.log10(mod(fit.x) / isim)
    # sw-node: D-19 edge 170 V 37 A ZVS row: rise 26.84 ns (10-90) -> 33.5 ns full, fall 19.48 -> 24.35 ns
    n = np.arange(1, 600, 2)
    va = np.abs(v_leg(n, 35e3, 170.0, 26.84e-9 / 0.8, 19.48e-9 / 0.8, "A"))
    dv = 20 * np.log10(va / vsim)
    low = n <= 51
    return {"fit_Ipk_A": float(ipk), "fit_phi_deg": float(np.degrees(phi)),
            "bus_current_model_minus_sim_dB_by_harmonic_0_to_20_even": [round(float(x), 2) for x in err],
            "v_swa_model_minus_sim_dB_n1_to_51_odd": [round(float(x), 2) for x in dv[low]],
            "v_swa_model_minus_sim_dB_median_n53_to_599": float(np.median(dv[~low])),
            "v_swa_model_minus_sim_dB_max_abs_n_le_101": float(np.max(np.abs(dv[n <= 101])))}


# ----------------------------------------------------------------------------------------------
# 5b. stage-19b inputs
# ----------------------------------------------------------------------------------------------


def edge_scale_table():
    """D-19 edge census (out-D19/edge-table.md), 37 A ZVS rows, ESL 1.06 nH: 10-90 times in ns."""
    return {170: {"rise_1090_ns": 26.84, "fall_1090_ns": 19.48}, 198: {"rise_1090_ns": 23.96, "fall_1090_ns": 18.58}}


def pour_inputs():
    """Switch-node copper geometry from the s19b copper dump + 2-D Laplace fringe to the PE pedestal."""
    src = COPPER if COPPER.exists() else None
    summary = None
    if src is not None:
        d = json.load(open(src))

        def area(p):
            a = np.array(p)
            x, y = a[:, 0], a[:, 1]
            return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

        def edge_len(pts, ymax=0.8, x0=-8.0, x1=109.0):
            a = np.array(pts)
            tot = 0.0
            for p, q in zip(a, np.roll(a, -1, axis=0)):
                if p[1] <= ymax and q[1] <= ymax:
                    lo, hi = sorted((p[0], q[0]))
                    tot += max(0.0, min(hi, x1) - max(lo, x0))
            return tot

        summary = {}
        for net in ("sw_a", "sw_b"):
            rows = []
            for z in d["zones"]:
                if z["net"] == net:
                    rows.append({"layer": z["layer"], "area_mm2": area(z["pts"]), "edge_mm_facing_sink": edge_len(z["pts"])})
            summary[net] = rows
        summary["board_sha256"] = "b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662"
        (HERE / "inputs").mkdir(exist_ok=True)
        (HERE / "inputs/copper-dump-s19b-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    else:
        summary = json.load(open(COPPER_FALLBACK))
    return summary


def fringe_cap_per_mm(z_pour_mm, h=0.5):
    """2-D Laplace (scipy sparse) y-z cross-section.  Pour sheet (y>=0.6, z=z_pour) at 1 V, PE pedestal
    (y in [-8,-0.2], z in [8,48]) and the outer box at 0 V.  Returns capacitance pour->pedestal per mm length (F/mm)."""
    from scipy.sparse import lil_matrix
    from scipy.sparse.linalg import spsolve
    y0, y1, z0, z1 = -40.0, 70.0, -30.0, 60.0
    ny, nz = int((y1 - y0) / h) + 1, int((z1 - z0) / h) + 1
    Y = y0 + h * np.arange(ny)
    Z = z0 + h * np.arange(nz)
    fixed = np.full((ny, nz), np.nan)
    fixed[0, :] = fixed[-1, :] = fixed[:, 0] = fixed[:, -1] = 0.0
    ped = (Y[:, None] >= -8.0 - 1e-9) & (Y[:, None] <= -0.2 + 1e-9) & (Z[None, :] >= 8.0 - 1e-9) & (Z[None, :] <= 48.0)
    fixed[ped] = 0.0
    iz = int(round((z_pour_mm - z0) / h))
    fixed[(Y >= 0.6 - 1e-9), iz] = 1.0
    idx = -np.ones((ny, nz), int)
    free = np.isnan(fixed)
    idx[free] = np.arange(free.sum())
    A = lil_matrix((free.sum(), free.sum()))
    b = np.zeros(free.sum())
    for i in range(1, ny - 1):
        for j in range(1, nz - 1):
            k = idx[i, j]
            if k < 0:
                continue
            A[k, k] = 4.0
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                m = idx[i + di, j + dj]
                if m >= 0:
                    A[k, m] = -1.0
                else:
                    b[k] += fixed[i + di, j + dj]
    sol = spsolve(A.tocsr(), b)
    V = np.where(free, 0.0, fixed)
    V[free] = sol
    # charge on the pedestal = sum over links from pedestal cells to non-pedestal neighbours of V_nb
    q = 0.0
    for i in range(1, ny - 1):
        for j in range(1, nz - 1):
            if ped[i, j]:
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if not ped[i + di, j + dj]:
                        q += V[i + di, j + dj]
    return EPS0 * q * 1e-3  # F per mm of length (links have conductance eps0 per unit depth; 1 mm depth)


def cm_capacitances():
    """Stage-19b switch-node -> PE capacitances, with sources."""
    geo = pour_inputs()
    tab_area = (151.2e-6, 240.1e-6)  # TO-247 exposed metal, m^2 (stack-calc.py [T03])
    er_aln, t_aln = 8.6, 2.0e-3
    # compound 2 x 0.03 mm, er ~ 4 (Electrolube HTCP20S class, assumed) in series with the AlN
    def c_tab(a):
        c_al = EPS0 * er_aln * a / t_aln
        c_gr = EPS0 * 4.0 * a / 0.06e-3
        return 1 / (1 / c_al + 1 / c_gr)

    lo, hi = c_tab(tab_area[0]), c_tab(tab_area[1])
    fr_f = fringe_cap_per_mm(0.0) if not QUICK else 3.2e-15
    fr_b = fringe_cap_per_mm(-1.6) if not QUICK else 1.5e-15

    def pour_fringe(net):
        tot = 0.0
        for r in geo[net]:
            tot += r["edge_mm_facing_sink"] * (fr_f if r["layer"] == "F.Cu" else fr_b)
        return tot

    def pour_area(net):
        return sum(r["area_mm2"] for r in geo[net]) * 1e-6

    return {"tab_C_range_F": [lo, hi], "tab_C_nominal_F": 0.5 * (lo + hi),
            "fringe_sw_a_F": pour_fringe("sw_a"), "fringe_sw_b_F": pour_fringe("sw_b"),
            "pour_area_m2": {"sw_a": pour_area("sw_a"), "sw_b": pour_area("sw_b")},
            "fringe_per_mm_F": {"F.Cu": fr_f, "B.Cu": fr_b}, "geometry": geo}


# ----------------------------------------------------------------------------------------------
# 5c. stage-19b run
# ----------------------------------------------------------------------------------------------

MODULE_NOM = dict(LNEW=41e-6, LDMADD=18e-6)  # DM total = 18 + 2*41 = 100 uH (DECISIONS "EMI below 150 kHz" item 4)
# Stage 38 (candidate 23, DECISIONS 47 items 4 / 5): the D-22 inlet module's four Y caps are removed and its CM choke is
# the KEMET SCF31X-220-2R1A011JH (5.68 mH, 4.39 mOhm; spec sheet generated 2026-10-15). Its DM leakage is unpublished:
# 1 % (56.8 uH) as the co-design study (leakage/co-design-2026-10-15/candidates.py CHOKES["NC5.68"]); the winding C /
# loss stay the TDK fit's (the study's convention). Board L1 stays the TDK B82726S2203A020 and C3 / C4 stay 2.2 nF.
# The module's 2 x 41 uH DM inductors are unchanged. 1e-15 F = a removed capacitor (the s19b / g01 convention).
MODULE_S38 = dict(CYADD=1e-15, CYHF=1e-15, LCMADD=5.68e-3, LDMADD=56.8e-6, RCMADD=4.39e-3)


def nominal_params(cm):
    c = cm["tab_C_nominal_F"]
    d_enc = 15e-3  # nominal enclosure/chassis distance to the large pours (ASSUMED; no enclosure-metal data)
    return {**MODULE_NOM, **MODULE_S38, "COIL_AT_TANK": True, "ESLY": 15e-9, "RLISN_SERIES": 5.0,
            "CTABA": c, "CTABB": c, "CTABH": c,
            "CPOURA": cm["fringe_sw_a_F"] + EPS0 * cm["pour_area_m2"]["sw_a"] / d_enc,
            "CPOURB": cm["fringe_sw_b_F"] + EPS0 * cm["pour_area_m2"]["sw_b"] / d_enc}


def scenarios(cm, nom):
    lo, hi = cm["tab_C_range_F"]
    # Stage 38: the part-value sensitivities are relative to the nominal parts (Y -20 %, chokes -30 %, winding C x2, DM
    # L x31/41, X -20 %), as the co-design study applies them (emi_core.sens_set); for the pre-stage-38 nominal they are
    # exactly the absolute values used before (1.76 / 3.76 / 1.76 nF, 1.12 mH, 22.156 pF, 31 uH, 0.8 / 1.76 / 3.76 uF).
    P = {**BASE, **nom}
    ca = nom["CTABA"]
    enc = lambda d: (cm["fringe_sw_a_F"] + EPS0 * cm["pour_area_m2"]["sw_a"] / d,
                     cm["fringe_sw_b_F"] + EPS0 * cm["pour_area_m2"]["sw_b"] / d)
    s = {"nominal": ({}, {})}
    s["tabs_mismatch_AlN_range"] = ({"CTABA": hi, "CTABB": lo}, {})
    s["tabs_mismatch_reversed"] = ({"CTABA": lo, "CTABB": hi}, {})
    s["insulator_swap_thin_pad_42pF"] = ({"CTABA": 50.4e-12, "CTABB": 33.6e-12, "CTABH": 42e-12}, {})
    pa, pb = enc(5e-3)
    s["enclosure_metal_5mm"] = ({"CPOURA": pa, "CPOURB": pb}, {})
    pa, pb = enc(1e9)
    s["no_enclosure_coupling"] = ({"CPOURA": pa, "CPOURB": pb}, {})
    s["coil_caps_at_sw_nodes_(D-22 convention)"] = ({"COIL_AT_TANK": False}, {})
    # study 16 range (pan floating 28.5-35.1 pF) and +20 pF upper bound for board copper modelled as air
    s["coil_PE_study16_low_28p5pF"] = ({"CCOILA": 14.4e-12, "CCOILB": 14.1e-12}, {})
    s["coil_PE_study16_high_35p1pF"] = ({"CCOILA": 17.8e-12, "CCOILB": 17.3e-12}, {})
    s["coil_PE_study16_plus_board_51pF"] = ({"CCOILA": 25.7e-12, "CCOILB": 25.3e-12}, {})
    # informational (not a compliance test configuration): pan earthed through a user, 91.4 pF (88.5-102)
    s["INFO_pan_earthed_91pF"] = ({"CCOILA": 46.2e-12, "CCOILB": 45.2e-12}, {})
    s["INFO_pan_earthed_102pF"] = ({"CCOILA": 51.6e-12, "CCOILB": 50.4e-12}, {})
    s["INFO_assumed_10pF_total"] = ({"CCOILA": 5e-12, "CCOILB": 5e-12}, {})
    s["INFO_assumed_100pF_total"] = ({"CCOILA": 50e-12, "CCOILB": 50e-12}, {})
    s["INFO_assumed_100pF_asym_70_30"] = ({"CCOILA": 70e-12, "CCOILB": 30e-12}, {})
    s["coil_PE_100pF_one_sided_100_0"] = ({"CCOILA": 100e-12, "CCOILB": 0.0}, {})
    s["thin_pad_and_coil_100pF_asym_70_30"] = ({"CTABA": 50.4e-12, "CTABB": 33.6e-12, "CTABH": 42e-12,
                                                "CCOILA": 70e-12, "CCOILB": 30e-12}, {})
    s["Y_caps_minus20pct"] = ({"CY": P["CY"] * 0.8, "CYADD": P["CYADD"] * 0.8, "CYHF": P["CYHF"] * 0.8}, {})
    s["Y_caps_ESL_x3"] = ({"ESLY": 45e-9, "ESLYADD": 45e-9, "ESLYHF": 30e-9}, {})
    s["Y_caps_board_only_module_Y_removed"] = ({"CYADD": 1e-15, "CYHF": 1e-15}, {})   # = the nominal since stage 38
    s["L1_minus30pct_and_module_choke_minus30pct"] = ({"LCM": P["LCM"] * 0.7, "LCMADD": P["LCMADD"] * 0.7}, {})
    s["L1_winding_C_x2"] = ({"CCH": P["CCH"] * 2, "CCMADD": P["CCMADD"] * 2}, {})
    s["module_DM_80uH"] = ({"LNEW": P["LNEW"] * 31 / 41}, {})
    s["module_DM_18uH_only (D-22 as specified)"] = ({"LNEW": 0}, {})
    s["module_DM_L_parasitic_C_100pF"] = ({"CPNEW": 100e-12}, {})
    s["X_caps_minus20pct"] = ({"CX": P["CX"] * 0.8, "CXIN": P["CXIN"] * 0.8, "CXNEW": P["CXNEW"] * 0.8,
                               "CDAMP": P["CDAMP"] * 0.8}, {})
    s["PE_bond_200nH"] = ({"LPE": 200e-9}, {})
    s["board_only_no_module"] = ({"_module": False}, {})
    s["edge_B_x1.2"] = ({}, {"edge_b": 1.2})
    s["edge_x0.5_slower"] = ({}, {"edge": 2.0})
    s["edge_x2_faster"] = ({}, {"edge": 0.5})
    s["edge_x4_faster_and_B_x1.2_thin_pad_coil_asym"] = ({"CTABA": 50.4e-12, "CTABB": 33.6e-12, "CTABH": 42e-12,
                                                          "CCOILA": 70e-12, "CCOILB": 30e-12}, {"edge": 0.25, "edge_b": 1.2})
    bad = {"CCOILA": 70e-12, "CCOILB": 30e-12}
    # REC* and STACKED below are pre-stage-38 alternative-design / stacked points with absolute part values (REC2 is a
    # 3.2 mH module choke, below the stage-38 5.68 mH; STACKED re-adds module Y); excluded from the verdict, information only
    s["REC1_bus_Y_2.2nF_bus_p_and_bus_n"] = ({"CBUSPE_X": 2.2e-9, "CBUSN_X": 2.2e-9}, {})
    s["REC2_module_CM_choke_x2 (3.2 mH)"] = ({"LCMADD": 3.2e-3, "LDMADD": 36e-6, "LNEW": 32e-6}, {})
    s["REC3_coil_shield_75pct_to_bus_n"] = ({"COIL_SHIELD_FRAC": 0.75}, {})
    s["REC4_REC1+REC3"] = ({"CBUSPE_X": 2.2e-9, "CBUSN_X": 2.2e-9, "COIL_SHIELD_FRAC": 0.75}, {})
    s["REC1_with_coil_100pF_asym_70_30"] = ({"CBUSPE_X": 2.2e-9, "CBUSN_X": 2.2e-9, **bad}, {})
    s["REC2_with_coil_100pF_asym_70_30"] = ({"LCMADD": 3.2e-3, "LDMADD": 36e-6, "LNEW": 32e-6, **bad}, {})
    s["REC4_with_coil_100pF_asym_70_30"] = ({"CBUSPE_X": 2.2e-9, "CBUSN_X": 2.2e-9, "COIL_SHIELD_FRAC": 0.75, **bad}, {})
    s["REC1_with_coil_100pF_one_sided"] = ({"CBUSPE_X": 2.2e-9, "CBUSN_X": 2.2e-9, "CCOILA": 100e-12, "CCOILB": 0.0}, {})
    s["STACKED_informational"] = ({"CTABA": 50.4e-12, "CTABB": 33.6e-12, "CTABH": 42e-12, "CCOILA": 70e-12,
                                   "CCOILB": 30e-12, "CY": 1.76e-9, "CYADD": 3.76e-9, "CYHF": 1.76e-9, "LCM": 1.12e-3,
                                   "LCMADD": 1.12e-3, "LNEW": 31e-6, "CX": 0.8e-6, "CXIN": 1.76e-6, "CXNEW": 3.76e-6,
                                   "CDAMP": 3.76e-6, "LPE": 200e-9, "ESLY": 45e-9}, {"edge": 0.5, "edge_b": 1.2})
    return s


def source_spectra(fs, h, vc, case, edge_scale=1.0, edge_b=1.0):
    """Phasors (v_A, v_B, i_bus) at harmonics h of fs for a source case at the line crest."""
    et = edge_scale_table()
    row = et[198 if vc > 185 else 170]
    isw_ref = 37.0
    isw = case["ipk"] * np.sin(case["phi"])
    k = np.clip(isw / isw_ref, 0.25, 4.0)  # dv/dt proportional to the switched (commutating) current in ZVS
    tr = row["rise_1090_ns"] * 1e-9 / 0.8 / k * edge_scale
    tf = row["fall_1090_ns"] * 1e-9 / 0.8 / k * edge_scale
    va = v_leg(h, fs, vc, tr, tf, "A")
    vb = v_leg(h, fs, vc, tr * edge_b, tf * edge_b, "B")
    ib = i_bus(h, case["ipk"], case["phi"], 0.5 * (tr + tf))
    return va, vb, ib, tr, tf


CASES = {  # tank current at the LINE CREST; peak = 2.17 x line RMS (firmware TANK_PEAK_PER_RMS)
    "pan_22A": dict(irms=22.0, phi=np.radians(50.0), note="22 A default ceiling, pan present (ZVS lag >= 45-50 deg)"),
    "pan_28A": dict(irms=28.0, phi=np.radians(50.0), note="28 A commissioned ceiling, pan present"),
    "nopan_22A": dict(irms=22.0, phi=np.radians(88.0), note="no-pan clamp 22 A, lag ~88 deg (empty coil, Q 50-100)"),
    "nopan_28A": dict(irms=28.0, phi=np.radians(88.0), note="no-pan with failed clamp (fault; informational)"),
}
for c in CASES.values():
    c["ipk"] = 2.17 * c["irms"]


L_MIN_LOADED = {"pan": 0.58 * 70e-6, "nopan": 66.5e-6}  # coil_mc.rs low_R_silargan_like kl min 0.58; round-6 installed 66.5 uH


def case_at(vc, case, fs, c_res=0.54e-6):
    """Tank peak current actually reachable at this fs: min(ceiling-derived peak, V1 sin(phi) / X_min(fs)),
    X_min = w L_min - 1/(w C): the controller sits at the lowest f that holds the limits, so high fs carries less current."""
    w = 2 * np.pi * fs
    lmin = L_MIN_LOADED["nopan" if case["phi"] > np.radians(80) else "pan"]
    xmin = max(w * lmin - 1 / (w * c_res), 0.5)
    ipk = min(case["ipk"], 4 / np.pi * vc * np.sin(case["phi"]) / xmin)
    return {**case, "ipk": ipk}


def tank_for(vc, case, fs, c_res=0.54e-6):
    """Series tank consistent with the source case: |Z| = (4/pi) Vc / Ipk, X = Z sin(phi), R = Z cos(phi);
    resonant bank fixed at 0.54 uF (hardware), coil L solved per fs (loaded-coil L is not fixed by data)."""
    z = 4 / np.pi * vc / case["ipk"]
    x, r = z * np.sin(case["phi"]), z * np.cos(case["phi"])
    w = 2 * np.pi * fs
    return {"RPAN": max(r, 0.02), "CRES": c_res, "LCOIL": (1 / (w * c_res) + x) / w}


def aggregate(tr_by_fs, p_unused, vc, case, fs_list, edge_scale=1.0, edge_b=1.0):
    """For each fs: terminal/CM/DM levels at every harmonic; returns arrays and worst-margin summary."""
    rows = []
    for fs in fs_list:
        tr = tr_by_fs[fs]
        h = tr["h"]
        f = h * fs
        va, vb, ib, *_ = source_spectra(fs, h, vc, case_at(vc, case, fs), edge_scale, edge_b)
        vl = tr["A"]["l_pe"] * va + tr["B"]["l_pe"] * vb + tr["DM"]["l_pe"] * ib
        vn = tr["A"]["n_pe"] * va + tr["B"]["n_pe"] * vb + tr["DM"]["n_pe"] * ib
        lv = levels(vl, vn)
        # DM-only (bus current) and CM-only (switch node) contributions for attribution
        lv_sw = levels(tr["A"]["l_pe"] * va + tr["B"]["l_pe"] * vb, tr["A"]["n_pe"] * va + tr["B"]["n_pe"] * vb)
        lv_bus = levels(tr["DM"]["l_pe"] * ib, tr["DM"]["n_pe"] * ib)
        qp, av, reg = limits(f)
        rows.append(dict(fs=fs, f=f, lv=lv, lv_sw=lv_sw, lv_bus=lv_bus, qp=qp, av=av, reg=reg))
    return rows


def worst(rows, mode="terminal", band="all"):
    """band: "all" | "hi" (>=150 kHz) | "lo" (<150 kHz) | (f_lo, f_hi) tuple in Hz (lo inclusive, hi exclusive)."""
    best = None
    for r in rows:
        f, lv = r["f"], r["lv"][mode]
        m_qp = r["qp"] - lv
        m_av = np.where(np.isnan(r["av"]), np.inf, r["av"] - lv)
        sel = r["reg"].copy()
        if band == "hi":
            sel &= f >= 150e3
        elif band == "lo":
            sel &= f < 150e3
        elif isinstance(band, tuple):
            sel &= (f >= band[0]) & (f < band[1])
        if not sel.any():
            continue
        mm = np.minimum(m_qp, m_av)  # AV binds above 150 kHz (it is 10 dB tighter), QP below
        i = np.flatnonzero(sel)[np.argmin(mm[sel])]
        cand = dict(margin_dB=float(mm[i]), QP_margin_dB=float(m_qp[i]),
                    AV_margin_dB=(float(m_av[i]) if np.isfinite(m_av[i]) else None),
                    f_hz=float(f[i]), fs_hz=float(r["fs"]), harmonic=int(round(f[i] / r["fs"])),
                    level_dBuV=float(lv[i]), limit_QP_dBuV=float(r["qp"][i]),
                    CM_dBuV=float(r["lv"]["CM"][i]), DM_dBuV=float(r["lv"]["DM"][i]),
                    sw_node_only_terminal_dBuV=float(r["lv_sw"]["terminal"][i]),
                    bus_current_only_terminal_dBuV=float(r["lv_bus"]["terminal"][i]))
        if best is None or cand["margin_dB"] < best["margin_dB"]:
            best = cand
    return best


BANDS = {"b_9k_150k_QP": (9e3, 150e3), "b_150k_500k": (150e3, 500e3), "b_0p5M_5M": (500e3, 5e6),
         "b_5M_30M": (5e6, 30.0001e6)}


def main():
    out = {"script": "emi_s19b.py", "quick": QUICK}
    # ---------------- controls ----------------
    c_d22 = control_d22(out)
    c_r3 = control_round3()
    c_cf = control_closed_form()
    c_src = control_sources()
    parity = max(r["max_rel_err_vs_ngspice"] for r in c_d22["transfer_parity"])
    d22_delta = max(abs(r["delta_dB"]) for r in c_d22["margins"])
    r3_delta = max(abs(r["delta_dB"]) for r in c_r3 if r["scenario"] != "balanced")  # balanced = ~-150 dBuV cancellation floor (numerical noise), excluded
    cf_delta = max(abs(r["delta_dB"]) for r in c_cf)
    out["controls"] = {"D22_native15": c_d22, "round3_native15_assumed_peaks": c_r3, "closed_form": c_cf,
                       "analytic_source_vs_D22_fft": c_src,
                       "asserts": {"D22_margin_repro_max_abs_delta_dB": d22_delta, "limit_dB": 1.0,
                                   "round3_peak_repro_max_abs_delta_dB": r3_delta,
                                   "closed_form_max_abs_delta_dB": cf_delta, "closed_form_limit_dB": 0.5,
                                   "transfer_parity_max_rel_err": parity}}
    assert d22_delta < 1.0, f"D-22 headline reproduction off by {d22_delta} dB"
    assert r3_delta < 1.0, f"round-3 peak lines off by {r3_delta} dB"
    assert cf_delta < 0.5, f"closed-form check off by {cf_delta} dB"
    print(f"controls OK: D-22 delta {d22_delta:.4f} dB, round-3 delta {r3_delta:.4f} dB, "
          f"closed-form {cf_delta:.2e} dB, transfer parity {parity:.2e}")

    # ---------------- stage-19b model ----------------
    cm = cm_capacitances()
    nom = nominal_params(cm)
    out["inputs"] = {"cm": {k: v for k, v in cm.items() if k != "geometry"}, "geometry_summary": cm["geometry"],
                     "nominal_params": nom, "cases": {k: {"irms": v["irms"], "ipk_A": v["ipk"], "phi_deg": float(np.degrees(v["phi"])),
                                                         "note": v["note"]} for k, v in CASES.items()},
                     "edge_table_D19_37A": edge_scale_table()}
    fs_nom = list(np.arange(35000, 60001, 500.0 if not QUICK else 5000.0))
    fs_sens = list(np.arange(35000, 60001, 1000.0 if not QUICK else 5000.0))
    scen = scenarios(cm, nom)
    ALL_CFG = [(vc, cn) for vc in (170.0, 198.0) for cn in CASES]
    REP_CFG = [(170.0, "pan_22A"), (198.0, "pan_28A"), (198.0, "nopan_22A")]
    results = {}
    for sname, (pov, sov) in scen.items():
        pov = dict(pov)
        module = pov.pop("_module", True)
        params = {**nom, **pov}
        cfgs = ALL_CFG if sname == "nominal" else REP_CFG
        fs_list = fs_nom if sname == "nominal" else fs_sens
        trs = {}
        for cfg in cfgs:
            vc, cn = cfg
            trs[cfg] = {}
            for fs in fs_list:
                h = np.arange(1, int(30e6 / fs) + 1)
                t = transfers({**params, **tank_for(vc, case_at(vc, CASES[cn], fs), fs)}, module, h * fs)
                t["h"] = h
                trs[cfg][fs] = t
        results[sname] = {"trs": trs, "fs": fs_list, "ov": sov, "cfgs": cfgs}
        print("solved", sname, flush=True)

    table = {}
    rows_keep = {}
    for sname, rr in results.items():
        table[sname] = {}
        for (vc, cname) in rr["cfgs"]:
            rows = aggregate(rr["trs"][(vc, cname)], None, vc, CASES[cname], rr["fs"], rr["ov"].get("edge", 1.0), rr["ov"].get("edge_b", 1.0))
            key = f"{int(vc)}V/{cname}"
            table[sname][key] = {"hi_150k_30M": worst(rows, "terminal", "hi"), "lo_9k_150k": worst(rows, "terminal", "lo"),
                                 "CM_hi": worst(rows, "CM", "hi"), "DM_hi": worst(rows, "DM", "hi"),
                                 "CM_lo": worst(rows, "CM", "lo"), "DM_lo": worst(rows, "DM", "lo"),
                                 **{b: worst(rows, "terminal", rng) for b, rng in BANDS.items()}}
            if sname == "nominal":
                rows_keep[key] = rows
    out["scenarios"] = table

    # ---------------- aux supplies: at-limit bound through the filter ----------------
    aux_p = {**nom}
    aux = {}
    f_aux = np.geomspace(150e3, 30e6, 400)
    ta = transfers(aux_p, True, f_aux, aux=True)
    qp, avl, reg = limits(f_aux)
    for nm, key in (("DM_injection", "AUXDM"), ("CM_injection", "AUXCM")):
        # Transfer from an injected rms current (A) to the worse LISN terminal voltage (V): Z [dB ohm].
        # A module that just meets the AV limit L [dBuV] into a bare 50 ohm LISN injects I = L - 34 dBuA.
        zdb = 20 * np.log10(np.maximum(np.abs(ta[key]["l_pe"]), np.abs(ta[key]["n_pe"])))
        margin = 34.0 - zdb  # = L - (Z + L - 34)
        i = np.flatnonzero(reg)[np.argmin(margin[reg])]
        # stage 38: two mains modules on the filtered side (PS2 on the board, PS3 via J11; PS1 deleted), incoherent ->
        # +10log10(2) dB worst case
        aux[nm] = {"margin_per_module_dB": float(margin[i]), "n_modules": 2,
                   "margin_modules_incoherent_dB": float(margin[i] - 10 * np.log10(2)), "at_hz": float(f_aux[i])}
    out["aux_supplies_at_limit_bound"] = aux

    # ---------------- verdict ----------------
    crit = {"pass_margin_dB": 6.0, "fail_margin_dB": 0.0}
    nomrows = table["nominal"]
    def minm(sc, keys, band):
        vals = [table[sc][k][band]["margin_dB"] for k in keys if k in table[sc] and table[sc][k][band]]
        return min(vals)
    pan_keys = [k for k in nomrows if "pan_" in k and "nopan" not in k]
    all_keys = [k for k in nomrows if "nopan_28A" not in k]  # (the table has REP_CFG keys for sensitivities)  # failed-clamp fault excluded from the criterion
    nominal_min = min(minm("nominal", all_keys, "hi_150k_30M"), minm("nominal", all_keys, "lo_9k_150k"))
    sens_names = [s for s in table if s != "nominal" and not s.startswith(("module_DM_18uH", "board_only", "Y_caps_board_only", "STACKED", "REC", "thin_pad_and", "insulator_swap", "edge_x4", "coil_PE_100pF_one_sided", "INFO_"))]  # excluded: alternative designs / stacked or beyond-spec corners (reported, informational)
    sens_min_22 = min(min(minm(s, [k for k in all_keys if k.endswith("22A")], "hi_150k_30M"),
                          minm(s, [k for k in all_keys if k.endswith("22A")], "lo_9k_150k")) for s in sens_names)
    sens_min_all = min(min(minm(s, all_keys, "hi_150k_30M"), minm(s, all_keys, "lo_9k_150k")) for s in sens_names)
    controls_ok = True
    if nominal_min >= crit["pass_margin_dB"] and sens_min_all >= crit["pass_margin_dB"]:
        verdict = "PASS"
    elif nominal_min < crit["fail_margin_dB"] or sens_min_22 < crit["fail_margin_dB"]:
        verdict = "FAIL"
    else:
        verdict = "INCONCLUSIVE"
    out["verdict"] = {"criterion": "PASS if min predicted margin (AV 150k-30M, QP 9k-150k, CW-equivalent at line crest) >= 6 dB in the "
                      "nominal case and every one-at-a-time sensitivity at 22 A and 28 A (pan and no-pan clamp), 170 and 198 V crest; "
                      "FAIL if nominal < 0 dB or any 22 A sensitivity < 0 dB; otherwise INCONCLUSIVE.",
                      "excluded_from_sensitivity_set": "alternative designs (D-22 18 uH module, board-only, module Y removed, thin-pad insulator), "
                      "stacked/beyond-spec corners (coil capacitance one-sided 100:0, stacked, edge x4 + coil asym + thin pad), the nopan_28A fault case, "
                      "and the REC* recommendation scenarios; all are still reported in results.json",
                      "nominal_min_margin_dB": nominal_min, "sensitivity_min_margin_22A_dB": sens_min_22,
                      "sensitivity_min_margin_all_dB": sens_min_all, "verdict": verdict, "controls_ok": controls_ok}
    print(json.dumps(out["verdict"], indent=1))
    # ---------------- stripped spectra for plots/CSV ----------------
    plot_data = {}
    for key, rows in rows_keep.items():
        f = np.concatenate([r["f"] for r in rows])
        lv = np.concatenate([r["lv"]["terminal"] for r in rows])
        cmv = np.concatenate([r["lv"]["CM"] for r in rows])
        dmv = np.concatenate([r["lv"]["DM"] for r in rows])
        qp = np.concatenate([r["qp"] for r in rows])
        av = np.concatenate([r["av"] for r in rows])
        reg = np.concatenate([r["reg"] for r in rows])
        o = np.argsort(f)
        plot_data[key] = dict(f=f[o], terminal=lv[o], CM=cmv[o], DM=dmv[o], qp=qp[o], av=av[o], reg=reg[o])
    fsm = {}
    for key in ("198V/pan_28A", "170V/pan_22A"):
        rows = rows_keep[key]
        fsm[key] = {"fs": [float(r["fs"]) for r in rows],
                    "hi": [float(np.min(np.where(r["reg"] & (r["f"] >= 150e3), np.minimum(r["qp"] - r["lv"]["terminal"], r["av"] - r["lv"]["terminal"]), np.inf))) for r in rows],
                    "lo": [float(np.min(np.where(r["reg"] & (r["f"] < 150e3), r["qp"] - r["lv"]["terminal"], np.inf))) for r in rows]}
    out["nominal_margin_vs_fs"] = fsm
    bp = {}
    for key in ("170V/pan_22A", "198V/pan_28A", "198V/nopan_22A"):
        bp[key] = {}
        for r in rows_keep[key]:
            if r["fs"] in (35000.0, 40000.0, 45000.0, 50000.0, 55000.0, 60000.0):
                sel = np.flatnonzero(r["f"] <= 510e3)
                bp[key][f"{r['fs'] / 1e3:.0f}kHz"] = [
                    {"n": int(round(r["f"][i] / r["fs"])), "f_hz": float(r["f"][i]), "terminal_dBuV": round(float(r["lv"]["terminal"][i]), 1),
                     "CM_dBuV": round(float(r["lv"]["CM"][i]), 1), "DM_dBuV": round(float(r["lv"]["DM"][i]), 1),
                     "QP_limit_dBuV": round(float(r["qp"][i]), 1), "AV_limit_dBuV": (None if np.isnan(r["av"][i]) else round(float(r["av"][i]), 1))}
                    for i in sel if r["lv"]["terminal"][i] > -10]
    out["bench_predictions_nominal"] = bp
    fgrid = np.geomspace(10e3, 1e6, 400)
    tg = transfers({**nom, **tank_for(198.0, case_at(198.0, CASES["pan_28A"], 45e3), 45e3)}, True, fgrid)
    gain = {"f": fgrid, "CM_gain_dB": 20 * np.log10(np.abs((tg["A"]["l_pe"] + tg["B"]["l_pe"]) / 2 * 2) + 1e-30),
            "DM_gain_dB": 20 * np.log10(np.abs(tg["DM"]["l_pe"]) + 1e-30)}
    out["cm_dm_gain_note"] = "CM_gain: |V_lisn_L| per 1 V applied to BOTH switch nodes in phase (V/V); DM_gain: |V_lisn_L| per 1 A bus current (V/A); nominal network, 45 kHz tank"
    out["cm_dm_gain_peak_CM"] = {"f_hz_at_max_below_300k": float(fgrid[np.argmax(np.where(fgrid < 300e3, gain["CM_gain_dB"], -1e9))])}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=lambda o: float(o) if isinstance(o, np.floating) else str(o)) + "\n")
    if "--no-plots" not in sys.argv:
        plots(plot_data, table, out, gain)
    print("wrote", HERE / "results.json")


def plots(pd, table, out, gain):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2))
    for key, d in out["nominal_margin_vs_fs"].items():
        axs[0].plot(np.array(d["fs"]) / 1e3, d["hi"], label=f"{key} 150 kHz-30 MHz (AV)")
        axs[0].plot(np.array(d["fs"]) / 1e3, d["lo"], "--", label=f"{key} 9-150 kHz (QP)")
    axs[0].axhline(6, color="k", lw=0.8)
    axs[0].set_xlabel("switching frequency (kHz)")
    axs[0].set_ylabel("worst margin (dB)")
    axs[0].set_ylim(0, 40)
    axs[0].legend(fontsize=7)
    axs[0].grid(alpha=0.3)
    axs[0].set_title("nominal: worst margin vs fs (frequency loop 35-60 kHz)")
    axs[1].semilogx(gain["f"] / 1e3, gain["CM_gain_dB"], label="CM: switch nodes in phase -> LISN L (V/V)")
    axs[1].semilogx(gain["f"] / 1e3, gain["DM_gain_dB"], label="DM: bus current -> LISN L (V/A)")
    axs[1].set_xlabel("kHz")
    axs[1].set_ylabel("dB")
    axs[1].legend(fontsize=7)
    axs[1].grid(True, which="both", alpha=0.3)
    axs[1].set_title("nominal filter transfer (45 kHz tank)")
    fig.tight_layout()
    fig.savefig(HERE / "margin_vs_fs_and_transfer.png", dpi=130)
    plt.close(fig)
    for key in ("170V/pan_22A", "198V/pan_28A", "198V/nopan_22A"):
        if key not in pd:
            continue
        d = pd[key]
        fig, ax = plt.subplots(figsize=(11, 5.5))
        m = d["reg"]
        ax.semilogx(d["f"][m] / 1e6, d["terminal"][m], ".", ms=2.0, color="C0", label="predicted worst-terminal line (CW-equiv. rms), all fs 35-60 kHz")
        ax.semilogx(d["f"][m] / 1e6, d["CM"][m], ".", ms=1.2, color="C2", alpha=0.5, label="CM")
        ax.semilogx(d["f"][m] / 1e6, d["DM"][m], ".", ms=1.2, color="C1", alpha=0.5, label="DM")
        f = np.geomspace(9e3, 30e6, 800)
        qp, av, reg = limits(f)
        ax.semilogx(f / 1e6, np.where(reg, qp, np.nan), "r-", lw=1.3, label="47 CFR 18.307(a) QP")
        ax.semilogx(f / 1e6, np.where(reg, av, np.nan), "r--", lw=1.3, label="AV")
        ax.set_xlabel("frequency (MHz)")
        ax.set_ylabel("dBuV")
        ax.set_ylim(-60, 120)
        ax.grid(True, which="both", alpha=0.25)
        ax.set_title(f"Stage 19b, {key}: model spectrum vs limits (not a measurement)")
        ax.legend(fontsize=7, loc="upper right")
        fig.tight_layout()
        fig.savefig(HERE / ("spectrum_" + key.replace("/", "_") + ".png"), dpi=130)
        plt.close(fig)


if __name__ == "__main__":
    main()
