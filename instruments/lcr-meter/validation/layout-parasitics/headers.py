"""Above-board capacitance of the 2-pin TSW-102-07-G-S headers (J3, JP4-JP6).

The 3-D FD domain stops 5 mm above F.Cu and contains no post metal, so the
posts are added here: thin-wire method of moments for two vertical posts
(square 0.635 mm -> capacitance-equivalent radius 0.59*a = 0.375 mm) at
2.54 mm pitch, from F.Cu (z = 0) to the post tip (2.54 mm insulator + 5.84 mm
mating post = 8.38 mm), above the In1 plane (image at depth 2*prepreg).
Uniform line charge on N segments per post, collocation on the post surface.

The insulator (glass-filled polyester, er ~3-4.2, assumed) fills the lowest
2.54 mm; its effect is approximated by scaling the charge on the insulator
portion by er (upper estimate) or 1 (lower).  Mating fixture/cable/shunt metal
is NOT included: on J3 it belongs to the fixture allowance; on a shunted JP the
two posts are one node.

Writes headers.json: Maxwell matrix [[C11, -Cm], [-Cm, C22]] in pF.
"""
from __future__ import annotations

import json

import numpy as np

from common import EPS0, HERE, NOMINAL_STACKUP, STACKUPS

PITCH, R_EQ, Z_TOP, Z_INS = 2.54, 0.59 * 0.635, 8.38, 2.54
N = 60


def seg_potential(z1, z2, rho, z):
    """Potential (x 4 pi eps0) at (rho, z) of unit line charge on z1..z2."""
    a = z2 - z; b = z1 - z
    return np.log((a + np.sqrt(rho**2 + a**2)) / (b + np.sqrt(rho**2 + b**2)))


def maxwell(h_plane, er_ins):
    zs = np.linspace(0, Z_TOP, N + 1)
    z1, z2 = zs[:-1], zs[1:]
    zc = 0.5 * (z1 + z2)
    xs = np.array([0.0, PITCH])
    # unknowns: q[post, seg] (charge per length); collocate at (x_post + R_EQ, zc)
    M = np.zeros((2 * N, 2 * N))
    for pi_, xp in enumerate(xs):
        for k in range(N):
            row = pi_ * N + k
            for pj, xq in enumerate(xs):
                rho = abs(xp - xq) if pi_ != pj else R_EQ
                pot = seg_potential(z1, z2, rho, zc[k])
                # image of the segment below the plane at z = -h_plane
                pot -= seg_potential(-2 * h_plane - z2, -2 * h_plane - z1, rho, zc[k])
                M[row, pj * N:(pj + 1) * N] = pot
    M /= 4 * np.pi * EPS0 * 1e-3  # V per (C/mm) with lengths in mm
    w = np.where(zc < Z_INS, er_ins, 1.0)
    C = np.zeros((2, 2))
    for j in range(2):
        V = np.zeros(2 * N); V[j * N:(j + 1) * N] = 1.0
        q = np.linalg.solve(M, V) * np.tile(z2 - z1, 2)
        q = q * np.tile(w, 2)
        C[0, j] = q[:N].sum(); C[1, j] = q[N:].sum()
    return C * 1e12


def main():
    h = STACKUPS[NOMINAL_STACKUP]['prepreg']
    out = {'method': __doc__.strip().split('\n')[0], 'assumptions': {
        'pitch_mm': PITCH, 'equiv_radius_mm': R_EQ, 'post_top_mm': Z_TOP, 'insulator_mm': Z_INS}}
    for er in (1.0, 3.6, 4.2):
        C = maxwell(h, er)
        out[f'er_ins={er}'] = {'C11_pF': C[0, 0], 'Cm_pF': -C[0, 1], 'C_to_ground_each_pF': C[0, 0] + C[0, 1]}
    (HERE / 'headers.json').write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))


if __name__ == '__main__':
    main()
