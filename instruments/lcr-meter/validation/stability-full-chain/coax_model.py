#!/usr/bin/env python3
"""Lossy RG-58 coax for loop_matrix.rs: skin-effect R ~ sqrt(f) plus dielectric G ~ f, fitted to the
Belden 8259 (RG-58) datasheet, written as SPICE-ready per-metre networks to coax_lossy.rs.

  python3 coax_model.py          (from validation/stability-full-chain; numpy + scipy)

Source: sources/cable/belden-8259-rg58.txt (Belden 8259 rev 0.533, 2026-02-20; URL and PDF hash in
sources/cable/cable-lookup.json): nominal attenuation 1-1000 MHz, conductor DCR 32 ohm/km, shield DCR
12 ohm/km, 101 pF/m, 50 ohm, velocity 66 %.  RG-58 is used because the existing lossless ladder is
RG-58's 101 pF/m / 252.5 nH/m, and because it is the lower-loss choice: Belden 84316 (RG-316) has
1.5-3x the attenuation (8.3 vs 5.4 dB/100 ft at 100 MHz), so it would damp a lead resonance more.

Model, per metre (low-loss line: alpha = R/(2 Z0) + G Z0/2):
  alpha(f) = a sqrt(f) + b f  (dB/100 ft, least squares on relative error over the datasheet points)
  series: Rdc (conductor + shield DCR) + Z_int(f), Z_int = Rs sqrt(f) (1 + j)   (skin effect: internal
          reactance equals the AC resistance), approximated by parallel R_k || L_k branches in series
          (Foster network, poles 4x apart, non-negative least squares on the complex target);
  shunt:  C_main + G(f) = 2 alpha_d / Z0, approximated by series R_k - C_k branches to ground (Debye
          terms, fitted to the real part); C_main is set so the line capacitance at 100 MHz is the
          datasheet 101 pF/m (it rises by up to sum C_k below the poles: dielectric dispersion).
The script checks the result by computing alpha from gamma = sqrt(Z Y) of the fitted networks at the
datasheet frequencies.  The 252.5 nH/m external inductance and 20 sections per metre are unchanged.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / 'sources' / 'cable' / 'belden-8259-rg58.txt'
Z0, C_PM, L_EXT = 50.0, 101e-12, 252.5e-9
NP_PER_DB100FT = 1 / (8.686 * 30.48)          # dB/100 ft -> Np/m


def datasheet():
    txt = SRC.read_text()
    pts = [(float(f), float(a)) for f, a in re.findall(r'^\s*(\d+) MHz\s+([\d.]+) dB/100ft', txt, re.M)]
    dcr = [float(x) for x in re.findall(r'\((\d+) Ohm/km\)', txt)]          # conductor, shield
    assert len(pts) >= 8 and len(dcr) == 2, (pts, dcr)
    return np.array(pts), sum(dcr) / 1000.0


def main():
    pts, rdc = datasheet()
    f, att = pts[:, 0], pts[:, 1]
    A = np.c_[np.sqrt(f), f] / att[:, None]                 # relative-error least squares
    (a, b), *_ = np.linalg.lstsq(A, np.ones_like(att), rcond=None)
    rs = 2 * Z0 * a * NP_PER_DB100FT / math.sqrt(1e6)          # ohm/m per sqrt(Hz)
    g1 = 2 * b * NP_PER_DB100FT / Z0 / 1e6                     # S/m per Hz
    fr = np.logspace(6, math.log10(3e9), 200)
    w = 2 * math.pi * fr
    # Foster series network for Z_int = rs sqrt(f) (1 + j)
    poles = 2 * math.pi * 5e5 * 4.0 ** np.arange(0, 10)         # 0.5 MHz ... 131 GHz rad/s (internal L stays physical below)
    tgt = rs * np.sqrt(fr)
    x = w[:, None] / poles[None, :]
    re_ = x ** 2 / (1 + x ** 2)                                # per unit R_k
    im_ = x / (1 + x ** 2)
    M = np.r_[re_ / tgt[:, None], im_ / tgt[:, None]]
    rk, _ = nnls(M, np.r_[np.ones_like(tgt), np.ones_like(tgt)])
    keep = rk > 1e-9
    foster = [(r, r / p) for r, p in zip(rk[keep], poles[keep])]
    # Debye shunt network for G = g1 f (real part only)
    dpoles = 2 * math.pi * 1e5 * 4.0 ** np.arange(0, 11)
    gt = g1 * fr
    xd = w[:, None] / dpoles[None, :]
    Md = (xd ** 2 / (1 + xd ** 2)) / gt[:, None]               # per unit conductance 1/R_k
    gk, _ = nnls(Md, np.ones_like(gt))
    keepd = gk > 1e-12
    debye = [(1 / g, g / p) for g, p in zip(gk[keepd], dpoles[keepd])]   # (R_k, C_k = 1/(R_k p))
    # each R_k - C_k branch is capacitive below its pole and resistive above it: set C_main so the
    # line capacitance is the datasheet 101 pF/m at 100 MHz, where the lead resonances sit
    w100 = 2 * math.pi * 1e8
    c_main = C_PM - sum(c / (1 + (w100 * r * c) ** 2) for r, c in debye)
    # check: alpha of the fitted networks vs datasheet
    def zy(fq):
        s = 2j * math.pi * fq
        z = rdc + s * L_EXT + sum(1 / (1 / r + 1 / (s * l)) for r, l in foster)
        y = s * c_main + sum(1 / (r + 1 / (s * c)) for r, c in debye)
        return z, y
    rows = []
    for fq, at in pts:
        z, y = zy(fq * 1e6)
        alpha = (np.sqrt(z * y)).real / NP_PER_DB100FT
        rows.append((fq, at, alpha))
    print(f'fit: alpha = {a:.4f} sqrt(f/MHz) + {b:.5f} f/MHz dB/100ft; Rs {rs:.3e} ohm/m/sqrt(Hz), '
          f'G {g1:.3e} S/m/Hz (tan d {g1 / (2 * math.pi * C_PM):.2e}); Rdc {rdc:.3f} ohm/m')
    print(f'Foster {len(foster)} branches, Debye {len(debye)} branches, C_main {c_main * 1e12:.2f} pF/m '
          f'(+ sum C_k {sum(c for _, c in debye) * 1e12:.3f} below the poles), internal L at 1 MHz '
          f'{(zy(1e6)[0] - rdc - 2j * math.pi * 1e6 * L_EXT).imag / (2 * math.pi * 1e6) * 1e9:.1f} nH/m')
    print('  f MHz   datasheet   model   (dB/100 ft)')
    for fq, at, al in rows:
        print(f'{fq:7.0f} {at:10.2f} {al:8.2f}  {100 * (al / at - 1):+5.1f} %')
    worst = max(abs(al / at - 1) for fq, at, al in rows if 10 <= fq <= 400)
    lines = ['// GENERATED by coax_model.py from ../../sources/cable/belden-8259-rg58.txt -- do not edit.',
             f'// Belden 8259 RG-58, per metre. alpha fit {a:.4f} sqrt(f) + {b:.5f} f dB/100ft (f in MHz);',
             f'// fitted networks reproduce the datasheet attenuation within {100 * worst:.1f} % over 10-400 MHz.',
             f'const COAX_RDC: f64 = {rdc:.6e};',
             f'const COAX_C_MAIN: f64 = {c_main:.6e};',
             f'const COAX_FOSTER: [(f64, f64); {len(foster)}] = [' + ', '.join(f'({r:.6e}, {l:.6e})' for r, l in foster) + '];',
             f'const COAX_DEBYE: [(f64, f64); {len(debye)}] = [' + ', '.join(f'({r:.6e}, {c:.6e})' for r, c in debye) + '];']
    (HERE / 'coax_lossy.rs').write_text('\n'.join(lines) + '\n')
    print('-> coax_lossy.rs')


if __name__ == '__main__':
    main()
