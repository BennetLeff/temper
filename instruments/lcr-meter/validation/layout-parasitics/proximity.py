"""Noisy-copper proximity and mutual capacitance to the summing node, TIA output and DUT HI.

Distances: exact shapely minimum distance between all copper of the noisy net
group and all copper of the target net, any layer pair.

Mutual capacitance (far-field, weak coupling): both nets are cut into cells of
CELL mm; each cell carries the charge-per-volt C_cell = C_net * A_cell / A_net
(C_net from closed_form.node_c_gnd, edge mode) at height h above the In1
plane (prepreg if In1 copper lies under the cell, H_VOID otherwise).  With
the image potential coefficient
    p_ij = [1/R - 1/sqrt(R^2 + (h_i + h_j)^2)] / (4 pi eps0 eps_eff),
first-order Maxwell coupling is C_m = sum_ij C_i p_ij C_j.  Copper on In2/B.Cu
under solid In1 is screened from top-side copper and is dropped (nominal) or
kept with h = its depth below In1 (high).  'high' also uses eps_eff = 1 and
H_VOID = 1.6 mm.  These are estimates, not bounds.

Also lists every net with F.Cu copper within 2 mm of the summing node or DUT HI,
with its closed-form sampled-edge mutual capacitance.  Writes proximity.json.
"""
from __future__ import annotations

import json

import numpy as np
from shapely import contains_xy, prepare
from shapely.geometry import box

from closed_form import node_c_gnd
from common import (EPS0, HERE, HI, LAYERS, NOISY, NOMINAL_STACKUP, STACKUPS, SUM, TIA,
                    geometry, net_shape, plane_in1)

CELL = 0.25


def cells(net, h_void, keep_screened):
    st = STACKUPS[NOMINAL_STACKUP]
    P = plane_in1(); prepare(P)
    pts, area, hs = [], [], []
    for layer in LAYERS:
        s = net_shape(net, layer)
        if s is None or layer == 'In1.Cu':
            continue
        minx, miny, maxx, maxy = s.bounds
        xs = np.arange(minx + CELL / 2, maxx, CELL)
        ys = np.arange(miny + CELL / 2, maxy, CELL)
        if len(xs) == 0 or len(ys) == 0:
            c = s.centroid
            X, Y = np.array([c.x]), np.array([c.y])
            A = np.array([s.area])
        else:
            X, Y = np.meshgrid(xs, ys); X = X.ravel(); Y = Y.ravel()
            inside = contains_xy(s, X, Y)
            X, Y = X[inside], Y[inside]
            A = np.full(len(X), CELL * CELL)
            if len(X) == 0:
                c = s.centroid; X, Y = np.array([c.x]), np.array([c.y]); A = np.array([s.area])
        over = contains_xy(P, X, Y)
        if layer == 'F.Cu':
            h = np.where(over, st['prepreg'] + st['t_outer'] / 2, h_void)
        else:
            depth = st['core'] if layer == 'In2.Cu' else st['core'] + st['prepreg']
            if not keep_screened:
                X, Y, A = X[~over], Y[~over], A[~over]
                h = np.full(len(X), h_void)
            else:
                h = np.where(over, depth, h_void)
        pts.append(np.stack([X, Y], 1)); area.append(A); hs.append(h)
    if not pts:
        return None
    return np.concatenate(pts), np.concatenate(area), np.concatenate(hs)


def coupling(net_a, nets_b, mode):
    h_void = 0.8 if mode == 'nom' else 1.6
    eeff = (1 + STACKUPS[NOMINAL_STACKUP]['er_prepreg']) / 2 if mode == 'nom' else 1.0
    ca = cells(net_a, h_void, mode == 'high')
    Ca = node_c_gnd(net_a, NOMINAL_STACKUP, 'edge')['total'] * 1e-12
    total = 0.0
    for nb in nets_b:
        cb = cells(nb, h_void, mode == 'high')
        if cb is None or net_shape(nb, 'F.Cu') is None and cb[0].size == 0:
            continue
        Cb = node_c_gnd(nb, NOMINAL_STACKUP, 'edge')['total'] * 1e-12
        if Cb <= 0:
            continue
        pa, aa, ha = ca; pb, ab, hb = cb
        qa = Ca * aa / aa.sum(); qb = Cb * ab / ab.sum()
        R = np.sqrt(((pa[:, None, :] - pb[None, :, :]) ** 2).sum(-1))
        H = ha[:, None] + hb[None, :]
        p = (1 / R - 1 / np.sqrt(R**2 + H**2)) / (4 * np.pi * EPS0 * 1e-3 * eeff)
        total += float(qa @ p @ qb)
    return total * 1e12  # pF


def min_dist(nets_b, target):
    best = (1e9, None)
    for n in nets_b:
        for la in LAYERS:
            a = net_shape(n, la)
            if a is None:
                continue
            for lb in LAYERS:
                b = net_shape(target, lb)
                if b is None:
                    continue
                d = a.distance(b)
                if d < best[0]:
                    best = (d, f'{n}@{la} to {target}@{lb}')
    return best


def main():
    present = {it['net'] for it in geometry()['items']}
    out = {'board_sha256': geometry()['board_sha256'], 'method': __doc__.strip().split('\n')[0],
           'groups': {}}
    for label, nets in NOISY.items():
        nets = [n for n in nets if n in present]
        g = out['groups'][label] = {'nets': nets}
        for tgt in (SUM, TIA, HI):
            d, where = min_dist(nets, tgt)
            g[tgt] = {'min_distance_mm': round(d, 3), 'closest': where,
                      'c_mutual_fF_nom': coupling(tgt, nets, 'nom') * 1e3,
                      'c_mutual_fF_high': coupling(tgt, nets, 'high') * 1e3}
        print(label, {t: (g[t]['min_distance_mm'], round(g[t]['c_mutual_fF_nom'], 4),
                          round(g[t]['c_mutual_fF_high'], 4)) for t in (SUM, TIA, HI)})
    # nearest F.Cu neighbours of the summing node and DUT HI (closed-form sampled-edge mutual)
    from closed_form import mutual
    for tgt in (SUM, HI):
        ts = net_shape(tgt, 'F.Cu')
        neigh = {}
        for n in sorted(present - {tgt}):
            s_ = net_shape(n, 'F.Cu')
            if s_ is None or s_.distance(ts) > 2.0:
                continue
            m = mutual(tgt, n, NOMINAL_STACKUP)
            neigh[n] = {'min_gap_mm': round(s_.distance(ts), 3), 'c_mutual_pF': m['total']}
        out[f'neighbours_of_{tgt}'] = dict(sorted(neigh.items(), key=lambda kv: -kv[1]['c_mutual_pF']))
        print(tgt, {k: (v['min_gap_mm'], round(v['c_mutual_pF'], 4)) for k, v in out[f'neighbours_of_{tgt}'].items()})
    (HERE / 'proximity.json').write_text(json.dumps(out, indent=1, default=float))


if __name__ == '__main__':
    main()
