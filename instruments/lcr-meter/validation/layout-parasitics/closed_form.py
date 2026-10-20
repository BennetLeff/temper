"""Closed-form capacitance estimates from native copper geometry.

Node-to-ground (Maxwell self) capacitance, per net:
  * F.Cu copper over In1 copper: tracks use Hammerstad-Jensen microstrip C'
    (finite thickness), over the track's effective length (area/width after
    removing pad areas); pads use parallel plate + edge fringe, the fringe per
    unit edge derived from the same microstrip formula.
  * F.Cu copper over a plane void: three explicit treatments
      - 'as_if_no_void': microstrip as if In1 were present.  Adding a grounded
        conductor can only raise a Maxwell self-capacitance, so this is an
        upper bound (to the accuracy of the microstrip formula).
      - 'edge': coplanar-gap coupling (conformal map, cross-ratio form) to the
        nearest In1 edge at slant gap g = sqrt(s^2 + h^2).  Nominal.
      - 'zero': void copper contributes nothing.  Lower estimate.
  * PTH pads and vias: annular ring on In1 coupled coplanar to the plane
    across its actual antipad gap (measured from the fill), plus ring/plane
    coupling of the In2/B.Cu rings through the core (parallel plate on the
    overlap, normally zero) -- dominated by the In1 ring.
  * In2.Cu tracks: microstrip referenced to In1 through the core.

Mutual capacitance between two nets (F.Cu): sampled-edge method.  The first
net's outline is sampled every DS mm; each sample facing the other net within
GMAX contributes Garg-Bahl coupled-microstrip gap capacitance (over plane) or
the coplanar-strip conformal-map capacitance (over a void), per unit length.

Writes closed_form.json.
"""
from __future__ import annotations

import json

import numpy as np
from scipy.special import ellipk
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from common import (C0, EPS0, HERE, HI, NOMINAL_STACKUP, RF_NETS, STACKUPS, SUM, TIA,
                    THIN_STACKUP, geometry, item_shape, net_shape, plane_in1)

ETA0 = 376.730313668
DS = 0.02
GMAX = 2.0


# ---------------------------------------------------------------- formulas
def _z01(u):
    f = 6 + (2 * np.pi - 6) * np.exp(-(30.666 / u) ** 0.7528)
    return ETA0 / (2 * np.pi) * np.log(f / u + np.sqrt(1 + (2 / u) ** 2))


def _eeff0(u, er):
    a = 1 + np.log((u**4 + (u / 52) ** 2) / (u**4 + 0.432)) / 49 + np.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)


def microstrip(w, h, t, er):
    """Hammerstad-Jensen (1980) with thickness correction.
    Returns (Z0 ohm, eps_eff, C' pF/mm)."""
    u = w / h
    if t > 0:
        du1 = t / (np.pi * h) * np.log(1 + 4 * np.e / (t / h / np.tanh(np.sqrt(6.517 * u)) ** 2))
        dur = 0.5 * (1 + 1 / np.cosh(np.sqrt(max(er - 1, 0)))) * du1
    else:
        du1 = dur = 0.0
    u1, ur = u + du1, u + dur
    ee = _eeff0(ur, er) * (_z01(u1) / _z01(ur)) ** 2
    z0 = _z01(ur) / np.sqrt(_eeff0(ur, er))
    c = np.sqrt(ee) / (C0 * z0) * 1e12 * 1e-3
    return z0, ee, c


def fringe_per_edge(w, h, t, er):
    """Fringe capacitance per unit edge (pF/mm) implied by the microstrip formula."""
    c = microstrip(w, h, t, er)[2]
    return max(0.0, (c - EPS0 * er * w / h * 1e9) / 2)


def kratio(k):
    """K(k')/K(k) (complete elliptic integrals, modulus k)."""
    return ellipk(1 - k * k) / ellipk(k * k)


def coplanar_pair(w1, g, w2, eeff):
    """Capacitance per length (pF/mm) between coplanar strips w1, w2 at gap g in a
    homogeneous medium of permittivity eeff (both half-spaces averaged):
    cross-ratio conformal map; w2 may be inf (half-plane)."""
    x1, x2, x3 = 0.0, w1, w1 + g
    if np.isinf(w2):
        cr = (x2 - x1) / (x3 - x1)
    else:
        x4 = x3 + w2
        cr = (x2 - x1) * (x4 - x3) / ((x3 - x1) * (x4 - x2))
    k = (1 - np.sqrt(cr)) / (1 + np.sqrt(cr))
    return EPS0 * eeff * kratio(k) * 1e9


def garg_bahl_cm(w, s, h, t, er):
    """Mutual capacitance per length (pF/mm) of symmetric coupled microstrips,
    Garg & Bahl (1979): Cm = (C_odd - C_even)/2 = (Cga + Cgd - Cf')/2."""
    z0, ee, c = microstrip(w, h, t, er)
    cf = max(0.0, (c - EPS0 * er * w / h * 1e9) / 2)
    A = np.exp(-0.1 * np.exp(2.33 - 2.53 * w / h))
    cfp = cf / (1 + A * (h / s) * np.tanh(8 * s / h)) * np.sqrt(er / ee)
    k = (s / h) / (s / h + 2 * w / h)
    cga = EPS0 * kratio(k) * 1e9  # air-side gap term, Garg-Bahl k = s/(s+2w)
    cgd = EPS0 * er / np.pi * np.log(1 / np.tanh(np.pi * s / (4 * h))) * 1e9 + \
        0.65 * cf * (0.02 * np.sqrt(er) / (s / h) + 1 - 1 / er**2)
    return max(0.0, (cga + cgd - cfp) / 2)


# ---------------------------------------------------------------- helpers
def stack_params(name):
    st = STACKUPS[name]
    return st['prepreg'], st['t_outer'], st['er_prepreg'], st


def antipad_gap(x, y, ring_r):
    """Radial gap from a ring of radius ring_r at (x, y) to the In1 copper."""
    return plane_in1().distance(Point(x, y)) - ring_r


def node_c_gnd(net, stackup, void_mode='edge'):
    h, t, er, st = stack_params(stackup)
    P = plane_in1()
    items = [it for it in geometry()['items'] if it['net'] == net]
    pads_f = unary_union([s for s in (item_shape(it, 'F.Cu') for it in items if it['kind'] != 'track')
                          if s is not None])
    out = {'tracks_over_plane': 0.0, 'tracks_over_void': 0.0, 'pads_over_plane': 0.0,
           'pads_over_void': 0.0, 'pth_via_inner_rings': 0.0, 'in2_tracks': 0.0}
    eeff_gap = (er + 1) / 2

    def void_c(shape, w):
        if shape.is_empty:
            return 0.0
        if void_mode == 'zero':
            return 0.0
        if void_mode == 'as_if_no_void':
            return None
        # edge treatment: every outline sample whose straight path to the
        # nearest In1 copper leaves the conductor directly (it faces the plane)
        # couples as a strip of width w to a half-plane at slant gap g.
        from shapely.ops import nearest_points
        tot = 0.0
        inner = shape.buffer(-1e-4)
        for geom in getattr(shape, 'geoms', [shape]):
            b = geom.exterior
            n = max(2, int(b.length / DS))
            for k in range(n):
                p = b.interpolate((k + 0.5) * b.length / n)
                q = nearest_points(p, P)[1]
                if inner.intersects(LineString([p, q])):
                    continue
                g = np.hypot(p.distance(q), h)
                tot += coplanar_pair(w, g, np.inf, eeff_gap) * (b.length / n)
        return tot

    for it in items:
        if it['kind'] == 'track':
            s = item_shape(it, it['layer'])
            if it['layer'] == 'F.Cu':
                s = s.difference(pads_f)
                over = s.intersection(P); void = s.difference(P)
                cprime = microstrip(it['w'], h, t, er)[2]
                out['tracks_over_plane'] += cprime * over.area / it['w']
                vc = void_c(void, it['w'])
                out['tracks_over_void'] += cprime * void.area / it['w'] if vc is None else vc
            elif it['layer'] == 'In2.Cu':
                hc = st['core'] + st['t_inner']
                out['in2_tracks'] += microstrip(it['w'], hc, st['t_inner'], st['er_core'])[2] * s.area / it['w']
            continue
        s = item_shape(it, 'F.Cu')
        if s is not None:
            bx = s.bounds
            wmin = min(bx[2] - bx[0], bx[3] - bx[1])
            over = s.intersection(P); void = s.difference(P)
            ce = fringe_per_edge(wmin, h, t, er)
            if not over.is_empty:
                out['pads_over_plane'] += EPS0 * er * over.area / h * 1e9 + ce * over.boundary.length
            if void_mode == 'as_if_no_void':
                out['pads_over_void'] += EPS0 * er * void.area / h * 1e9 + ce * void.boundary.length
            else:
                out['pads_over_void'] += void_c(void, wmin) or 0.0
        # inner-layer rings of plated holes: coplanar ring/plane across antipad
        if it['kind'] == 'via' or it.get('pth'):
            ring = item_shape(it, 'In1.Cu')
            if ring is not None:
                r_out = (ring.bounds[2] - ring.bounds[0]) / 2
                g = antipad_gap(it['x'], it['y'], r_out)
                w_ring = r_out - it['drill'] / 2
                if g > 1e-3:
                    out['pth_via_inner_rings'] += coplanar_pair(w_ring, g, np.inf, st['er_core'] * 0.5 + st['er_prepreg'] * 0.5) * \
                        2 * np.pi * (r_out + g / 2)
    out['total'] = sum(v for k, v in out.items())
    return out


def facing_samples(net_a, net_b, layer='F.Cu', gmax=GMAX):
    """Sample net_a's outline; yield (point, distance, local widths) facing net_b."""
    A = net_shape(net_a, layer); B = net_shape(net_b, layer)
    if A is None or B is None:
        return []
    samples = []
    near = A.intersection(B.buffer(gmax))
    if near.is_empty:
        return []
    for geom in getattr(A, 'geoms', [A]):
        for ring in [geom.exterior] + list(geom.interiors):
            L = ring.length
            n = max(2, int(L / DS))
            for k in range(n):
                p = ring.interpolate((k + 0.5) * L / n)
                d = B.distance(p)
                if d > gmax or d < 1e-6:
                    continue
                # facing test: the straight gap path to B must not re-enter A
                q = B.exterior.interpolate(B.exterior.project(p)) if B.geom_type == 'Polygon' else None
                from shapely.ops import nearest_points
                q = nearest_points(p, B)[1]
                seg = LineString([p, q])
                if seg.length > 1e-6 and A.buffer(-1e-4).intersects(seg):
                    continue
                samples.append((p, q, d, L / n))
    return samples


def local_width(shape, p, q):
    """Width of `shape` measured from p away from q (along the gap direction)."""
    v = np.array([p.x - q.x, p.y - q.y]); v /= np.linalg.norm(v)
    far = LineString([(p.x, p.y), (p.x + 5 * v[0], p.y + 5 * v[1])])
    inter = far.intersection(shape.buffer(1e-4))
    return max(0.05, min(inter.length if not inter.is_empty else 0.2, 2.0))


def mutual(net_a, net_b, stackup):
    h, t, er, st = stack_params(stackup)
    P = plane_in1()
    A = net_shape(net_a, 'F.Cu'); B = net_shape(net_b, 'F.Cu')
    tot_plane = tot_void = 0.0
    nmin = 1e9
    for p, q, d, dl in facing_samples(net_a, net_b):
        wa = local_width(A, p, q); wb = local_width(B, q, p)
        mid = Point((p.x + q.x) / 2, (p.y + q.y) / 2)
        nmin = min(nmin, d)
        if P.contains(mid):
            tot_plane += garg_bahl_cm(0.5 * (wa + wb), d, h, t, er) * dl
        else:
            tot_void += coplanar_pair(wa, d, wb, (er + 1) / 2) * dl
    return {'over_plane': tot_plane, 'over_void': tot_void, 'total': tot_plane + tot_void,
            'min_gap_mm': nmin}


def two_wire_c_per_mm(D, r, er=1.0):
    """Capacitance per length between two parallel round conductors (pF/mm)."""
    return np.pi * EPS0 * er / np.arccosh(D / (2 * r)) * 1e9


def header_pair_c(er_ins):
    """Pin-to-pin capacitance of a 2-pin TSW-07 header above the board:
    2.54 mm insulator (glass-filled polyester, er_ins) + 5.84 mm post in air.
    Square 0.635 mm post -> equivalent round radius 0.59*side for capacitance."""
    r = 0.59 * 0.635  # equivalent radius of a square conductor of side a is 0.59 a
    return two_wire_c_per_mm(2.54, r) * 5.84 + two_wire_c_per_mm(2.54, r, er_ins) * 2.54


def main():
    res = {'board_sha256': geometry()['board_sha256'], 'method': __doc__.strip().split('\n')[0]}
    import os
    variant = os.environ.get('LP_GEOMETRY', 'geometry.json').replace('geometry', '').replace('.json', '').strip('_')
    present = {it['net'] for it in geometry()['items']}
    nets = [n for n in [SUM, 'TIA_SUM', TIA, HI] + list(RF_NETS.values()) if n in present]
    res['c_gnd_pF'] = {}
    for st in (NOMINAL_STACKUP, THIN_STACKUP):
        for mode in ('zero', 'edge', 'as_if_no_void'):
            for n in nets:
                res['c_gnd_pF'].setdefault(n, {})[f'{st}/{mode}'] = node_c_gnd(n, st, mode)
    res['mutual_pF'] = {}
    sums = [n for n in (SUM, 'TIA_SUM') if n in present]
    pairs = [(s_, TIA) for s_ in sums] + [(s_, HI) for s_ in sums] + \
        [(s_, 'LOW_BUF') for s_ in sums] + [(HI, 'HIGH_BUF')] + \
        [(s_, n) for s_ in sums for n in RF_NETS.values()] + [(TIA, n) for n in RF_NETS.values()]
    if 'TIA_SUM' in present:
        pairs.append(('TIA_SUM', SUM))
    for a, b in pairs:
        for st in (NOMINAL_STACKUP, THIN_STACKUP):
            res['mutual_pF'][f'{a}|{b}|{st}'] = mutual(a, b, st)
    res['header_pin_pair_pF'] = {f'er_ins={e}': header_pair_c(e) for e in (3.0, 3.6, 4.2)}
    res['microstrip_check'] = {f'w={w}': dict(zip(('Z0', 'eeff', 'C_pF_per_mm'),
                                                microstrip(w, 0.2104, 0.035, 4.4)))
                               for w in (0.15, 0.2, 0.25, 0.3, 0.4)}
    (HERE / f"closed_form{'_' + variant if variant else ''}.json").write_text(json.dumps(res, indent=1, default=float))
    for n, d in res['c_gnd_pF'].items():
        print(n, {k: round(v['total'], 3) for k, v in d.items()})
    for k, v in res['mutual_pF'].items():
        print(k, {a: round(b, 4) for a, b in v.items()})
    print(res['header_pin_pair_pF'])


if __name__ == '__main__':
    main()
