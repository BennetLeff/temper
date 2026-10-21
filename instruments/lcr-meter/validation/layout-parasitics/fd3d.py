"""3-D finite-volume electrostatic capacitance extraction over the analog front end.

Cross-check for the closed-form capacitance estimates.  It uses the exported
native copper of every net on all four layers, the *actual* filled In1.Cu GND
polygon (so the deliberate plane voids are represented exactly as fabricated,
to grid resolution), plated barrels of vias and PTH pads, and a layered
dielectric (air / prepreg / core / prepreg / air).

All nets other than the extracted conductors are held at 0 V (AC ground:
supplies, driven outputs, GND).  The result is the short-circuit (Maxwell)
capacitance matrix of the conductors listed in CONDUCTORS.

Usage:  python3 fd3d.py <dx_mm> <bc: neumann|dirichlet> [stackup] [window]
Writes fd_<window>_<stackup>_<dx>_<bc>.json.
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pyamg
import scipy.sparse as sp
import shapely

from common import (EPS0, HERE, LAYERS, NOMINAL_STACKUP, STACKUPS, geometry, item_shape,
                    plane_in1)

import os
CONDUCTORS = os.environ.get('LP_CONDUCTORS', 'DUT_LO,TIA_OUT,DUT_HI,RF100,RF5K,RF100K,LOW_BUF,HIGH_BUF').split(',')
VARIANT = os.environ.get('LP_GEOMETRY', 'geometry.json').replace('geometry', '').replace('.json', '').strip('_')
WINDOWS = {
    # whole AFE: contains all copper of the conductors above with >= 1.4 mm margin
    'afe': (152.0, 181.5, 81.5, 127.0),
    # zoom on U7 / C104 / R43-45 / JP4 for grid-convergence study
    'zoom': (157.0, 172.0, 104.0, 119.5),
    # Rev E whole front end incl. the K1-K3 relay row (geometry_reve.json): conductor copper
    # bbox is x 152.00-189.03, y 88.18-138.05 mm; check_window() enforces the >= 1.4 mm margin.
    'reve': (150.5, 190.5, 86.7, 139.5),
    # Rev E zoom on K1 (pins 3/4/7/8), the In2 TIA_OUT/RF100/RF100K/SOURCE_BUF buses: grid convergence
    'reve_relay': (158.0, 176.0, 119.5, 136.0),
    # Rev E zoom on the broadside-coupled SOURCE_BUF (In2, x 188.8) / DUT_HI (B.Cu, x 188.9) run
    'reve_hiside': (185.0, 192.0, 105.0, 120.0),
    # Rev E with R104 (board cf379f85, geometry_reve_r104.json): SRC_DRV / R104 at y 85.3-92,
    # conductor bbox x 152.00-189.03, y 85.33-138.05 mm
    'reve_r104': (150.5, 190.5, 83.9, 139.5),
    # R104 board: SOURCE_BUF moved to In2 x 185.5, DUT_HI still B.Cu x 188.9
    'reve_hiside_r104': (183.5, 191.0, 105.0, 120.0),
}
ZOOM_WINDOWS = {'zoom', 'reve_relay', 'reve_hiside', 'reve_hiside_r104'}
MARGIN_MM = 1.4


def check_window(window):
    """Whole-board windows must contain all copper of every conductor with MARGIN_MM to spare."""
    if window in ZOOM_WINDOWS:
        return
    from shapely.ops import unary_union
    shapes = [s for it in geometry()['items'] if it['net'] in CONDUCTORS
              for s in (item_shape(it, l) for l in LAYERS) if s is not None]
    bx = unary_union(shapes).bounds
    x0, x1, y0, y1 = WINDOWS[window]
    m = min(bx[0] - x0, x1 - bx[2], bx[1] - y0, y1 - bx[3])
    if m < MARGIN_MM:
        raise SystemExit(f'window {window} {WINDOWS[window]} misses conductor bbox {bx} (margin {m:.2f} mm)')


def graded(total, h0, hmax, ratio=1.45):
    """Steps starting at h0, growing by ratio up to hmax, summing exactly to total."""
    steps, s = [], h0
    while sum(steps) + s < total:
        steps.append(s)
        s = min(s * ratio, hmax)
    rem = total - sum(steps)
    if steps and rem < 0.5 * steps[-1]:
        steps[-1] += rem
    else:
        steps.append(rem)
    return steps


def symmetric(total, h0, hmax):
    half = graded(total / 2, h0, hmax)
    return half + half[::-1]


def zgrid(st, dz_fine):
    """Node z positions (mm, z=0 at F.Cu) and per-interval permittivity."""
    pp, core = st['prepreg'], st['core'] + 2 * st['t_inner']
    # above board (air) built separately and prepended
    above = graded(5.0, dz_fine, 1.2)
    z_above = np.cumsum(above)[::-1]
    n_pp = max(3, int(round(pp / dz_fine)))
    below_steps = ([pp / n_pp] * n_pp, st['er_prepreg']), (symmetric(core, dz_fine, 0.2), st['er_core']), \
                  ([pp / n_pp] * n_pp, st['er_prepreg']), (graded(3.0, dz_fine, 1.2), 1.0)
    z = [0.0]
    eps = []
    for steps, er in below_steps:
        for s in steps:
            z.append(z[-1] - s)
            eps.append(er)
    z_all = np.concatenate([z_above, np.array(z)])  # descending
    eps_all = np.concatenate([np.ones(len(z_above)), np.array(eps)])
    # ascending order
    z_all = z_all[::-1].copy()
    eps_all = eps_all[::-1].copy()
    k_f = int(np.argmin(abs(z_all - 0.0)))
    k_in1 = int(np.argmin(abs(z_all + pp)))
    k_in2 = int(np.argmin(abs(z_all + pp + core)))
    k_b = int(np.argmin(abs(z_all + 2 * pp + core)))
    return z_all, eps_all, {'F.Cu': k_f, 'In1.Cu': k_in1, 'In2.Cu': k_in2, 'B.Cu': k_b}


def rasterize(shape, xs, ys, sub=3, frac=0.5):
    """Boolean mask of nodes whose control cell is >= frac covered by shape."""
    mask = np.zeros((len(ys), len(xs)), bool)
    if shape is None or shape.is_empty:
        return mask
    dx = xs[1] - xs[0]
    minx, miny, maxx, maxy = shape.bounds
    i0 = max(0, int(np.floor((minx - xs[0]) / dx)) - 1)
    i1 = min(len(xs), int(np.ceil((maxx - xs[0]) / dx)) + 2)
    j0 = max(0, int(np.floor((miny - ys[0]) / dx)) - 1)
    j1 = min(len(ys), int(np.ceil((maxy - ys[0]) / dx)) + 2)
    if i1 <= i0 or j1 <= j0:
        return mask
    off = (np.arange(sub) + 0.5) / sub - 0.5
    X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1])
    cnt = np.zeros(X.shape, int)
    shapely.prepare(shape)
    for ox in off:
        for oy in off:
            cnt += shapely.contains_xy(shape, X + ox * dx, Y + oy * dx)
    mask[j0:j1, i0:i1] = cnt >= frac * sub * sub
    return mask


def build(dx, window, stackup, bc):
    x0, x1, y0, y1 = WINDOWS[window]
    st = STACKUPS[stackup]
    xs = np.arange(x0, x1 + 1e-9, dx)
    ys = np.arange(y0, y1 + 1e-9, dx)
    z, eps, kl = zgrid(st, min(dx, st['prepreg'] / 4))
    nx, ny, nz = len(xs), len(ys), len(z)
    N = nx * ny * nz
    # conductor label per node: -1 free, 0 ground, 1.. targets
    lab = np.full((nz, ny, nx), -1, np.int16)
    tid = {n: i + 1 for i, n in enumerate(CONDUCTORS)}
    from shapely.geometry import box, Point
    win = box(x0, y0, x1, y1)
    g = geometry()
    # ground plane In1 (actual fill)
    lab[kl['In1.Cu']][rasterize(plane_in1().intersection(win), xs, ys)] = 0
    # planar copper of all items
    for it in g['items']:
        v = tid.get(it['net'], 0)
        for layer in LAYERS:
            s = item_shape(it, layer)
            if s is None or not s.intersects(win):
                continue
            m = rasterize(s.intersection(win), xs, ys)
            sl = lab[kl[layer]]
            if v == 0:
                sl[m & (sl < 0)] = 0
            else:
                sl[m] = v
        # plated barrels (vias, PTH pads) span F.Cu..B.Cu
        if it['kind'] == 'via' or (it['kind'] == 'pad' and it.get('pth')):
            r = it['drill'] / 2
            if r <= 0 or not win.contains(Point(it['x'], it['y'])):
                continue
            m = rasterize(Point(it['x'], it['y']).buffer(max(r, 0.51 * dx), 16), xs, ys, frac=0.3)
            for k in range(kl['B.Cu'], kl['F.Cu'] + 1):
                sl = lab[k]
                if v == 0:
                    sl[m & (sl < 0)] = 0
                else:
                    sl[m] = v
    if bc == 'dirichlet':
        for sl in (lab[0], lab[-1]):
            sl[sl < 0] = 0
        lab[:, 0, :][lab[:, 0, :] < 0] = 0
        lab[:, -1, :][lab[:, -1, :] < 0] = 0
        lab[:, :, 0][lab[:, :, 0] < 0] = 0
        lab[:, :, -1][lab[:, :, -1] < 0] = 0

    dz = np.diff(z)
    # conductances (eps0 = 1, lengths mm)
    # x-links at plane k: eps averaged over half intervals above/below
    wk = np.zeros(nz)
    for k in range(nz):
        if k > 0:
            wk[k] += eps[k - 1] * dz[k - 1] / 2
        if k < nz - 1:
            wk[k] += eps[k] * dz[k] / 2
    gx = wk * dx / dx  # (eps*dz) * dy / dx  with dy = dx
    gz = eps * dx * dx / dz  # between k and k+1
    idx = np.arange(N).reshape(nz, ny, nx)
    rows, cols, vals = [], [], []

    def link(a, b, gval):
        rows.append(a.ravel()); cols.append(b.ravel()); vals.append(gval.ravel())

    link(idx[:, :, :-1], idx[:, :, 1:], np.broadcast_to(gx[:, None, None], (nz, ny, nx - 1)))
    link(idx[:, :-1, :], idx[:, 1:, :], np.broadcast_to(gx[:, None, None], (nz, ny - 1, nx)))
    link(idx[:-1, :, :], idx[1:, :, :], np.broadcast_to(gz[:, None, None], (nz - 1, ny, nx)))
    r = np.concatenate(rows); c = np.concatenate(cols); v = np.concatenate(vals)
    off = sp.coo_matrix((v, (r, c)), shape=(N, N)).tocsr()
    off = off + off.T
    diag = np.asarray(off.sum(axis=1)).ravel()
    A = (sp.diags(diag) - off).tocsr()
    return dict(A=A, lab=lab.ravel(), xs=xs, ys=ys, z=z, eps=eps, kl=kl, tid=tid, N=N,
                shape=(nz, ny, nx))


def solve(dx, bc, stackup=NOMINAL_STACKUP, window='afe'):
    t0 = time.time()
    check_window(window)
    m = build(dx, window, stackup, bc)
    A, lab = m['A'], m['lab']
    free = np.flatnonzero(lab < 0)
    fixed = np.flatnonzero(lab >= 0)
    Aff = A[free][:, free].tocsr()
    Afd = A[free][:, fixed].tocsr()
    t1 = time.time()
    ml = pyamg.smoothed_aggregation_solver(Aff, symmetry='symmetric', max_coarse=2000)
    t2 = time.time()
    present = [n for n in CONDUCTORS if np.any(lab == m['tid'][n])]
    C = {}
    resid = {}
    for n in present:
        vd = (lab[fixed] == m['tid'][n]).astype(float)
        b = -Afd @ vd
        res = []
        vf = ml.solve(b, tol=1e-7, accel='cg', maxiter=400, residuals=res)
        V = np.zeros(m['N'])
        V[free] = vf
        V[fixed] = vd
        Q = A @ V
        row = {}
        for n2 in present:
            row[n2] = float(Q[lab == m['tid'][n2]].sum()) * EPS0 * 1e-3 * 1e12  # pF
        row['__ground__'] = float(Q[lab == 0].sum()) * EPS0 * 1e-3 * 1e12
        C[n] = row
        resid[n] = (len(res), res[-1] / res[0])
    t3 = time.time()
    out = {'dx_mm': dx, 'bc': bc, 'stackup': stackup, 'window': window,
           'window_bounds_mm': WINDOWS[window], 'grid': m['shape'], 'unknowns': int(len(free)),
           'z_nodes_mm': [round(v, 5) for v in m['z']],
           'board_sha256': geometry()['board_sha256'],
           'maxwell_pF': C, 'cg_iterations_and_relres': resid,
           'seconds': {'build': t1 - t0, 'amg_setup': t2 - t1, 'solves': t3 - t2}}
    tag = f"fd_{window}_{stackup}_{dx:g}_{bc}{'_' + VARIANT if VARIANT else ''}.json"
    (HERE / 'fd_results').mkdir(exist_ok=True)
    (HERE / 'fd_results' / tag).write_text(json.dumps(out, indent=1))
    return out


if __name__ == '__main__':
    dx = float(sys.argv[1]); bc = sys.argv[2]
    st = sys.argv[3] if len(sys.argv) > 3 else NOMINAL_STACKUP
    win = sys.argv[4] if len(sys.argv) > 4 else 'afe'
    o = solve(dx, bc, st, win)
    print(json.dumps({k: o[k] for k in ('grid', 'unknowns', 'seconds')}))
    for n, row in o['maxwell_pF'].items():
        print(n, {k: round(v, 4) for k, v in row.items()})
