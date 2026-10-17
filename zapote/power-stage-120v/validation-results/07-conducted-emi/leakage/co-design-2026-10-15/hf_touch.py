#!/usr/bin/env python3 -I
"""Estimate (outside the committed leakage model): switching-frequency touch current in the open-PE test.

The committed leakage budget charges only 60 Hz capacitive current and claims no number for the 35-60 kHz coil/switch-node
current to PE (leakage README 'Not included').  This re-uses the s19b EMI network (same filter, CM capacitances, tank and
sources) with the receiver replaced by the touch-current test:
  * PE bond and LISN sense removed; chassis (PE node) to earth through the IEC 60990 Fig. 4 body + weighting network
    (1500 ohm || 0.22 uF, in series with 500 ohm; weighting 10 kohm + 22 nF across the 500 ohm; weighted touch current
    = U2 / 500 ohm).  UL's meter (1500 ohm || 0.15 uF, reading across the 1500 ohm) has a similar ~0.7 kHz corner; the
    unweighted current through the body model is reported too.
  * mains L and N to earth: (a) the LISN's 50 uH + 5 ohm // 50 ohm port impedance (CISPR-like mains), (b) stiff (1 mohm).
Sources at the line crest (worst instant), every harmonic of fs to 3 MHz, fs 35-60 kHz (1 kHz), configs as s19b's
sensitivities.  Current at different frequencies adds in quadrature with the 60 Hz term: I = sqrt(I60^2 + Ihf^2).
This is an ESTIMATE: no measurement network for UL 1026 was read, and the crest value overstates the line-cycle RMS.
"""
from __future__ import annotations

import numpy as np

import emi_core as E

m = E.m


def _touch_net(p, module, mains, meter="iec60990"):
    n = m.build(p, module)
    drop = []
    for e in n.el:
        k = e[0]
        if k == "L" and e[1] in ("LlisnL", "LlisnN", "Lbond"):
            drop.append(e)
        elif k in "RC" and (e[1], e[2]) in (("line_in", "lisn_l"), ("neut_in", "lisn_n"), ("lisn_l", "pe"), ("lisn_n", "pe"),
                                            ("pe", "pe_l"), ("0", "lisnrL"), ("0", "lisnrN")):
            drop.append(e)
    n.el = [e for e in n.el if e not in drop]
    for ln, s in (("line_in", "L"), ("neut_in", "N")):
        if mains == "lisn":
            n.R("0", f"mr{s}", 5.0)
            n.L(f"Lmains{s}", f"mr{s}", ln, 50e-6)
            n.C(ln, f"mc{s}", 0.1e-6)
            n.R(f"mc{s}", "0", 50.0)
        else:
            n.R(ln, "0", 1e-3)
    if meter == "iec60990":  # IEC 60990 Fig. 4
        n.R("pe", "b1", 1500.0)
        n.C("pe", "b1", 0.22e-6)
        n.R("b1", "0", 500.0)
        n.R("b1", "b2", 10e3)
        n.C("b2", "0", 22e-9)
    else:  # UL 101-style meter: 1500 ohm || 0.15 uF, current = V / 1500 ohm (secondary-source description, est)
        n.R("pe", "b1", 1500.0)
        n.C("pe", "b1", 0.15e-6)
        n.R("b1", "0", 1e-3)
        n.R("b1", "b2", 1e12)
    return n


def control_meter():
    """Closed-form check of both meter networks driven by a 1 mA current source at 60 Hz and 35 kHz."""
    out = []
    for f in (60.0, 35e3):
        w = 2 * np.pi * f
        n = m.Net()
        n.I("Is", "0", "pe")
        n.R("pe", "b1", 1500.0); n.C("pe", "b1", 0.22e-6); n.R("b1", "0", 500.0); n.R("b1", "b2", 10e3); n.C("b2", "0", 22e-9)
        u2 = n.solve([f], {"s": {"Is": 1e-3}}, {"u2": ("b2", "0")})["s"]["u2"][0]
        # closed form: all 1 mA flows into the 500 ohm // (10k + 1/jwC1) branch pair
        zb = 1 / (1 / 500.0 + 1 / (10e3 + 1 / (1j * w * 22e-9)))
        ref = 1e-3 * zb * (1 / (1j * w * 22e-9)) / (10e3 + 1 / (1j * w * 22e-9))
        out.append({"f_hz": f, "weighted_mA_per_mA_mna": abs(u2) / 500 * 1e3, "closed_form": abs(ref) / 500 * 1e3})
        n = m.Net()
        n.I("Is", "0", "pe")
        n.R("pe", "b1", 1500.0); n.C("pe", "b1", 0.15e-6); n.R("b1", "0", 1e-3)
        v = n.solve([f], {"s": {"Is": 1e-3}}, {"v": ("pe", "b1")})["s"]["v"][0]
        ref = 1e-3 * 1 / (1 / 1500 + 1j * w * 0.15e-6)
        out.append({"f_hz": f, "UL101_mA_per_mA_mna": abs(v) / 1500 * 1e3, "closed_form": abs(ref) / 1500 * 1e3})
    return out


def hf_touch(over: dict, nom: dict, cfgs=E.REP3, fs_list=None, fmax=3e6):
    over = dict(over)
    module = over.pop("_module", True)
    p0 = {**m.BASE, **nom, **over}
    fs_list = fs_list or E.FS_SENS
    out = {}
    for mains, meter in (("lisn", "iec60990"), ("stiff", "iec60990"), ("lisn", "ul101")):
        worst = None
        for vc, cn in cfgs:
            for fs in fs_list:
                case = m.case_at(vc, m.CASES[cn], fs)
                p = {**p0, **m.tank_for(vc, case, fs)}
                h = np.arange(1, int(fmax / fs) + 1)
                net = _touch_net(p, module, mains, meter)
                tr = net.solve(h * fs, m.EXC, {"u1": ("b1", "0"), "u2": ("b2", "0"), "u0": ("pe", "b1")})
                va, vb, ib, *_ = m.source_spectra(fs, h, vc, case)
                u1 = tr["A"]["u1"] * va + tr["B"]["u1"] * vb + tr["DM"]["u1"] * ib
                u2 = tr["A"]["u2"] * va + tr["B"]["u2"] * vb + tr["DM"]["u2"] * ib
                if meter == "iec60990":
                    iw = np.sqrt(np.sum(np.abs(u2) ** 2) / 2) / 500.0 * 1e3   # mA rms, weighted (perception/reaction)
                    iu = np.sqrt(np.sum(np.abs(u1) ** 2) / 2) / 500.0 * 1e3   # mA rms, unweighted (body model)
                else:
                    v = tr["A"]["u0"] * va + tr["B"]["u0"] * vb + tr["DM"]["u0"] * ib
                    iw = np.sqrt(np.sum(np.abs(v) ** 2) / 2) / 1500.0 * 1e3   # mA rms read by the UL-style meter
                    iu = float("nan")
                if worst is None or iw > worst["weighted_mA"]:
                    worst = dict(weighted_mA=float(iw), unweighted_mA=float(iu), fs_hz=float(fs), cfg=f"{int(vc)}V/{cn}")
        out[f"{mains}_mains_{meter}"] = worst
    return out
