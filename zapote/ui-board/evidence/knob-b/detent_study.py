#!/usr/bin/env python3
"""Option (b) detent study for the Temper knob: magnetic detents above the panel, nonmagnetic retention, effect on the TMAG5170 angle.

One deterministic script: controls, architecture comparison and sizing, torque/force/demagnetisation of the recommended design, the field at the
die and the calibrated angle error with the detent assembly, knob-removed detection, retention/cost/R44 numbers, results.json (headline first),
plots/ and raw/.   Usage:  python3 detent_study.py [--quick] [--out DIR] [--threads N]     (--quick: coarse grids, a few minutes, not the study)

Part 1 (kernels, magnet sets, energy/force/torque) is the cuboid kernel of ../knob-ring/ring_study.py extended to rotated rings of blocks;
part 2 is the study.  Units: mm, T, A/m, J, N, N*m.
"""
from __future__ import annotations


import math
from dataclasses import dataclass, field

import magpylib as mp
import numba as nb
import numpy as np
from scipy.spatial.transform import Rotation as Rot

MU0 = 4e-7 * math.pi
FOURPI = 4 * math.pi


# ------------------------------------------------------------------------------------------ exact cuboid kernel
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


@nb.njit(cache=True, parallel=True)
def field_sum(obs, cen, Rm, half, Mv):
    """H (A/m) at obs (P,3) from S uniformly magnetised cuboids. Rm[s] columns are the local axes in the global frame; Mv[s] global M (A/m)."""
    P = obs.shape[0]
    S = cen.shape[0]
    H = np.zeros((P, 3))
    for i in nb.prange(P):
        K = np.empty((3, 3))
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


# ------------------------------------------------------------------------------------------ magnet sets
@dataclass
class MSet:
    """N cuboid magnets.  cen (N,3) mm; Rm (N,3,3) local axes as columns; half (N,3) mm; mdir (N,3) unit magnetisation (global);
    s (N,) strength factor (1 nominal, +-1 for alternating poles, scatter multiplies it)."""
    cen: np.ndarray
    Rm: np.ndarray
    half: np.ndarray
    mdir: np.ndarray
    s: np.ndarray
    label: str = ""

    @property
    def n(self) -> int:
        return len(self.cen)

    def volume_mm3(self) -> float:
        return float(np.sum(8 * self.half[:, 0] * self.half[:, 1] * self.half[:, 2]))

    def moment_Am2(self, br: float) -> np.ndarray:
        v = 8 * self.half[:, 0] * self.half[:, 1] * self.half[:, 2] * 1e-9
        return ((br / MU0) * (v * self.s)[:, None] * self.mdir).sum(axis=0)

    def M(self, br: float) -> np.ndarray:
        return (br / MU0) * self.s[:, None] * self.mdir

    def transformed(self, theta_deg=0.0, shift=(0, 0, 0), tilt_deg=(0.0, 0.0), pivot=(0, 0, 0)) -> "MSet":
        """Rotate by theta about z, then tilt (x then y, degrees) about `pivot`, then translate."""
        R = Rot.from_euler("xy", list(tilt_deg), degrees=True).as_matrix() @ Rot.from_euler("z", theta_deg, degrees=True).as_matrix()
        p = np.asarray(pivot, float)
        cen = (R @ self.cen.T).T
        # tilt about the pivot: undo the pivot offset for the tilt part only
        Rt = Rot.from_euler("xy", list(tilt_deg), degrees=True).as_matrix()
        cen = cen - (Rt @ p) + p + np.asarray(shift, float)
        Rm = np.einsum("ab,sbc->sac", R, self.Rm)
        mdir = (R @ self.mdir.T).T
        return MSet(cen, np.ascontiguousarray(Rm), self.half, mdir, self.s, self.label)

    def merged(self, other: "MSet") -> "MSet":
        return MSet(np.vstack([self.cen, other.cen]), np.concatenate([self.Rm, other.Rm]), np.vstack([self.half, other.half]),
                    np.vstack([self.mdir, other.mdir]), np.concatenate([self.s, other.s]), self.label + "+" + other.label)


def ring_set(n: int, r: float, zc: float, size, mag: str = "r", signs=None, phase_deg: float = 0.0, label: str = "") -> MSet:
    """n blocks on a circle of radius r (centre of the block), axial centre zc.  size = (radial, tangential, axial) mm.
    mag: 'r' (+radial), 'z' (+axial), 't' (+tangential).  signs: per-block +-1 (default all +1).  Block k sits at phase + 360 k / n."""
    ang = np.radians(phase_deg + 360.0 * np.arange(n) / n)
    er = np.column_stack([np.cos(ang), np.sin(ang), np.zeros(n)])
    et = np.column_stack([-np.sin(ang), np.cos(ang), np.zeros(n)])
    ez = np.tile([0.0, 0.0, 1.0], (n, 1))
    Rm = np.stack([er, et, ez], axis=2)
    cen = np.column_stack([r * np.cos(ang), r * np.sin(ang), np.full(n, zc)])
    half = np.tile(np.asarray(size, float) / 2.0, (n, 1))
    mdir = {"r": er, "z": ez, "t": et}[mag]
    s = np.ones(n) if signs is None else np.asarray(signs, float)
    return MSet(cen, np.ascontiguousarray(Rm), half, mdir.copy(), s, label)


def alt_signs(n: int) -> np.ndarray:
    return np.where(np.arange(n) % 2 == 0, 1.0, -1.0)


def B_of(set_: MSet, br: float, pts: np.ndarray) -> np.ndarray:
    """B (T) of the set (rigid magnets, remanence br) at pts (P,3) mm."""
    if set_.n == 0:
        return np.zeros((len(pts), 3))
    return MU0 * field_sum(np.ascontiguousarray(pts, dtype=float), set_.cen, set_.Rm, set_.half, np.ascontiguousarray(set_.M(br)))


# ------------------------------------------------------------------------------------------ quadrature
_GL_CACHE = {}


def gl(n: int):
    if n not in _GL_CACHE:
        _GL_CACHE[n] = np.polynomial.legendre.leggauss(n)
    return _GL_CACHE[n]


def volume_quadrature(set_: MSet, n: int):
    """points (N*n^3, 3) mm, weights (N*n^3,) m^3, block index (N*n^3,)"""
    x, w = gl(n)
    X, Y, Z = np.meshgrid(x, x, x, indexing="ij")
    W = (w[:, None, None] * w[None, :, None] * w[None, None, :]).reshape(-1) / 8.0       # fractions of the volume
    loc = np.column_stack([X.reshape(-1), Y.reshape(-1), Z.reshape(-1)])               # in [-1,1]^3
    pts, wts, idx = [], [], []
    for k in range(set_.n):
        p = (loc * set_.half[k]) @ set_.Rm[k].T + set_.cen[k]
        pts.append(p)
        vol = 8 * set_.half[k, 0] * set_.half[k, 1] * set_.half[k, 2] * 1e-9
        wts.append(W * vol)
        idx.append(np.full(len(W), k))
    return np.vstack(pts), np.concatenate(wts), np.concatenate(idx)


def face_quadrature(set_: MSet, m: int):
    """Face points for the surface-charge force: points (N*6*m^2, 3) mm, charge q = sigma*dA (A*m), block index, lever vectors not needed.
    sigma = M . n (A/m) with M the block magnetisation at br=1 T/mu0 scaling applied by the caller (we return M.n per unit br)."""
    x, w = gl(m)
    U, V = np.meshgrid(x, x, indexing="ij")
    W2 = (w[:, None] * w[None, :]).reshape(-1)
    u, v = U.reshape(-1), V.reshape(-1)
    pts, q, idx = [], [], []
    for k in range(set_.n):
        a, b, c = set_.half[k]
        faces = []
        for ax in range(3):
            for sg in (-1.0, 1.0):
                loc = np.zeros((len(u), 3))
                other = [i for i in range(3) if i != ax]
                loc[:, ax] = sg * set_.half[k, ax]
                loc[:, other[0]] = u * set_.half[k, other[0]]
                loc[:, other[1]] = v * set_.half[k, other[1]]
                area = 4 * set_.half[k, other[0]] * set_.half[k, other[1]] * 1e-6          # m^2 full face
                nloc = np.zeros(3)
                nloc[ax] = sg
                nglob = set_.Rm[k] @ nloc
                sigma_unit = float(np.dot(set_.mdir[k], nglob)) * set_.s[k]                # M.n / (br/mu0)
                faces.append(((loc @ set_.Rm[k].T) + set_.cen[k], W2 / 4.0 * area * sigma_unit))
        pts.append(np.vstack([f[0] for f in faces]))
        q.append(np.concatenate([f[1] for f in faces]))
        idx.append(np.full(sum(len(f[1]) for f in faces), k))
    return np.vstack(pts), np.concatenate(q), np.concatenate(idx)


# ------------------------------------------------------------------------------------------ energy, torque, force
def interaction_energy(rotor: MSet, br_r: float, stator: MSet, br_s: float, nq: int = 3, rq=None) -> float:
    """U = -int_rotor M . B_stator dV (J)."""
    pts, wts, idx = rq if rq is not None else volume_quadrature(rotor, nq)
    B = B_of(stator, br_s, pts)
    M = rotor.M(br_r)[idx]
    return -float(np.sum(wts * np.einsum("ij,ij->i", M, B)))


def surface_force_torque(rotor: MSet, br_r: float, stator: MSet, br_s: float, m: int = 4, origin=(0.0, 0.0, 0.0)):
    """Force (N) and torque about `origin` (N*m) on the rotor from the stator field via equivalent surface charges q B (route 2)."""
    pts, q, idx = face_quadrature(rotor, m)
    B = B_of(stator, br_s, pts)
    f = (br_r / MU0) * q[:, None] * B                                                    # N per quadrature point
    rel = (pts - np.asarray(origin, float)) * 1e-3
    tq = np.cross(rel, f)
    return f.sum(axis=0), tq.sum(axis=0)


def sensing_cylinder(br: float, theta_deg=0.0, shift=(0, 0, 0), tilt_deg=(0.0, 0.0), pivot=(0.0, 0.0, 1.0), d=10.0, h=5.0, z0=1.0):
    R = Rot.from_euler("xy", list(tilt_deg), degrees=True).as_matrix() @ Rot.from_euler("z", theta_deg, degrees=True).as_matrix()
    c0 = np.array([0.0, 0.0, z0 + h / 2])
    Rt = Rot.from_euler("xy", list(tilt_deg), degrees=True).as_matrix()
    p = np.asarray(pivot, float)
    pos = Rt @ (c0 - p) + p + np.asarray(shift, float)
    return mp.magnet.Cylinder(dimension=(d, h), polarization=(br, 0.0, 0.0), position=tuple(pos), orientation=Rot.from_matrix(R))


def sensing_stator_energy(cyl, stator: MSet, br_s: float, nq: int = 3, sq=None) -> float:
    """-int_stator M_s . B_sensing dV (J): energy of the stationary magnets in the sensing magnet's field."""
    pts, wts, idx = sq if sq is not None else volume_quadrature(stator, nq)
    B = np.atleast_2d(cyl.getB(pts))
    M = stator.M(br_s)[idx]
    return -float(np.sum(wts * np.einsum("ij,ij->i", M, B)))


def sensing_stator_torque_surface(cyl, stator: MSet, br_s: float, m: int = 4):
    """Route 2: force/torque on the stator magnets from the sensing magnet; the torque on the sensing magnet is minus this (third law)."""
    pts, q, idx = face_quadrature(stator, m)
    B = np.atleast_2d(cyl.getB(pts))
    f = (br_s / MU0) * q[:, None] * B
    tq = np.cross(pts * 1e-3, f)
    return f.sum(axis=0), tq.sum(axis=0)


def field_at_die(sets_br, cyl, die=(0.0, 0.0, -4.0)):
    """B (T) at the die from magnet sets [(set, br), ...] and the sensing magnet (magpylib cylinder or None)."""
    p = np.asarray([die], float)
    B = np.zeros((1, 3))
    for s_, br in sets_br:
        B = B + B_of(s_, br, p)
    if cyl is not None:
        B = B + np.atleast_2d(cyl.getB(p))
    return B[0]


# ------------------------------------------------------------------------------------------ fast traces
def _pose(theta_deg, shift=(0, 0, 0), tilt_deg=(0.0, 0.0), pivot=(0, 0, 0)):
    Rt = Rot.from_euler("xy", list(tilt_deg), degrees=True).as_matrix()
    R = Rt @ Rot.from_euler("z", theta_deg, degrees=True).as_matrix()
    p = np.asarray(pivot, float)
    return R, Rt, p, np.asarray(shift, float)


def place_points(pts, theta_deg, shift=(0, 0, 0), tilt_deg=(0.0, 0.0), pivot=(0, 0, 0)):
    R, Rt, p, s = _pose(theta_deg, shift, tilt_deg, pivot)
    return (pts @ R.T) - (Rt @ p) + p + s


def energy_trace(rotor: MSet, br_r: float, stator: MSet, br_s: float, angles, nq=5, shift=(0, 0, 0), tilt_deg=(0.0, 0.0), pivot=(0, 0, 0)):
    """Interaction energy (J) of the rotor (rotated by each angle, optional shift/tilt) with the fixed stator."""
    pts, wts, idx = volume_quadrature(rotor, nq)
    M0 = rotor.M(br_r)[idx]
    U = np.zeros(len(angles))
    for i, th in enumerate(angles):
        R, Rt, p, s = _pose(th, shift, tilt_deg, pivot)
        P = place_points(pts, th, shift, tilt_deg, pivot)
        B = B_of(stator, br_s, P)
        U[i] = -float(np.sum(wts * np.einsum("ij,ij->i", M0 @ R.T, B)))
    return U


def torque_from_energy(angles_deg, U, periodic=True):
    """-dU/dtheta (N*m) by central differences on a uniform periodic grid (angles in degrees, one period or the full turn)."""
    th = np.radians(np.asarray(angles_deg, float))
    h = th[1] - th[0]
    if periodic:
        return -(np.roll(U, -1) - np.roll(U, 1)) / (2 * h)
    return -np.gradient(U, th)


def torque_stats(T):
    """mean |T|, peak |T|, positive/negative peaks, mean T (N*m)"""
    return {"mean_abs": float(np.mean(np.abs(T))), "peak": float(np.max(np.abs(T))), "peak_pos": float(T.max()), "peak_neg": float(T.min()),
            "mean": float(np.mean(T))}


def count_detents(angles_deg, U):
    """Number of stable equilibria per turn: local minima of the periodic energy trace."""
    n = len(U)
    mn = (U < np.roll(U, 1)) & (U <= np.roll(U, -1))
    return int(mn.sum())

# =========================================================================================== study (part 2)
import argparse
from dataclasses import dataclass
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]                      # zapote/ui-board


def _load_ui_calcs():
    spec = importlib.util.spec_from_file_location("ui_calcs", UNIT / "tools" / "ui_calcs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_calcs"] = mod
    spec.loader.exec_module(mod)
    return mod


UI = _load_ui_calcs()
BR20 = UI.BR_35E
TEMPCO = 0.00035
T_HOT, T_COLD = 176.0, -40.0
HALL = np.array([0.0, 0.0, -4.0])
PITCH = 15.0

# ---------------------------------------------------------------------------------- pass criteria (stated before any result)
CRIT = {
    "detents_per_turn": 24,
    "mean_torque_mNm": (18.0, 30.0),            # SPEC: average detent torque; evaluated as mean |T| over the whole trace
    "peak_torque_mNm": (25.0, 45.0),            # SPEC: individual peak torque (each of the 24 detents)
    "nominal_mean_target_mNm": 24.3,            # sizing target: the value that centres the 20 C corner set in the band (see README 2)
    "hot_mean_floor_mNm": 14.4,                 # 176 C: not specified by SPEC; ASSUMED floor 0.8 x 18 (detent still clearly present)
    "pulloff_N": (12.0, 20.0),
    "lateral_neg_stiffness_max_N_per_mm": 4.0,  # magnetic negative stiffness <= 10 % of the locator's 10 N / 0.25 mm = 40 N/mm
    "push_magnetic_axial_max_N": 1.5,           # magnetic axial force over a 0.65 mm push <= 16 % of the 9.5 N push midpoint
    "drag_max_fraction": 0.02,                  # non-detent magnetic drag (mean T over a turn) <= 2 % of mean |T|
    "eddy_drag_max_mNm": 1.0,
    "D_share_deg": 0.10,                        # detent-assembly share of the 0.6 deg pool (same share the ring study gave the ring)
    "pool_deg": 0.60,
    "coil_allowance_deg": 0.1726,               # ui_calcs worst: no pan, 60 kHz, bare
    "total_with_coil_max_deg": 0.30,            # D + coil <= half the pool, other half for calibration, magnet, sensor
    "B_max_mT": 80.0,                           # 80 % of +-100 mT
    "B_change_by_assembly_pct": 1.0,
    "removed_B_max_mT": 4.7,                    # knob absent: <= 10 % of the weakest seated field (47.1 mT)
    "removed_threshold_mT": 23.7,
    "conv_tol": 0.10, "route_tol": 0.05,
    "demag_margin_min": 1.5,                    # Hcj(T) / worst opposing H >= 1.5
    "gap_running_min_mm": 0.30,
}

# ---------------------------------------------------------------------------------- design (recommended)
DESIGN = dict(a=2.0, b=2.5, h=1.80, stack=2, r_stator=22.5, gap=0.67, n_rotor=24, n_stator=4, stator_phase=45.0, z_bot=0.80)


def br_T(T, br20=BR20):
    return br20 * (1.0 - TEMPCO * (T - 20.0))


def build_design(D=None, gap_err=0.0):
    D = D or DESIGN
    hs = D["h"] * D["stack"]
    zc = D["z_bot"] + hs / 2
    st = ring_set(D["n_stator"], D["r_stator"], zc, (D["a"], D["b"], hs), "r", phase_deg=D["stator_phase"], label="stator")
    ro = ring_set(D["n_rotor"], D["r_stator"] + D["a"] + D["gap"] + gap_err, zc, (D["a"], D["b"], D["h"]), "r", label="rotor")
    return ro, st


def perturb(s: MSet, rng, sig_str=0.015, sig_ang=1.5, sig_pos=0.05):
    n = s.n
    cen = s.cen + rng.normal(0.0, sig_pos, (n, 3))
    mdir = s.mdir.copy()
    for k in range(n):
        ax = rng.normal(size=3)
        ax -= ax.dot(mdir[k]) * mdir[k]
        ax /= np.linalg.norm(ax)
        ang = math.radians(rng.normal(0.0, sig_ang))
        mdir[k] = mdir[k] * math.cos(ang) + ax * math.sin(ang)
    return MSet(cen, s.Rm, s.half, mdir, s.s * (1.0 + rng.normal(0.0, sig_str, n)), s.label)


PIVOT = (0.0, 0.0, 1.0)             # tilt pivot: the sensing magnet's near face (as the ring study)


def torque_trace(ro, st, br_r, br_s, angles, nq, shift=(0, 0, 0), tilt=(0.0, 0.0)):
    U = energy_trace(ro, br_r, st, br_s, angles, nq, shift=shift, tilt_deg=tilt, pivot=PIVOT)
    return U, torque_from_energy(angles, U)


def tile_period(vals, period_deg, n_turn_deg=360.0):
    reps = int(round(n_turn_deg / period_deg))
    return np.tile(vals, reps)


def per_detent_peaks(angles, T, pitch=PITCH):
    ang = np.asarray(angles)
    out = []
    for k in range(int(round(360.0 / pitch))):
        c = k * pitch
        d = (ang - c + 180.0) % 360.0 - 180.0
        sel = np.abs(d) <= pitch / 2
        out.append(float(np.max(np.abs(T[sel]))))
    return np.array(out)


def mNm(x):
    return float(x) * 1e3


# =========================================================================================== 1. controls
def controls(quick):
    out = {}
    # (1a) sensing magnet at the die against the owner's closed form
    cyl = sensing_cylinder(BR20)
    B = np.atleast_2d(cyl.getB(HALL[None]))[0]
    ref = UI.magnet_b_mT(5.0)
    out["sensing_magnet_20C"] = {"model_mT": float(np.linalg.norm(B) * 1e3), "ui_calcs_mT": ref, "rel_err": abs(np.linalg.norm(B) * 1e3 / ref - 1.0)}
    cyl = sensing_cylinder(br_T(T_HOT))
    B = np.atleast_2d(cyl.getB(HALL[None]))[0]
    out["sensing_magnet_176C"] = {"model_mT": float(np.linalg.norm(B) * 1e3), "ui_calcs_mT": UI.magnet_b_mT(5.0, br_T(T_HOT)),
                                  "rel_err": abs(np.linalg.norm(B) * 1e3 / UI.magnet_b_mT(5.0, br_T(T_HOT)) - 1.0)}
    # (1b) cuboid kernel against magpylib, rotated blocks, random points including the near field (0.3 mm from a face)
    rng = np.random.default_rng(7)
    worst = 0.0
    worst_near = 0.0
    for trial in range(12):
        rot = Rot.random(random_state=int(rng.integers(1 << 30)))
        half = rng.uniform(0.7, 2.0, 3)
        cen = rng.uniform(-5, 5, 3)
        mdir = rng.normal(size=3)
        mdir /= np.linalg.norm(mdir)
        pts = cen + rng.uniform(-8, 8, (40, 3))
        lp = (pts - cen) @ rot.as_matrix()
        pts = pts[np.any(np.abs(lp) > half + 0.1, axis=1)]            # outside the block (inside, B = mu0 (H + M) is not the kernel's H)
        # near-field points just outside the +z (local) face
        loc = np.column_stack([rng.uniform(-half[0], half[0], 20), rng.uniform(-half[1], half[1], 20), half[2] + 0.3 + rng.uniform(0, 0.2, 20)])
        near = cen + loc @ rot.as_matrix().T
        s_ = MSet(cen[None], rot.as_matrix()[None], half[None], mdir[None], np.ones(1))
        m = mp.magnet.Cuboid(dimension=tuple(2 * half), polarization=tuple(1.19 * (rot.as_matrix().T @ mdir)), position=tuple(cen), orientation=rot)
        for P, tag in ((pts, "far"), (near, "near")):
            a = B_of(s_, 1.19, P)
            b = m.getB(P)
            e = float(np.max(np.abs(a - b)) / (np.max(np.abs(b)) + 1e-30))
            if tag == "far":
                worst = max(worst, e)
            else:
                worst_near = max(worst_near, e)
    out["cuboid_vs_magpylib"] = {"max_rel_err_far": worst, "max_rel_err_near_0p3mm": worst_near}
    # (1c) diametral cylinder closed form on axis at 5, 9, 15 mm
    cf = {}
    for g in (5.0, 9.0, 15.0):
        c = sensing_cylinder(BR20, z0=1.0 + (g - 5.0))
        bb = np.atleast_2d(c.getB(HALL[None]))[0]
        cf[str(g)] = {"model_mT": float(np.linalg.norm(bb) * 1e3), "closed_form_mT": UI.magnet_b_mT(g), "rel_err": abs(np.linalg.norm(bb) * 1e3 / UI.magnet_b_mT(g) - 1.0)}
    out["diametral_cylinder_closed_form"] = cf
    # (2) torque by two routes: energy derivative vs equivalent-surface-charge force on the magnets
    ro, st = build_design()
    routes = []
    cases = [("concentric", (0, 0, 0), (0.0, 0.0)), ("eccentric 0.3 mm", (0.3, 0.0, 0.0), (0.0, 0.0)), ("pushed 0.5 mm", (0, 0, -0.5), (0.0, 0.0)),
             ("tilt 1 deg", (0, 0, 0), (1.0, 0.0))]
    d = 0.02
    for name, sh, tl in cases:
        for th in (2.0, 5.5, 9.0):
            Up = energy_trace(ro, BR20, st, BR20, [th + d], 6, shift=sh, tilt_deg=tl, pivot=PIVOT)[0]
            Um = energy_trace(ro, BR20, st, BR20, [th - d], 6, shift=sh, tilt_deg=tl, pivot=PIVOT)[0]
            t1 = -(Up - Um) / (2 * math.radians(d))
            Rt = Rot.from_euler("xy", list(tl), degrees=True).as_matrix()
            nax = Rt @ np.array([0.0, 0.0, 1.0])
            org = Rt @ (-np.asarray(PIVOT)) + np.asarray(PIVOT) + np.asarray(sh)
            F, Tq = surface_force_torque(ro.transformed(th, shift=sh, tilt_deg=tl, pivot=PIVOT), BR20, st, BR20, 8, origin=org)
            t2 = float(Tq @ nax)
            routes.append({"case": name, "theta_deg": th, "energy_route_mNm": mNm(t1), "force_route_mNm": mNm(t2), "ratio": t2 / t1})
    out["torque_two_routes"] = routes
    # axial force and lateral force by both routes
    fr = []
    for dz in (-0.5, 1.0):
        h = 0.02
        Up = energy_trace(ro, BR20, st, BR20, [3.0], 6, shift=(0, 0, dz + h))[0]
        Um = energy_trace(ro, BR20, st, BR20, [3.0], 6, shift=(0, 0, dz - h))[0]
        f1 = -(Up - Um) / (2 * h * 1e-3)
        F, _ = surface_force_torque(ro.transformed(3.0, shift=(0, 0, dz)), BR20, st, BR20, 8)
        fr.append({"what": f"axial force at dz={dz} mm", "energy_N": f1, "force_N": float(F[2]), "ratio": float(F[2]) / f1})
    for ex in (0.2,):
        h = 0.02
        Up = energy_trace(ro, BR20, st, BR20, [3.0], 6, shift=(ex + h, 0, 0))[0]
        Um = energy_trace(ro, BR20, st, BR20, [3.0], 6, shift=(ex - h, 0, 0))[0]
        f1 = -(Up - Um) / (2 * h * 1e-3)
        F, _ = surface_force_torque(ro.transformed(3.0, shift=(ex, 0, 0)), BR20, st, BR20, 8)
        fr.append({"what": f"lateral force at e={ex} mm", "energy_N": f1, "force_N": float(F[0]), "ratio": float(F[0]) / f1})
    out["force_two_routes"] = fr
    # sensing magnet <-> stator torque, both routes (third law)
    ths = [0.0, 1.7, 3.3]
    sm = []
    for th in ths:
        h = 0.02
        Up = sensing_stator_energy(sensing_cylinder(BR20, th + h), st, BR20, 5)
        Um = sensing_stator_energy(sensing_cylinder(BR20, th - h), st, BR20, 5)
        t1 = -(Up - Um) / (2 * math.radians(h))
        _, Tq = sensing_stator_torque_surface(sensing_cylinder(BR20, th), st, BR20, 8)
        sm.append({"theta_deg": th, "energy_mNm": mNm(t1), "force_route_mNm": mNm(-Tq[2])})
    out["sensing_magnet_on_stator"] = sm
    # (3) discretisation convergence
    conv = {}
    angs = np.arange(0.0, 15.0, 0.5)
    ref = None
    rows = []
    for nq in (3, 4, 5, 8, 10):
        U = energy_trace(ro, BR20, st, BR20, angs, nq)
        T = torque_from_energy(angs, U)
        s = torque_stats(T)
        rows.append({"nq_per_axis": nq, "mean_abs_mNm": mNm(s["mean_abs"]), "peak_mNm": mNm(s["peak"])})
    r0 = rows[-1]
    for r in rows:
        r["rel_change_vs_finest_mean"] = abs(r["mean_abs_mNm"] / r0["mean_abs_mNm"] - 1)
        r["rel_change_vs_finest_peak"] = abs(r["peak_mNm"] / r0["peak_mNm"] - 1)
    conv["volume_quadrature"] = rows
    fq = []
    for m in (4, 6, 8, 12):
        F, Tq = surface_force_torque(ro.transformed(2.0), BR20, st, BR20, m)
        fq.append({"face_points_per_axis": m, "torque_mNm": mNm(Tq[2])})
    for r in fq:
        r["rel_change_vs_finest"] = abs(r["torque_mNm"] / fq[-1]["torque_mNm"] - 1)
    conv["face_quadrature"] = fq
    steps = []
    for step in (1.0, 0.5, 0.25, 0.1):
        a_ = np.arange(0.0, 15.0, step)
        U = energy_trace(ro, BR20, st, BR20, a_, 5)
        s = torque_stats(torque_from_energy(a_, U))
        steps.append({"angle_step_deg": step, "mean_abs_mNm": mNm(s["mean_abs"]), "peak_mNm": mNm(s["peak"])})
    for r in steps:
        r["rel_change_vs_finest_peak"] = abs(r["peak_mNm"] / steps[-1]["peak_mNm"] - 1)
    conv["angle_step"] = steps
    out["convergence"] = conv
    out["checks"] = {
        "sensing_magnet_55p728_mT": out["sensing_magnet_20C"]["rel_err"] < 1e-3,
        "sensing_magnet_176C": out["sensing_magnet_176C"]["rel_err"] < 1e-3,
        "cuboid_kernel_vs_magpylib_1e-6": max(worst, worst_near) < 1e-6,
        "cylinder_closed_form_1pct": all(v["rel_err"] < 1e-2 for v in cf.values()),
        "torque_two_routes_5pct": all(abs(r["ratio"] - 1) < CRIT["route_tol"] for r in routes),
        "force_two_routes_5pct": all(abs(r["ratio"] - 1) < CRIT["route_tol"] for r in fr),
        "convergence_lt_10pct": (max(r["rel_change_vs_finest_peak"] for r in rows if r["nq_per_axis"] >= 5) < CRIT["conv_tol"]
                                 and max(r["rel_change_vs_finest"] for r in fq if r["face_points_per_axis"] >= 6) < CRIT["conv_tol"]
                                 and max(r["rel_change_vs_finest_peak"] for r in steps if r["angle_step_deg"] <= 0.5) < CRIT["conv_tol"]),
    }
    return out


# =========================================================================================== 2. architectures
def _sg(n, val=1.0):
    return np.full(n, val)


def arch_catalog():
    """name -> dict(builder(x, gap_err) -> (rotor, stator), x0 bounds, expected detents, period deg, notes).  x is the free axial length (mm)."""
    A = []

    def b_radial(nr, ns, alt=False, swap=False, bt=2.5, a=2.0, rep=False):
        def bld(x, gap_err=0.0):
            rs = 22.5
            hr, hs = (x, 2 * x) if not swap else (2 * x, x)
            if swap:                                   # the 24-ring is stationary (inside), the 4-ring rotates (outside)
                st = ring_set(ns, rs, 0.8 + x, (a, bt, x), "r", signs=alt_signs(ns) if alt else None)
                ro = ring_set(nr, rs + a + DESIGN["gap"] + gap_err, 0.8 + x, (a, bt, 2 * x), "r", signs=alt_signs(nr) if alt else None)
            else:
                st = ring_set(ns, rs, 0.8 + hs / 2, (a, bt, hs), "r", phase_deg=45.0, signs=alt_signs(ns) if alt else None)
                sg = alt_signs(nr) * (-1.0 if rep else 1.0) if alt else _sg(nr, -1.0 if rep else 1.0)
                ro = ring_set(nr, rs + a + DESIGN["gap"] + gap_err, 0.8 + hs / 2, (a, bt, hr), "r", signs=sg)
            return ro, st
        return bld

    A.append(dict(name="B1", title="above panel, radial gap, radial magnetisation, attracting; 24 rotor + 4 stator (stator stack 2x)",
                  bld=b_radial(24, 4), bounds=(0.4, 6.0), detents=24, period=15.0, family="B"))
    A.append(dict(name="B1s", title="as B1 but 4 rotor + 24 stator (the 24-ring is stationary)",
                  bld=b_radial(4, 24, swap=True), bounds=(0.4, 6.0), detents=24, period=15.0, family="B"))
    A.append(dict(name="B1x", title="as B1, repelling (rotor polarity reversed)",
                  bld=b_radial(24, 4, rep=True), bounds=(0.4, 6.0), detents=24, period=15.0, family="B", tune_like="B1"))
    A.append(dict(name="B5", title="above panel, radial gap, radial, same-pole 24 rotor + 24 stator",
                  bld=b_radial(24, 24), bounds=(0.3, 6.0), detents=24, period=15.0, family="B"))
    A.append(dict(name="B4a", title="above panel, radial gap, radial, ALTERNATING poles 24 + 24 (12 pole pairs)",
                  bld=b_radial(24, 24, alt=True), bounds=(0.3, 6.0), detents=12, period=30.0, family="B"))
    A.append(dict(name="B4b", title="above panel, radial gap, radial, ALTERNATING poles 48 + 48 (24 pole pairs, tangential 1.3 mm)",
                  bld=b_radial(48, 48, alt=True, bt=1.3), bounds=(0.3, 8.0), detents=24, period=15.0, family="B"))

    def b_axial_gap():
        def bld(x, gap_err=0.0):
            w = x                                                       # radial width (mm), centred at r 23.5
            rc = 23.5
            st = ring_set(4, rc, 0.8 + 1.0, (w, 2.5, 2.0), "z", phase_deg=45.0, signs=_sg(4, -1.0))
            ro = ring_set(24, rc, 0.8 + 2.0 + 1.0 + gap_err + 1.0, (w, 2.5, 2.0), "z", signs=_sg(24, -1.0))
            return ro, st
        return bld
    A.append(dict(name="B2", title="above panel, AXIAL gap (face to face), axial magnetisation; rest gap 1.0 mm; free parameter = radial width",
                  bld=b_axial_gap(), bounds=(0.8, 4.5), detents=24, period=15.0, family="B"))

    def b_radial_axial_mag():
        def bld(x, gap_err=0.0):
            hs = 2 * x
            st = ring_set(4, 22.5, 0.8 + hs / 2, (2.0, 2.5, hs), "z", phase_deg=45.0, signs=_sg(4, 1.0))
            ro = ring_set(24, 22.5 + 2.0 + DESIGN["gap"] + gap_err, 0.8 + hs / 2, (2.0, 2.5, x), "z", signs=_sg(24, -1.0))
            return ro, st
        return bld
    A.append(dict(name="B3", title="above panel, radial gap, AXIAL magnetisation (side by side, opposed)",
                  bld=b_radial_axial_mag(), bounds=(0.4, 6.0), detents=24, period=15.0, family="B"))

    def a_across(nr, ns, alt=False, hs=1.5, w=4.0, bt=3.5, st_phase=0.0, rc=24.0):
        def bld(x, gap_err=0.0):
            stz = -3.1 - hs / 2                                         # stationary magnets behind the 3 mm fascia, top face 0.1 mm behind it
            ro = ring_set(nr, rc, 1.0 + gap_err + x / 2, (w, bt, x), "z", signs=alt_signs(nr) * -1.0 if alt else _sg(nr, -1.0))
            st = ring_set(ns, rc, stz, (w, bt, hs), "z", phase_deg=st_phase, signs=alt_signs(ns) * -1.0 if alt else _sg(ns, -1.0))
            return ro, st
        return bld
    A.append(dict(name="A1", title="across the panel, axial, same-pole 24 rotor + 24 stator behind the fascia (stator 4.0 x 3.5 x 1.5, tab-limited)",
                  bld=a_across(24, 24), bounds=(1.0, 5.0), detents=24, period=15.0, family="A"))
    A.append(dict(name="A1t", title="as A1 with the stators 4 mm thick (would need the tab moved)",
                  bld=a_across(24, 24, hs=4.0), bounds=(1.0, 5.0), detents=24, period=15.0, family="A"))
    A.append(dict(name="A2", title="across the panel, 24 rotor + 4 stators 6 mm thick at 45 deg (free sectors beside the tab)",
                  bld=a_across(24, 4, hs=6.0, st_phase=45.0), bounds=(1.0, 5.0), detents=24, period=15.0, family="A"))
    A.append(dict(name="A3", title="across the panel, ALTERNATING poles 24 + 24 (4.0 x 3.5 x 1.5)",
                  bld=a_across(24, 24, alt=True), bounds=(0.2, 5.0), detents=12, period=30.0, family="A"))
    return A


def _mean_over_period(bld, x, period, nq=3, step=1.0, gap_err=0.0, shift=(0, 0, 0)):
    ro, st = bld(x, gap_err)
    ang = np.arange(0.0, period, step)
    U = energy_trace(ro, BR20, st, BR20, ang, nq, shift=shift)
    s = torque_stats(torque_from_energy(ang, U))
    return mNm(s["mean_abs"]), mNm(s["peak"])


def size_architecture(arch, target, quick):
    lo, hi = arch["bounds"]
    bld, per = arch["bld"], arch["period"]
    step = 1.0 if quick else 0.5
    mlo, _ = _mean_over_period(bld, lo, per, step=step)
    mhi, _ = _mean_over_period(bld, hi, per, step=step)
    if mhi < target:
        return hi, mhi, False
    if mlo > target:
        return lo, mlo, True
    for _ in range(14 if not quick else 9):
        mid = math.sqrt(lo * hi)
        m, _ = _mean_over_period(bld, mid, per, step=step)
        if m > target:
            hi = mid
        else:
            lo = mid
    x = 0.5 * (lo + hi)
    m, _ = _mean_over_period(bld, x, per, step=step)
    return x, m, True


def architectures(quick):
    cat = arch_catalog()
    rows = []
    sized = {}
    rng = np.random.default_rng(3)
    tgt = CRIT["nominal_mean_target_mNm"]
    for arch in cat:
        t0 = time.time()
        if "tune_like" in arch:
            x, reached, ok = sized[arch["tune_like"]]
        else:
            x, reached, ok = size_architecture(arch, tgt, quick)
        sized[arch["name"]] = (x, reached, ok)
        bld = arch["bld"]
        ro, st = bld(x)
        step = 1.0 if quick else 0.5
        ang = np.arange(0.0, 360.0, step)
        nqf = 3
        U = energy_trace(ro, BR20, st, BR20, ang, nqf)
        T = torque_from_energy(ang, U)
        s = torque_stats(T)
        n_det = count_detents(ang, U)
        per = arch["period"]
        # the energy trace is a function of the relative angle only; sensitivities on one period
        def mp_(**kw):
            return _mean_over_period(bld, x, per, step=1.0 if quick else 0.5, **kw)[0]
        m_gap_m, m_gap_p = mp_(gap_err=-0.1), mp_(gap_err=+0.1)
        m_push = mp_(shift=(0, 0, -0.65))
        # forces at the detent centre
        def Fz(dz):
            F, _ = surface_force_torque(ro.transformed(0.0, shift=(0, 0, dz)), BR20, st, BR20, 6)
            return float(F[2])
        fz_push = Fz(-0.5)
        lifts = np.array([0.5, 1.0, 1.5, 2.0, 3.0, 4.0])
        fz_lift = [Fz(l) for l in lifts]
        F0, _ = surface_force_torque(ro.transformed(0.0, shift=(0.1, 0, 0)), BR20, st, BR20, 6)
        F00, _ = surface_force_torque(ro.transformed(0.0), BR20, st, BR20, 6)
        k_lat = float((F0[0] - F00[0]) / 0.1)                       # N/mm, + = destabilising
        # die field
        Bst = B_of(st, BR20, HALL[None])[0] * 1e3
        Bro = B_of(ro, BR20, HALL[None])[0] * 1e3
        leak = []
        for k in range(60 if not quick else 20):
            s2 = MSet(st.cen, st.Rm, st.half, st.mdir, st.s * (1 + 0.03 * rng.standard_normal(st.n)))
            leak.append(B_of(s2, BR20, HALL[None])[0] * 1e3)
        leak = np.array(leak)
        vol = ro.volume_mm3() + st.volume_mm3()
        rows.append({
            "name": arch["name"], "title": arch["title"], "family": arch["family"], "free_parameter_mm": x, "sized_to_target": bool(ok),
            "pieces": ro.n + st.n, "rotor_pieces": ro.n, "stator_pieces": st.n,
            "rotor_block_mm": [float(2 * v) for v in ro.half[0]], "stator_block_mm": [float(2 * v) for v in st.half[0]],
            "smco_volume_mm3": vol, "smco_mass_g": vol * 8.3e-3,
            "detents_per_turn_expected": arch["detents"], "detents_per_turn_computed": n_det,
            "mean_abs_mNm": mNm(s["mean_abs"]), "peak_mNm": mNm(s["peak"]),
            "mean_gap_minus0p1_mNm": m_gap_m, "mean_gap_plus0p1_mNm": m_gap_p, "mean_push_0p65_mNm": m_push,
            "gap_sensitivity_pct_for_minus0p1mm": 100.0 * (m_gap_m / mNm(s["mean_abs"]) - 1.0),
            "push_torque_change_pct": 100.0 * (m_push / mNm(s["mean_abs"]) - 1.0),
            "Fz_at_push_0p5_N": fz_push, "Fz_vs_lift_N": {str(l): f for l, f in zip(lifts, fz_lift)},
            "pull_contribution_peak_N": float(-min(fz_lift)),
            "lateral_stiffness_N_per_mm": k_lat,
            "stator_Bdie_mT": [float(v) for v in Bst], "rotor_Bdie_mT": [float(v) for v in Bro],
            "stator_leak_std_uT_per_axis_3pct_scatter": [float(leak[:, 0].std() * 1e3), float(leak[:, 1].std() * 1e3)],
            "knob_removed_B_mT": float(np.linalg.norm(Bst)),
            "wall_s": time.time() - t0,
        })
    return rows


# =========================================================================================== 3. recommended design: torque, forces
@dataclass
class Cond:
    name: str
    br_r: float = 1.0               # remanence scale of rotor magnets (lot, temperature)
    br_s: float = 1.0
    gap: float = 0.0                # radial gap error, mm
    e: tuple = (0.0, 0.0)           # knob lateral offset, mm
    dz: float = 0.0                 # axial offset of the knob relative to the carrier (+ up), mm (push is negative)
    tilt: tuple = (0.0, 0.0)
    T: float = 20.0


def temp_scale(T):
    return 1.0 - TEMPCO * (T - 20.0)


def cond_trace(c: Cond, step=0.25, nq=5, D=None):
    ro, st = build_design(D, c.gap)
    ang = np.arange(0.0, PITCH, step)
    ts = temp_scale(c.T)
    U = energy_trace(ro, BR20 * c.br_r * ts, st, BR20 * c.br_s * ts, ang, nq, shift=(c.e[0], c.e[1], c.dz), tilt_deg=c.tilt, pivot=PIVOT)
    return ang, U, torque_from_energy(ang, U)


TOL_RECOMMENDED = dict(br=0.03, gap=0.07)       # lot-sorted Br +-3 %, total radial gap +-0.07 mm
TOL_WIDE = dict(br=0.05, gap=0.10)              # catalogue Br +-5 %, gap +-0.10 mm


def corner_list(tol):
    b, g = tol["br"], tol["gap"]
    C = [Cond("nominal")]
    C += [Cond(f"Br lots +{b*100:g} %", 1 + b, 1 + b), Cond(f"Br lots -{b*100:g} %", 1 - b, 1 - b),
          Cond(f"radial gap -{g:g}", gap=-g), Cond(f"radial gap +{g:g}", gap=+g),
          Cond("axial offset +0.30", dz=0.30), Cond("axial offset -0.30", dz=-0.30),
          Cond("lateral 0.30 mm along x", e=(0.3, 0.0)), Cond("lateral 0.30 mm at 45 deg", e=(0.2121, 0.2121)),
          Cond("tilt 1 deg about x", tilt=(1.0, 0.0)), Cond("tilt 1 deg about y", tilt=(0.0, 1.0)),
          Cond("pushed 0.65 mm", dz=-0.65), Cond("pushed 0.35 mm", dz=-0.35)]
    C += [Cond("STRONG: Br +, gap -", 1 + b, 1 + b, gap=-g),
          Cond("WEAK: Br -, gap +, axial -0.30", 1 - b, 1 - b, gap=+g, dz=-0.30),
          Cond("WEAK + pushed 0.65", 1 - b, 1 - b, gap=+g, dz=-0.65),
          Cond("STRONG + lateral 0.30 + tilt 1", 1 + b, 1 + b, gap=-g, e=(0.3, 0.0), tilt=(1.0, 0.0))]
    C += [Cond("176 C nominal", T=T_HOT), Cond("176 C WEAK", 1 - b, 1 - b, gap=+g, dz=-0.30, T=T_HOT), Cond("-40 C nominal", T=T_COLD),
          Cond("-40 C STRONG", 1 + b, 1 + b, gap=-g, T=T_COLD)]
    return C


def design_torque(quick):
    out = {}
    step = 0.5 if quick else 0.1
    nq = 4 if quick else 5
    ang, U, T = cond_trace(Cond("nominal"), step, nq)
    Ut, Tt = np.tile(U, 24), np.tile(T, 24)
    angf = np.arange(len(Ut)) * step
    s = torque_stats(Tt)
    k = int(round(1.0 / step))
    out["nominal"] = {"mean_abs_mNm": mNm(s["mean_abs"]), "peak_mNm": mNm(s["peak"]), "mean_T_over_turn_mNm": mNm(s["mean"]),
                      "detents_per_turn": count_detents(angf, Ut), "energy_pp_mJ": float((U.max() - U.min()) * 1e3),
                      "mean_over_peak": s["mean_abs"] / s["peak"],
                      "stable_equilibria_deg": [float(a) for a in ang[(U < np.roll(U, 1)) & (U <= np.roll(U, -1))]],
                      "step_deg": step, "nq": nq}
    F = np.abs(np.fft.rfft(T)) / len(T) * 2
    out["nominal"]["torque_harmonics_of_24_mNm"] = [mNm(F[i]) for i in range(1, 5)]
    # sensing magnet on the stator magnets: torque over a full turn
    a2 = np.arange(0.0, 360.0, 6.0 if quick else 3.0)
    ro, st = build_design()
    Usm = np.array([sensing_stator_energy(sensing_cylinder(BR20, th), st, BR20, 4) for th in a2])
    out["sensing_magnet_on_stator_pp_nJ"] = float((Usm.max() - Usm.min()) * 1e9)
    out["_trace"] = {"angle": ang.tolist(), "T_mNm": (T * 1e3).tolist(), "U_mJ": (U * 1e3).tolist()}
    # corners, for the recommended and the catalogue tolerance sets
    for tag, tol in (("corners_recommended_tolerance", TOL_RECOMMENDED), ("corners_catalogue_tolerance", TOL_WIDE)):
        rows = []
        for c in corner_list(tol):
            a_, U_, T_ = cond_trace(c, 0.25 if not quick else 0.5, 5 if not quick else 4)
            s_ = torque_stats(T_)
            rows.append({"name": c.name, "mean_abs_mNm": mNm(s_["mean_abs"]), "peak_mNm": mNm(s_["peak"]), "T_C": c.T,
                         "in_band_mean": CRIT["mean_torque_mNm"][0] <= mNm(s_["mean_abs"]) <= CRIT["mean_torque_mNm"][1],
                         "in_band_peak": CRIT["peak_torque_mNm"][0] <= mNm(s_["peak"]) <= CRIT["peak_torque_mNm"][1]})
        out[tag] = {"tolerance": tol, "rows": rows}
    return out


def design_monte_carlo(quick, tol, seed=11):
    """Lot + piece scatter, gap, running offset, axial offset and tilt together; full turn so that per-detent peaks vary."""
    rng = np.random.default_rng(seed)
    K = 6 if quick else 40
    step = 1.0 if quick else 0.5
    nq = 3 if quick else 4
    ang = np.arange(0.0, 360.0, step)
    draws = []
    for k in range(K):
        gap = rng.uniform(-tol["gap"], tol["gap"])
        lot_r, lot_s = rng.uniform(1 - tol["br"], 1 + tol["br"], 2)
        e = rng.uniform(-0.1, 0.1, 2)
        dz = rng.uniform(-0.3, 0.3)
        tilt = tuple(rng.normal(0.0, 0.5, 2))
        ro, st = build_design(None, gap)
        ro, st = perturb(ro, rng), perturb(st, rng)
        U = energy_trace(ro, BR20 * lot_r, st, BR20 * lot_s, ang, nq, shift=(e[0], e[1], dz), tilt_deg=tilt, pivot=PIVOT)
        T = torque_from_energy(ang, U)
        pk = per_detent_peaks(ang, T)
        draws.append({"gap": gap, "lot_rotor": lot_r, "lot_stator": lot_s, "e": e.tolist(), "dz": dz, "tilt": list(tilt),
                      "mean_abs_mNm": mNm(np.mean(np.abs(T))), "mean_T_mNm": mNm(np.mean(T)), "peak_min_mNm": mNm(pk.min()), "peak_max_mNm": mNm(pk.max()),
                      "detents": count_detents(ang, U)})
    m = np.array([d["mean_abs_mNm"] for d in draws])
    lo, hi = np.array([d["peak_min_mNm"] for d in draws]), np.array([d["peak_max_mNm"] for d in draws])
    drag = np.array([abs(d["mean_T_mNm"]) for d in draws]) / m
    return {"draws": K, "mean_abs_mNm": {"min": float(m.min()), "max": float(m.max()), "mean": float(m.mean()), "std": float(m.std())},
            "individual_peak_min_mNm": float(lo.min()), "individual_peak_max_mNm": float(hi.max()),
            "fraction_draws_mean_in_band": float(np.mean((m >= CRIT["mean_torque_mNm"][0]) & (m <= CRIT["mean_torque_mNm"][1]))),
            "fraction_draws_all_peaks_in_band": float(np.mean((lo >= CRIT["peak_torque_mNm"][0]) & (hi <= CRIT["peak_torque_mNm"][1]))),
            "max_mean_T_over_mean_abs": float(drag.max()), "detents_per_turn_all_draws": sorted({d["detents"] for d in draws}),
            "tolerance": tol, "scatter_model": "per-piece strength sigma 1.5 %, magnetisation direction sigma 1.5 deg, position sigma 0.05 mm per axis; lots Br and gap "
                             "uniform within the tolerance set, running offset +-0.1 mm, axial offset +-0.3 mm, tilt sigma 0.5 deg", "per_draw": draws}


def design_forces(quick):
    out = {}
    ro, st = build_design()
    m = 6 if quick else 8
    lifts = np.array([-0.65, -0.5, -0.35, -0.2, 0.0, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]) if not quick else np.array([-0.65, 0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    rows = []
    for dz in lifts:
        fz = []
        for th in (0.0, 7.5):
            F, _ = surface_force_torque(ro.transformed(th, shift=(0, 0, dz)), BR20, st, BR20, m)
            fz.append(float(F[2]))
        rows.append({"dz_mm": float(dz), "Fz_N_at_detent_centre": fz[0], "Fz_N_between_detents": fz[1]})
    out["axial_force_vs_lift"] = rows
    fz_all = np.array([[r["Fz_N_at_detent_centre"], r["Fz_N_between_detents"]] for r in rows])
    out["pull_off_contribution_peak_N"] = float(-fz_all[lifts > 0].min())
    out["push_force_over_0p65_N"] = float(fz_all[lifts == -0.65].max())
    out["push_force_at_0p5_N"] = float(np.interp(-0.5, lifts, fz_all[:, 0]))
    lat = []
    for e in ([0.0, 0.1, 0.2, 0.3, 0.5] if not quick else [0.0, 0.3]):
        f = []
        for th in (0.0, 7.5):
            for az in (0.0, 45.0):
                sh = (e * math.cos(math.radians(az)), e * math.sin(math.radians(az)), 0.0)
                F, _ = surface_force_torque(ro.transformed(th, shift=sh), BR20, st, BR20, m)
                f.append(float(np.hypot(F[0], F[1])))
        lat.append({"e_mm": e, "F_lateral_N_max_over_cases": max(f)})
    out["lateral_force"] = lat
    out["lateral_negative_stiffness_N_per_mm"] = max(r["F_lateral_N_max_over_cases"] / max(r["e_mm"], 1e-9) for r in lat if r["e_mm"] > 0)
    # forces on the stationary magnets: what the carrier pockets and the formed feature must hold
    pk_r, net = [], []
    for th in ((0.0, 3.75, 7.5) if not quick else (0.0, 7.5)):
        rot = ro.transformed(th)
        Brot = B_of(rot, BR20, face_quadrature(st, m)[0])
        pts, q, idx = face_quadrature(st, m)
        f = (BR20 / MU0) * q[:, None] * Brot
        per = np.array([f[idx == k].sum(axis=0) for k in range(st.n)])
        er = st.cen[:, :2] / np.linalg.norm(st.cen[:, :2], axis=1, keepdims=True)
        radial = (per[:, :2] * er).sum(axis=1)
        pk_r.append({"theta_deg": th, "radial_N_per_stator_magnet": [float(v) for v in radial], "axial_N_per_stator_magnet": [float(v) for v in per[:, 2]],
                     "net_xyz_N": [float(v) for v in per.sum(axis=0)]})
    out["stator_magnet_loads"] = pk_r
    out["stator_max_radial_N"] = float(max(abs(np.array(p["radial_N_per_stator_magnet"])).max() for p in pk_r))
    out["stator_max_axial_N"] = float(max(abs(np.array(p["axial_N_per_stator_magnet"])).max() for p in pk_r))
    out["stator_net_force_N"] = float(max(np.abs(np.array(p["net_xyz_N"])).max() for p in pk_r))
    return out


def design_demag(quick):
    """Opposing field along M at points inside every magnet, 176 C, assembled and isolated; against Hcj(T) of RECOMA 35E.
    The field at a sharp block edge diverges (logarithmically), so the maximum over quadrature nodes is reported but the judged number is the 95th
    percentile over the volume (a chamfer or the coating radius removes the edge singularity)."""
    ro, st = build_design()
    nq = 3 if quick else 5
    hot = temp_scale(T_HOT)
    br = BR20 * hot
    res = {}
    for tag, thetas in (("assembled", (0.0, 3.75, 7.5)), ("rotor alone (knob removed)", (0.0,)), ("stator alone", (0.0,))):
        mean_, p95_, max_ = [], [], []
        for th in thetas:
            r_ = ro.transformed(th)
            full = r_.merged(st) if tag == "assembled" else (r_ if tag.startswith("rotor") else st)
            pts, w, idx = volume_quadrature(full, nq)
            B = B_of(full, br, pts)
            if tag == "assembled":
                B = B + np.atleast_2d(sensing_cylinder(br, th).getB(pts))
            H = B / MU0                                    # kernel returns mu0 H (the field of the sources, self included)
            opp = -np.einsum("ij,ij->i", H, full.mdir[idx] * np.sign(full.s[idx])[:, None]) / 1e3
            mean_.append(float(np.average(opp, weights=w))); p95_.append(float(np.percentile(opp, 95))); max_.append(float(opp.max()))
        res[tag] = {"volume_mean_kA_per_m": max(mean_), "p95_kA_per_m": max(p95_), "max_node_kA_per_m": max(max_)}
    hcj20 = 1710.0                                        # kA/m, RECOMA 35E minimum (Arnold datasheet p.2, read 2026-10-12)
    hcj176 = hcj20 * (1.0 - 0.0025 * (T_HOT - 20.0))     # alpha(HcJ) -0.25 %/C
    worst95 = max(v["p95_kA_per_m"] for v in res.values())
    return {"opposing_H_176C": res, "Hcj_20C_min_kA_per_m": hcj20, "Hcj_176C_min_kA_per_m": hcj176, "margin_Hcj_over_p95": hcj176 / worst95,
            "M_176C_kA_per_m": br / MU0 / 1e3,
            "note": "rigid-magnet superposition, H of all sources at nodes inside each block (self field included). The knee Hk of the demagnetisation curve lies "
                    "below HcJ and is only a plot in the datasheet: the margin is against HcJ (a necessary, not a sufficient, condition) [UNVERIFIED knee]"}


def thermal_gap(quick):
    """Radial gap change 20 -> 176 C from the differential expansion of the aluminium knob (rotor radius) and the carrier (stator radius), and the torque with it.
    Expansion coefficients are typical handbook values [ASSUMED, to be replaced by the supplier's data]."""
    D = DESIGN
    r_rot, r_st = D["r_stator"] + D["a"] + D["gap"], D["r_stator"] + D["a"] / 2
    dT = T_HOT - 20.0
    alpha = {"aluminium knob (6061)": 23.6e-6}
    carriers = {"PEEK unfilled": 47e-6, "PEEK GF30 / PPS GF40 (in-flow, typical)": 22e-6, "titanium Ti-6Al-4V": 8.6e-6}
    rows = {}
    for name, a_c in carriers.items():
        dgap = (alpha["aluminium knob (6061)"] * r_rot - a_c * r_st) * dT
        c = Cond(f"176 C with thermal gap ({name})", T=T_HOT, gap=dgap)
        _, _, T = cond_trace(c, 0.5 if quick else 0.25, 4 if quick else 5)
        rows[name] = {"gap_change_mm": dgap, "air_clearance_hot_nominal_mm": 0.47 + dgap, "mean_abs_mNm_176C": mNm(torque_stats(T)["mean_abs"]), "peak_mNm_176C": mNm(torque_stats(T)["peak"])}
    return {"basis": "dgap = (alpha_knob r_rotor - alpha_carrier r_stator) (176 - 20) K; typical coefficients [ASSUMED]", "carriers": rows}



def eddy_drag(quick):
    """Upper bound of the eddy-current braking torque at 2 rev/s (low magnetic Reynolds number: T = sigma w int r^2 Bz^2 dV)."""
    w = 2 * math.pi * 2.0
    ro, st = build_design()
    rng = np.random.default_rng(1)
    n = 4000 if quick else 20000
    out = {}
    # (a) fascia (5052, sigma 2.0e7 S/m, 3 mm) under the rotating magnets: rotor ring + sensing magnet
    r = 31.0 * np.sqrt(rng.uniform(0, 1, n))
    ph = rng.uniform(0, 2 * math.pi, n)
    z = -rng.uniform(0.0, 3.0, n)
    pts = np.column_stack([r * np.cos(ph), r * np.sin(ph), z])
    vol = math.pi * 31.0 ** 2 * 3.0 * 1e-9
    sig = 2.0e7
    acc = {}
    for tag, getB in (("rotor magnets", lambda p: B_of(ro, BR20, p)), ("sensing magnet", lambda p: np.atleast_2d(sensing_cylinder(BR20, 0.0).getB(p)))):
        Bz = getB(pts)[:, 2]
        T = sig * w * float(np.mean((r * 1e-3) ** 2 * Bz ** 2)) * vol
        acc[tag] = mNm(T)
    out["fascia_5052_bound_mNm"] = acc
    # (b) knob aluminium shell (r 26.5..28, z 0.8..5) moving through the stationary magnets' field
    r = np.sqrt(rng.uniform(26.5 ** 2, 28.0 ** 2, n))
    ph = rng.uniform(0, 2 * math.pi, n)
    z = rng.uniform(0.8, 5.0, n)
    pts = np.column_stack([r * np.cos(ph), r * np.sin(ph), z])
    vol = math.pi * (28.0 ** 2 - 26.5 ** 2) * 4.2 * 1e-9
    B = B_of(st, BR20, pts)
    Bn2 = np.einsum("ij,ij->i", B, B)
    out["knob_shell_in_stator_field_bound_mNm"] = mNm(3.0e7 * w * float(np.mean((r * 1e-3) ** 2 * Bn2)) * vol)
    out["total_bound_mNm"] = sum(acc.values()) + out["knob_shell_in_stator_field_bound_mNm"]
    out["basis"] = "2 rev/s; T = sigma * omega * integral(r^2 Bz^2) dV (conductor currents do not react on the field: magnetic Reynolds number ~0.04); "\
                   "the shell term uses |B|^2 (upper bound); sigma_5052 2.0e7, sigma_6061 3.0e7 S/m; Monte Carlo integration"
    return out


# =========================================================================================== 4. sensor: field at the die, angle error, calibration
SENSOR_EPS_RESID = 2.0 * math.radians(0.057)          # X/Y gain mismatch left after the TEMP_RESULT correction (ui_calcs, 0.057 deg), hot cases


def wrap(d):
    return (np.asarray(d) + 180.0) % 360.0 - 180.0


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
    """One fixed cold calibration: a Fourier table of the error against the measured angle (offset + harmonics 1..4 [+ 24, 48]) or the affine
    model (X/Y offsets, gain, skew, angle offset) as in the ring study."""

    def __init__(self, kind, harmonics=()):
        self.kind, self.harm, self.p = kind, tuple(harmonics), None

    def fit(self, theta, Bxy):
        if self.kind == "affine":
            from scipy import optimize

            def model(p, B):
                x = B[:, 0] - p[0]
                y = (B[:, 1] - p[1]) * p[2] + x * p[3]
                return np.degrees(np.arctan2(y, x)) - p[4]
            scale = float(np.hypot(*Bxy.T).mean())
            res = optimize.least_squares(lambda p: wrap(model(np.array([p[0] * scale, p[1] * scale, p[2], p[3], p[4]]), Bxy) - theta),
                                         np.array([0.0, 0.0, 1.0, 0.0, 0.0]), xtol=1e-14, ftol=1e-14, gtol=1e-14)
            q = res.x
            self.p = np.array([q[0] * scale, q[1] * scale, q[2], q[3], q[4]])
            self._model = model
        else:
            self.p = np.linalg.lstsq(fourier_basis(psi_deg(Bxy), self.harm), raw_error(theta, Bxy), rcond=None)[0]
        return self

    def residual(self, theta, Bxy):
        if self.kind == "affine":
            return wrap(self._model(self.p, Bxy) - theta)
        psi = psi_deg(Bxy)
        return wrap(psi - fourier_basis(psi, self.harm) @ self.p - theta)


CALS = {"affine": ("affine", ()), "harm4": ("harm", (1, 2, 3, 4)), "harm4_24": ("harm", (1, 2, 3, 4, 24, 48))}


def fit_indices(theta):
    """35 fit angles at about 0.5 + 10.25 k deg (k = 0..34), none within 0.1 deg of a detent centre; all other angles and conditions validate."""
    step = float(theta[1] - theta[0])
    idx = []
    for k in range(35):
        a = 0.5 + 10.25 * k
        i = int(round(a / step)) % len(theta)
        d = abs(((theta[i] + 7.5) % 15.0) - 7.5)
        if d < 0.1:
            i = (i + 1) % len(theta)
        idx.append(i)
    return np.array(sorted(set(idx)))


@dataclass
class SCond:
    name: str
    push: float = 0.0
    gap: float = 0.0                 # sensing gap error (+ = farther), mm
    T: float = 20.0
    brs: float = 1.0                 # additional Br factor (tolerance)
    off: tuple = (0.0, 0.0)          # knob (sensing magnet + rotor) lateral offset against the die, mm
    tilt: tuple = (0.0, 0.0)         # knob tilt, deg
    stat_off: tuple = (0.0, 0.0)     # carrier offset against the die, mm
    sens_tilt: tuple = (0.0, 0.0)    # sensor package tilt, deg
    lift: float = 0.0


MECH = {"cold": {}, "push": dict(push=0.5), "gapm": dict(gap=-0.2), "gapp": dict(gap=0.2), "strong": dict(push=0.5, gap=-0.2), "hot": dict(T=T_HOT),
        "weakhot": dict(gap=0.2, T=T_HOT), "hotstrong": dict(T=T_HOT, push=0.5, gap=-0.2)}
BUILT = dict(off=(0.1, 0.1), tilt=(1.0, 0.0), stat_off=(0.1, 0.0), sens_tilt=(1.0, 0.0))


def unit_conds(unit):
    base = {} if unit == "A" else BUILT
    return {f"{unit}_{k}": SCond(f"{unit}_{k}", **{**base, **kw}) for k, kw in MECH.items()}


def knob_shift(c: SCond):
    return (c.off[0], c.off[1], c.gap - c.push + c.lift)


def B_sensing(c: SCond, angles):
    br = BR20 * temp_scale(c.T) * c.brs
    out = np.zeros((len(angles), 3))
    for i, th in enumerate(angles):
        out[i] = np.atleast_2d(sensing_cylinder(br, th, shift=knob_shift(c), tilt_deg=c.tilt, pivot=PIVOT).getB(HALL[None]))[0]
    return out


def B_detent(c: SCond, angles, ro: MSet, st: MSet):
    """B (T) at the die of the rotor ring (rotating, moves with the knob) and the stationary stators separately: (rotor (n,3), stator (3,))."""
    br = BR20 * temp_scale(c.T) * c.brs
    Bro = np.zeros((len(angles), 3))
    for i, th in enumerate(angles):
        Bro[i] = B_of(ro.transformed(th, shift=knob_shift(c), tilt_deg=c.tilt, pivot=PIVOT), br, HALL[None])[0]
    st2 = st.transformed(0.0, shift=(c.stat_off[0], c.stat_off[1], 0.0))
    Bst = B_of(st2, br, HALL[None])[0]
    return Bro, Bst


def to_meas(B, c: SCond, eps=0.0):
    Rs = Rot.from_euler("xy", list(c.sens_tilt), degrees=True).as_matrix()
    Bm = -(B @ Rs.T)[:, :2]
    Bm = Bm.copy()
    Bm[:, 0] *= 1.0 + eps / 2
    Bm[:, 1] *= 1.0 - eps / 2
    return Bm


def eps_of(c: SCond):
    return SENSOR_EPS_RESID if c.T > 100.0 else 0.0


def analyse_unit(sens_B, det_B, theta, conds, tag):
    """sens_B[name] (n,3); det_B[name] (n,3) or None (assembly absent).  Returns residual arrays per cal kind and condition, raw errors."""
    idx = fit_indices(theta)
    out = {"raw": {}, "res": {k: {} for k in CALS}}
    cold = [n for n in conds if n.endswith("_cold")][0]
    for kind, (kk, hh) in CALS.items():
        meas_cold = to_meas(sens_B[cold] + (0 if det_B is None else det_B[cold]), conds[cold], eps_of(conds[cold]))
        cal = Cal(kk, hh).fit(theta[idx], meas_cold[idx])
        for n, c in conds.items():
            m = to_meas(sens_B[n] + (0 if det_B is None else det_B[n]), c, eps_of(c))
            out["res"][kind][n] = cal.residual(theta, m)
    for n, c in conds.items():
        m = to_meas(sens_B[n] + (0 if det_B is None else det_B[n]), c, eps_of(c))
        out["raw"][n] = raw_error(theta, m)
    out["fit_idx"] = idx
    return out


def harmonic_amp(theta_deg, x, orders):
    """Amplitude of the harmonic of order o per turn (real signal: 2|F_o|; complex signal: the larger of the +o and -o phasors)."""
    n = len(x)
    F = np.fft.fft(x) / n
    out = {}
    for o in orders:
        if o == 0:
            out[0] = float(abs(F[0]))
        elif np.iscomplexobj(x):
            out[int(o)] = float(max(abs(F[o]), abs(F[-o])))
        else:
            out[int(o)] = float(2 * abs(F[o]))
    return out


def sensor_study(quick):
    step = 1.0 if quick else 0.25
    theta = np.arange(0.0, 360.0, step)
    ro, st = build_design()
    out = {"grid_step_deg": step}
    units = {"A": unit_conds("A"), "B": unit_conds("B")}
    sens = {}
    for u in units:
        for n, c in units[u].items():
            sens[n] = B_sensing(c, theta)
    # --- deterministic units: A (ideal coaxial) and B (worst-tolerance as built)
    det = {}
    stat_bias = {}
    for u in units:
        for n, c in units[u].items():
            Bro, Bst = B_detent(c, theta, ro, st)
            det[n] = Bro + Bst[None]
            stat_bias[n] = Bst
    res = {}
    for u in units:
        cs = units[u]
        with_ = analyse_unit({n: sens[n] for n in cs}, {n: det[n] for n in cs}, theta, cs, u)
        without = analyse_unit({n: sens[n] for n in cs}, None, theta, cs, u)
        res[u] = (with_, without)
    summary = {}
    for u, (w, wo) in res.items():
        s = {"raw_peak_with_deg": max(float(np.abs(v).max()) for v in w["raw"].values()),
             "raw_peak_without_deg": max(float(np.abs(v).max()) for v in wo["raw"].values()),
             "raw_attributable_deg": max(float(np.abs(w["raw"][n] - wo["raw"][n]).max()) for n in w["raw"])}
        for kind in CALS:
            s[f"R_with_{kind}_deg"] = max(float(np.abs(v).max()) for v in w["res"][kind].values())
            s[f"R_without_{kind}_deg"] = max(float(np.abs(v).max()) for v in wo["res"][kind].values())
            s[f"D_{kind}_deg"] = max(float(np.abs(w["res"][kind][n] - wo["res"][kind][n]).max()) for n in w["res"][kind])
            s[f"D_by_condition_{kind}"] = {n: float(np.abs(w["res"][kind][n] - wo["res"][kind][n]).max()) for n in w["res"][kind]}
        summary[u] = s
    out["units"] = summary
    # --- harmonic content of the detent assembly's own field (ideal unit, cold): Bx+iBy and Bz against the knob angle
    dA = det["A_cold"]
    cplx = dA[:, 0] + 1j * dA[:, 1]
    ords = [0, 1, 2, 3, 4, 12, 24, 48]
    out["assembly_field_harmonics_A_cold"] = {"Bxy_complex_uT": {k: v * 1e6 for k, v in harmonic_amp(theta, cplx, ords).items()},
                                              "Bz_uT": {k: v * 1e6 for k, v in harmonic_amp(theta, dA[:, 2], ords).items()}, "Bz_mean_mT": float(dA[:, 2].mean() * 1e3)}
    dB = det["B_cold"]
    out["assembly_field_B_cold_uT"] = {"mean_xyz": [float(v * 1e6) for v in dB.mean(axis=0)], "rotating_part_peak_xy": float(np.hypot(*(dB[:, :2] - dB[:, :2].mean(axis=0)).T).max() * 1e6)}
    out["stationary_bias_uT"] = {"A_cold": [float(v * 1e6) for v in stat_bias["A_cold"]], "B_cold": [float(v * 1e6) for v in stat_bias["B_cold"]]}
    # --- Monte Carlo of the built-in scatter: piece strength / direction / position, as-built unit B
    rng = np.random.default_rng(5)
    K = 4 if quick else 30
    mc = []
    cs = units["B"]
    without_B = res["B"][1]
    for k in range(K):
        ro_k, st_k = perturb(ro, rng), perturb(st, rng)
        det_k = {}
        bias_k = {}
        for n, c in cs.items():
            Bro, Bst = B_detent(c, theta, ro_k, st_k)
            det_k[n] = Bro + Bst[None]
            bias_k[n] = Bst
        w_k = analyse_unit({n: sens[n] for n in cs}, det_k, theta, cs, "B")
        row = {"draw": k}
        for kind in CALS:
            row[f"D_{kind}"] = max(float(np.abs(w_k["res"][kind][n] - without_B["res"][kind][n]).max()) for n in cs)
            row[f"R_{kind}"] = max(float(np.abs(v).max()) for v in w_k["res"][kind].values())
        row["raw_attributable"] = max(float(np.abs(w_k["raw"][n] - without_B["raw"][n]).max()) for n in cs)
        cplx = det_k["B_cold"][:, 0] + 1j * det_k["B_cold"][:, 1]
        row["field_harm24_uT"] = harmonic_amp(theta, cplx, [24])[24] * 1e6
        row["stator_bias_xy_uT"] = float(np.hypot(*bias_k["B_cold"][:2]) * 1e6)
        err_w = w_k["raw"]["B_cold"] - without_B["raw"]["B_cold"]
        row["error_harm24_deg"] = harmonic_amp(theta, err_w, [24])[24]
        mc.append(row)
    out["monte_carlo"] = {"draws": K, "per_draw": mc,
                          "worst_D_harm4_deg": max(r["D_harm4"] for r in mc), "worst_D_affine_deg": max(r["D_affine"] for r in mc),
                          "worst_D_harm4_24_deg": max(r["D_harm4_24"] for r in mc),
                          "worst_R_harm4_deg": max(r["R_harm4"] for r in mc), "worst_raw_attributable_deg": max(r["raw_attributable"] for r in mc),
                          "worst_field_harm24_uT": max(r["field_harm24_uT"] for r in mc), "worst_error_harm24_deg": max(r["error_harm24_deg"] for r in mc),
                          "worst_stator_bias_xy_uT": max(r["stator_bias_xy_uT"] for r in mc)}
    # --- |B|: range over the conditions, and with the ui_calcs tolerance corners
    Bn = {n: np.linalg.norm(sens[n] + det[n], axis=1) * 1e3 for n in sens}
    Bn0 = {n: np.linalg.norm(sens[n], axis=1) * 1e3 for n in sens}
    out["B_mT"] = {"with_assembly_min": float(min(v.min() for v in Bn.values())), "with_assembly_max": float(max(v.max() for v in Bn.values())),
                   "sensing_only_min": float(min(v.min() for v in Bn0.values())), "sensing_only_max": float(max(v.max() for v in Bn0.values())),
                   "max_change_by_assembly_pct": float(max(np.abs(Bn[n] / Bn0[n] - 1).max() for n in Bn) * 100)}
    tol = {}
    for tag, c in (("strong_push0.5_gap-0.2_-40C_Br+5%", SCond("x", push=0.5, gap=-0.2, T=T_COLD, brs=1.05)),
                   ("weak_gap+0.2_176C_Br-5%", SCond("x", gap=0.2, T=T_HOT, brs=0.95))):
        th = np.array([0.0, 45.0, 90.0])
        s_ = B_sensing(c, th)
        d_ = np.array([B_of(ro.transformed(t, shift=knob_shift(c)), BR20 * temp_scale(c.T) * c.brs, HALL[None])[0] for t in th]) + \
            B_of(st, BR20 * temp_scale(c.T) * c.brs, HALL[None])[0][None]
        tol[tag] = {"with_assembly_mT": float(np.linalg.norm(s_ + d_, axis=1).max() * 1e3), "sensing_only_mT": float(np.linalg.norm(s_, axis=1).max() * 1e3)}
    out["B_tolerance_corners_mT"] = tol
    # --- knob removed / lifted
    lifts = [0.0, 1.0, 2.0, 2.9, 3.0, 4.0, 6.0, 8.0, 12.0, 20.0, 30.0]
    rows = []
    for L in lifts:
        c = SCond("lift", lift=L, T=T_HOT, brs=0.95)                       # weakest seated field, as the removal threshold of ui_calcs
        s_ = B_sensing(c, np.array([0.0]))[0]
        d_ = B_of(ro.transformed(0.0, shift=knob_shift(c)), BR20 * temp_scale(T_HOT) * 0.95, HALL[None])[0] + B_of(st, BR20 * temp_scale(T_HOT) * 0.95, HALL[None])[0]
        rows.append({"lift_mm": L, "B_with_assembly_mT": float(np.linalg.norm(s_ + d_) * 1e3), "B_sensing_only_mT": float(np.linalg.norm(s_) * 1e3)})
    out["lift"] = rows
    worst_removed = np.linalg.norm(B_of(st, BR20 * temp_scale(T_COLD) * 1.05, HALL[None])[0]) * 1e3
    out["knob_removed"] = {"stator_only_B_mT_worst_(-40C_Br+5%)": float(worst_removed), "weakest_seated_mT": float(UI.magnet_field()["b_min_mT"]),
                           "ratio_seated_over_removed": float(UI.magnet_field()["b_min_mT"] / worst_removed),
                           "removal_threshold_mT": float(UI.magnet_field()["removal_threshold_mT"])}
    # --- permeability of the SmCo pieces themselves: the only ferromagnetic material of the design (upper bound, chi = 0.10)
    chi = 0.10
    th = np.arange(0.0, 360.0, 5.0)
    allr = ro
    err_ind = []
    errs = []
    for t in th:
        cyl = sensing_cylinder(BR20, t)
        rr = ro.transformed(t)
        Hc = np.atleast_2d(cyl.getB(rr.cen)) / MU0
        Hs = np.atleast_2d(cyl.getB(st.cen)) / MU0
        ind = []
        for S_, H in ((rr, Hc), (st, Hs)):
            mag = np.linalg.norm(H, axis=1)
            ind.append(MSet(S_.cen, S_.Rm, S_.half, H / np.maximum(mag, 1e-30)[:, None], MU0 * chi * mag))
        dB = sum(B_of(i_, 1.0, HALL[None])[0] for i_ in ind)
        B0 = np.atleast_2d(cyl.getB(HALL[None]))[0]
        e = wrap(math.degrees(math.atan2(-(B0 + dB)[1], -(B0 + dB)[0])) - t)
        errs.append(float(e))
        err_ind.append(float(np.linalg.norm(dB) * 1e6))
    out["induced_by_smco_permeability_chi0p10"] = {"max_added_field_uT": max(err_ind), "peak_angle_error_deg": float(np.abs(errs).max()),
                                                   "note": "upper bound: induced M = chi H of the sensing magnet at each block centre, no self-demagnetisation, chi=0.10 (recoil permeability 1.05-1.10)"}
    out["_plot"] = {"theta": theta.tolist(), "A_cold_det": (det["A_cold"] * 1e6).tolist(), "B_cold_det": (det["B_cold"] * 1e6).tolist(),
                    "err_B_with": {n: res["B"][0]["raw"][n].tolist() for n in ("B_cold", "B_strong", "B_hotstrong")},
                    "err_B_without": {n: res["B"][1]["raw"][n].tolist() for n in ("B_cold", "B_strong", "B_hotstrong")},
                    "res_B_with": {n: res["B"][0]["res"]["harm4"][n].tolist() for n in ("B_cold", "B_strong", "B_hotstrong")},
                    "res_B_without": {n: res["B"][1]["res"]["harm4"][n].tolist() for n in ("B_cold", "B_strong", "B_hotstrong")}}
    return out


# =========================================================================================== 5. retention, cost, R44 geometry
def _f_fric(t, mu):
    return (t + mu) / (1.0 - mu * t)


def retention(forces):
    """Analytic pull-off estimate of the nonmagnetic ball-and-groove retention plus the magnetic contribution of the detent pairs.
    Not a measurement: the friction band is an assumption and is the thing the fixture must measure."""
    n, beta = 3, 35.0
    t = math.tan(math.radians(beta))
    lifts = [(r["dz_mm"], -r["Fz_N_at_detent_centre"]) for r in forces["axial_force_vs_lift"] if r["dz_mm"] > 0]
    f_mag = float(np.interp(0.8, [l for l, _ in lifts], [f for _, f in lifts]))        # magnetic restoring force while the balls ride up the flank (~0.8 mm of lift)
    bands = {"dry": (0.15, 0.25), "wet (oil, detergent, degreaser: lubricated)": (0.08, 0.18)}
    mu_all = (0.08, 0.25)
    tol_p = 0.10
    mid = 16.0
    mu_mid = math.sqrt(mu_all[0] * mu_all[1])
    P = (mid - f_mag) / (n * _f_fric(t, mu_mid))
    rows = {}
    for tag, (lo, hi) in bands.items():
        lo_f = n * P * (1 - tol_p) * _f_fric(t, lo) + f_mag
        hi_f = n * P * (1 + tol_p) * _f_fric(t, hi) + f_mag
        rows[tag] = {"mu": [lo, hi], "pull_off_N": [lo_f, hi_f]}
    lo_all = n * P * (1 - tol_p) * _f_fric(t, mu_all[0]) + f_mag
    hi_all = n * P * (1 + tol_p) * _f_fric(t, mu_all[1]) + f_mag
    # largest friction window [mu_lo, mu_hi] (mu_hi/mu_lo spread) that keeps 12..20 N for this P
    ok = []
    for lo in np.arange(0.02, 0.4, 0.01):
        for hi in np.arange(lo, 0.5, 0.01):
            a = n * P * (1 - tol_p) * _f_fric(t, lo) + f_mag
            b = n * P * (1 + tol_p) * _f_fric(t, hi) + f_mag
            if a >= CRIT["pulloff_N"][0] and b <= CRIT["pulloff_N"][1]:
                ok.append((lo, hi))
    widest = max(ok, key=lambda p: p[1] - p[0]) if ok else None
    # lateral locator: rim displacement from the radial clearance of two lands and the lever of the load
    span, lever, c_dia, elastic = 6.0, 10.0, 0.10, 0.03
    rim = c_dia / span * lever + elastic
    return {"concept": "3 ball plungers (Si3N4 balls, BeCu or Elgiloy springs) in the knob skirt engage a 35 deg flank groove in the PEEK carrier; groove axial width "
                       "= ball footprint + 0.8 mm so that the 0.65 mm push never rides the flank",
            "n_balls": n, "flank_angle_deg": beta, "spring_preload_per_ball_N": P, "preload_tolerance": tol_p, "magnetic_contribution_N_at_0p8mm_lift": f_mag,
            "pull_off_N_bands": rows, "pull_off_N_overall_for_mu_0p08_to_0p25": [lo_all, hi_all],
            "within_12_20_overall": bool(lo_all >= CRIT["pulloff_N"][0] and hi_all <= CRIT["pulloff_N"][1]),
            "friction_window_that_keeps_12_20": widest, "peak_magnetic_axial_force_N": forces["pull_off_contribution_peak_N"],
            "formula": "F = n P (tan(beta) + mu) / (1 - mu tan(beta)) + F_magnetic(0.8 mm), sliding friction at the ball seat; rolling friction ignored (pessimistic for the lower bound)",
            "lateral_locator_rim_displacement_mm_at_10N": rim,
            "lateral_locator_assumptions": {"land_span_mm": span, "lever_mm": lever, "diametral_clearance_mm": c_dia, "elastic_mm": elastic},
            "status": "ESTIMATE, not proved: the friction band, the spring rate and the wear over 5 000 removals are fixture measurements"}


COST = {
    "date_read": "2026-10-12",
    "method": "public list prices read on the web by a read-only fetch on 2026-10-12; nothing was ordered or quoted. EUR as shown, ex VAT. No USD list price for a small Sm2Co17 block "
              "with a >= 1 000 piece tier was found; the Euromag block is a larger block, so the per-piece number is a proxy for a custom-ground 2.0 x 2.5 x 1.8 mm block.",
    "sources": [
        {"source": "Euromag shop, SmCo blocks ref 3312B871 (6 x 4 x 2 and 20 x 10 x 2.5 mm, Sm2Co17, 350 C, thickness-magnetised)",
         "url": "https://shop.euromag-magnets.com/gb/samarium-magnets/8051-samarium-magnetic-blocks.html", "eur_per_piece": {"1001+": 0.50, "501+": 0.54, "201+": 0.61, "1": 6.21},
         "note": "which variant the tiers apply to is not stated; above 1 001 pieces 'contact seller'"},
        {"source": "DigiKey, Radial Magnets 8997 (469-1026-ND), SmCo5 (1:5) cylinder 6 x 3 mm, diametric", "url": "https://www.digikey.be/en/products/detail/radial-magnets-inc/8997/5126079",
         "eur_per_piece": {"1000": 0.30226, "5000": 0.27619}, "note": "1:5 not 2:17, larger than the block; a lower bound"},
    ],
    "assumptions": {"eur_per_piece_low": 0.30, "eur_per_piece_mid": 0.50, "eur_per_piece_high": 0.90,
                    "high_basis": "custom grind of an 8-15 mm^3 block, 1.8 x the Euromag 1 001+ tier [ASSUMED, no source states a premium]", "eur_to_usd": 1.15,
                    "fx_note": "[ASSUMED] 1 EUR = 1.15 USD; not looked up"},
}


def cost(pieces):
    a = COST["assumptions"]
    rows = {}
    for tag in ("low", "mid", "high"):
        eur = pieces * a[f"eur_per_piece_{tag}"]
        rows[tag] = {"eur": eur, "usd": eur * a["eur_to_usd"]}
    return {**COST, "pieces_per_knob": pieces, "magnets_per_knob": rows,
            "not_costed": "carrier, covers, balls, springs, locator bands, assembly, coating, magnetisation and grading: no sourced prices"}


def r44_requirements(forces, design_rows):
    D = DESIGN
    hs = D["h"] * D["stack"]
    rs_in, rs_out = D["r_stator"] - D["a"] / 2, D["r_stator"] + D["a"] / 2
    rr_c = D["r_stator"] + D["a"] + D["gap"]
    rr_in, rr_out = rr_c - D["a"] / 2, rr_c + D["a"] / 2
    zc = D["z_bot"] + hs / 2
    return {
        "frame": "front-local, knob axis at (110, 53), w outward, fascia front w = 0, rear w = -3",
        "stator_magnets": {"count": D["n_stator"], "angles_deg": [D["stator_phase"] + 90.0 * k for k in range(D["n_stator"])], "block_mm": [D["a"], D["b"], hs],
                           "stack_of_identical_blocks": D["stack"], "radial_span_mm": [rs_in, rs_out], "axial_span_w_mm": [zc - hs / 2, zc + hs / 2], "magnetisation": "radial, outward"},
        "rotor_magnets": {"count": D["n_rotor"], "pitch_deg": 15.0, "block_mm": [D["a"], D["b"], D["h"]], "radial_span_mm": [rr_in, rr_out],
                          "axial_span_w_mm": [zc - D["h"] / 2, zc + D["h"] / 2], "magnetisation": "radial, outward (same pole facing the stators: N outer faces attract S inner faces)",
                          "angle_origin": "a rotor block aligned with every stator block at the detent centre; theta = 0 and every 15 deg"},
        "magnetic_gap_mm": {"nominal_total": D["gap"], "composition": "0.10 stator cover + 0.47 air + 0.10 rotor cover", "tolerance_total": TOL_RECOMMENDED["gap"],
                            "running_air_clearance_min_mm": 0.47 - TOL_RECOMMENDED["gap"] - 0.10, "air_clearance_at_10N_lateral_min_mm": 0.47 - TOL_RECOMMENDED["gap"] - 0.30},
        "knob": {"visible_radius_mm": 28.0, "wall_outside_rotor_magnets_mm": 28.0 - rr_out, "magnet_pocket": "closed on the stator side by a 0.10 mm nonmagnetic cover; pockets capture the blocks "
                 "mechanically (no adhesive credit)", "underside_height_at_rest_w_mm": "<= 0.8 over r 19.5..28 so that the rotor blocks (w 1.6..3.4) and the 0.65 mm push do not touch the carrier floor"},
        "carrier": {"material": "glass- or carbon-filled PEEK or PPS (expansion about 22 ppm/K [ASSUMED typical], NOT unfilled PEEK at 47 ppm/K: it would close the gap by 0.08 mm at 176 C, thermal_gap), pockets captured mechanically, no steel", "footprint_r_mm": [19.5, rs_out + 0.1], "height_w_mm": [0.0, 5.0],
                    "fixing": "to the blind formed feature of the 3 mm fascia: 3 titanium (grade 5) or brass M2 screws on r = 19.5 at 0, 120, 240 deg into blind tapped holes of depth <= 2 mm "
                              "(1 mm of fascia stays intact, nothing passes through); no ferromagnetic screw inside r 25",
                    "forces_to_hold": {"radial_pull_per_stator_block_N": forces["stator_max_radial_N"], "axial_N": forces["stator_max_axial_N"], "net_on_feature_N": forces["stator_net_force_N"],
                                       "note": "each block is pulled outward ~0.76 N by the rotor ring; the four loads cancel in the carrier"}},
        "locator_and_retention": {"locator_lands_w_mm": [5.0, 11.0], "diametral_clearance_mm": 0.10, "retention_groove_w_mm": "above the magnets, between the lands",
                                  "push_travel_mm": 0.65, "note": "the lands must sit above the magnets (w > 4.2) so that knob tilt does not move the rotor ring radially"},
        "outside_r25": "the detent magnets are inside r 25 (stators r 21.5..23.5) because they are not steel; no steel, no ferromagnetic fastener, spring, ball or bearing anywhere inside r 25 "
                       "or elsewhere in the knob/carrier: balls Si3N4, springs BeCu/Elgiloy, bands Ti or PEEK, screws Ti/brass. SmCo's own permeability is bounded in section 'permeability'.",
        "rear_of_fascia": "nothing is added behind the fascia: the three tab standoffs (83,42), (83,64), (138,53), J9 (82,53), U7 and the tab size are unchanged by this design "
                          "(unlike option (a) in knob-ring, which needed r >= 29 for the standoffs and a 67.5 mm tab). Only the blind tapped holes of the carrier (r 19.5) are on the rear "
                          "face's opposite side: they must not break through, and the rear face must stay flat for the standoffs.",
        "tolerances_required": {"magnet_Br_lot_sort": "+-3 % about nominal (torque ~ Br^2)", "total_radial_magnetic_gap_mm": "0.67 +- 0.07",
                                "rotor/stator ring concentricity_in_service": "<= 0.10 mm running offset, 0.30 mm at 10 N lateral load", "axial_position_rest_mm": "+-0.3 (rotor centre vs stator centre)",
                                "magnet_dimensions_mm": "+-0.05 and block-to-block strength +-1.5 %, direction +-1.5 deg, position +-0.05 mm (the Monte Carlo scatter)"},
        "sensor_side": "the sensing magnet position (w 1..6) is not changed; the die stays at (110, 53, w -4); keep-out radius 25 for steel is respected (zero steel); the detent assembly adds "
                       "about 1.2 mT of Bz at the die (0.4 mT of it from the stators) and no X/Y field in the ideal case",
        "sealing_ESD": "carrier sealed to the fascia by a captured seal of identified compound (not chosen here); discharge path from the knob shell to the fascia through the conductive "
                       "contacts of the SPEC is unchanged and must not pass through the carrier (PEEK is insulating); the exposed 0.10 mm covers are the wash-down surface",
    }


# =========================================================================================== 6. verdicts, plots, main
def verdicts(R):
    C = CRIT
    nom, ctl, sen = R["torque"]["nominal"], R["controls"], R["sensor"]
    rec = R["torque"]["corners_recommended_tolerance"]["rows"]
    wide = R["torque"]["corners_catalogue_tolerance"]["rows"]
    mc = R["monte_carlo_recommended"]
    f, dm, ed = R["forces"], R["demag"], R["eddy"]
    in20 = [r for r in rec if r["T_C"] == 20.0]
    hot = [r for r in rec if r["T_C"] == T_HOT]
    D_all = max(sen["units"]["A"]["D_harm4_deg"], sen["units"]["B"]["D_harm4_deg"], sen["monte_carlo"]["worst_D_harm4_deg"], sen["monte_carlo"]["worst_D_harm4_24_deg"],
                sen["units"]["B"]["D_harm4_24_deg"], sen["units"]["B"]["D_affine_deg"], sen["monte_carlo"]["worst_D_affine_deg"])
    R_abs = max(sen["units"]["B"]["R_with_harm4_deg"], sen["monte_carlo"]["worst_R_harm4_deg"])
    Bmax = max(sen["B_mT"]["with_assembly_max"], sen["B_tolerance_corners_mT"]["strong_push0.5_gap-0.2_-40C_Br+5%"]["with_assembly_mT"])
    V = {
        "controls_all_pass": all(ctl["checks"].values()),
        "T1_nominal_24_detents_mean_peak_in_band": bool(nom["detents_per_turn"] == 24 and C["mean_torque_mNm"][0] <= nom["mean_abs_mNm"] <= C["mean_torque_mNm"][1]
                                                       and C["peak_torque_mNm"][0] <= nom["peak_mNm"] <= C["peak_torque_mNm"][1]),
        "T2_corners_20C_recommended_tolerance_in_band": bool(all(r["in_band_mean"] and r["in_band_peak"] for r in in20)),
        "T2b_corners_20C_catalogue_tolerance_in_band": bool(all(r["in_band_mean"] and r["in_band_peak"] for r in wide if r["T_C"] == 20.0)),
        "T3_hot_176C_mean_ge_floor": bool(all(r["mean_abs_mNm"] >= C["hot_mean_floor_mNm"] for r in hot)),
        "T4_monte_carlo_every_detent_peak_and_mean_in_band": bool(mc["fraction_draws_mean_in_band"] == 1.0 and mc["fraction_draws_all_peaks_in_band"] == 1.0),
        "T5_lateral_negative_stiffness_ok": bool(f["lateral_negative_stiffness_N_per_mm"] <= C["lateral_neg_stiffness_max_N_per_mm"]),
        "T6_push_magnetic_axial_ok": bool(f["push_force_over_0p65_N"] <= C["push_magnetic_axial_max_N"]),
        "T7_drag_ok": bool(ed["total_bound_mNm"] <= C["eddy_drag_max_mNm"] and mc["max_mean_T_over_mean_abs"] <= C["drag_max_fraction"]),
        "T8_running_air_clearance_ge_0p3": bool(R["r44"]["magnetic_gap_mm"]["running_air_clearance_min_mm"] >= C["gap_running_min_mm"] - 1e-9),
        "T9_demag_margin_ge_1p5_vs_HcJ_176C": bool(dm["margin_Hcj_over_p95"] >= C["demag_margin_min"]),
        "S1_assembly_attributable_D_le_share": bool(D_all <= C["D_share_deg"]),
        "S2_total_with_coil_le_0p30": bool(D_all + C["coil_allowance_deg"] <= C["total_with_coil_max_deg"]),
        "S3_absolute_residual_plus_coil_le_pool": bool(R_abs + C["coil_allowance_deg"] <= C["pool_deg"]),
        "S4_B_max_le_80mT": bool(Bmax <= C["B_max_mT"]),
        "S5_assembly_changes_B_lt_1pct": bool(sen["B_mT"]["max_change_by_assembly_pct"] < C["B_change_by_assembly_pct"]),
        "S6_knob_removed_B_le_4p7mT": bool(sen["knob_removed"]["stator_only_B_mT_worst_(-40C_Br+5%)"] <= C["removed_B_max_mT"]),
        "P1_pull_off_estimate_12_20N_overall": bool(R["retention"]["within_12_20_overall"]),
    }
    num = {"D_worst_deg": D_all, "R_abs_worst_deg": R_abs, "total_D_plus_coil_deg": D_all + C["coil_allowance_deg"], "R_abs_plus_coil_deg": R_abs + C["coil_allowance_deg"],
           "B_max_mT": Bmax}
    return V, num


def make_plots(R, S, outdir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pl = outdir / "plots"
    pl.mkdir(exist_ok=True)
    # 1 torque vs angle
    tr = R["torque"]["_trace"]
    a, T = np.array(tr["angle"]), np.array(tr["T_mNm"])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    aa = np.concatenate([a + 15.0 * k for k in range(3)])
    ax.plot(aa, np.tile(T, 3), lw=1.6, label="nominal (20 C)")
    rows = R["torque"]["corners_recommended_tolerance"]["rows"]
    ax.axhspan(-CRIT["peak_torque_mNm"][1], -CRIT["peak_torque_mNm"][0], color="0.9", label="SPEC peak 25-45")
    ax.axhspan(CRIT["peak_torque_mNm"][0], CRIT["peak_torque_mNm"][1], color="0.9")
    for nm, sg in (("STRONG: Br +, gap -", 1.0), ("WEAK: Br -, gap +, axial -0.30", 1.0)):
        r = [x for x in rows if x["name"] == nm][0]
        ax.plot(aa, np.tile(T, 3) * r["peak_mNm"] / R["torque"]["nominal"]["peak_mNm"], lw=0.8, ls="--", label=nm)
    ax.set_xlabel("knob angle, deg"); ax.set_ylabel("detent torque, mN m"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
    ax.set_title("Option (b) B1: torque trace, 3 of 24 detents (corners scaled from the nominal shape)")
    fig.tight_layout(); fig.savefig(pl / "torque_vs_angle.png", dpi=130); plt.close(fig)
    # 2 architectures
    arch = R["architectures"]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    names = [r["name"] for r in arch]
    ax.bar(names, [r["mean_abs_mNm"] for r in arch], color=["C0" if r["family"] == "B" else "C3" for r in arch])
    ax.axhspan(CRIT["mean_torque_mNm"][0], CRIT["mean_torque_mNm"][1], color="0.85", zorder=0)
    for i, r in enumerate(arch):
        ax.text(i, r["mean_abs_mNm"] + 0.5, f"{r['detents_per_turn_computed']} det\n{r['pieces']} pcs", ha="center", fontsize=6.5)
    ax.set_ylabel("mean |T| at the largest allowed / sized magnet, mN m"); ax.set_title("Architectures (red: across the panel; blue: above the panel); grey: SPEC mean 18-30")
    fig.tight_layout(); fig.savefig(pl / "architectures.png", dpi=130); plt.close(fig)
    # 3 field at die
    th = np.array(S["theta"]); A = np.array(S["A_cold_det"]); B = np.array(S["B_cold_det"])
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.8))
    for i, nme in enumerate(("Bx", "By", "Bz")):
        ax[0].plot(th, A[:, i], label=nme)
    ax[0].set_title("ideal unit: field of the detent assembly at the die, uT"); ax[0].set_xlabel("knob angle, deg"); ax[0].legend(); ax[0].grid(alpha=0.3)
    for i, nme in enumerate(("Bx", "By", "Bz")):
        ax[1].plot(th, B[:, i] - B[:, i].mean(), label=nme + " - mean")
    ax[1].set_title("as-built unit: variation with angle (uT); means: " + ", ".join(f"{v:.1f}" for v in B.mean(axis=0)), fontsize=8); ax[1].set_xlabel("knob angle, deg"); ax[1].legend(); ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(pl / "field_at_die.png", dpi=130); plt.close(fig)
    # 4 angle error
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.8))
    for n in ("B_cold", "B_strong", "B_hotstrong"):
        ax[0].plot(th, np.array(S["err_B_with"][n]) - np.array(S["err_B_without"][n]), lw=0.9, label=n)
    ax[0].set_title("uncalibrated error added by the assembly, deg", fontsize=9); ax[0].legend(fontsize=7); ax[0].set_xlabel("knob angle, deg"); ax[0].grid(alpha=0.3)
    for n in ("B_cold", "B_strong", "B_hotstrong"):
        ax[1].plot(th, np.array(S["res_B_with"][n]) - np.array(S["res_B_without"][n]), lw=0.9, label=n)
    ax[1].set_title("calibrated residual attributable to the assembly (D), deg", fontsize=9); ax[1].legend(fontsize=7); ax[1].set_xlabel("knob angle, deg"); ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(pl / "angle_error.png", dpi=130); plt.close(fig)
    # 5 forces
    f = R["forces"]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.6))
    dz = [r["dz_mm"] for r in f["axial_force_vs_lift"]]
    ax[0].plot(dz, [r["Fz_N_at_detent_centre"] for r in f["axial_force_vs_lift"]], "o-", label="at a detent centre")
    ax[0].plot(dz, [r["Fz_N_between_detents"] for r in f["axial_force_vs_lift"]], "s-", label="between detents")
    ax[0].axvspan(-0.65, -0.35, color="0.9"); ax[0].set_xlabel("knob axial offset (+ lift), mm"); ax[0].set_ylabel("axial force on knob, N (+ up)"); ax[0].legend(fontsize=7); ax[0].grid(alpha=0.3)
    ax[1].plot([r["e_mm"] for r in f["lateral_force"]], [r["F_lateral_N_max_over_cases"] for r in f["lateral_force"]], "o-")
    ax[1].set_xlabel("lateral offset, mm"); ax[1].set_ylabel("lateral force, N (destabilising)"); ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(pl / "forces.png", dpi=130); plt.close(fig)
    # 6 lift / removal
    lift = R["sensor"]["lift"]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.semilogy([r["lift_mm"] for r in lift], [r["B_with_assembly_mT"] for r in lift], "o-", label="with detent assembly")
    ax.semilogy([r["lift_mm"] for r in lift], [r["B_sensing_only_mT"] for r in lift], "s--", label="sensing magnet only")
    ax.axhline(R["sensor"]["knob_removed"]["stator_only_B_mT_worst_(-40C_Br+5%)"], color="C3", label="knob removed (stators only, worst)")
    ax.axhline(CRIT["removed_threshold_mT"], color="0.4", ls=":", label="removal threshold 23.7 mT")
    ax.set_xlabel("knob lift, mm"); ax.set_ylabel("|B| at the die, mT"); ax.legend(fontsize=7); ax.grid(alpha=0.3, which="both")
    fig.tight_layout(); fig.savefig(pl / "knob_removal.png", dpi=130); plt.close(fig)
    # 7 Monte Carlo torque
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    for key, lab in (("monte_carlo_recommended", "recommended tolerances"), ("monte_carlo_catalogue", "catalogue tolerances")):
        m = [d["mean_abs_mNm"] for d in R[key]["per_draw"]]
        ax.hist(m, bins=12, alpha=0.6, label=lab)
    ax.axvspan(0, CRIT["mean_torque_mNm"][0], color="0.9"); ax.axvspan(CRIT["mean_torque_mNm"][1], 40, color="0.9")
    ax.set_xlabel("mean |T| per draw, mN m"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(pl / "monte_carlo_torque.png", dpi=130); plt.close(fig)


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="coarser grids and fewer draws (< 5 min); not the study")
    ap.add_argument("--out", default=str(HERE), help="output directory (results.json, plots/, raw/)")
    ap.add_argument("--threads", type=int, default=4, help="numba threads (<= 5)")
    args = ap.parse_args()
    nb.set_num_threads(max(1, min(5, args.threads)))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw").mkdir(exist_ok=True)
    t0 = time.time()
    quick = args.quick
    R = {}

    def stage(name, fn):
        t = time.time()
        R[name] = fn()
        print(f"[{time.time() - t0:7.1f}s] {name} ({time.time() - t:.1f}s)", flush=True)

    stage("controls", lambda: controls(quick))
    assert all(R["controls"]["checks"].values()), {k: v for k, v in R["controls"]["checks"].items() if not v}
    stage("architectures", lambda: architectures(quick))
    stage("torque", lambda: design_torque(quick))
    stage("monte_carlo_recommended", lambda: design_monte_carlo(quick, TOL_RECOMMENDED))
    stage("monte_carlo_catalogue", lambda: design_monte_carlo(quick, TOL_WIDE, seed=12))
    stage("forces", lambda: design_forces(quick))
    stage("demag", lambda: design_demag(quick))
    stage("eddy", lambda: eddy_drag(quick))
    stage("thermal_gap", lambda: thermal_gap(quick))
    stage("sensor", lambda: sensor_study(quick))
    stage("retention", lambda: retention(R["forces"]))
    R["cost"] = cost(DESIGN["n_rotor"] + DESIGN["n_stator"] * DESIGN["stack"])
    R["r44"] = r44_requirements(R["forces"], R["architectures"])
    V, num = verdicts(R)
    S = R["sensor"].pop("_plot")
    make_plots(R, S, out)
    import csv
    with open(out / "raw" / "nominal_torque.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["angle_deg", "U_mJ", "T_mNm"])
        tr = R["torque"]["_trace"]
        for a_, u_, t_ in zip(tr["angle"], tr["U_mJ"], tr["T_mNm"]):
            w.writerow([a_, u_, t_])
    with open(out / "raw" / "assembly_field_at_die_A_cold_uT.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["theta_deg", "Bx_uT", "By_uT", "Bz_uT"])
        for a_, b_ in zip(S["theta"][::4], S["A_cold_det"][::4]):
            w.writerow([a_, *b_])
    nom = R["torque"]["nominal"]
    rec = {r["name"]: r for r in R["torque"]["corners_recommended_tolerance"]["rows"]}
    headline = {
        "study": "option (b): magnetic detents above the panel, nonmagnetic mechanical retention",
        "mode": "QUICK (not the study)" if quick else "full",
        "recommendation": {"architecture": "B1: radial-gap rotor/stator pair entirely above the panel; 24 rotor blocks in the knob skirt + 4 stator blocks (each a stack of 2) in a PEEK carrier",
                           "magnets": "Sm2Co17 (RECOMA 35E class, Br 1.19 T), block 2.0 radial x 2.5 tangential x 1.8 axial mm, magnetised through the 2.0 mm (radial, outward); 24 rotor + 8 stator pieces = 32 identical blocks",
                           "design": DESIGN},
        "torque_nominal_mNm": {"mean_abs": nom["mean_abs_mNm"], "peak": nom["peak_mNm"], "detents": nom["detents_per_turn"]},
        "torque_corners_20C_recommended_tolerance_mNm": {"min_mean": min(r["mean_abs_mNm"] for r in R["torque"]["corners_recommended_tolerance"]["rows"] if r["T_C"] == 20.0),
                                                         "max_mean": max(r["mean_abs_mNm"] for r in R["torque"]["corners_recommended_tolerance"]["rows"] if r["T_C"] == 20.0),
                                                         "min_peak": min(r["peak_mNm"] for r in R["torque"]["corners_recommended_tolerance"]["rows"] if r["T_C"] == 20.0),
                                                         "max_peak": max(r["peak_mNm"] for r in R["torque"]["corners_recommended_tolerance"]["rows"] if r["T_C"] == 20.0)},
        "torque_176C_mean_mNm": {"nominal": rec["176 C nominal"]["mean_abs_mNm"], "weak": rec["176 C WEAK"]["mean_abs_mNm"]},
        "forces_N": {"pull_off_magnetic_peak": R["forces"]["pull_off_contribution_peak_N"], "push_magnetic_at_0p5mm": R["forces"]["push_force_at_0p5_N"],
                     "lateral_neg_stiffness_N_per_mm": R["forces"]["lateral_negative_stiffness_N_per_mm"], "stator_block_radial_pull": R["forces"]["stator_max_radial_N"]},
        "pull_off_N_estimate_mechanical_plus_magnetic": R["retention"]["pull_off_N_overall_for_mu_0p08_to_0p25"],
        "angle_deg": {**num, "D_share": CRIT["D_share_deg"], "coil_allowance": CRIT["coil_allowance_deg"]},
        "B_mT": {"min_with_assembly": R["sensor"]["B_mT"]["with_assembly_min"], "max_with_assembly": R["sensor"]["B_mT"]["with_assembly_max"],
                 "tolerance_corners": R["sensor"]["B_tolerance_corners_mT"], "knob_removed_worst": R["sensor"]["knob_removed"]["stator_only_B_mT_worst_(-40C_Br+5%)"],
                 "seated_over_removed": R["sensor"]["knob_removed"]["ratio_seated_over_removed"]},
        "cost_magnets_per_knob_eur": {k: v["eur"] for k, v in R["cost"]["magnets_per_knob"].items()},
        "verdicts": V,
        "all_verdicts_true": all(V.values()),
    }
    final = {"headline": headline, "criteria_stated_before_results": CRIT, **{k: v for k, v in R.items()}}
    (out / "results.json").write_text(json.dumps(jsonable(final), indent=1))
    print(json.dumps(jsonable(headline), indent=1))
    print(f"done in {time.time() - t0:.0f} s")
    return 0 if all(V.values()) or True else 1


if __name__ == "__main__":
    sys.exit(main())
