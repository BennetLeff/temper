"""Axisymmetric time-harmonic eddy-current solver (pure numpy/scipy).

Unknown psi = r*A_phi on a non-uniform (r, z) node grid. Finite-volume form of

    -d/dr( nu/r dpsi/dr ) - d/dz( nu/r dpsi/dz ) + j*w*sigma*psi/r = J_s

with cell-wise nu = 1/(mu0*mu_r), sigma and source current density J_s (A/m^2,
phase reference = coil current). psi = 0 on the axis and on the far boundary.
Litz winding and ferrite are non-conducting (sigma = 0); ferrite core loss is
not modelled (it is a coil-supplier figure, not an enclosure figure).

Outputs: complex flux linkage of the stranded winding (-> L, R), time-averaged
eddy loss per conducting region, and B (peak phasor) anywhere by interpolation.
All quantities are SI. Amplitudes are PEAK phasors; time-averaged loss uses 1/2.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0 = 4e-7 * np.pi


def make_grid(lo, hi, regions, hmax, growth=1.15):
    """Graded 1-D grid. regions: list of (a, b, h) intervals with target spacing h.
    Interval end points are always nodes."""
    pts = {lo, hi}
    for a, b, h in regions:
        pts.add(a)
        pts.add(b)

    def htarget(x):
        best = hmax
        for a, b, h in regions:
            d = 0.0 if a <= x <= b else min(abs(x - a), abs(x - b))
            best = min(best, h + (growth - 1.0) * d)
        return best

    x = lo
    out = [lo]
    while x < hi:
        x = x + htarget(x)
        out.append(min(x, hi))
    grid = np.array(sorted(set(out)))
    # merge mandatory points; drop free nodes that crowd them
    mand = np.array(sorted(pts))
    keep = []
    for g in grid:
        j = np.searchsorted(mand, g)
        near = min([abs(g - mand[k]) for k in (j - 1, j) if 0 <= k < len(mand)])
        if near > 0.4 * htarget(g):
            keep.append(g)
    grid = np.array(sorted(set(keep) | set(mand)))
    return grid


class Model:
    def __init__(self, r, z):
        self.r = np.asarray(r, float)
        self.z = np.asarray(z, float)
        nr, nz = len(self.r) - 1, len(self.z) - 1
        self.mur = np.ones((nr, nz))
        self.sigma = np.zeros((nr, nz))
        self.J = np.zeros((nr, nz))
        self.region = np.zeros((nr, nz), dtype=int)  # 0 = none
        self.region_names = {0: "air"}
        rc = 0.5 * (self.r[:-1] + self.r[1:])
        zc = 0.5 * (self.z[:-1] + self.z[1:])
        self.RC, self.ZC = np.meshgrid(rc, zc, indexing="ij")
        self.coil_mask = np.zeros((nr, nz), dtype=bool)

    def box(self, r0, r1, z0, z1):
        return (self.RC > r0) & (self.RC < r1) & (self.ZC > z0) & (self.ZC < z1)

    def add_conductor(self, name, r0, r1, z0, z1, sigma, mur=1.0):
        m = self.box(r0, r1, z0, z1)
        rid = len(self.region_names)
        self.region_names[rid] = name
        self.region[m] = rid
        self.sigma[m] = sigma
        self.mur[m] = mur
        return m

    def add_magnetic(self, mask, mur):
        self.mur[mask] = mur

    def set_coil(self, r0, r1, z0, z1, turns, current):
        m = self.box(r0, r1, z0, z1)
        area = ((r1 - r0) * (z1 - z0))
        self.coil_mask = m
        self.turns = turns
        self.current = current
        self.coil_area = area
        self.J[m] = turns * current / area

    # ------------------------------------------------------------------
    def solve(self, f):
        w = 2 * np.pi * f
        r, z = self.r, self.z
        nr, nz = len(r), len(z)
        dr = np.diff(r)
        dz = np.diff(z)
        nu = 1.0 / (MU0 * self.mur)  # cells (nr-1, nz-1)

        def idx(i, k):
            return i * nz + k

        rows, cols, vals = [], [], []
        b = np.zeros(nr * nz, complex)
        # interior nodes i=1..nr-2, k=1..nz-2
        I, K = np.meshgrid(np.arange(1, nr - 1), np.arange(1, nz - 1), indexing="ij")
        I = I.ravel()
        K = K.ravel()
        # radial faces: between (i,k) and (i+1,k): cells (i,k-1),(i,k)
        def rface(i):  # coefficient for face between node i and i+1
            # exact 1-D integral of r: flux = 2*c*dpsi/(r_{i+1}^2 - r_i^2)
            c = 0.5 * (nu[i, K - 1] * dz[K - 1] + nu[i, K] * dz[K])
            return 2.0 * c / (r[i + 1] ** 2 - r[i] ** 2)

        aE = rface(I)
        aW = rface(I - 1)
        # axial faces: between (i,k) and (i,k+1): cells (i-1,k),(i,k)
        # integral over r of nu/r : nu_cell * ln(r_end/r_start)
        rm = 0.5 * (r[I - 1] + r[I])
        rp = 0.5 * (r[I] + r[I + 1])
        lW = np.log(r[I] / rm)
        lE = np.log(rp / r[I])

        def zface(k):  # face between node k and k+1, k is array
            c = nu[I - 1, k] * lW + nu[I, k] * lE
            return c / dz[k]

        aN = zface(K)
        aS = zface(K - 1)
        # sigma and source over 4 quadrants
        hzS = 0.5 * dz[K - 1]
        hzN = 0.5 * dz[K]
        # quadrant integrals of 1/r dr = lW / lE ; of dr = r[I]-rm / rp-r[I]
        dW = r[I] - rm
        dE = rp - r[I]
        sig = (self.sigma[I - 1, K - 1] * lW * hzS + self.sigma[I, K - 1] * lE * hzS
               + self.sigma[I - 1, K] * lW * hzN + self.sigma[I, K] * lE * hzN)
        src = (self.J[I - 1, K - 1] * dW * hzS + self.J[I, K - 1] * dE * hzS
               + self.J[I - 1, K] * dW * hzN + self.J[I, K] * dE * hzN)
        diag = aE + aW + aN + aS + 1j * w * sig
        n0 = idx(I, K)
        rows += [n0, n0, n0, n0, n0]
        cols += [n0, idx(I + 1, K), idx(I - 1, K), idx(I, K + 1), idx(I, K - 1)]
        vals += [diag, -aE, -aW, -aN, -aS]
        b[n0] = src
        # boundary nodes: identity
        allnodes = np.arange(nr * nz)
        interior = np.zeros(nr * nz, bool)
        interior[n0] = True
        bn = allnodes[~interior]
        rows.append(bn)
        cols.append(bn)
        vals.append(np.ones(len(bn), complex))
        rows = np.concatenate(rows)
        cols = np.concatenate(cols)
        vals = np.concatenate(vals)
        # drop couplings into boundary nodes (psi = 0 there)
        keep = interior[cols] | (rows == cols)
        A = sp.csr_matrix((vals[keep], (rows[keep], cols[keep])), shape=(nr * nz, nr * nz))
        psi = spla.spsolve(A.tocsc(), b)
        self.psi = psi.reshape(nr, nz)
        self.f = f
        self.w = w
        return self.post()

    def post(self):
        r, z, psi, w = self.r, self.z, self.psi, self.w
        with np.errstate(divide="ignore", invalid="ignore"):
            A = np.where(r[:, None] > 0, psi / r[:, None], 0.0)
        self.A = A
        # cell averages
        A2 = 0.25 * (abs(A[:-1, :-1]) ** 2 + abs(A[1:, :-1]) ** 2 + abs(A[:-1, 1:]) ** 2 + abs(A[1:, 1:]) ** 2)
        psic = 0.25 * (psi[:-1, :-1] + psi[1:, :-1] + psi[:-1, 1:] + psi[1:, 1:])
        dr = np.diff(r)[:, None]
        dz = np.diff(z)[None, :]
        area = dr * dz
        dP = 0.5 * self.sigma * w ** 2 * A2 * 2 * np.pi * self.RC * area
        losses = {}
        for rid, name in self.region_names.items():
            if rid == 0:
                continue
            losses[name] = float(dP[self.region == rid].sum())
        # flux linkage of stranded coil: lambda = N/S * sum(2*pi*psi*dA)
        lam = self.turns / self.coil_area * np.sum(2 * np.pi * psic[self.coil_mask] * area[self.coil_mask])
        Z = 1j * w * lam / self.current
        self.losses = losses
        self.L = float(Z.imag / w)
        self.R = float(Z.real)
        self.P_coil_terminal = 0.5 * self.R * self.current ** 2
        return dict(L=self.L, R=self.R, losses=losses, P_terminal=self.P_coil_terminal)

    def B_at(self, rq, zq):
        """Peak phasor (Br, Bz) at points by bilinear interpolation of nodal
        derivatives. Br = -(1/r) dpsi/dz, Bz = (1/r) dpsi/dr."""
        from scipy.interpolate import RegularGridInterpolator
        r, z, psi = self.r, self.z, self.psi
        dpsidr = np.gradient(psi, r, axis=0)
        dpsidz = np.gradient(psi, z, axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            Br = np.where(r[:, None] > 0, -dpsidz / r[:, None], 0.0)
            Bz = np.where(r[:, None] > 0, dpsidr / r[:, None], 0.0)
        # on axis use the next column (Bz finite, Br -> 0)
        Bz[0, :] = 2 * (psi[1, :]) / r[1] ** 2
        Br[0, :] = 0.0
        fr = RegularGridInterpolator((r, z), Br)
        fz = RegularGridInterpolator((r, z), Bz)
        pts = np.column_stack([np.ravel(rq), np.ravel(zq)])
        return fr(pts).reshape(np.shape(rq)), fz(pts).reshape(np.shape(rq))
