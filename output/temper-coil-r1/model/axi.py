"""Axisymmetric time-harmonic eddy-current solver for the coil-r1 model (numpy/scipy, SI units).

Lineage: the finite-volume formulation on psi = r*A_phi is the one in enclosure study 06
`output/temper-r32-studies/06-emi-strayfield/fem_axi.py` (sha256 f2d21553..., validated there against Wheeler,
image theory and the surface-impedance integral). This file re-implements it with four additions:

  1. discrete stranded turns: every Litz turn is its own square (equal area to the round bundle) carrying weight*I,
     so the flux linkage, the per-turn field (for the Litz proximity loss) and the pan heating follow the real
     turn positions instead of a smeared section;
  2. anisotropic reluctivity (nu_r, nu_z per cell), for homogenised ferrite-bar layers;
  3. nonlinear effective permeability in chosen conducting regions (pan steel), by fixed-point iteration on the
     peak field (the usual "effective permeability" harmonic method; an ESTIMATE of large-signal behaviour);
  4. cell-centred B and loss maps for post-processing.

Governing equation (r-z plane, peak phasors, e^{jwt}):
    -d/dr( nu_z/r dpsi/dr ) - d/dz( nu_r/r dpsi/dz ) + j w sigma psi / r = J_s
with B_r = -(1/r) dpsi/dz, B_z = (1/r) dpsi/dr, psi = 0 on the axis and the far boundary.
Litz turns and ferrite are non-conducting (sigma = 0): the Litz strand loss is computed afterwards from the field
(litz.py), the ferrite core loss from B (ferrite.py).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0 = 4e-7 * np.pi


def make_grid(lo, hi, regions, hmax, growth=1.12, mandatory=()):
    """Graded 1-D grid. regions: (a, b, h) intervals with target spacing h; spacing grows by `growth` away from them.
    Region ends and `mandatory` points are always nodes."""
    mand = sorted({lo, hi, *[x for a, b, _ in regions for x in (a, b)], *mandatory})
    mand = np.array([m for m in mand if lo <= m <= hi])

    def ht(x):
        best = hmax
        for a, b, h in regions:
            d = 0.0 if a <= x <= b else min(abs(x - a), abs(x - b))
            best = min(best, h + (growth - 1.0) * d)
        return best

    pts, x = [lo], lo
    while x < hi:
        x = min(x + ht(x), hi)
        pts.append(x)
    pts = np.array(pts)
    keep = []
    for g in pts:
        j = np.searchsorted(mand, g)
        near = min(abs(g - mand[k]) for k in (j - 1, j) if 0 <= k < len(mand))
        if near > 0.35 * ht(g):
            keep.append(g)
    return np.array(sorted(set(keep) | set(mand.tolist())))


class Model:
    def __init__(self, r, z):
        self.r = np.asarray(r, float)
        self.z = np.asarray(z, float)
        nr, nz = len(self.r) - 1, len(self.z) - 1
        self.mur_r = np.ones((nr, nz))
        self.mur_z = np.ones((nr, nz))
        self.sigma = np.zeros((nr, nz))
        self.region = np.zeros((nr, nz), dtype=int)
        self.region_names = {0: "air"}
        self.nonlinear = {}           # region id -> callable mu_eff(H_peak)  (H in A/m)
        rc = 0.5 * (self.r[:-1] + self.r[1:])
        zc = 0.5 * (self.z[:-1] + self.z[1:])
        self.rc, self.zc = rc, zc
        self.RC, self.ZC = np.meshgrid(rc, zc, indexing="ij")
        self.dA = np.diff(self.r)[:, None] * np.diff(self.z)[None, :]
        self.turn_masks, self.turn_weights, self.turn_areas = [], [], []
        self.turn_r = []

    # -------------------------------------------------------------- geometry
    def box(self, r0, r1, z0, z1):
        return (self.RC > r0) & (self.RC < r1) & (self.ZC > z0) & (self.ZC < z1)

    def add_conductor(self, name, r0, r1, z0, z1, sigma, mur=1.0, mu_of_H=None):
        m = self.box(r0, r1, z0, z1)
        rid = len(self.region_names)
        self.region_names[rid] = name
        self.region[m] = rid
        self.sigma[m] = sigma
        self.mur_r[m] = mur
        self.mur_z[m] = mur
        if mu_of_H is not None:
            self.nonlinear[rid] = mu_of_H
        return rid

    def set_mu(self, mask, mur_r, mur_z=None):
        mur_z = mur_r if mur_z is None else mur_z
        self.mur_r[mask] = np.broadcast_to(mur_r, self.mur_r.shape)[mask] if np.ndim(mur_r) else mur_r
        self.mur_z[mask] = np.broadcast_to(mur_z, self.mur_z.shape)[mask] if np.ndim(mur_z) else mur_z

    def add_turn(self, r_c, z_c, side, weight):
        """Square stranded conductor (side x side) centred at (r_c, z_c), carrying weight * I."""
        m = self.box(r_c - side / 2, r_c + side / 2, z_c - side / 2, z_c + side / 2)
        if not m.any():
            raise ValueError(f"turn at r={r_c} has no cells: refine the grid")
        self.turn_masks.append(m)
        self.turn_weights.append(weight)
        self.turn_areas.append(float(self.dA[m].sum()))
        self.turn_r.append(r_c)

    def source(self, current):
        J = np.zeros_like(self.sigma)
        for m, w, a in zip(self.turn_masks, self.turn_weights, self.turn_areas):
            J[m] += w * current / a
        return J

    # -------------------------------------------------------------- assembly
    def _assemble(self, w):
        r, z = self.r, self.z
        nr, nz = len(r), len(z)
        dz = np.diff(z)
        nu_r = 1.0 / (MU0 * self.mur_r)
        nu_z = 1.0 / (MU0 * self.mur_z)
        I, K = np.meshgrid(np.arange(1, nr - 1), np.arange(1, nz - 1), indexing="ij")
        I, K = I.ravel(), K.ravel()

        def rface(i):   # face between node i and i+1 (radial flux), z-extent over cells k-1 and k
            c = 0.5 * (nu_z[i, K - 1] * dz[K - 1] + nu_z[i, K] * dz[K])
            return 2.0 * c / (r[i + 1] ** 2 - r[i] ** 2)

        aE, aW = rface(I), rface(I - 1)
        rm = 0.5 * (r[I - 1] + r[I])
        rp = 0.5 * (r[I] + r[I + 1])
        lW, lE = np.log(r[I] / rm), np.log(rp / r[I])

        def zface(k):
            return (nu_r[I - 1, k] * lW + nu_r[I, k] * lE) / dz[k]

        aN, aS = zface(K), zface(K - 1)
        hzS, hzN = 0.5 * dz[K - 1], 0.5 * dz[K]
        sig = (self.sigma[I - 1, K - 1] * lW * hzS + self.sigma[I, K - 1] * lE * hzS
               + self.sigma[I - 1, K] * lW * hzN + self.sigma[I, K] * lE * hzN)
        n0 = I * nz + K
        diag = aE + aW + aN + aS + 1j * w * sig
        rows = np.concatenate([n0] * 5)
        cols = np.concatenate([n0, n0 + nz, n0 - nz, n0 + 1, n0 - 1])
        vals = np.concatenate([diag, -aE, -aW, -aN, -aS])
        interior = np.zeros(nr * nz, bool)
        interior[n0] = True
        keep = interior[cols]
        bn = np.flatnonzero(~interior)
        rows = np.concatenate([rows[keep], bn])
        cols = np.concatenate([cols[keep], bn])
        vals = np.concatenate([vals[keep], np.ones(len(bn), complex)])
        A = sp.csc_matrix((vals, (rows, cols)), shape=(nr * nz, nr * nz))
        self._quad = (I, K, rm, rp, hzS, hzN, n0)
        return A

    def _rhs(self, J):
        I, K, rm, rp, hzS, hzN, n0 = self._quad
        r = self.r
        dW, dE = r[I] - rm, rp - r[I]
        b = np.zeros(len(self.r) * len(self.z), complex)
        b[n0] = (J[I - 1, K - 1] * dW * hzS + J[I, K - 1] * dE * hzS + J[I - 1, K] * dW * hzN + J[I, K] * dE * hzN)
        return b

    # -------------------------------------------------------------- solve
    def solve(self, f, current=1.0, nl_iter=30, nl_tol=0.01, relax=0.5, verbose=False):
        """Solve at frequency f (Hz) for a peak turn current `current` (A). Returns post() dict."""
        self.f, self.w, self.current = f, 2 * np.pi * f, current
        J = self.source(current)
        b = None
        for it in range(nl_iter if self.nonlinear else 1):
            A = self._assemble(self.w)
            if b is None:
                b = self._rhs(J)
            psi = spla.spsolve(A, b)
            self.psi = psi.reshape(len(self.r), len(self.z))
            if not self.nonlinear:
                break
            Bm = np.hypot(*[np.abs(x) for x in self.B_cells()])
            change = 0.0
            for rid, mu_of_H in self.nonlinear.items():
                m = self.region == rid
                mu_old = self.mur_r[m]
                # fixed point on B: find mu such that B = mu0 mu(H) H with H = B/(mu0 mu)
                H = Bm[m] / (MU0 * mu_old)
                mu_new = mu_of_H(H)
                mu_upd = mu_old ** (1 - relax) * mu_new ** relax      # geometric under-relaxation
                change = max(change, float(np.max(np.abs(mu_upd / mu_old - 1))))
                self.mur_r[m] = mu_upd
                self.mur_z[m] = mu_upd
            if verbose:
                print(f"   nl it {it}: max rel mu change {change:.3g}")
            if change < nl_tol:
                break
        self.nl_change = change if self.nonlinear else 0.0
        return self.post()

    # -------------------------------------------------------------- post
    def B_cells(self):
        """Peak phasor (Br, Bz) at cell centres."""
        p = self.psi
        dr = np.diff(self.r)[:, None]
        dz = np.diff(self.z)[None, :]
        dpdz = ((p[:-1, 1:] + p[1:, 1:]) - (p[:-1, :-1] + p[1:, :-1])) / (2 * dz)
        dpdr = ((p[1:, :-1] + p[1:, 1:]) - (p[:-1, :-1] + p[:-1, 1:])) / (2 * dr)
        return -dpdz / self.RC, dpdr / self.RC

    def A_cells(self):
        p = self.psi
        pc = 0.25 * (p[:-1, :-1] + p[1:, :-1] + p[:-1, 1:] + p[1:, 1:])
        return pc / self.RC

    def loss_density(self):
        """Time-averaged eddy loss per cell (W) for the solved current."""
        A = self.A_cells()
        return 0.5 * self.sigma * self.w ** 2 * np.abs(A) ** 2 * 2 * np.pi * self.RC * self.dA

    def post(self):
        p = self.psi
        pc = 0.25 * (p[:-1, :-1] + p[1:, :-1] + p[:-1, 1:] + p[1:, 1:])
        lam = 0.0 + 0.0j
        for m, w, a in zip(self.turn_masks, self.turn_weights, self.turn_areas):
            lam += w / a * np.sum(2 * np.pi * pc[m] * self.dA[m])
        Z = 1j * self.w * lam / self.current
        dP = self.loss_density()
        losses = {name: float(dP[self.region == rid].sum()) for rid, name in self.region_names.items() if rid}
        self.L, self.R = float(Z.imag / self.w), float(Z.real)
        self.losses = losses
        return dict(L=self.L, R=self.R, losses=losses, P_terminal=0.5 * self.R * self.current ** 2)

    def turn_B2(self):
        """Per turn: area-mean of |B|^2 (peak^2, summing both components' magnitudes) over the bundle square."""
        Br, Bz = self.B_cells()
        b2 = np.abs(Br) ** 2 + np.abs(Bz) ** 2
        return [float(np.sum(b2[m] * self.dA[m]) / np.sum(self.dA[m])) for m in self.turn_masks]

    def B_at(self, rq, zq):
        from scipy.interpolate import RegularGridInterpolator
        Br, Bz = self.B_cells()
        pts = np.column_stack([np.ravel(rq), np.ravel(zq)])
        fr = RegularGridInterpolator((self.rc, self.zc), Br, bounds_error=False, fill_value=None)
        fz = RegularGridInterpolator((self.rc, self.zc), Bz, bounds_error=False, fill_value=None)
        return fr(pts).reshape(np.shape(rq)), fz(pts).reshape(np.shape(rq))
