#!/usr/bin/env python3
"""Rim detent-ring study (option (a), geometry A0) for the TMAG5170 knob sensor.

Question: does a stationary 1010 steel detent ring (24 teeth, r 25.5-27.5, w -4..-3) plus 24 rim
magnets on the knob keep the sensing-magnet angle error inside the ring's share of the 0.6 deg pool?

Method (see README.md): permanent magnets analytically (magpylib for the Ø10x5 diametral cylinder,
an exact cuboid kernel for the 24 rim blocks); the steel by a volume-integral method of moments on
annular-sector cells (each a uniformly magnetised rotated cuboid, exact cuboid field kernel,
point collocation at cell centres), linear (mu_r sweep) or saturating (representative 1010 B-H,
Newton-chord iteration) with an optional vector-play hysteresis. Writes results.json, plots/*.png,
raw/*.csv next to this file.

Usage:  python3 ring_study.py [--quick] [--workers N] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numba as nb  # noqa: E402
import numpy as np  # noqa: E402
from scipy import interpolate, linalg, optimize  # noqa: E402
from scipy.sparse import linalg as spla  # noqa: E402
from scipy.sparse.linalg import LinearOperator  # noqa: E402
from scipy.spatial.transform import Rotation as Rot  # noqa: E402

import magpylib as mp  # noqa: E402

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]                      # zapote/ui-board
MU0 = 4e-7 * math.pi
FOURPI = 4 * math.pi


def _load_ui_calcs():
    spec = importlib.util.spec_from_file_location("ui_calcs", UNIT / "tools" / "ui_calcs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_calcs"] = mod
    spec.loader.exec_module(mod)
    return mod


UI = _load_ui_calcs()

# ------------------------------------------------------------------------------------------ geometry (A0)
AXIS_UV = (110.0, 53.0)
R_OUT, R_ROOT, R_TIP = 27.5, 26.5, 25.5
RING_W = (-4.0, -3.0)
N_TEETH = 24
PITCH = 360.0 / N_TEETH                     # 15 deg
TOOTH_W = 7.5                               # deg
RIM_R, RIM_SIZE, RIM_W = 26.5, (1.0, 2.0, 2.0), (1.0, 3.0)   # radial, tangential, axial; w extent
CEN_D, CEN_H, CEN_W = 10.0, 5.0, (1.0, 6.0)
HALL = np.array([0.0, 0.0, -4.0])
BR20 = UI.BR_35E                            # 1.19 T, 35E nominal at 20 C (ui_calcs)
TEMPCO = 0.00035                            # reversible, per K (ui_calcs)
T_HOT = 176.0

# ------------------------------------------------------------------------------------------ budget (stated before results)
POOL_DEG = 0.60                             # 1.0 deg absolute budget - 0.40 deg non-repeatable (ui_calcs, U24)
RING_SHARE_DEG = 0.10                       # pool/3 = 0.20 (calibration, magnet, mechanism); ring = half of the mechanism third
B_RANGE_80PCT_MT = 80.0                     # 80 % of the +/-100 mT range (ui_calcs)
STEEL_KNEE_T = 1.5                          # report saturation against this steel flux density
CONV_TOL = 0.10                             # halving element size must change the peak error by < 10 %
CTRL1_TOL, CTRL2_TOL = 0.02, 0.01
SENSOR_EPS_RESID = 2.0 * math.radians(0.057)    # X/Y gain mismatch left after TEMP_RESULT correction (ui_calcs 0.057 deg)
SENSOR_EPS_SLOPE = 0.040 / 100.0            # uncorrected X/Y sensitivity mismatch drift, 4.0 % per 100 K (DECISIONS U23, SBASAF4 p.7, max)


# =========================================================================================== exact cuboid field kernel
@nb.njit(cache=True)
def _lnp(eta, xi, ze, R):
    if eta >= 0.0:
        return math.log(eta + R)
    d = xi * xi + ze * ze
    if d <= 0.0:
        d = 1e-300
    return math.log(d / (R - eta))


@nb.njit(cache=True)
def _hz_case(x, y, z, a, b, c, out):
    hx = 0.0
    hy = 0.0
    hz = 0.0
    for k in range(2):
        sk = 1.0 if k == 1 else -1.0
        ze = (c if k == 1 else -c) - z
        for p in range(2):
            sp = 1.0 if p == 1 else -1.0
            xi = (a if p == 1 else -a) - x
            for q in range(2):
                sq = 1.0 if q == 1 else -1.0
                eta = (b if q == 1 else -b) - y
                R = math.sqrt(xi * xi + eta * eta + ze * ze)
                s = sk * sp * sq
                hx += s * _lnp(eta, xi, ze, R)
                hy += s * _lnp(xi, eta, ze, R)
                if ze != 0.0:
                    hz += -s * math.atan(xi * eta / (ze * R))
                else:
                    hz += -s * (0.0 if xi * eta == 0.0 else (math.pi / 2 if xi * eta > 0 else -math.pi / 2))
    out[0] = hx / FOURPI
    out[1] = hy / FOURPI
    out[2] = hz / FOURPI


@nb.njit(cache=True)
def kernel_local(x, y, z, a, b, c, K):
    """K[i, j]: local H_i at (x, y, z) from a cuboid (half dims a, b, c) with unit M along local axis j."""
    o = np.empty(3)
    _hz_case(x, y, z, a, b, c, o)
    K[0, 2] = o[0]
    K[1, 2] = o[1]
    K[2, 2] = o[2]
    _hz_case(y, z, x, b, c, a, o)
    K[1, 0] = o[0]
    K[2, 0] = o[1]
    K[0, 0] = o[2]
    _hz_case(z, x, y, c, a, b, o)
    K[2, 1] = o[0]
    K[0, 1] = o[1]
    K[1, 1] = o[2]


@nb.njit(cache=True)
def field_sum(obs, cen, Rm, half, Mv):
    """H (A/m) at obs (P,3) from S uniformly magnetised cuboids. Rm[s] columns are the local axes in the global frame; Mv[s] global M (A/m)."""
    P = obs.shape[0]
    S = cen.shape[0]
    H = np.zeros((P, 3))
    K = np.empty((3, 3))
    for i in range(P):
        for s in range(S):
            d0 = obs[i, 0] - cen[s, 0]
            d1 = obs[i, 1] - cen[s, 1]
            d2 = obs[i, 2] - cen[s, 2]
            xl = Rm[s, 0, 0] * d0 + Rm[s, 1, 0] * d1 + Rm[s, 2, 0] * d2
            yl = Rm[s, 0, 1] * d0 + Rm[s, 1, 1] * d1 + Rm[s, 2, 1] * d2
            zl = Rm[s, 0, 2] * d0 + Rm[s, 1, 2] * d1 + Rm[s, 2, 2] * d2
            kernel_local(xl, yl, zl, half[s, 0], half[s, 1], half[s, 2], K)
            m0 = Rm[s, 0, 0] * Mv[s, 0] + Rm[s, 1, 0] * Mv[s, 1] + Rm[s, 2, 0] * Mv[s, 2]
            m1 = Rm[s, 0, 1] * Mv[s, 0] + Rm[s, 1, 1] * Mv[s, 1] + Rm[s, 2, 1] * Mv[s, 2]
            m2 = Rm[s, 0, 2] * Mv[s, 0] + Rm[s, 1, 2] * Mv[s, 1] + Rm[s, 2, 2] * Mv[s, 2]
            hl0 = K[0, 0] * m0 + K[0, 1] * m1 + K[0, 2] * m2
            hl1 = K[1, 0] * m0 + K[1, 1] * m1 + K[1, 2] * m2
            hl2 = K[2, 0] * m0 + K[2, 1] * m1 + K[2, 2] * m2
            for j in range(3):
                H[i, j] += Rm[s, j, 0] * hl0 + Rm[s, j, 1] * hl1 + Rm[s, j, 2] * hl2
    return H


@nb.njit(cache=True, parallel=True)
def build_matrix(obs, cen, Rm, half):
    """G[3i+a, 3j+b]: global H_{i,a} at obs i per unit global M_{j,b} of cell j (obs == cen gives the A matrix incl. self terms)."""
    P = obs.shape[0]
    N = cen.shape[0]
    G = np.empty((3 * P, 3 * N))
    for i in nb.prange(P):
        K = np.empty((3, 3))
        for j in range(N):
            d0 = obs[i, 0] - cen[j, 0]
            d1 = obs[i, 1] - cen[j, 1]
            d2 = obs[i, 2] - cen[j, 2]
            xl = Rm[j, 0, 0] * d0 + Rm[j, 1, 0] * d1 + Rm[j, 2, 0] * d2
            yl = Rm[j, 0, 1] * d0 + Rm[j, 1, 1] * d1 + Rm[j, 2, 1] * d2
            zl = Rm[j, 0, 2] * d0 + Rm[j, 1, 2] * d1 + Rm[j, 2, 2] * d2
            kernel_local(xl, yl, zl, half[j, 0], half[j, 1], half[j, 2], K)
            for a in range(3):
                for b in range(3):
                    s = 0.0
                    for p in range(3):
                        for q in range(3):
                            s += Rm[j, a, p] * K[p, q] * Rm[j, b, q]
                    G[3 * i + a, 3 * j + b] = s
    return G


# =========================================================================================== ring mesh
class Mesh:
    """Annular-sector cells aligned with the 15 deg tooth pitch (exact C24 symmetry of the mesh)."""

    def __init__(self, n_r: int, n_phi: int, n_z: int, notch_pitches=()):
        assert n_phi % 4 == 0
        self.n_r, self.n_phi, self.n_z = n_r, n_phi, n_z
        cen, Rm, half, tooth = [], [], [], []
        dr, dz = 1.0 / n_r, 1.0 / n_z
        dphi = PITCH / n_phi
        for k in range(N_TEETH):
            if k in notch_pitches:
                continue
            for j in range(n_phi):
                lo = PITCH * k - PITCH / 2 + j * dphi
                phic = lo + dphi / 2
                in_tooth = abs(phic - PITCH * k) < TOOTH_W / 2
                layers = [(R_ROOT + (i + 0.5) * dr, False) for i in range(n_r)]
                if in_tooth:
                    layers += [(R_TIP + (i + 0.5) * dr, True) for i in range(n_r)]
                pr = math.radians(phic)
                er = np.array([math.cos(pr), math.sin(pr), 0.0])
                et = np.array([-math.sin(pr), math.cos(pr), 0.0])
                ez = np.array([0.0, 0.0, 1.0])
                for rm, is_tip in layers:
                    for iz in range(n_z):
                        zc = RING_W[0] + (iz + 0.5) * dz
                        cen.append([rm * math.cos(pr), rm * math.sin(pr), zc])
                        Rm.append(np.column_stack([er, et, ez]))
                        half.append([dr / 2, rm * math.radians(dphi) / 2, dz / 2])
                        tooth.append(is_tip)
        self.cen = np.array(cen)
        self.Rm = np.array(Rm)
        self.half = np.array(half)
        self.tip = np.array(tooth)
        self.vol = 8 * self.half[:, 0] * self.half[:, 1] * self.half[:, 2]          # mm^3
        self.N = len(self.cen)

    def A(self) -> np.ndarray:
        return build_matrix(self.cen, self.cen, self.Rm, self.half)


# =========================================================================================== steel models
# Representative 1010 low-carbon steel normal-magnetisation curve (H in A/m, B in T). Handbook-typical anchors;
# NOT a measured curve. mu_r(initial) ~ 350, mu_r(max) ~ 2200 near 0.55 T, knee ~1.3-1.6 T, J_s ~ 2.1 T.
H_TAB = np.array([0, 10, 25, 50, 100, 200, 400, 800, 1500, 3000, 6000, 12000, 25000, 50000, 1e5, 3e5, 1e6, 1e7])
B_TAB = np.array([0, 0.0044, 0.0125, 0.040, 0.150, 0.550, 1.00, 1.30, 1.50, 1.65, 1.78, 1.90, 2.02, 2.10, 2.20, 2.50, 3.40, 13.9])


class Steel:
    """Anhysteretic M(H) = m(|H|) H/|H| (PCHIP through the table), optional vector play hysteresis (coercive Hc, A/m)."""

    def __init__(self, hs: float = 1.0, js: float = 1.0, Hc: float = 0.0, label: str = ""):
        J = (B_TAB - MU0 * H_TAB) / MU0
        self.hs, self.js, self.Hc, self.label = hs, js, Hc, label
        self._f = interpolate.PchipInterpolator(H_TAB, J)
        self._d = self._f.derivative()
        self.chi0 = float(self.js * self.hs * self._d(0.0))

    def m(self, h):
        return self.js * self._f(np.minimum(h * self.hs, 1e7))

    def dm(self, h):
        return self.js * self.hs * self._d(np.minimum(h * self.hs, 1e7))

    P_SOFT = 8.0

    def _phi(self, sn):
        """Smoothed play factor phi(|d|) = Hc / (Hc^p + |d|^p)^(1/p): 1 inside the stop, Hc/|d| far outside."""
        p, Hc = self.P_SOFT, self.Hc
        return Hc * (Hc ** p + sn ** p) ** (-1.0 / p)

    def play(self, H, Hprev):
        if self.Hc <= 0.0:
            return H
        d = H - Hprev
        sn = np.linalg.norm(d, axis=1, keepdims=True)
        return H - d * self._phi(sn)

    def F(self, Heff):
        h = np.linalg.norm(Heff, axis=1, keepdims=True)
        return self.m(h) * Heff / np.maximum(h, 1e-300)

    def tangent(self, H, Hprev):
        """dM/dH (N,3,3) at H, history Hprev."""
        N = H.shape[0]
        Heff = self.play(H, Hprev)
        h = np.linalg.norm(Heff, axis=1)
        hh = np.maximum(h, 1e-12)
        nh = Heff / hh[:, None]
        mm = self.m(h)
        dmm = self.dm(h)
        P = nh[:, :, None] * nh[:, None, :]
        I = np.eye(3)[None]
        small = (h < 1e-9)
        sec = np.where(small, dmm, mm / hh)
        DF = sec[:, None, None] * (I - P) + dmm[:, None, None] * P
        if self.Hc > 0.0:
            d = H - Hprev
            sn = np.linalg.norm(d, axis=1)
            u = d / np.maximum(sn, 1e-300)[:, None]
            PU = u[:, :, None] * u[:, None, :]
            p, Hc = self.P_SOFT, self.Hc
            phi = self._phi(sn)
            dphi = -Hc * sn ** (p - 1.0) * (Hc ** p + sn ** p) ** (-1.0 / p - 1.0)
            DG = phi[:, None, None] * I + (sn * dphi)[:, None, None] * PU
            DF = np.einsum("nab,nbc->nac", DF, I - DG)
        return DF


class Linear:
    def __init__(self, mu_r: float):
        self.mu_r = mu_r
        self.chi = mu_r - 1.0
        self.label = f"linear mu_r={mu_r:g}"
        self.Hc = 0.0


# =========================================================================================== sources and pose
def br_at(T: float) -> float:
    return BR20 * (1.0 - TEMPCO * (T - 20.0))


class Cond:
    """One mechanical/thermal condition. Offsets are in the ring frame (ring and Hall coaxial unless ring_off is used)."""

    def __init__(self, name, push=0.0, gap=0.0, off=(0.0, 0.0), tilt=(0.0, 0.0), T=20.0, ring_off=(0.0, 0.0)):
        self.name, self.push, self.gap, self.off, self.tilt, self.T, self.ring_off = name, push, gap, off, tilt, T, ring_off

    def dz(self):
        return self.gap - self.push

    def symmetric(self):
        return self.off == (0.0, 0.0) and self.tilt == (0.0, 0.0) and self.ring_off == (0.0, 0.0)

    def meta(self):
        return {"push_mm": self.push, "gap_error_mm": self.gap, "knob_offset_mm": list(self.off), "tilt_deg": list(self.tilt),
                "ring_offset_mm": list(self.ring_off), "magnet_T_C": self.T}


def tilt_matrix(tilt):
    return Rot.from_euler("xy", [tilt[0], tilt[1]], degrees=True).as_matrix()


class Pose:
    """Knob (central + 24 rim magnets) placed for angle theta, expressed in the ring frame."""

    def __init__(self, cond: Cond):
        self.c = cond
        self.Rt = tilt_matrix(cond.tilt)
        self.P0 = np.array([0.0, 0.0, CEN_W[0]])
        self.s = np.array([cond.off[0], cond.off[1], cond.dz()])
        self.br = br_at(cond.T)
        k = np.arange(N_TEETH)
        self.ang0 = np.radians(PITCH * k)
        zc = 0.5 * (RIM_W[0] + RIM_W[1])
        self.rim_c0 = np.column_stack([RIM_R * np.cos(self.ang0), RIM_R * np.sin(self.ang0), np.full(N_TEETH, zc)])
        self.rim_half = np.tile(np.array(RIM_SIZE) / 2.0, (N_TEETH, 1))
        self.cen_c0 = np.array([0.0, 0.0, 0.5 * (CEN_W[0] + CEN_W[1])])

    def _world(self, p):
        return (self.Rt @ (p - self.P0).T).T + self.P0 + self.s

    def rim(self, theta_deg):
        Rz = Rot.from_euler("z", theta_deg, degrees=True).as_matrix()
        pc = (Rz @ self.rim_c0.T).T
        cen = self._world(pc)
        ang = self.ang0 + math.radians(theta_deg)
        er = np.column_stack([np.cos(ang), np.sin(ang), np.zeros_like(ang)])
        et = np.column_stack([-np.sin(ang), np.cos(ang), np.zeros_like(ang)])
        ez = np.tile([0.0, 0.0, 1.0], (N_TEETH, 1))
        Rm = np.stack([er, et, ez], axis=2)                      # columns
        Rm = np.einsum("ab,sbc->sac", self.Rt, Rm)
        Mv = (self.br / MU0) * Rm[:, :, 2]
        return cen, np.ascontiguousarray(Rm), self.rim_half, np.ascontiguousarray(Mv)

    def central(self, theta_deg):
        R = self.Rt @ Rot.from_euler("z", theta_deg, degrees=True).as_matrix()
        pos = self._world(self.cen_c0[None])[0]
        return mp.magnet.Cylinder(dimension=(CEN_D, CEN_H), polarization=(self.br, 0.0, 0.0),
                                  position=tuple(pos), orientation=Rot.from_matrix(R))

    def B_free(self, theta_deg, obs):
        """B (T) of central + rim magnets (no steel) at obs (P,3), ring frame."""
        bc = np.atleast_2d(self.central(theta_deg).getB(obs))
        cen, Rm, half, Mv = self.rim(theta_deg)
        br = MU0 * field_sum(np.ascontiguousarray(obs), cen, Rm, half, Mv)
        return bc, br

    def H_ext(self, theta_deg, obs):
        bc, br = self.B_free(theta_deg, obs)
        return (bc + br) / MU0, br / MU0


# =========================================================================================== steel solver
class RingSolver:
    def __init__(self, mesh: Mesh, A: np.ndarray | None = None):
        self.mesh = mesh
        self.A = mesh.A() if A is None else A
        self.N = mesh.N
        self._inv = {}
        self.Afull = None

    # -- Hall response (3, 3N): B_hall = MU0 * G @ M
    def hall_G(self, hall):
        return build_matrix(np.array([hall], float), self.mesh.cen, self.mesh.Rm, self.mesh.half)

    def lin_factor(self, mu_r):
        """Inverse (small meshes) or LU (large meshes) of I - chi A, cached per mu_r."""
        if mu_r not in self._inv:
            chi = mu_r - 1.0
            if self.N <= 3000:
                Mx = np.eye(3 * self.N) - chi * self.A
                self._inv[mu_r] = ("inv", linalg.inv(Mx, overwrite_a=True, check_finite=False))
            else:
                Mx = np.empty((3 * self.N, 3 * self.N), order="F")
                Mx[:] = -chi * self.A
                Mx[np.arange(3 * self.N), np.arange(3 * self.N)] += 1.0
                self._inv[mu_r] = ("lu", linalg.lu_factor(Mx, overwrite_a=True, check_finite=False))
        return self._inv[mu_r]

    def solve_linear(self, mu_r, Hext):
        kind, f = self.lin_factor(mu_r)
        rhs = (mu_r - 1.0) * Hext.reshape(-1)
        M = f @ rhs if kind == "inv" else linalg.lu_solve(f, rhs, check_finite=False)
        return M.reshape(-1, 3)

    def solve_nl(self, steel: Steel, Hext, M0, Hprev, ramp=False, rtol=1e-6, max_it=40, prec=None):
        """Inexact Newton (GMRES preconditioned by a reusable LU of an earlier Jacobian) for M = F(play(Hext + A M)).
        Returns M, Heff, prec (reusable), info."""
        N = self.N
        A = self.A
        A3 = A.reshape(N, 3, 3 * N)
        lams = [1.0] if not ramp else list(np.geomspace(2e-3, 1.0, 14))
        M = M0.copy()
        Hp = Hprev
        info = {"iters": 0, "refac": 0, "gmres": 0}

        def resid(Mx, He):
            H = He + (A @ Mx.reshape(-1)).reshape(-1, 3)
            Heff = steel.play(H, Hp)
            Fv = steel.F(Heff)
            r = Mx - Fv
            scale = max(np.max(np.abs(Mx)), np.max(np.abs(Fv)), 1e-3)
            return r, np.max(np.abs(r)) / scale, H, Heff

        def factor(DF):
            J = np.empty((3 * N, 3 * N), order="F")
            blk = 256
            for i0 in range(0, N, blk):
                i1 = min(N, i0 + blk)
                J[3 * i0:3 * i1, :] = -np.einsum("nab,nbj->naj", DF[i0:i1], A3[i0:i1]).reshape(3 * (i1 - i0), 3 * N)
            J[np.arange(3 * N), np.arange(3 * N)] += 1.0
            info["refac"] += 1
            return linalg.lu_factor(J, overwrite_a=True, check_finite=False)

        for lam in lams:
            He = lam * Hext
            r, res, H, Heff = resid(M, He)
            for it in range(max_it):
                if res < rtol:
                    break
                DF = steel.tangent(H, Hp)
                if prec is None:
                    prec = factor(DF)
                op = LinearOperator((3 * N, 3 * N), dtype=float,
                                    matvec=lambda v, DF=DF: v - np.einsum("nab,nb->na", DF, (A @ v).reshape(-1, 3)).reshape(-1))
                pm = LinearOperator((3 * N, 3 * N), dtype=float, matvec=lambda v, lu=prec: linalg.lu_solve(lu, v, check_finite=False))
                cnt = [0]

                def cb(_):
                    cnt[0] += 1
                d, flag = spla.gmres(op, r.reshape(-1), M=pm, rtol=min(1e-2, 0.1 * res) if res > 1e-6 else 1e-4 * res / rtol * rtol,
                                     restart=25, maxiter=2, callback=cb, callback_type="pr_norm")
                info["gmres"] += cnt[0]
                if flag != 0:
                    prec = factor(DF)
                    pm = LinearOperator((3 * N, 3 * N), dtype=float, matvec=lambda v, lu=prec: linalg.lu_solve(lu, v, check_finite=False))
                    d, flag = spla.gmres(op, r.reshape(-1), M=pm, rtol=1e-6, restart=25, maxiter=4)
                d = d.reshape(-1, 3)
                t = 1.0
                while True:
                    Mn = M - t * d
                    rn, resn, Hn, Heffn = resid(Mn, He)
                    if resn < (1.0 - 1e-4 * t) * res or t < 1e-3:
                        break
                    t *= 0.5
                M, r, res, H, Heff = Mn, rn, resn, Hn, Heffn
                info["iters"] += 1
        if res >= rtol:
            info["unconverged"] = float(res)
        return M, Heff, prec, info


# =========================================================================================== sweeps
def sweep(solver: RingSolver, cond: Cond, material, angles):
    """Raw field at the Hall point versus knob angle (list/array, in order, path dependent for hysteresis).

    Returns dict of arrays: B_free (n,3) [T], B_steel (n,3), Bmax_cell, W (J), meta. material None -> ring absent.
    """
    pose = Pose(cond)
    hall = HALL.copy()
    ring_shift = np.array([cond.ring_off[0], cond.ring_off[1], 0.0])
    # ring frame -> if the ring is displaced by +ring_off, the ring sits at cen + ring_off. Work in the ring frame
    # by moving the Hall and the knob by -ring_off instead.
    hall_r = hall - ring_shift
    pose.s = pose.s - ring_shift
    n = len(angles)
    B_free = np.zeros((n, 3))
    B_steel = np.zeros((n, 3))
    W = np.zeros(n)
    Bcell_max = np.zeros(n)
    Hcell_max = np.zeros(n)
    frac_knee = np.zeros(n)
    chi_ratio_min = np.ones(n)
    G = None if material is None else solver.hall_G(hall_r)
    cen = None if material is None else solver.mesh.cen
    vol = None if material is None else solver.mesh.vol * 1e-9
    M = None
    state = {"M": None, "Hprev": None, "prec": None, "th": None}
    tot_iters = 0

    def nl_solve(th):
        Hext_, _ = pose.H_ext(th, cen)
        if state["M"] is None:
            # start from the linear solution at mu_r = 300 (close to the initial permeability); fall back to the load ramp from the virgin state
            M0, Hp0 = solver.solve_linear(300.0, Hext_), np.zeros((solver.N, 3))
            M_, Heff_, prec_, info_ = solver.solve_nl(material, Hext_, M0, Hp0, ramp=False, prec=state["prec"])
            if "unconverged" in info_:
                state["prec"] = None
                M_, Heff_, prec_, info_ = solver.solve_nl(material, Hext_, np.zeros((solver.N, 3)), Hp0, ramp=True, prec=None)
        else:
            M0, Hp0 = state["M"], state["Hprev"]
            M_, Heff_, prec_, info_ = solver.solve_nl(material, Hext_, M0, Hp0, ramp=False, prec=state["prec"])
        state["prec"] = prec_
        if "unconverged" in info_:
            return None, Hext_, info_
        state.update(M=M_, Hprev=Heff_, th=th)
        return M_, Hext_, info_

    def nl_advance(th, depth=0):
        M_, Hext_, info_ = nl_solve(th)
        if M_ is not None:
            return M_, Hext_, info_["iters"]
        if depth >= 7 or state["th"] is None:
            raise RuntimeError(f"steel solve did not converge at {th} deg: {info_}")
        mid = 0.5 * (state["th"] + th)
        nl_advance(mid, depth + 1)
        return nl_advance(th, depth + 1)

    for i, th in enumerate(angles):
        bc, br = pose.B_free(th, hall_r[None])
        B_free[i] = (bc + br)[0]
        if material is None:
            continue
        if isinstance(material, Linear):
            Hext, _ = pose.H_ext(th, cen)
            M = solver.solve_linear(material.mu_r, Hext)
        else:
            M, Hext, nit = nl_advance(th)
            tot_iters += nit
        H = Hext + (solver.A @ M.reshape(-1)).reshape(-1, 3)
        B_steel[i] = MU0 * (G @ M.reshape(-1))
        Bc = MU0 * (H + M)
        Bn = np.linalg.norm(Bc, axis=1)
        Bcell_max[i] = Bn.max()
        Hcell_max[i] = np.linalg.norm(H, axis=1).max()
        frac_knee[i] = np.mean(Bn > STEEL_KNEE_T)
        W[i] = -0.5 * MU0 * np.sum(vol * np.einsum("ij,ij->i", M, Hext))
    return {"angles": np.asarray(angles, float), "B_free": B_free, "B_steel": B_steel, "W": W, "Bcell_max": Bcell_max,
            "Hcell_max": Hcell_max, "frac_knee": frac_knee, "iters": tot_iters}


def sweep_linear_multi(solver: RingSolver, cond: Cond, mus, angles):
    """Linear steels sharing one evaluation of the permanent-magnet field per angle. -> {mu: result dict as in sweep()}"""
    pose = Pose(cond)
    ring_shift = np.array([cond.ring_off[0], cond.ring_off[1], 0.0])
    hall_r = HALL - ring_shift
    pose.s = pose.s - ring_shift
    n = len(angles)
    G = solver.hall_G(hall_r)
    cen, vol = solver.mesh.cen, solver.mesh.vol * 1e-9
    out = {mu: {"B_steel": np.zeros((n, 3)), "W": np.zeros(n), "Bcell_max": np.zeros(n), "Hcell_max": np.zeros(n), "frac_knee": np.zeros(n)} for mu in mus}
    B_free = np.zeros((n, 3))
    for i, th in enumerate(angles):
        bc, br = pose.B_free(th, hall_r[None])
        B_free[i] = (bc + br)[0]
        Hext, _ = pose.H_ext(th, cen)
        for mu in mus:
            M = solver.solve_linear(mu, Hext)
            H = Hext + (solver.A @ M.reshape(-1)).reshape(-1, 3)
            o = out[mu]
            o["B_steel"][i] = MU0 * (G @ M.reshape(-1))
            Bn = np.linalg.norm(MU0 * (H + M), axis=1)
            o["Bcell_max"][i], o["Hcell_max"][i], o["frac_knee"][i] = Bn.max(), np.linalg.norm(H, axis=1).max(), np.mean(Bn > STEEL_KNEE_T)
            o["W"][i] = -0.5 * MU0 * np.sum(vol * np.einsum("ij,ij->i", M, Hext))
    for mu in mus:
        out[mu].update({"angles": np.asarray(angles, float), "B_free": B_free.copy(), "iters": 0})
    return out


# =========================================================================================== angle error and calibration
def wrap(d):
    return (np.asarray(d) + 180.0) % 360.0 - 180.0


def apply_sensor(Bxy, eps):
    """X/Y sensitivity mismatch eps (X high, Y low by eps/2 each) -> measured pair."""
    out = np.array(Bxy, float)
    out[:, 0] *= 1.0 + eps / 2
    out[:, 1] *= 1.0 - eps / 2
    return out


def psi_deg(Bxy):
    return np.degrees(np.arctan2(Bxy[:, 1], Bxy[:, 0]))


def raw_error(theta, Bxy):
    return wrap(psi_deg(Bxy) - theta)


def fourier_basis(psi, harmonics):
    p = np.radians(psi)
    cols = [np.ones_like(p)]
    for h in harmonics:
        cols += [np.cos(h * p), np.sin(h * p)]
    return np.column_stack(cols)


class Cal:
    """One fixed cold calibration. kind: 'affine' (offset, gain, skew, angle offset) or 'harm' (Fourier error table)."""

    def __init__(self, kind, harmonics=()):
        self.kind, self.harm = kind, tuple(harmonics)
        self.p = None

    def fit(self, theta, Bxy):
        if self.kind == "affine":
            def model(p, B):
                x = B[:, 0] - p[0]
                y = (B[:, 1] - p[1]) * p[2] + x * p[3]
                return np.degrees(np.arctan2(y, x)) - p[4]
            scale = float(np.hypot(*Bxy.T).mean())
            p0 = np.array([0.0, 0.0, 1.0, 0.0, 0.0])
            res = optimize.least_squares(lambda p: wrap(model(np.array([p[0] * scale, p[1] * scale, p[2], p[3], p[4]]), Bxy) - theta),
                                         p0, xtol=1e-14, ftol=1e-14, gtol=1e-14)
            q = res.x
            self.p = np.array([q[0] * scale, q[1] * scale, q[2], q[3], q[4]])
            self._model = model
        else:
            e = raw_error(theta, Bxy)
            psi = psi_deg(Bxy)
            X = fourier_basis(psi, self.harm)
            self.p = np.linalg.lstsq(X, e, rcond=None)[0]
        return self

    def corrected(self, Bxy):
        if self.kind == "affine":
            return self._model(self.p, Bxy)
        psi = psi_deg(Bxy)
        return psi - fourier_basis(psi, self.harm) @ self.p

    def residual(self, theta, Bxy):
        return wrap(self.corrected(Bxy) - theta)


CALS = {"affine": ("affine", ()), "harm4": ("harm", (1, 2, 3, 4)), "harm4_24": ("harm", (1, 2, 3, 4, 24, 48))}


def tile_symmetric(angles15, Bxyz):
    """Rotate a 0..15 deg (excl. 15) sweep to the full turn: B(th + 15k) = Rz(15k) B(th)."""
    out_t, out_B = [], []
    for k in range(N_TEETH):
        c, s = math.cos(math.radians(PITCH * k)), math.sin(math.radians(PITCH * k))
        R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        out_t.append(angles15 + PITCH * k)
        out_B.append(Bxyz @ R.T)
    return np.concatenate(out_t), np.concatenate(out_B)


# =========================================================================================== cases
T0_OFF, T0_TILT, T0_RING = (0.1, 0.1), (1.0, 0.0), (0.1, 0.0)
MECH = {"cold": {}, "push": dict(push=0.5), "gapm": dict(gap=-0.2), "gapp": dict(gap=0.2),
        "strong": dict(push=0.5, gap=-0.2), "hot": dict(T=T_HOT), "weakhot": dict(gap=0.2, T=T_HOT),
        "hotstrong": dict(T=T_HOT, push=0.5, gap=-0.2)}
SINGLES = {"offpx": dict(off=(0.1, 0.0)), "offmx": dict(off=(-0.1, 0.0)), "offpy": dict(off=(0.0, 0.1)), "offmy": dict(off=(0.0, -0.1)),
           "tiltx": dict(tilt=(1.0, 0.0)), "tilty": dict(tilt=(0.0, 1.0)), "ringpx": dict(ring_off=(0.1, 0.0)), "ringpy": dict(ring_off=(0.0, 0.1))}
GROUP_DESC = {"A": "ideal coaxial unit (C24-symmetric; sweep one 15 deg pitch, tile to the full turn)",
              "B": "worst-tolerance as-built unit: knob offset (0.1, 0.1) mm, tilt 1 deg about u, ring offset (0.1, 0) mm, then the conditions of group A on top",
              "C": "single tolerances, one at a time, released and cold (uncalibrated drift only)"}


def build_cases():
    C = {}
    for g, base in (("A", {}), ("B", dict(off=T0_OFF, tilt=T0_TILT, ring_off=T0_RING))):
        for suffix, kw in MECH.items():
            name = f"{g}_{suffix}"
            C[name] = (g, Cond(name, **{**base, **kw}))
    for suffix, kw in SINGLES.items():
        C[f"C_{suffix}"] = ("C", Cond(f"C_{suffix}", **kw))
    return C


CASES = build_cases()
LIN_MUS = (200, 500, 1000, 2000)                        # linear steel sweep, mu_r (material-sensitivity study)
NL_CASES = [n for n in CASES if n.startswith("A_")] + ["B_cold", "B_strong", "B_hotstrong", "C_tiltx"]      # saturating solves (others: linear only)
EXTRA_NL_CASES = ["A_cold", "A_strong", "A_weakhot", "B_cold"]
HYST = {"A_cold": ["nl_h160_cw", "nl_h160_ccw", "nl_h400_cw", "nl_h400_ccw"]}
REF_KEY = "lin1000"                   # calibration and table reference material (present in every case); "nl" is a material variant where it was run


def is_hyst(key):
    return key.endswith("_cw") or key.endswith("_ccw")


def pk(d):
    """plot/CSV material: saturating where it was run, else the reference linear steel"""
    return "nl" if "nl" in d else REF_KEY


def make_material(key, cond):
    if key == "none":
        return None
    if key.startswith("lin"):
        return Linear(float(key[3:]))
    hot = cond.T > 100.0
    hs, js = (1.3, 0.97) if hot else (1.0, 1.0)             # [ASSUMED] 176 C: 1010 low-field permeability x1.3, J_s x0.97
    if key == "nl":
        return Steel(hs, js, 0.0, "representative 1010 B-H, anhysteretic")
    if key == "nl_soft":
        return Steel(2.0 * hs, js, 0.0, "soft curve (H axis x2)")
    if key == "nl_hard":
        return Steel(0.5 * hs, js, 0.0, "hard curve (H axis /2)")
    if key.startswith("nl_h"):
        hc = float(key.split("_")[1][1:])
        return Steel(hs, js, hc, f"representative 1010 B-H with vector play Hc={hc:g} A/m")
    raise KeyError(key)


class Grid:
    """Angle grids. Linear materials and the ideal unit (group A) are solved at the 0.25 deg grid; the saturating solves on asymmetric
    units and the hysteresis runs are solved on coarser grids and their increment over the reference material is spline-interpolated."""

    def __init__(self, quick: bool, tiny: bool = False):
        self.quick, self.tiny = quick, tiny
        self.step_sym = 5.0 if tiny else (1.0 if quick else 0.25)
        self.step_asym = 15.0 if tiny else (3.0 if quick else 0.25)
        self.step_hyst = 5.0 if tiny else (1.0 if quick else 0.5)
        self.hyst_pitches = 4
        self.base = np.arange(0.0, PITCH, self.step_sym)

    def nl_step(self, name, key, mesh_key):
        g = CASES[name][0]
        if key.endswith("_cw") or key.endswith("_ccw"):
            return self.step_hyst
        if g == "A" and mesh_key == "prod":
            return self.step_sym
        if mesh_key == "prod_fullturn":
            return self.step_sym
        if not key.startswith("nl"):
            return self.step_asym
        if self.tiny:
            return 30.0 if (key == "nl" and (g == "B" or mesh_key == "notch")) else 60.0
        if key == "nl" and (g == "B" or mesh_key == "notch"):
            return 6.0 if self.quick else 2.0
        return 12.0 if self.quick else 4.0


def task_list(grid: Grid):
    tasks = []
    for name, (g, c) in CASES.items():
        keys = ["none", "linall"]
        if name in NL_CASES:
            keys.append("nl")
        if name in EXTRA_NL_CASES:
            keys += ["nl_soft", "nl_hard"]
        keys += HYST.get(name, [])
        for k in keys:
            tasks.append((name, k, "prod"))
    tasks.append(("A_cold", "lin1000", "prod_fullturn"))           # periodicity control
    tasks.append(("A_cold", "lin1000", "notch"))                    # standoff cut-out probe
    tasks.append(("A_cold", "nl", "notch"))
    # long jobs first
    def cost(t):
        name, k, mesh = t
        g = CASES[name][0]
        c = 1.0
        if is_hyst(k):
            return -1000.0                                   # longest jobs first
        if k.startswith("nl"):
            c *= 4
        if g != "A" or mesh in ("notch", "prod_fullturn"):
            c *= 20 if not grid.quick else 2
        return -c
    return sorted(tasks, key=cost)


_SOLVERS = {}
_GRID = None


def _init_worker(quick, tiny=False, cache_dir=None):
    global _GRID, _CACHE_DIR
    _GRID = Grid(quick, tiny)
    _CACHE_DIR = Path(cache_dir) if cache_dir else None
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(2)
    except Exception:
        pass
    nb.set_num_threads(2)


def get_solver(mesh_key):
    if mesh_key not in _SOLVERS:
        if mesh_key in ("prod", "prod_fullturn"):
            m = Mesh(2, 8, 2)
        elif mesh_key == "notch":
            m = Mesh(2, 8, 2, notch_pitches=NOTCH_PITCHES)
        elif mesh_key == "coarse":
            m = Mesh(1, 4, 1)
        elif mesh_key == "fine":
            m = Mesh(4, 16, 4)
        else:
            raise KeyError(mesh_key)
        _SOLVERS[mesh_key] = RingSolver(m)
    return _SOLVERS[mesh_key]


# standoff cut-out probe: pitches containing the three standoff directions (0, ~158, ~202 deg) +- one neighbour each
NOTCH_PITCHES = (0, 10, 11, 13, 14)


_CACHE_DIR = None


def run_task_cached(task):
    """run_task with a per-task pickle cache (so an interrupted or failed run keeps its finished sweeps)"""
    import pickle
    name, key, mesh_key = task
    if _CACHE_DIR is not None:
        f = _CACHE_DIR / f"{name}__{key}__{mesh_key}.pkl"
        if f.exists():
            return pickle.loads(f.read_bytes())
    out = run_task(task)
    if _CACHE_DIR is not None:
        tmp = _CACHE_DIR / (f"{name}__{key}__{mesh_key}.pkl.tmp")
        tmp.write_bytes(pickle.dumps(out))
        tmp.replace(_CACHE_DIR / f"{name}__{key}__{mesh_key}.pkl")
    return out


def run_task(task):
    name, key, mesh_key = task
    grid = _GRID
    g, cond = CASES[name]
    solver = get_solver(mesh_key)
    mat = None if key == "linall" else make_material(key, cond)
    t0 = time.time()
    if key == "linall":
        ang = grid.base if (g == "A" and mesh_key == "prod") else np.arange(0.0, 360.0, grid.step_asym)
        res = sweep_linear_multi(solver, cond, LIN_MUS, ang)
        outs = []
        for mu, o in res.items():
            o["wall_s"] = (time.time() - t0) / len(LIN_MUS)
            o["task"] = (name, f"lin{mu}", mesh_key)
            outs.append(o)
        return outs
    if key.endswith("_cw") or key.endswith("_ccw"):
        n = grid.hyst_pitches
        st = grid.step_hyst
        base = np.arange(0.0, PITCH, st)
        if key.endswith("_cw"):
            ang = np.arange(0.0, n * PITCH, st)
        else:
            ang = np.arange(n * PITCH, 0.0, -st)
        res = sweep(solver, cond, mat, ang)
        nb_ = len(base)
        sel = slice(len(ang) - nb_, len(ang))
        prev = slice(len(ang) - 2 * nb_, len(ang) - nb_)
        def to_base(sl):
            """Rotate the samples of pitch `sl` back into the base pitch: B(th + 15 m) = Rz(15 m) B(th)."""
            a = res["angles"][sl]
            m = np.round((a - a % PITCH) / PITCH).astype(int)
            base = a - PITCH * m
            order = np.argsort(base, kind="stable")
            Bf, Bs = np.zeros((len(a), 3)), np.zeros((len(a), 3))
            for i in range(len(a)):
                c, s_ = math.cos(math.radians(-PITCH * m[i])), math.sin(math.radians(-PITCH * m[i]))
                R = np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
                Bf[i], Bs[i] = R @ res["B_free"][sl][i], R @ res["B_steel"][sl][i]
            return base[order], Bf[order], Bs[order], order
        base_a, Bf_, Bs_, order = to_base(sel)
        _, _, Bs_prev, _ = to_base(prev)
        out = {k: (v[sel][order] if isinstance(v, np.ndarray) and v.ndim >= 1 and len(v) == len(ang) else v) for k, v in res.items()}
        out["B_free"], out["B_steel"], out["angles"] = Bf_, Bs_, base_a
        # periodic-regime check: previous pitch vs last pitch (B_steel difference, base frame)
        out["periodic_check_T"] = float(np.max(np.abs(Bs_prev - Bs_)))
    elif g == "A" and mesh_key == "prod":
        out = sweep(solver, cond, mat, grid.base)
    else:
        ang = np.arange(0.0, 360.0, grid.nl_step(name, key, mesh_key))
        out = sweep(solver, cond, mat, ang)
    out["wall_s"] = time.time() - t0
    out["task"] = task
    return out


# =========================================================================================== analysis helpers
def die_temp_C():
    return float(UI.sensor_thermal()["die_C"])


def sensor_eps(cond: Cond, variant: str) -> float:
    if cond.T < 100.0 or variant == "ideal":
        return 0.0
    if variant == "corrected":
        return SENSOR_EPS_RESID
    if variant == "uncorrected":
        return SENSOR_EPS_SLOPE * (die_temp_C() - 25.0)
    raise KeyError(variant)


SENSOR_VARIANTS = ("ideal", "corrected", "uncorrected")


def assemble(results, grid: Grid):
    """-> D[case][key] = dict(theta, B (n,3) total, Bfree, Bsteel, W, meta) on the full-turn grid of the case.

    Entries solved on a coarser grid (saturating asymmetric units, hysteresis) get the increment over their reference material
    (lin1000 for the first, then nl) spline-interpolated (periodic cubic) onto the fine grid; `increment_interpolated` marks them."""
    from scipy.interpolate import CubicSpline
    D = {}
    stage1, stage2 = [], []
    for r in results:
        name, key, mesh_key = r["task"]
        if mesh_key != "prod":
            D.setdefault("_" + mesh_key, {})[(name, key)] = r
            continue
        g = CASES[name][0]
        if g == "A":
            th, Bf = tile_symmetric(r["angles"], r["B_free"])
            _, Bs = tile_symmetric(r["angles"], r["B_steel"])
            W = np.tile(r["W"], N_TEETH)
        else:
            th, Bf, Bs, W = r["angles"], r["B_free"], r["B_steel"], r["W"]
        fine = grid.step_sym if g == "A" else grid.step_asym
        step = float(th[1] - th[0])
        ent = {"theta": th, "Bfree": Bf, "Bsteel": Bs, "W": W, "Bcell_max": float(np.max(r["Bcell_max"])), "Hcell_max": float(np.max(r["Hcell_max"])),
               "frac_knee": float(np.max(r["frac_knee"])), "iters": r["iters"], "wall_s": r["wall_s"], "periodic_check_T": r.get("periodic_check_T"),
               "increment_interpolated": False, "solve_step_deg": step}
        if step > fine + 1e-9:
            (stage1 if key == "nl" else stage2).append((name, key, ent, fine, step))
        else:
            D.setdefault(name, {})[key] = ent
    for stage, ref in ((stage1, "lin1000"), (stage2, "nl")):
        for name, key, ent, fine, step in stage:
            base = D[name][ref]
            ratio = int(round(step / fine))
            th = ent["theta"]
            incB = ent["Bsteel"] - base["Bsteel"][::ratio]
            incW = ent["W"] - base["W"][::ratio]
            tt = np.append(th, 360.0)
            ent["Bsteel"] = base["Bsteel"] + CubicSpline(tt, np.vstack([incB, incB[:1]]), bc_type="periodic")(base["theta"])
            ent["W"] = base["W"] + CubicSpline(tt, np.append(incW, incW[0]), bc_type="periodic")(base["theta"])
            ent["Bfree"], ent["theta"], ent["increment_interpolated"] = base["Bfree"], base["theta"], True
            D[name][key] = ent
    for name in CASES:
        for key, ent in D[name].items():
            ent["B"] = ent["Bfree"] + ent["Bsteel"]
    return D


def meas_xy(entry, cond, variant):
    Bm = -entry["B"][:, :2]
    return apply_sensor(Bm, sensor_eps(cond, variant))


def fit_indices(theta, step):
    """Cold-calibration fit angles: 0.5 + 10.25 k deg, k = 0..34 (35 angles on the 0.25 deg grid). The step is chosen coprime with the 15 deg tooth
    pitch, so the fit samples 35 different phases of a 24-fold ripple (a step that divides the pitch would see only three), and none lands on a
    detent centre. Every other angle of the cold run, and every other condition, validates."""
    n = len(theta)
    if step > 0.5:
        return np.arange(n)[::2]
    q = int(round(10.25 / step))
    q0 = int(round(0.5 / step))
    idx = q0 + q * np.arange(35)
    return idx[idx < n]


def cal_fit_all(theta, Bxy, idx):
    out = {}
    for cname, (kind, harm) in CALS.items():
        out[cname] = Cal(kind, harm).fit(theta[idx], Bxy[idx])
    return out


def analyse(D, grid: Grid):
    out = {"cases": {}, "calibration": {}, "fit_description": {}}
    # ------------- per-case raw numbers (sensor ideal)
    for name, (g, cond) in CASES.items():
        d = D[name]
        th = d[REF_KEY]["theta"]
        e_ring = {k: raw_error(th, meas_xy(d[k], cond, "ideal")) for k in d}
        e_none = e_ring["none"]
        rec = {"group": g, "condition": cond.meta(), "n_angles": int(len(th)), "step_deg": float(th[1] - th[0])}
        Bn = {k: np.linalg.norm(d[k]["B"], axis=1) for k in d}
        rec["B_mT"] = {k: [round(float(Bn[k].min() * 1e3), 4), round(float(Bn[k].max() * 1e3), 4)] for k in d}
        rec["Bxy_mT_range_ref"] = {"Bx": [float(d[REF_KEY]["B"][:, 0].min() * 1e3), float(d[REF_KEY]["B"][:, 0].max() * 1e3)],
                                   "By": [float(d[REF_KEY]["B"][:, 1].min() * 1e3), float(d[REF_KEY]["B"][:, 1].max() * 1e3)],
                                   "Bz": [float(d[REF_KEY]["B"][:, 2].min() * 1e3), float(d[REF_KEY]["B"][:, 2].max() * 1e3)]}
        rec["peak_uncal_deg"] = {k: float(np.max(np.abs(e_ring[k]))) for k in d}
        rec["peak_uncal_ring_attributable_deg"] = {k: float(np.max(np.abs(e_ring[k] - e_none))) for k in d if k != "none"}
        rec["steel"] = {k: {"Bcell_max_T": d[k]["Bcell_max"], "Hcell_max_A_per_m": d[k]["Hcell_max"], "frac_cells_above_1p5T": d[k]["frac_knee"]}
                        for k in d if k.startswith("nl") or k == "lin1000"}
        rec["ring_induced_B_uT_at_hall"] = {k: float(np.max(np.linalg.norm(d[k]["Bsteel"], axis=1)) * 1e6) for k in d if k != "none"}
        out["cases"][name] = rec
    # ------------- calibration (group A and B each fitted cold, validated everywhere else)
    for g, cold in (("A", "A_cold"), ("B", "B_cold")):
        names = [n for n, (gg, _) in CASES.items() if gg == g]
        cond0 = CASES[cold][1]
        th = D[cold][REF_KEY]["theta"]
        idx = fit_indices(th, float(th[1] - th[0]))
        mask_val = np.ones(len(th), bool)
        mask_val[idx] = False
        cal_ref = cal_fit_all(th, meas_xy(D[cold][REF_KEY], cond0, "ideal"), idx)
        cal_none = cal_fit_all(th, meas_xy(D[cold]["none"], cond0, "ideal"), idx)
        out["fit_description"][g] = {"fit_angles_deg": [float(th[idx[0]]), float(th[idx[1]]), "...", float(th[idx[-1]])], "n_fit": int(len(idx)),
                                     "condition": cond0.meta(), "reference_material": REF_KEY,
                                     "parameters": {c: [float(x) for x in cal_ref[c].p] for c in cal_ref}}
        tab = {}
        for name in names:
            cond = CASES[name][1]
            d = D[name]
            keys = [k for k in d if k != "none"]
            tab[name] = {}
            for var in SENSOR_VARIANTS:
                if var != "ideal" and cond.T < 100:
                    continue
                m0 = mask_val if name == cold else np.ones(len(th), bool)
                xy0 = meas_xy(d["none"], cond, var)
                for cname in CALS:
                    r_none = cal_none[cname].residual(th, xy0)
                    rec = {"noring_R": float(np.max(np.abs(r_none[m0])))}
                    for k in keys:
                        xy = meas_xy(d[k], cond, var)
                        r_ring = cal_ref[cname].residual(th, xy)
                        rec[k] = {"R": float(np.max(np.abs(r_ring[m0]))), "D": float(np.max(np.abs((r_ring - r_none)[m0]))),
                                  "R_at_detent_centres": float(np.max(np.abs(r_ring[np.isclose(th % PITCH, 0.0) & m0]))) if np.any(np.isclose(th % PITCH, 0.0) & m0) else None}
                    tab[name][f"{var}/{cname}"] = rec
        out["calibration"][g] = tab
    return out


# =========================================================================================== controls
def torque_crosscheck():
    """Independent check of the energy-method torque and axial force: forces on the permanent magnets from the steel's own field
    (steel magnetisation frozen), by reciprocity equal to the derivative of W = -mu0/2 sum V M.H_ext with re-induction (linear steel)."""
    mesh = Mesh(2, 8, 2)
    sol = RingSolver(mesh)
    mu = 1000.0
    vol = mesh.vol * 1e-9
    th0 = 3.75

    def state(cond, th):
        p = Pose(cond)
        He, _ = p.H_ext(th, mesh.cen)
        return p, He, sol.solve_linear(mu, He)

    def W_of(cond, th):
        p, He, M = state(cond, th)
        return -0.5 * MU0 * np.sum(vol * np.einsum("ij,ij->i", M, He))

    def U_of(cond, th, M):
        """Energy of the permanent magnets in the (frozen-M) steel field: rim blocks as 3x3x3 point dipoles, sensing magnet as a 9x9x5 grid."""
        p = Pose(cond)
        cen, Rm, half, Mv = p.rim(th)
        off1 = np.array([-1.0, 0.0, 1.0]) * (2.0 / 3.0)
        pts, mom = [], []
        for k in range(len(cen)):
            for ox in off1:
                for oy in off1:
                    for oz in off1:
                        pts.append(cen[k] + Rm[k] @ (np.array([ox, oy, oz]) * half[k]))
                        mom.append(Mv[k] * (8 * np.prod(half[k]) * 1e-9) / 27.0)
        Rb = p.Rt @ Rot.from_euler("z", th, degrees=True).as_matrix()
        g = (np.arange(9) + 0.5) / 9.0 * CEN_D - CEN_D / 2
        gz = (np.arange(5) + 0.5) / 5.0 * CEN_H
        vc = CEN_H * CEN_D * CEN_D / (9 * 9 * 5) * 1e-9            # cell volume (mm^3 -> m^3); only cells inside the circle count
        cells = [(x, y, z) for x in g for y in g for z in gz if x * x + y * y <= (CEN_D / 2) ** 2]
        vc = math.pi * (CEN_D / 2) ** 2 * CEN_H * 1e-9 / len(cells)
        for x, y, z in cells:
            pb = np.array([x, y, CEN_W[0] + z])
            pts.append(p._world(pb[None])[0])
            mom.append((p.br / MU0) * vc * Rb[:, 0])
        pts, mom = np.array(pts), np.array(mom)
        B = MU0 * field_sum(np.ascontiguousarray(pts), mesh.cen, mesh.Rm, mesh.half, M)
        return -float(np.sum(np.einsum("ij,ij->i", mom, B)))

    d = 0.1
    c0 = Cond("x")
    tqW = -(W_of(c0, th0 + d) - W_of(c0, th0 - d)) / (2 * math.radians(d))
    _, _, M0 = state(c0, th0)
    tqU = -(U_of(c0, th0 + d, M0) - U_of(c0, th0 - d, M0)) / (2 * math.radians(d))
    dz = 0.05
    FW = -(W_of(Cond("p", gap=dz), th0) - W_of(Cond("m", gap=-dz), th0)) / (2 * dz * 1e-3)
    FU = -(U_of(Cond("p", gap=dz), th0, M0) - U_of(Cond("m", gap=-dz), th0, M0)) / (2 * dz * 1e-3)
    out = {"material": "linear mu_r=1000", "theta_deg": th0,
           "torque_energy_method_uNm": tqW * 1e6, "torque_direct_force_on_magnets_uNm": tqU * 1e6, "torque_ratio": tqU / tqW if tqW else None,
           "axial_force_energy_method_mN": FW * 1e3, "axial_force_direct_mN": FU * 1e3, "axial_ratio": FU / FW if FW else None,
           "tolerance": "ratio within 0.9..1.1 (direct route: rim blocks as 27 point dipoles, sensing magnet as 9x9x5 grid)"}
    return out


def run_controls(quick: bool):
    c = {}
    # (0) constants equal the unit's own floorplan
    import ast
    src = {}
    for node in ast.parse((UNIT / "tools" / "floorplan.py").read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            try:
                val = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            tg = node.targets[0]
            if isinstance(tg, ast.Name):
                src[tg.id] = val
            elif isinstance(tg, ast.Tuple) and isinstance(val, tuple):
                for n_, v_ in zip(tg.elts, val):
                    src[n_.id] = v_
    assert tuple(src["ENCODER"]) == AXIS_UV and src["STEEL_KEEPOUT_R"] == 25.0 and src["DIE_W"] == HALL[2]
    assert src["MAGNET_D"] == CEN_D and src["MAGNET_NEAR_FACE_W"] == CEN_W[0]
    c["floorplan_constants"] = {"knob_axis": AXIS_UV, "die_w": src["DIE_W"], "steel_keepout_r": src["STEEL_KEEPOUT_R"], "ok": True}
    # (1) ring absent: sensing-magnet field at the die vs ui_calcs
    pose = Pose(Cond("ctl"))
    bc, br = pose.B_free(0.0, HALL[None])
    transverse = float(np.hypot(bc[0, 0], bc[0, 1]) * 1e3)
    total = float(np.linalg.norm(bc[0] + br[0]) * 1e3)
    ref = UI.magnet_b_mT(5.0)
    ref176 = UI.magnet_field()["b_nominal_176C_mT"]
    hot = Pose(Cond("ctl_hot", T=T_HOT)).B_free(0.0, HALL[None])
    hot_t = float(np.hypot(hot[0][0, 0], hot[0][0, 1]) * 1e3)
    c["ctl1_sensing_magnet_at_die"] = {"model_transverse_mT_20C": transverse, "ui_calcs_mT_20C": ref, "rel_err": transverse / ref - 1.0,
                                       "model_total_mT_with_rim_magnets_ring_absent": total,
                                       "model_transverse_mT_176C": hot_t, "ui_calcs_mT_176C": ref176, "rel_err_176C": hot_t / ref176 - 1.0,
                                       "tolerance": CTRL1_TOL}
    assert abs(transverse / ref - 1.0) < CTRL1_TOL and abs(hot_t / ref176 - 1.0) < CTRL1_TOL
    # (2a) cuboid kernel vs magpylib (random rotated cuboid, random points)
    rng = np.random.default_rng(7)
    rot = Rot.from_euler("zyx", [30, 20, -40], degrees=True)
    cen = np.array([[1.0, 2.0, 3.0]])
    half = np.array([[0.4, 0.9, 0.3]])
    obs = cen + rng.normal(size=(12, 3)) * np.array([2.5, 3.0, 2.0])
    Mloc = np.array([0.3, -0.5, 0.8]) * 1e6
    Mg = rot.as_matrix() @ Mloc
    Hk = field_sum(obs, cen, rot.as_matrix()[None], half, Mg[None])
    src_m = mp.magnet.Cuboid(dimension=tuple(2 * half[0]), polarization=tuple(Mloc * MU0), position=tuple(cen[0]), orientation=rot)
    Hm = src_m.getH(obs)                       # magpylib 5: H in A/m
    kern_err = float(np.max(np.abs(Hk - Hm)) / np.max(np.abs(Hm)))
    c["ctl2a_cuboid_kernel_vs_magpylib"] = {"max_rel_err": kern_err, "tolerance": 1e-6}
    assert kern_err < 1e-6
    # (2b) diametral cylinder on axis vs the closed form of ui_calcs at three gaps
    rows = []
    for gap in (5.0, 9.0, 15.0):
        cyl = mp.magnet.Cylinder(dimension=(CEN_D, CEN_H), polarization=(BR20, 0, 0), position=(0, 0, -4.0 + gap + CEN_H / 2))
        b = np.atleast_2d(cyl.getB(np.array([[0.0, 0.0, -4.0]])))[0]     # nearest face gap mm above the Hall plane
        rows.append({"gap_mm": gap, "magpylib_mT": float(np.hypot(b[0], b[1]) * 1e3), "closed_form_mT": UI.magnet_b_mT(gap),
                     "rel_err": float(np.hypot(b[0], b[1]) * 1e3 / UI.magnet_b_mT(gap) - 1.0)})
    c["ctl2b_diametral_cylinder_on_axis_vs_closed_form"] = {"rows": rows, "tolerance": CTRL2_TOL}
    assert all(abs(r["rel_err"]) < CTRL2_TOL for r in rows)
    # (2c) the MoM solver against a closed form: a linear sphere in a uniform field, M = 3 (mu-1)/(mu+2) H0
    R, h = 5.0, 0.5
    gg = np.arange(-R, R + 1e-9, h)
    gg = gg - gg.mean()
    X, Y, Z = np.meshgrid(gg, gg, gg, indexing="ij")
    P = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    P = P[np.linalg.norm(P, axis=1) < R]
    Ns = len(P)
    Rm = np.tile(np.eye(3), (Ns, 1, 1))
    hf = np.full((Ns, 3), h / 2)
    As = build_matrix(P, P, Rm, hf)
    H0 = np.array([1000.0, 0.0, 0.0])
    sph = []
    for mu in (3.0, 10.0):
        chi = mu - 1.0
        Ms = np.linalg.solve(np.eye(3 * Ns) - chi * As, chi * np.tile(H0, Ns)).reshape(-1, 3)
        Mex = 3 * (mu - 1) / (mu + 2) * H0[0]
        mom = float(Ms[:, 0].sum() * h ** 3)
        mex = Ns * h ** 3 * Mex                     # equal-volume sphere (the voxel sphere's own volume)
        obs_s = np.array([[3 * R, 0.0, 0.0], [0.0, 0.0, 3 * R]])
        Hc = field_sum(obs_s, P, Rm, hf, Ms)
        Hd = mex / (4 * math.pi * (3 * R) ** 3)
        sph.append({"mu_r": mu, "cells": Ns, "mean_M_ratio": float(Ms[:, 0].mean() / Mex), "moment_ratio": mom / mex,
                    "Hx_on_axis_3R_ratio": float(Hc[0, 0] / (2 * Hd)), "Hz_equator_3R_ratio": float(Hc[1, 0] / (-Hd))})
    c["ctl2c_mom_solver_sphere_in_uniform_field"] = {"rows": sph, "tolerance": CTRL2_TOL,
                                                     "note": "mu_r=3 is the asserted case; a voxelised sphere's demagnetising factor differs from 1/3 by about 1.5 %, "
                                                             "which is amplified at large mu_r (mu_r=10 shown for information)"}
    r3 = sph[0]
    assert abs(r3["mean_M_ratio"] - 1) < CTRL2_TOL and abs(r3["moment_ratio"] - 1) < CTRL2_TOL and abs(r3["Hx_on_axis_3R_ratio"] - 1) < CTRL2_TOL
    # (4) independent cross-check of the torque and axial force (virtual work vs forces on the magnets)
    tc = torque_crosscheck()
    c["ctl4_torque_force_cross_check"] = tc
    assert 0.9 < tc["torque_ratio"] < 1.1 and 0.9 < tc["axial_ratio"] < 1.1, tc
    # steel B-H table sanity
    st = Steel()
    c["bh_curve"] = {"mu_r_initial": st.chi0 + 1.0, "mu_r_max": float(np.max(st.m(np.geomspace(1, 1e5, 400)) * MU0 / (MU0 * np.geomspace(1, 1e5, 400)) + 1)),
                     "B_at_H": {f"{h_:g}": float(MU0 * (h_ + st.m(np.array([h_]))[0])) for h_ in (100, 400, 1000, 3000, 12000)}}
    return c


# =========================================================================================== geometry conflict
def geometry_conflict():
    from math import dist, hypot
    ax = AXIS_UV
    RING_OUT = R_OUT
    HEAD_R = 2.5
    TAB_FRONT_W, PKG_TOP = -4.78, -3.68
    cur_hol = [(83.0, 42.0), (83.0, 64.0), (138.0, 53.0)]
    j9_c, j9_size = (82.0, 53.0), (4.25, 13.0)
    tab_cur = (78.0, 142.0, 37.0, 69.0)

    def box_dist(c, size, p=ax):
        bx0, bx1, by0, by1 = c[0] - size[0] / 2, c[0] + size[0] / 2, c[1] - size[1] / 2, c[1] + size[1] / 2
        dx = max(bx0 - p[0], 0, p[0] - bx1)
        dy = max(by0 - p[1], 0, p[1] - by1)
        return hypot(dx, dy)

    out = {"ring": {"outer_r": RING_OUT, "tip_r": R_TIP, "w": list(RING_W)},
           "axial": {"ring_w": list(RING_W), "tab_front_face_w": TAB_FRONT_W, "tab_rear_face_w": -6.38, "fascia_rear_w": -3.0,
                     "front_face_headroom_under_ring_mm": RING_W[0] - TAB_FRONT_W, "front_face_headroom_to_fascia_mm": -3.0 - TAB_FRONT_W,
                     "standoff_body_w_span": [TAB_FRONT_W, -3.0], "standoff_overlaps_ring_axially_mm": min(-3.0, -3.0) - max(TAB_FRONT_W, RING_W[0]),
                     "rear_face_parts_clear_of_ring_underside_mm": RING_W[0] - (-6.38)}}
    cur = []
    for h in cur_hol:
        d = dist(h, ax)
        cur.append({"centre_uv": h, "centre_to_axis_mm": round(d, 3), "head_nearest_axis_mm": round(d - HEAD_R, 3),
                    "plan_clearance_to_ring_outer_mm": round(d - HEAD_R - RING_OUT, 3), "angle_deg": round(math.degrees(math.atan2(h[1] - ax[1], h[0] - ax[0])) % 360, 1)})
    out["current_standoffs"] = cur
    dj = box_dist(j9_c, j9_size)
    out["current_J9"] = {"centre_uv": j9_c, "box_nearest_axis_mm": round(dj, 3), "plan_clearance_to_ring_outer_mm": round(dj - RING_OUT, 3),
                         "face_assumed": "tab rear face (see README: a SM10B-SRSS-TB cannot fit in the 1.78 mm front-face gap; datasheet height not fetched)"}
    need = 29.0
    out["clearance_requirement"] = {"envelope_nearest_axis_mm": need, "basis": "ring outer 27.5 + 1.5 mm for ring position tolerance, adhesive fillet and assembly"}
    # proposal: three standoffs, tab 67.5 x 32 (u 77.5..145, v 37..69)
    tab_new = (77.5, 145.0, 37.0, 69.0)
    wall = 3.35                                   # hole r 1.35 + 2.0 mm wall (floorplan rule tab_holes_wall_ge_2mm)
    new_hol = [(tab_new[0] + wall, tab_new[2] + wall), (tab_new[0] + wall, tab_new[3] - wall), (tab_new[1] - wall, 53.0)]
    prop = []
    for h in new_hol:
        d = dist(h, ax)
        prop.append({"centre_uv": [round(h[0], 3), round(h[1], 3)], "centre_to_axis_mm": round(d, 3), "head_nearest_axis_mm": round(d - HEAD_R, 3),
                     "plan_clearance_to_ring_outer_mm": round(d - HEAD_R - RING_OUT, 3),
                     "wall_to_tab_edge_mm": round(min(h[0] - tab_new[0], tab_new[1] - h[0], h[1] - tab_new[2], tab_new[3] - h[1]) - 1.35, 3)})
    out["proposal"] = {"tab_u": tab_new[:2], "tab_v": tab_new[2:], "tab_size_mm": [tab_new[1] - tab_new[0], tab_new[3] - tab_new[2]],
                       "standoffs": prop,
                       "support_triangle_contains_hall": _inside_triangle(new_hol, ax),
                       "J9": {"centre_uv": j9_c, "clearance_to_tab_edge_mm": round(min(j9_c[0] - j9_size[0] / 2 - tab_new[0], 1e9), 3),
                              "hole_clearance_mm": [round(_box_circle(j9_c, j9_size, h, 1.35), 3) for h in new_hol],
                              "nearest_axis_mm": round(dj, 3), "note": "stays; rear face"},
                       "all_standoff_heads_ge_29": all(p["head_nearest_axis_mm"] >= need for p in prop),
                       "all_walls_ge_2mm": all(p["wall_to_tab_edge_mm"] >= 2.0 for p in prop),
                       "enclosed_by_tab_growth_mm": {"minus_u": tab_cur[0] - tab_new[0], "plus_u": tab_new[1] - tab_cur[1]}}
    # J9 on the front face would need r >= 29: how far must the tab grow towards -u?
    j9_front = {"needed_box_nearest_axis_mm": need, "centre_u_max": ax[0] - need - j9_size[0] / 2, "tab_edge_u_max_with_1mm_margin": ax[0] - need - j9_size[0] - 1.0}
    out["J9_if_front_face"] = j9_front
    assert out["proposal"]["all_standoff_heads_ge_29"] and out["proposal"]["all_walls_ge_2mm"] and out["proposal"]["support_triangle_contains_hall"]
    return out


def _inside_triangle(tri, p):
    (x1, y1), (x2, y2), (x3, y3) = tri
    d = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    a = ((y2 - y3) * (p[0] - x3) + (x3 - x2) * (p[1] - y3)) / d
    b = ((y3 - y1) * (p[0] - x3) + (x1 - x3) * (p[1] - y3)) / d
    return bool(a > 0 and b > 0 and 1 - a - b > 0)


def _box_circle(c, size, p, r):
    dx = max(c[0] - size[0] / 2 - p[0], 0, p[0] - (c[0] + size[0] / 2))
    dy = max(c[1] - size[1] / 2 - p[1], 0, p[1] - (c[1] + size[1] / 2))
    return math.hypot(dx, dy) - r


# =========================================================================================== further analyses
def delta_err(d, cond, key, variant="ideal"):
    th = d[REF_KEY]["theta"]
    e = raw_error(th, meas_xy(d[key], cond, variant))
    e0 = raw_error(th, meas_xy(d["none"], cond, variant))
    return th, e, e0


def harmonic_content(th, e, hs=(1, 2, 3, 4, 24)):
    """Amplitude (deg) of harmonics of the angle (full-turn grid) in e."""
    p = np.radians(th)
    out = {}
    for h in hs:
        a = 2 * np.mean(e * np.cos(h * p))
        b = 2 * np.mean(e * np.sin(h * p))
        out[str(h)] = float(math.hypot(a, b))
    return out


def summarise(D, A, grid: Grid):
    S = {}
    # ---- uncalibrated peaks and field range
    peaks = []
    for name, (g, cond) in CASES.items():
        d = D[name]
        th, e, e0 = delta_err(d, cond, REF_KEY)
        peaks.append((name, float(np.max(np.abs(e))), float(np.max(np.abs(e0))), float(np.max(np.abs(e - e0)))))
    S["peak_uncalibrated_deg"] = {"ring_present_ref": {n: round(p, 6) for n, p, _, _ in peaks}, "ring_absent": {n: round(q, 6) for n, _, q, _ in peaks},
                                  "ring_attributable_ref": {n: round(r, 6) for n, _, _, r in peaks},
                                  "max_ring_present": max(peaks, key=lambda t: t[1])[:2], "max_ring_absent": [max(peaks, key=lambda t: t[2])[0], max(peaks, key=lambda t: t[2])[2]],
                                  "max_ring_attributable": [max(peaks, key=lambda t: t[3])[0], max(peaks, key=lambda t: t[3])[3]]}
    # material family for the ring-attributable uncalibrated peak
    mat = {}
    for name, (g, cond) in CASES.items():
        d = D[name]
        mat[name] = {k: round(float(np.max(np.abs(delta_err(d, cond, k)[1] - delta_err(d, cond, k)[2]))), 6) for k in d if k != "none"}
    S["ring_attributable_uncal_by_material_deg"] = mat
    worst_mat = max(((n, k, v) for n, m in mat.items() for k, v in m.items()), key=lambda t: t[2])
    S["ring_attributable_uncal_max_over_all_materials_deg"] = {"case": worst_mat[0], "material": worst_mat[1], "value": worst_mat[2]}
    # |B| range
    rng = {}
    for key in ("none", REF_KEY):
        mn = min((float(np.linalg.norm(D[n][key]["B"], axis=1).min()), n) for n in CASES)
        mx = max((float(np.linalg.norm(D[n][key]["B"], axis=1).max()), n) for n in CASES)
        rng[key] = {"min_mT": round(mn[0] * 1e3, 4), "min_case": mn[1], "max_mT": round(mx[0] * 1e3, 4), "max_case": mx[1]}
    rel = max(float(np.max(np.abs(np.linalg.norm(D[n][REF_KEY]["B"], axis=1) / np.linalg.norm(D[n]["none"]["B"], axis=1) - 1.0))) for n in CASES)
    cold_gain = 1.0 + TEMPCO * 60.0
    rng["ring_changes_abs_B_by_max_fraction"] = rel
    rng["tolerance_extended"] = {"max_mT": round(rng[REF_KEY]["max_mT"] * 1.05 * cold_gain, 3), "min_mT": round(rng[REF_KEY]["min_mT"] * 0.95, 3),
                                 "basis": "Br +/-5 %, -40 C (+2.1 %) as in ui_calcs magnet_field; the study cases are 20 and 176 C only",
                                 "ui_calcs_b_max_mT": UI.magnet_field()["b_max_mT"], "ui_calcs_b_min_mT": UI.magnet_field()["b_min_mT"],
                                 "limit_80pct_of_100mT": B_RANGE_80PCT_MT}
    S["field_range"] = rng
    # ---- saturation
    sat = {}
    nlc = [n for n in CASES if "nl" in D[n]]
    for name in CASES:
        sat[name] = {k: {"Bcell_max_T": round(v["Bcell_max"], 4), "frac_above_1p5T": v["frac_knee"], "Hcell_max_A_per_m": round(v["Hcell_max"], 1)}
                     for k, v in D[name].items() if k in ("lin200", "lin1000", "lin2000", "nl", "nl_soft", "nl_hard")}
    S["saturation"] = sat
    S["saturation_summary"] = {"max_cell_B_nl_T": max(sat[n]["nl"]["Bcell_max_T"] for n in nlc),
                               "max_cell_B_nl_soft_T": max(sat[n]["nl_soft"]["Bcell_max_T"] for n in CASES if "nl_soft" in sat[n]),
                               "max_cell_B_lin2000_T": max(sat[n]["lin2000"]["Bcell_max_T"] for n in CASES),
                               "max_fraction_cells_above_1p5T_nl": max(sat[n]["nl"]["frac_above_1p5T"] for n in nlc),
                               "cases_with_saturating_solve": nlc,
                               "knee_note": "B of the representative curve at H=400 A/m is 1.0 T, 1.5 T at 1500 A/m, 1.9 T at 12 kA/m"}
    # ---- calibrated headline: cold cases with the ideal sensor, hot cases with the sensor drift corrected as in ui_calcs
    hl = {}
    for cname in CALS:
        rows = []
        for g in ("A", "B"):
            for name, tab in A["calibration"][g].items():
                var = "ideal" if CASES[name][1].T < 100 else "corrected"
                rec = tab[f"{var}/{cname}"]
                for k, v in rec.items():
                    if k != "noring_R":
                        rows.append((v["D"], v["R"], name, k))
        nohy = [r for r in rows if not is_hyst(r[3])]
        hy_ = [r for r in rows if is_hyst(r[3])]
        hl[cname] = {"max_D_all_variants_deg": list(max(rows)[:1]) + [max(rows)[2], max(rows)[3]],
                     "max_D_without_hysteresis_deg": [max(nohy)[0], max(nohy)[2], max(nohy)[3]],
                     "max_D_hysteresis_runs_deg": [max(hy_)[0], max(hy_)[2], max(hy_)[3]] if hy_ else None,
                     "max_D_linear_materials_deg": [max(r for r in rows if r[3].startswith("lin"))[0], max(r for r in rows if r[3].startswith("lin"))[2], max(r for r in rows if r[3].startswith("lin"))[3]],
                     "max_D_saturating_anhysteretic_deg": [max(r for r in rows if r[3] in ("nl", "nl_soft", "nl_hard"))[0], max(r for r in rows if r[3] in ("nl", "nl_soft", "nl_hard"))[2], max(r for r in rows if r[3] in ("nl", "nl_soft", "nl_hard"))[3]],
                     "max_R_total_all_variants_deg": [max(rows, key=lambda t: t[1])[1], max(rows, key=lambda t: t[1])[2], max(rows, key=lambda t: t[1])[3]]}
    S["calibrated_headline"] = hl
    # un-corrected sensor drift on hot cases
    unc = []
    for g in ("A", "B"):
        for name, tab in A["calibration"][g].items():
            rec = tab.get("uncorrected/harm4")
            if rec:
                unc.append((rec[REF_KEY]["R"], rec[REF_KEY]["D"], name))
    S["sensor_drift_uncorrected_harm4"] = {"max_R_total_deg": max(u[0] for u in unc), "max_D_deg": max(u[1] for u in unc), "eps": SENSOR_EPS_SLOPE * (die_temp_C() - 25.0),
                                           "die_C": die_temp_C(),
                                           "note": "X/Y sensitivity mismatch drift left uncorrected: a sensor term that is present with or without the ring; D is unaffected"}
    # ---- detent-centre versus between-detent for the headline B residual
    dc = {}
    for name in [n for n, (g, _) in CASES.items() if g == "B"]:
        rec = A["calibration"]["B"][name].get("ideal/harm4", {}).get(REF_KEY)
        if rec:
            dc[name] = {"R_all_angles": rec["R"], "R_detent_centres_only": rec["R_at_detent_centres"]}
    S["detent_centre_vs_all_angles_B_harm4"] = dc
    # ---- harmonic content of the ring-attributable uncalibrated error (B_cold, nl)
    th, e, e0 = delta_err(D["B_cold"], CASES["B_cold"][1], "nl")
    S["harmonics_ring_attributable_B_cold_nl_deg"] = harmonic_content(th, e - e0)
    thA, eA, e0A = delta_err(D["A_cold"], CASES["A_cold"][1], "nl")
    S["A_cold_nl_ring_attributable"] = {"peak_deg": float(np.max(np.abs(eA - e0A))), "harmonics_deg": harmonic_content(thA, eA - e0A),
                                        "note": "ideal coaxial unit; any 24th harmonic is the saturation-induced sin(24 theta) term; linear materials give exactly zero"}
    S["A_cold_linear_ring_attributable_peak_deg"] = {k: float(np.max(np.abs(delta_err(D["A_cold"], CASES["A_cold"][1], k)[1] - delta_err(D["A_cold"], CASES["A_cold"][1], k)[2])))
                                                     for k in ("lin200", "lin500", "lin1000", "lin2000")}
    # ---- hysteresis (group A)
    hy = {}
    for name in HYST:
        cond = CASES[name][1]
        d = D[name]
        th = d["nl"]["theta"]
        rec = {}
        for hc in ("h160", "h400"):
            if f"nl_{hc}_cw" not in d:
                continue
            ecw = raw_error(th, meas_xy(d[f"nl_{hc}_cw"], cond, "ideal"))
            eccw = raw_error(th, meas_xy(d[f"nl_{hc}_ccw"], cond, "ideal"))
            e0 = raw_error(th, meas_xy(d["none"], cond, "ideal"))
            enl = raw_error(th, meas_xy(d["nl"], cond, "ideal"))
            rec[hc] = {"peak_cw_deg": float(np.max(np.abs(ecw - e0))), "peak_ccw_deg": float(np.max(np.abs(eccw - e0))),
                       "cw_minus_ccw_peak_deg": float(np.max(np.abs(ecw - eccw))), "vs_anhysteretic_peak_deg": float(max(np.max(np.abs(ecw - enl)), np.max(np.abs(eccw - enl)))),
                       "ring_B_uT_cw_vs_ccw_max_diff": float(np.max(np.abs(d[f"nl_{hc}_cw"]["Bsteel"] - d[f"nl_{hc}_ccw"]["Bsteel"])) * 1e6),
                       "ring_B_uT_vs_anhysteretic_max_diff": float(max(np.max(np.abs(d[f"nl_{hc}_cw"]["Bsteel"] - d["nl"]["Bsteel"])), np.max(np.abs(d[f"nl_{hc}_ccw"]["Bsteel"] - d["nl"]["Bsteel"]))) * 1e6),
                       "periodic_regime_check_T": [d[f"nl_{hc}_cw"]["periodic_check_T"], d[f"nl_{hc}_ccw"]["periodic_check_T"]]}
        hy[name] = rec
    S["hysteresis"] = hy
    # ---- periodicity control
    pf = D["_prod_fullturn"][("A_cold", "lin1000")]
    th_full = pf["angles"]
    tiled = D["A_cold"]["lin1000"]
    S["periodicity_control"] = {"max_abs_dB_T_full_turn_vs_tiled": float(np.max(np.abs((pf["B_free"] + pf["B_steel"]) - tiled["B"]))),
                                "relative_to_Bpeak": float(np.max(np.abs((pf["B_free"] + pf["B_steel"]) - tiled["B"])) / np.max(np.abs(tiled["B"])))}
    assert S["periodicity_control"]["relative_to_Bpeak"] < 1e-8
    # ---- torque and axial force (energy method, W = -mu0/2 int M . H_ext)
    tq = {}
    for key in ("lin200", "lin1000", "lin2000", "nl"):
        W = D["A_cold"][key]["W"]
        th = D["A_cold"][key]["theta"]
        dth = math.radians(float(th[1] - th[0]))
        Wp = np.concatenate([W, W[:1]])
        tau = -(np.roll(W, -1) - np.roll(W, 1)) / (2 * dth)
        tq[key] = {"detent_torque_peak_mNm": round(float(np.max(np.abs(tau)) * 1e3), 4), "W_ripple_peak_to_peak_uJ": round(float((W.max() - W.min()) * 1e6), 4)}
    S["detent_torque"] = {"per_material": tq, "tooth_pitch_deg": PITCH, "positions": 24,
                          "note": "torque = -dW/dtheta of the induced-steel interaction energy -mu0/2 sum V M.H_ext (exact for linear steel; for the saturating curve it is an estimate, no hysteresis loss included)"}
    F = {}
    for key in ("lin200", "lin1000", "lin2000", "nl"):
        Wm = {n: float(np.mean(D[n][key]["W"])) for n in ("A_gapm", "A_cold", "A_gapp")}
        F[key] = {"axial_force_N_positive_is_away_from_ring": round(-(Wm["A_gapp"] - Wm["A_gapm"]) / 0.4e-3, 4)}
    S["axial_pull"] = {"per_material": F, "note": "central finite difference of the angle-averaged W over gap error -0.2..+0.2 mm; negative = pulls the knob toward the ring; includes the sensing magnet's own pull; "
                                                  "a stationary-fixture measurement is still needed for the feel target"}
    # ---- notch probe
    if "_notch" in D:
        N_ = D["_notch"]
        out = {}
        for k in ("lin1000", "nl"):
            r = N_[("A_cold", k)]
            th = r["angles"]
            e0 = raw_error(th, -(r["B_free"][:, :2]))
            Bt = r["B_free"] + r["B_steel"]
            e = raw_error(th, -(Bt[:, :2]))
            de = e - e0
            # a static harmonic fit through order 4 (a cold calibration takes it out)
            X = fourier_basis(psi_deg(-Bt[:, :2]), (1, 2, 3, 4))
            fit = X @ np.linalg.lstsq(X, de, rcond=None)[0]
            out[k] = {"step_deg": float(th[1] - th[0]), "peak_uncal_deg": float(np.max(np.abs(de))),
                      "peak_after_removing_harmonics_1_to_4_deg": float(np.max(np.abs(de - fit))),
                      "harmonics_deg": harmonic_content(th, de), "Bcell_max_T": float(np.max(r["Bcell_max"])),
                      "ring_B_uT_max": float(np.max(np.linalg.norm(r["B_steel"], axis=1)) * 1e6)}
        S["notched_ring_probe"] = {"notched_pitches": list(NOTCH_PITCHES), "angle_span_deg": len(NOTCH_PITCHES) * PITCH, "results": out,
                                   "meaning": "ring with the pitches that contain the three present standoff directions (0, 158, 202 deg) removed, released, cold, ideal coaxial unit"}
    return S


def refine_extrema(D, S, quick: bool):
    """Re-solve at 0.0625 and 0.03125 deg around the top-3 extrema of the ring-attributable uncalibrated error of the worst group B/C case."""
    best = max(((n, S["peak_uncalibrated_deg"]["ring_attributable_ref"][n]) for n, (g, _) in CASES.items() if g != "A"), key=lambda t: t[1])
    name = best[0]
    g, cond = CASES[name]
    solver = get_solver("prod")
    out = {"case": name, "note": "re-solved around the three largest |ring-attributable error| extrema; peaks at 0.25, 0.0625, 0.03125 deg spacing"}
    for key in ("lin1000", "nl"):
        if key not in D[name]:
            continue
        th, e, e0 = delta_err(D[name], cond, key)
        de = e - e0
        order = np.argsort(-np.abs(de))
        picks = []
        for i in order:
            if all(abs(((th[i] - th[j] + 180) % 360) - 180) > 3.0 for j in picks):
                picks.append(i)
            if len(picks) == 3:
                break
        rec = []
        for i in picks:
            vals = {"grid_peak": float(abs(de[i])), "theta0": float(th[i])}
            for step in (0.0625, 0.03125):
                span = 0.25 if not quick else 0.0
                angs = th[i] + np.arange(-span, span + 1e-9, step) if span else np.array([th[i]])
                r = sweep(solver, cond, make_material(key, cond), angs)
                ea = raw_error(angs, -(r["B_free"][:, :2] + r["B_steel"][:, :2]))
                e0a = raw_error(angs, -(r["B_free"][:, :2]))
                vals[f"refined_peak_step_{step}"] = float(np.max(np.abs(ea - e0a)))
            vals["rel_change_refined_vs_grid"] = abs(vals["refined_peak_step_0.0625"] - vals["grid_peak"]) / max(vals["grid_peak"], 1e-12)
            vals["rel_change_halving_step"] = abs(vals["refined_peak_step_0.03125"] - vals["refined_peak_step_0.0625"]) / max(vals["refined_peak_step_0.0625"], 1e-12)
            rec.append(vals)
        out[key] = rec
    return out


def convergence_study(quick: bool, step=None):
    """Halve the element size: coarse (1.0 mm), production (0.5 mm), fine (0.25 mm; linear everywhere, saturating at two angles)."""
    name = "B_cold"
    g, cond = CASES[name]
    step = step or (12.0 if quick else 6.0)
    ang = np.arange(0.0, 360.0, step)
    meshes = [("coarse", 1.0, (1, 4, 1)), ("prod", 0.5, (2, 8, 2))] + ([] if quick else [("fine", 0.25, (4, 16, 4))])
    out = {"case": name, "angles_deg_step": step, "levels": {}}
    peak = {}
    solvers = {}
    for mk, h, _ in meshes:
        sol = get_solver(mk) if mk != "fine" else RingSolver(Mesh(4, 16, 4))
        solvers[mk] = sol
        lv = {"element_mm": h, "cells": sol.N}
        for key in (("lin1000",) if mk == "fine" else ("lin200", "lin1000", "lin2000")):
            r = sweep(sol, cond, make_material(key, cond), ang)
            ea = raw_error(ang, -(r["B_free"][:, :2] + r["B_steel"][:, :2]))
            e0 = raw_error(ang, -(r["B_free"][:, :2]))
            lv[key] = {"peak_total_uncal_deg": float(np.max(np.abs(ea))), "peak_ring_attributable_deg": float(np.max(np.abs(ea - e0))),
                       "ring_B_peak_uT": float(np.max(np.linalg.norm(r["B_steel"], axis=1)) * 1e6)}
            peak[(mk, key)] = (lv[key], ea - e0)
        if mk != "fine":
            r = sweep(sol, cond, make_material("nl", cond), ang)
            ea = raw_error(ang, -(r["B_free"][:, :2] + r["B_steel"][:, :2]))
            e0 = raw_error(ang, -(r["B_free"][:, :2]))
            lv["nl"] = {"peak_total_uncal_deg": float(np.max(np.abs(ea))), "peak_ring_attributable_deg": float(np.max(np.abs(ea - e0))),
                        "ring_B_peak_uT": float(np.max(np.linalg.norm(r["B_steel"], axis=1)) * 1e6)}
            peak[(mk, "nl")] = (lv["nl"], ea - e0, r)
        out["levels"][mk] = lv
        if mk == "fine":
            pass
    # relative changes on halving
    seq = [m for m, _, _ in meshes]
    ch = {}
    for key in ("lin200", "lin1000", "lin2000", "nl"):
        ch[key] = {}
        for a, b in zip(seq[:-1], seq[1:]):
            if key in out["levels"][a] and key in out["levels"][b]:
                for q in ("peak_total_uncal_deg", "peak_ring_attributable_deg"):
                    x, y = out["levels"][a][key][q], out["levels"][b][key][q]
                    ch[key][f"{a}->{b}:{q}"] = abs(y - x) / max(abs(x), 1e-12)
    out["relative_change_on_halving"] = ch
    last = (seq[-2], seq[-1])
    out["criterion"] = (f"control 3: halving {last[0]} -> {last[1]} changes the peak total angle error (linear mu_r=1000) by < {CONV_TOL:.0%}. "
                        "The ring-attributable part of that error is reported separately and is converged more slowly (thin high-permeability plate, piecewise-uniform magnetisation)")
    out["pass"] = bool(ch["lin1000"][f"{last[0]}->{last[1]}:peak_total_uncal_deg"] < CONV_TOL)
    ring_prod = out["levels"][last[0]]["lin1000"]["peak_ring_attributable_deg"]
    ring_fine = out["levels"][last[1]]["lin1000"]["peak_ring_attributable_deg"]
    out["ring_attributable_change_on_halving"] = abs(ring_fine - ring_prod) / max(ring_prod, 1e-12)
    out["mesh_uncertainty_factor_on_ring_part"] = max(1.0, ring_fine / max(ring_prod, 1e-12))
    out["ring_induced_B_peak_uT_by_level"] = {m: out["levels"][m]["lin1000"]["ring_B_peak_uT"] for m in out["levels"]}
    out["saturating_fine_mesh"] = "not run (cost); saturating coarse -> production change is in `relative_change_on_halving.nl`"
    return out


# =========================================================================================== verdict
CRITERIA = {
    "pool_deg": POOL_DEG,
    "ring_share_deg": RING_SHARE_DEG,
    "derivation": ("ui_calcs/U24: 1.0 deg absolute budget minus the 0.40 deg non-repeatable error (3.5 sigma noise + stray field + quantisation + 0.057 deg gain residual) "
                   "leaves 0.60 deg for calibration residual, magnet and mechanism. ui_calcs allocates nothing of it. Equal thirds give 0.20 deg to the mechanism; "
                   "the ring is one mechanism part, so it may use half of that third: 0.10 deg."),
    "P1": "ring-attributable calibrated residual D <= 0.10 deg (cold calibration harm4, validated on non-fit angles and all other conditions, every material variant incl. soft/hard curves and Hc=400 A/m hysteresis, sensor drift corrected as in ui_calcs)",
    "P2": "absolute calibrated residual R of the worst as-built unit with the ring <= 0.60 deg (the whole pool)",
    "P3": "|B| at the die stays inside 80 % of the +/-100 mT range with the ui_calcs tolerances (<= 80 mT) and the ring changes |B| by < 1 %",
    "P4": "all controls pass (ui_calcs 55.7 mT within 2 %, analytic cases within 1 %, convergence < 10 % on halving)",
    "inconclusive_if": "D is within a factor 2 of the share (the B-H curve and the coil/standoff/mount details are not measured)",
}


def verdict(S, A, conv, ctrl):
    hl = S["calibrated_headline"]["harm4"]
    mesh_f = conv.get("mesh_uncertainty_factor_on_ring_part", 1.0)
    Dmax = hl["max_D_all_variants_deg"][0] * mesh_f
    Draw = hl["max_D_all_variants_deg"][0]
    Dnohy = hl["max_D_without_hysteresis_deg"][0] * mesh_f
    Rmax = hl["max_R_total_all_variants_deg"][0]
    Dmax_unc = S["ring_attributable_uncal_max_over_all_materials_deg"]["value"] * mesh_f
    b_ext = S["field_range"]["tolerance_extended"]["max_mT"]
    Rmax = Rmax * mesh_f
    p = {"P1_D_le_share": bool(Dmax <= RING_SHARE_DEG), "P2_R_le_pool": bool(Rmax <= POOL_DEG),
         "P3_field": bool(b_ext <= B_RANGE_80PCT_MT and S["field_range"]["ring_changes_abs_B_by_max_fraction"] < 0.01),
         "P4_controls_and_convergence": bool(conv["pass"])}
    if all(p.values()) and Dmax <= RING_SHARE_DEG / 2.0 and Dmax_unc <= RING_SHARE_DEG / 2.0:
        v = "PASS"
    elif not p["P1_D_le_share"]:
        v = "FAIL"
    else:
        v = "INCONCLUSIVE"
    tq = S["detent_torque"]["per_material"]["nl"]["detent_torque_peak_mNm"]
    coil = {k: UI.stray_field()["cases"][k]["angle_error_peak_deg"] for k in ("nopan_60000_bare", "pan_31000_bare", "nopan_60000_base_roof", "pan_31000_base_roof")}
    totals = {"basis": "ring D (mesh-adjusted, all variants) and ring D without hysteresis, added to the existing worst-case stray-field allowance (ui_calcs stray_field, no ring in that calculation)",
              "coil_allowance_deg": coil,
              "with_hysteresis": {k: {"linear_sum_deg": Dmax + c, "rss_deg": math.hypot(Dmax, c)} for k, c in coil.items()},
              "without_hysteresis": {k: {"linear_sum_deg": Dnohy + c, "rss_deg": math.hypot(Dnohy, c)} for k, c in coil.items()},
              "pool_left_for_calibration_magnet_and_rest_of_mechanism_deg": POOL_DEG - Dmax,
              "nonrepeatable_plus_ring_deg": UI.stray_field()["cases"]["nopan_60000_bare"]["nonrepeatable_error_peak_deg"] + Dmax,
              "absolute_budget_deg": 1.0}
    return {"verdict_angle_error_budget": v, "totals_with_coil_allowance": totals, "criteria": p, "D_max_deg_as_computed": Draw, "mesh_uncertainty_factor": mesh_f, "D_max_deg": Dmax, "D_max_without_hysteresis_deg": Dnohy,
            "R_total_max_deg": Rmax, "D_uncal_max_deg": Dmax_unc, "share_deg": RING_SHARE_DEG,
            "margin_factor_on_share": RING_SHARE_DEG / max(Dmax, 1e-12), "margin_factor_without_hysteresis": RING_SHARE_DEG / max(Dnohy, 1e-12),
            "detent_function": {"peak_detent_torque_mNm": tq, "spec_peak_torque_mNm": [25, 45], "spec_average_torque_mNm": [18, 30],
                                "ratio_to_spec_average_low": tq / 18.0, "verdict": "FAIL" if tq < 1.0 else "check"}}


# =========================================================================================== outputs
def write_csv(D, outdir: Path):
    (outdir / "raw").mkdir(exist_ok=True)
    for name in ("A_cold", "A_strong", "A_weakhot", "B_cold", "B_strong", "B_hotstrong", "C_tiltx", "C_offpx"):
        cond = CASES[name][1]
        d = D[name]
        mk = pk(d)
        th = d[mk]["theta"]
        e = raw_error(th, meas_xy(d[mk], cond, "ideal"))
        e0 = raw_error(th, meas_xy(d["none"], cond, "ideal"))
        with open(outdir / "raw" / f"{name}.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["material", "theta_deg", "Bx_mT", "By_mT", "Bz_mT", "Bx_noring_mT", "By_noring_mT", "Bz_noring_mT", "steel_Bx_uT", "steel_By_uT", "steel_Bz_uT",
                        "err_uncal_ring_deg", "err_uncal_noring_deg"])
            for i in range(len(th)):
                B, B0, Bs = d[mk]["B"][i], d["none"]["B"][i], d[mk]["Bsteel"][i]
                w.writerow([mk, f"{th[i]:.4f}"] + [f"{x*1e3:.6f}" for x in B] + [f"{x*1e3:.6f}" for x in B0] + [f"{x*1e6:.5f}" for x in Bs] + [f"{e[i]:.7f}", f"{e0[i]:.7f}"])


def make_plots(D, A, S, conv, outdir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    (outdir / "plots").mkdir(exist_ok=True)
    plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.3, "font.size": 9})
    col = {"x": "#1f77b4", "y": "#d62728", "z": "#2ca02c"}
    # 1 raw field
    d = D["A_cold"]["nl"]
    th = d["theta"]
    fig, ax = plt.subplots(3, 1, figsize=(8.5, 9))
    for i, c in enumerate("xyz"):
        ax[0].plot(th, d["B"][:, i] * 1e3, color=col[c], label=f"B{c}")
    ax[0].set_ylabel("B at the die, mT")
    ax[0].set_title("A0 ring, ideal coaxial unit, released, 20 C, saturating 1010: raw Bx, By, Bz over the full turn")
    ax[0].legend(ncol=3)
    m = th <= 30.0
    for i, c in enumerate("xyz"):
        ax[1].plot(th[m], d["Bsteel"][m, i] * 1e6, color=col[c], label=f"steel B{c}")
    ax[1].set_ylabel("steel contribution, uT")
    ax[1].set_title("Ring-induced part (two tooth pitches): follows the rotating sensing magnet, no 24-fold ripple in X/Y")
    ax[1].legend(ncol=3)
    db = D["B_cold"]["nl"]
    mB = db["theta"] <= 30.0
    for i, c in enumerate("xyz"):
        ax[2].plot(db["theta"][mB], db["Bsteel"][mB, i] * 1e6, color=col[c], label=f"steel B{c}")
    ax[2].set_xlabel("knob angle, deg")
    ax[2].set_ylabel("steel contribution, uT")
    ax[2].set_title("Same for the worst-tolerance as-built unit (group B)")
    ax[2].legend(ncol=3)
    fig.tight_layout()
    fig.savefig(outdir / "plots" / "raw_field_vs_angle.png")
    plt.close(fig)
    # 2 uncalibrated error
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 7.5), sharex=True)
    for name, c in (("B_cold", "#1f77b4"), ("B_hotstrong", "#d62728"), ("C_tiltx", "#2ca02c"), ("C_offpx", "#9467bd")):
        cond = CASES[name][1]
        th_, e, e0 = delta_err(D[name], cond, pk(D[name]))
        ax[0].plot(th_, e, color=c, lw=1.0, label=f"{name} with ring")
        ax[0].plot(th_, e0, color=c, lw=1.0, ls="--", label=f"{name} no ring")
        ax[1].plot(th_, e - e0, color=c, lw=1.0, label=name)
    ax[0].set_ylabel("uncalibrated error, deg")
    ax[0].set_title("Angle error versus knob angle (raw atan2 of the sensor X/Y)")
    ax[0].legend(ncol=2, fontsize=7)
    ax[1].set_ylabel("ring-attributable, deg")
    ax[1].set_xlabel("knob angle, deg")
    ax[1].axhline(RING_SHARE_DEG, color="k", ls=":")
    ax[1].axhline(-RING_SHARE_DEG, color="k", ls=":")
    ax[1].set_title("with ring minus without ring (dotted: the ring's share +/-0.10 deg)")
    ax[1].legend(ncol=4, fontsize=7)
    fig.tight_layout()
    fig.savefig(outdir / "plots" / "angle_error_vs_angle.png")
    plt.close(fig)
    # 3 calibrated residual group B
    cold = "B_cold"
    th0 = D[cold][REF_KEY]["theta"]
    idx = fit_indices(th0, float(th0[1] - th0[0]))
    cal = Cal(*CALS["harm4"]).fit(th0[idx], meas_xy(D[cold][REF_KEY], CASES[cold][1], "ideal")[idx])
    cal0 = Cal(*CALS["harm4"]).fit(th0[idx], meas_xy(D[cold]["none"], CASES[cold][1], "ideal")[idx])
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 7.5), sharex=True)
    for name, c in (("B_push", "#1f77b4"), ("B_gapm", "#ff7f0e"), ("B_strong", "#2ca02c"), ("B_hot", "#d62728"), ("B_hotstrong", "#9467bd")):
        cond = CASES[name][1]
        d = D[name]
        var = "corrected"
        r = cal.residual(th0, meas_xy(d[REF_KEY], cond, var))
        r0 = cal0.residual(th0, meas_xy(d["none"], cond, var))
        ax[0].plot(th0, r, color=c, lw=1.0, label=f"{name} (ring)")
        ax[1].plot(th0, r - r0, color=c, lw=1.0, label=name)
    ax[0].set_ylabel("calibrated residual, deg")
    ax[0].set_title("One fixed cold calibration (harmonic table, 35 angles), validated on all angles and conditions; the two large curves are the hot sensor gain residual (0.057 deg), present without the ring")
    ax[0].title.set_fontsize(8)
    ax[0].legend(ncol=3, fontsize=7)
    ax[1].set_ylabel("ring-attributable D, deg")
    ax[1].set_xlabel("knob angle, deg")
    ax[1].axhline(RING_SHARE_DEG, color="k", ls=":")
    ax[1].axhline(-RING_SHARE_DEG, color="k", ls=":")
    ax[1].legend(ncol=3, fontsize=7)
    fig.tight_layout()
    fig.savefig(outdir / "plots" / "calibrated_residual.png")
    plt.close(fig)
    # 4 summary of D by material
    fig, ax = plt.subplots(figsize=(9, 5.5))
    names = [n for n, (g, _) in CASES.items() if g in ("A", "B")]
    keys = ["lin200", "lin500", "lin1000", "lin2000", "nl", "nl_soft", "nl_hard", "nl_h160_cw", "nl_h400_cw", "nl_h400_ccw"]
    mx = {}
    for k in keys:
        v = []
        for n in names:
            g = CASES[n][0]
            rec = A["calibration"][g][n].get("corrected/harm4") or A["calibration"][g][n].get("ideal/harm4")
            if CASES[n][1].T < 100:
                rec = A["calibration"][g][n]["ideal/harm4"]
            if k in rec:
                v.append(rec[k]["D"])
        mx[k] = max(v) if v else 0.0
    ax.bar(range(len(keys)), [mx[k] for k in keys], color="#1f77b4")
    ax.axhline(RING_SHARE_DEG, color="k", ls=":", label="ring share 0.10 deg")
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(keys, rotation=40, ha="right")
    ax.set_ylabel("max over cases of the calibrated ring-attributable D, deg")
    ax.set_title("Material sensitivity of the ring's calibrated residual (A and B groups)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "plots" / "material_sensitivity.png")
    plt.close(fig)
    # 4b hysteresis (ideal unit, one tooth pitch, both rotation directions)
    if "nl_h160_cw" in D["A_cold"]:
        d = D["A_cold"]
        cond = CASES["A_cold"][1]
        th = d["nl"]["theta"]
        e0 = raw_error(th, meas_xy(d["none"], cond, "ideal"))
        mpt = th < PITCH
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        for key, c, ls, lab in (("nl", "k", "-", "anhysteretic"), ("nl_h160_cw", "#1f77b4", "-", "Hc 160 A/m, clockwise"), ("nl_h160_ccw", "#1f77b4", "--", "Hc 160 A/m, counter-clockwise"),
                                ("nl_h400_cw", "#d62728", "-", "Hc 400 A/m, clockwise"), ("nl_h400_ccw", "#d62728", "--", "Hc 400 A/m, counter-clockwise")):
            ax.plot(th[mpt], (raw_error(th, meas_xy(d[key], cond, "ideal")) - e0)[mpt], color=c, ls=ls, lw=1.3, label=lab)
        ax.axhline(RING_SHARE_DEG, color="k", ls=":")
        ax.axhline(-RING_SHARE_DEG, color="k", ls=":")
        ax.set_xlabel("knob angle within one tooth pitch, deg")
        ax.set_ylabel("ring-attributable angle error, deg")
        ax.set_title("Steel hysteresis (vector play model, periodic regime): the error reverses with rotation direction")
        ax.title.set_fontsize(9)
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        fig.savefig(outdir / "plots" / "hysteresis.png")
        plt.close(fig)
    # 5 steel flux density
    fig, ax = plt.subplots(figsize=(9, 5))
    ns = list(CASES)
    ns = [n for n in ns if "nl" in S["saturation"][n]]
    ax.bar(range(len(ns)), [S["saturation"][n]["nl"]["Bcell_max_T"] for n in ns], color="#d62728")
    ax.axhline(1.5, color="k", ls=":", label="1.5 T")
    ax.set_xticks(range(len(ns)))
    ax.set_xticklabels(ns, rotation=70, ha="right", fontsize=7)
    ax.set_ylabel("highest cell flux density in the ring, T")
    ax.set_title("Steel flux density with the saturating 1010 curve (any angle)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "plots" / "steel_flux_density.png")
    plt.close(fig)
    # 6 convergence
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for key, c in (("lin200", "#1f77b4"), ("lin1000", "#2ca02c"), ("lin2000", "#d62728"), ("nl", "#9467bd")):
        xs, ys = [], []
        for mk in ("coarse", "prod", "fine"):
            lv = conv["levels"].get(mk, {})
            if key in lv:
                xs.append(lv["element_mm"])
                ys.append(lv[key]["peak_ring_attributable_deg"])
        ax.plot(xs, ys, "o-", color=c, label=key)
    ax.set_xscale("log")
    ax.invert_xaxis()
    ax.set_xlabel("element size, mm")
    ax.set_ylabel(f"peak ring-attributable error, deg (case B_cold, {conv.get('angles_deg_step', 0):g} deg grid)")
    ax.set_title("Mesh convergence")
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "plots" / "mesh_convergence.png")
    plt.close(fig)


def r6(x):
    """round floats to 6 significant digits for a stable results.json"""
    if isinstance(x, dict):
        return {k: r6(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [r6(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(f"{float(x):.6g}")
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="coarse angle grids and no fine mesh: a smoke test, not the study")
    ap.add_argument("--tiny", action="store_true", help="debug grids (implies --quick)")
    ap.add_argument("--cache-dir", type=Path, help="keep one pickle per finished sweep here and reuse them on a rerun")
    ap.add_argument("--save-raw", type=Path, help="pickle the raw sweep results here")
    ap.add_argument("--load-raw", type=Path, help="skip the sweeps and reuse a pickle written by --save-raw")
    ap.add_argument("--skip-convergence", action="store_true", help="debug only: skip the mesh-convergence stage (the verdict is then not valid)")
    ap.add_argument("--workers", type=int, default=max(1, min(6, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()
    args.quick = args.quick or args.tiny
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    grid = Grid(args.quick, args.tiny)
    log = lambda *a: print(f"[{time.time()-t0:7.1f}s]", *a, file=sys.stderr, flush=True)
    log("controls")
    ctrl = run_controls(args.quick)
    log("controls pass")
    if args.load_raw:
        import pickle
        results = pickle.loads(args.load_raw.read_bytes())
        log(f"loaded {len(results)} raw results from {args.load_raw}")
    else:
        tasks = task_list(grid)
        log(f"{len(tasks)} sweep tasks on {args.workers} workers")
        results = []
        if args.cache_dir:
            args.cache_dir.mkdir(parents=True, exist_ok=True)
        with ProcessPoolExecutor(args.workers, initializer=_init_worker, initargs=(args.quick, args.tiny, str(args.cache_dir) if args.cache_dir else None)) as ex:
            futs = [ex.submit(run_task_cached, t) for t in tasks]
            done = 0
            for t, fu in zip(tasks, futs):
                r = fu.result()
                results.extend(r if isinstance(r, list) else [r])
                done += 1
                if done % 10 == 0:
                    log(f"  {done}/{len(tasks)} tasks collected (submission order)")
        if args.save_raw:
            import pickle
            args.save_raw.write_bytes(pickle.dumps(results))
    log("assemble and analyse")
    D = assemble(results, grid)
    A = analyse(D, grid)
    S = summarise(D, A, grid)
    log("extremum refinement")
    ref = refine_extrema(D, S, args.quick)
    log("convergence study")
    conv = {"pass": True, "skipped": True, "levels": {}} if args.skip_convergence else convergence_study(args.quick)
    geo = geometry_conflict()
    ver = verdict(S, A, conv, ctrl)
    log("verdict", ver["verdict_angle_error_budget"], "| detent function", ver["detent_function"]["verdict"])
    mesh_info = {"production": {"cells": get_solver("prod").N, "element_mm": 0.5, "phi_cells_per_pitch": 8, "z_layers": 2},
                 "volume_mm3": float(get_solver("prod").mesh.vol.sum()), "analytic_volume_mm3": float(math.pi * (R_OUT ** 2 - R_ROOT ** 2) + 0.5 * math.pi * (R_ROOT ** 2 - R_TIP ** 2))}
    peaks_all = [(c["peak_uncal_deg"][k], n, k) for n, c in A["cases"].items() for k in c["peak_uncal_deg"] if k != "none"]
    peaks_attr = [(c["peak_uncal_ring_attributable_deg"][k], n, k) for n, c in A["cases"].items() for k in c["peak_uncal_ring_attributable_deg"]]
    peaks_attr_nohy = [t for t in peaks_attr if not is_hyst(t[2])]
    headline = {
        "verdict_angle_error_budget": ver["verdict_angle_error_budget"], "verdict_detent_function": ver["detent_function"]["verdict"],
        "peak_uncalibrated_error_deg": {"ring_present_max": list(max(peaks_all)), "ring_absent_max": max(c["peak_uncal_deg"]["none"] for c in A["cases"].values()),
                                        "ring_attributable_max_no_hysteresis": list(max(peaks_attr_nohy)), "ring_attributable_max_with_hysteresis": list(max(peaks_attr))},
        "calibrated_residual_deg": {"D_max_all_variants_mesh_adjusted": ver["D_max_deg"], "D_max_without_hysteresis_mesh_adjusted": ver["D_max_without_hysteresis_deg"],
                                    "R_total_max_mesh_adjusted": ver["R_total_max_deg"], "mesh_uncertainty_factor": ver["mesh_uncertainty_factor"], "share_deg": RING_SHARE_DEG},
        "B_mT": {"weakest_with_ring": S["field_range"]["lin1000"]["min_mT"], "strongest_with_ring": S["field_range"]["lin1000"]["max_mT"],
                 "ring_changes_B_by_at_most_fraction": S["field_range"]["ring_changes_abs_B_by_max_fraction"], "with_ui_calcs_tolerances": S["field_range"]["tolerance_extended"]},
        "steel": S["saturation_summary"],
        "hysteresis_D_deg": {k: v for k, v in S["hysteresis"]["A_cold"].items()},
        "torque_and_pull": {"detent_torque_peak_mNm": S["detent_torque"]["per_material"]["nl"]["detent_torque_peak_mNm"], "axial_force_N": S["axial_pull"]["per_material"]["nl"]},
        "geometry": {"standoffs_current_clearance_mm": [p["plan_clearance_to_ring_outer_mm"] for p in geo["current_standoffs"]],
                     "standoffs_proposed_clearance_mm": [p["plan_clearance_to_ring_outer_mm"] for p in geo["proposal"]["standoffs"]], "proposed_tab_mm": geo["proposal"]["tab_size_mm"]},
    }
    import importlib.metadata as md
    env = {p: md.version(p) for p in ("numpy", "scipy", "matplotlib", "magpylib", "numba", "threadpoolctl")}
    env["python"] = sys.version.split()[0]
    out = {
        "schema": "temper.ui-board.knob-ring.v1", "headline": headline, "environment": env, "generated_by": "evidence/knob-ring/ring_study.py", "quick_mode": args.quick, "tiny_mode": args.tiny,
        "inputs": {"geometry_A0": {"ring": {"outer_r": R_OUT, "root_r": R_ROOT, "tip_r": R_TIP, "w": list(RING_W), "teeth": N_TEETH, "tooth_deg": TOOTH_W},
                                  "rim_magnets": {"count": 24, "r": RIM_R, "size_r_t_ax_mm": list(RIM_SIZE), "w": list(RIM_W), "Br_20C_T": BR20, "magnetisation": "+w"},
                                  "sensing_magnet": {"d_h_mm": [CEN_D, CEN_H], "w": list(CEN_W), "Br_20C_T": BR20, "magnetisation": "+u at 0 deg, diametral"},
                                  "hall_uvw": [110.0, 53.0, -4.0], "temp_coefficient_per_K": TEMPCO},
                   "steel_curve_H_A_per_m": H_TAB.tolist(), "steel_curve_B_T": B_TAB.tolist(),
                   "steel_curve_status": "representative handbook-typical 1010 anhysteretic curve, NOT a measured curve; soft/hard family = H axis x2 / x0.5; hot: H axis x1.3, J_s x0.97 [ASSUMED]",
                   "sensor_model": {"eps_residual_after_temp_correction": SENSOR_EPS_RESID, "eps_uncorrected_slope_per_K": SENSOR_EPS_SLOPE, "die_C_hot_case": die_temp_C(),
                                    "offset_drift": "not modelled (no sourced number); the cold calibration fits a static offset"},
                   "coil_allowance_deg": {"worst_bare_nopan_60kHz": UI.stray_field()["cases"]["nopan_60000_bare"]["angle_error_peak_deg"],
                                          "assembled_nopan_base_roof": UI.stray_field()["cases"]["nopan_60000_base_roof"]["angle_error_peak_deg"],
                                          "pan_31kHz_bare": UI.stray_field()["cases"]["pan_31000_bare"]["angle_error_peak_deg"]},
                   "grid": {"step_sym_deg": grid.step_sym, "step_asym_deg": grid.step_asym, "hysteresis_pitches": grid.hyst_pitches}},
        "criteria_stated_before_results": CRITERIA, "mesh": mesh_info, "controls": ctrl, "group_descriptions": GROUP_DESC,
        "summary": S, "calibration": A["calibration"], "calibration_fit": A["fit_description"], "cases": A["cases"],
        "refinement_at_extrema": ref, "convergence": conv, "geometry_conflict": geo, "verdict": ver,
    }
    (args.out / "results.json").write_text(json.dumps(r6(out), indent=1, sort_keys=True) + "\n")
    write_csv(D, args.out)
    make_plots(D, A, S, conv, args.out)
    log("done")
    print(json.dumps(r6(ver), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
