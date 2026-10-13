"""Sense-loop pickup on native-21 stage 19c from the coil stray field (F8 rerun; copied from
02-protection-timing/coil-pickup/loops.py).  Each loop is a closed 3-D polyline built from the 19c copper
(native21s19c-all-copper.json.gz): Dijkstra over each net's tracks and vias, joined by explicit pour/plane/body
closures.  Flux = closed integral of A.dl with A_phi(r,z) = A0(r) - (z - z0) Br(r) (field.py), so planar (Bz) and
layer-change (Br) pickup are both included.  Frequency and tank current are arguments of emf_mv()."""
import json, heapq, math, sys
import numpy as np
from shapely.geometry import Polygon

import gzip, os
HERE = os.path.dirname(os.path.abspath(__file__))
COPPER = os.environ.get('F8_COPPER') or os.path.join(HERE, '..', '..', '..', '..', 'native-21', 'verification', 'native21s21b-all-copper.json.gz')
_raw = json.load(gzip.open(COPPER))
# same shape the 13b copper-dump.json had: tracks {net,a,b,layer}, vias {net,at}
D = dict(tracks=[dict(net=p['net'], a=p['start'], b=p['end'], layer=p['layer']) for p in _raw['primitives'] if p['kind'] == 'track'],
         vias=[dict(net=p['net'], at=p['centre']) for p in _raw['primitives'] if p['kind'] == 'via'])
_PADS = {p['ref']: p['centre'] for p in _raw['primitives'] if p['kind'] == 'pad'}
BOARD_SHA = _raw['board_sha256']
# layer heights (mm, world z): F.Cu at the map's copper plane 26.8, then down through the 1.65 mm stack
Z = {'F.Cu': 26.8, 'In1.Cu': 26.8 - 0.47, 'In2.Cu': 26.8 - 1.03, 'B.Cu': 26.8 - 1.50}
I_MAP = 45.0
def scale(i_pk): return i_pk / I_MAP

def key(p, l): return (round(p[0], 2), round(p[1], 2), l)

def graph(net):
    g = {}
    def add(a, b, w):
        g.setdefault(a, []).append((b, w)); g.setdefault(b, []).append((a, w))
    nodes = []
    for t in D['tracks']:
        if t['net'] != net: continue
        a, b = key(t['a'], t['layer']), key(t['b'], t['layer'])
        add(a, b, math.dist(t['a'], t['b'])); nodes += [a, b]
    # snap coincident endpoints on the same layer (rounding noise) and T-junctions onto segment interiors
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if a != b and a[2] == b[2] and math.dist(a[:2], b[:2]) < 0.35:
                add(a, b, math.dist(a[:2], b[:2]))
    for v in D['vias']:
        if v['net'] != net: continue
        ks = [n for n in set(nodes) if math.dist(n[:2], v['at']) < 0.35]
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                add(a, b, 0.01)
    return g

def path(net, p0, l0, p1, l1):
    """Shortest track path between the nodes nearest p0 (on l0) and p1 (on l1). Returns [(x,y,layer)]."""
    g = graph(net)
    near = lambda p, l: min((n for n in g if n[2] == l), key=lambda n: math.dist(n[:2], p))
    s, t = near(p0, l0), near(p1, l1)
    for q, n in ((p0, s), (p1, t)):
        if math.dist(q, n[:2]) > 1.5:
            raise ValueError(f'{net}: nearest node {n} is {math.dist(q, n[:2]):.2f} mm from {q}')
    dist, prev, h = {s: 0}, {}, [(0, s)]
    while h:
        d, u = heapq.heappop(h)
        if u == t: break
        if d > dist[u]: continue
        for v, w in g[u]:
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w; prev[v] = u; heapq.heappush(h, (d + w, v))
    if t not in dist: raise ValueError(f'{net}: no path {s} -> {t}')
    out = [t]
    while out[-1] != s: out.append(prev[out[-1]])
    return [(n[0], n[1], n[2]) for n in reversed(out)], dist[t]


def flux(loop, P, step=0.1):
    """loop: closed list of (x_k, y_k, layer). Returns (total, Bz part, Br part) in uT*mm2 (rms, 45 A pk).
    World frame: x_w = x_k - 141, y_w = 236 - y_k, z up; axis at world (0, 261). Positive = +z flux
    through the loop traversed counter-clockwise seen from above (world)."""
    tot = bz = br = 0.0j
    pts = loop + [loop[0]]
    for (xa, ya, la), (xb, yb, lb) in zip(pts[:-1], pts[1:]):
        if la != lb and (xa, ya) != (xb, yb):
            # a body/closure that changes layer: split into horizontal run on la then vertical
            pass
        z = Z[la]
        wa = np.array([xa - 141.0, 236.0 - ya]); wb = np.array([xb - 141.0, 236.0 - yb])
        L = np.linalg.norm(wb - wa)
        if L == 0: continue
        n = max(2, int(L / step))
        s = (np.arange(n) + 0.5) / n
        q = wa[None, :] + s[:, None] * (wb - wa)[None, :]
        rel = q - np.array([0.0, 261.0])
        r = np.hypot(rel[:, 0], rel[:, 1])
        phi_hat = np.stack([-rel[:, 1], rel[:, 0]], 1) / r[:, None]
        dl = (wb - wa) / n
        proj = phi_hat @ dl
        a0 = P.A(r)
        brr = np.interp(r, P.rg, np.real(P.Br)) + 1j * np.interp(r, P.rg, np.imag(P.Br))
        a1 = -(z - P.z0) * brr
        bz += np.sum(a0 * proj); br += np.sum(a1 * proj)
    return bz + br, bz, br

def area(loop):
    xy = [(p[0], p[1]) for p in loop]
    sh = sum(xy[i - 1][0] * xy[i][1] - xy[i][0] * xy[i - 1][1] for i in range(len(xy))) / 2
    try:
        pg = Polygon(xy).buffer(0)
        geo = pg.area
    except Exception:
        geo = float('nan')
    return sh, geo

def emf_mv(phi_uTmm2, f_hz, ipk):
    """rms flux phasor at 45 A pk (uT*mm2) -> peak EMF phasor jw*Phi in mV at the actual current.
    Phase is referenced to the tank current (real axis = in phase with i_tank, i.e. the value at the
    current peak); the CSV-map profile is real-signed so its EMF is pure quadrature."""
    return 1j * 2 * math.pi * f_hz * complex(phi_uTmm2) * 1e-12 * math.sqrt(2) * scale(ipk) * 1e3

def centroid(loop):
    xs = [p[0] for p in loop]; ys = [p[1] for p in loop]
    return sum(xs) / len(xs), sum(ys) / len(ys)

def pad(ref, num):
    return tuple(_PADS['%s.%s' % (ref, num)])
