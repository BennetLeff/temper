"""Vectorised first-harmonic (FHA) tank model, identical in physics to round 4's RG.fha() / round 5's fha_solve(),
for Monte Carlo over thousands of pan/coil/bank draws. ASSUMED.

Square-wave full bridge on the unsmoothed bus |Vpk sin|: the line-cycle RMS of the fundamental is 0.9 V_line,
so line-cycle tank RMS i = 0.9 V / |Z(f)| and P = i^2 R(f). kp, ki (ngspice/FHA) and kpk (ngspice peak / RMS)
are calibrated against the round-6 ngspice grid in analyze6.py.

Key function: required_current() -> the line-cycle tank RMS a draw needs to reach its power target at the
lowest legal frequency, or +inf if the window floor (max(35 kHz, 1.05 f_res)) cannot reach it.
"""
from __future__ import annotations

import numpy as np

import common6 as M

BETA = M.B4.COIL["beta_kl"][0]
GAMMA = M.B4.COIL["gamma_coil"][0]


def lr(d, f):
    fr = f / 40e3
    L = d["L0"] * 1e-6 * d["kl"] * fr ** BETA
    R = d["rac"] * fr ** GAMMA + d["L0"] * d["r40"] * fr ** d["alpha"]
    return L, R


def fres(d):
    f = np.full(np.shape(d["kl"]), 35e3)
    for _ in range(30):
        L, _ = lr(d, f)
        f = 1 / (2 * np.pi * np.sqrt(L * d["C"]))
    return f


def pi_at(d, V, f, kp=1.0, ki=1.0):
    L, R = lr(d, f)
    X = 2 * np.pi * f * L - 1 / (2 * np.pi * f * d["C"])
    i = 0.9003163 * V / np.sqrt(R * R + X * X)
    return (i * i * R) * kp, i * ki


def draws(pan, n, rng, l0, fk, fr, c_bank, rac=M.R_AC_MC, rac_scale=1.0):
    """Uniform draws inside a class's ranges, as round 5's MC: kl, r40, L0 +/-10 %, C +/-10 %, R_ac."""
    kl = 1 - (1 - rng.uniform(pan["kl40"][1], pan["kl40"][2], n)) * fk
    return {"L0": l0 * rng.uniform(1 - M.L_TOL, 1 + M.L_TOL, n), "kl": kl,
            "r40": rng.uniform(pan["r40"][1], pan["r40"][2], n) * fr, "alpha": np.full(n, pan["alpha"]),
            "rac": rng.uniform(rac[0], rac[1], n) * rac_scale, "C": c_bank * rng.uniform(1 - M.C_TOL, 1 + M.C_TOL, n)}


def required_current(d, V, p_tgt, kp=1.0, ki=1.0, f_floor_min=M.F_MIN, f_max=M.F_MAX):
    """Line RMS needed to deliver p_tgt (P falls monotonically with f above resonance). Returns
    (i_req, f_op, status) with status 0 = reachable in window, 1 = needs burst (60 kHz still too much: i_req is the
    60 kHz current, which is never the binding case), 2 = floor-limited (cannot reach p_tgt; i_req = inf)."""
    fr = fres(d)
    f0 = np.maximum(f_floor_min, M.ZVS * fr)
    p0, i0 = pi_at(d, V, f0, kp, ki)
    p1, i1 = pi_at(d, V, np.full_like(f0, f_max), kp, ki)
    lo, hi = f0.copy(), np.full_like(f0, f_max)
    for _ in range(16):
        mid = 0.5 * (lo + hi)
        pm, _ = pi_at(d, V, mid, kp, ki)
        big = pm > p_tgt
        lo = np.where(big, mid, lo)
        hi = np.where(big, hi, mid)
    f = 0.5 * (lo + hi)
    _, i = pi_at(d, V, f, kp, ki)
    status = np.zeros(f.shape, int)
    status[p1 >= p_tgt] = 1
    i = np.where(status == 1, i1, i)
    f = np.where(status == 1, f_max, f)
    floor = p0 < 0.99 * p_tgt
    status[floor] = 2
    i = np.where(floor, np.inf, i)
    f = np.where(floor, f0, f)
    return i, f, status, fr


def power_at_ceiling(d, V, p_tgt, imax, kp=1.0, ki=1.0):
    """Delivered power with an RMS ceiling imax (constant frequency per pan, round-4 rule)."""
    fr = fres(d)
    f0 = np.maximum(M.F_MIN, M.ZVS * fr)
    lo, hi = f0.copy(), np.full_like(f0, M.F_MAX)

    def ok(f):
        p, i = pi_at(d, V, f, kp, ki)
        return (p <= p_tgt * 1.0005) & (i <= imax)

    good0 = ok(f0)
    for _ in range(16):
        mid = 0.5 * (lo + hi)
        g = ok(mid)
        hi = np.where(g, mid, hi)
        lo = np.where(g, lo, mid)
    f = np.where(good0, f0, hi)
    p, i = pi_at(d, V, f, kp, ki)
    return p, i, f, fr
