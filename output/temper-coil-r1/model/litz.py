"""Litz winding resistance: R_dc from copper area and length, R_ac = R_dc + strand skin + strand proximity in the
FEM winding field (every turn's own area-mean |B|^2, which includes the bundle's internal field).

Strand proximity, round strand of diameter d in a transverse peak field B (d << skin depth; low-frequency limit of the
Bessel solution, Ferreira 1994 / Sullivan 1999):   P' = pi w^2 B^2 d^4 / (128 rho)   [W/m per strand, time-average]
Strand skin factor (same limit):                   F_skin = 1 + (d/delta)^4 / 192     (negligible here)
For a bundle of n strands carrying peak current I in field <B^2> = b2 * I^2 (b2 from the FEM at 1 A peak):
    R_prox = 2 P / I^2 = 2 n pi w^2 b2 d^4 / (128 rho)  per metre of bundle
ASSUMPTIONS (stated, not measured): ideal transposition (equal strand currents: type-2 served Litz), copper strand
diameter 0.100 mm (AWG 38 nominal 0.1007), 270 strands, lay take-up 1.03 (power-stage litz_rac.py uses the same),
termination resistance 1.0 mOhm total (two crimped/soldered ring lugs). The leads (about 0.4 m) see only their own field.
"""
from __future__ import annotations

import math

import numpy as np

import materials as M

N_STRANDS, D_STRAND = 270, 0.100e-3
LAY = 1.03
R_TERM = 1.0e-3


def cu_area(n=N_STRANDS, d=D_STRAND):
    return n * math.pi * d * d / 4


def r_dc(length_m, T=25.0, n=N_STRANDS, d=D_STRAND):
    return M.rho_cu(T) * length_m * LAY / cu_area(n, d) + R_TERM


def prox_per_m(b2_per_A2, f, T, n=N_STRANDS, d=D_STRAND):
    """R_prox per metre for a bundle in a field whose area-mean peak |B|^2 is b2 per (peak A)^2."""
    w = 2 * math.pi * f
    return 2 * n * math.pi * w * w * b2_per_A2 * d ** 4 / (128 * M.rho_cu(T))


def skin_factor(f, T, d=D_STRAND):
    delta = math.sqrt(M.rho_cu(T) / (math.pi * f * M.MU0))
    return 1 + (d / delta) ** 4 / 192


def lead_b2(I_pk=1.0, n=N_STRANDS, d=D_STRAND, fill=0.55):
    """Area-mean |B|^2 inside an isolated round bundle (its own field only), per (peak A)^2."""
    a = math.sqrt(cu_area(n, d) / fill / math.pi)
    # B(r) = mu0 I r / (2 pi a^2) inside a uniformly filled bundle -> mean of B^2 over the disc = mu0^2 I^2 / (8 pi^2 a^2)
    return (M.MU0 * I_pk) ** 2 / (8 * math.pi ** 2 * a * a)


def winding_rac(model, f, T=25.0, lead_m=0.40, n=N_STRANDS, d=D_STRAND):
    """R_dc, R_ac and per-turn breakdown for a solved coil_model (1 A peak or any current: b2 is normalised)."""
    I = model.current
    b2 = np.array(model.turn_B2()) / I ** 2
    r = np.array(model.turn_r)
    w = np.array(model.turn_weights)
    length_turns = 2 * math.pi * r * w                     # metres of bundle per ring
    l_wind = float(length_turns.sum())
    l_tot = l_wind + lead_m
    rdc = r_dc(l_tot, T, n, d)
    fs = skin_factor(f, T, d)
    rprox_turns = prox_per_m(b2, f, T, n, d) * length_turns * LAY
    rprox_leads = prox_per_m(lead_b2(1.0, n, d), f, T, n, d) * lead_m * LAY
    rprox = float(rprox_turns.sum() + rprox_leads)
    rac = (rdc - R_TERM) * fs + R_TERM + rprox
    return dict(f_Hz=f, T_C=T, length_m=l_tot, R_dc_ohm=rdc, R_prox_ohm=rprox, R_ac_ohm=rac, F_R=rac / rdc,
                B_rms_winding_mT_per_A=float(np.sqrt(np.average(b2, weights=length_turns)) * 1e3),
                B_max_turn_mT_per_A=float(np.sqrt(b2.max()) * 1e3),
                per_turn=[dict(r_mm=float(ri * 1e3), weight=float(wi), B_mT_per_A=float(math.sqrt(bi) * 1e3),
                               R_prox_mohm=float(rp * 1e3)) for ri, wi, bi, rp in zip(r, w, b2, rprox_turns)])
