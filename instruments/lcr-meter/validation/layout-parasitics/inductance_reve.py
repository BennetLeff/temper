"""Rev E loop inductance: C104 branch and the three relay-switched RF branches.

Same Neumann partial-inductance method and part/package assumptions as
inductance.py, with two generalisations that the Rev E routing needs:

1. board_path_ml(): shortest path over a multi-layer graph -- tracks on all
   four copper layers (split at T-junctions and via positions) plus vias as
   vertical segments between the z of the layers they connect.  inductance.py
   walks F.Cu only, which cannot follow the Rev E TIA_OUT (F.Cu -> B.Cu ->
   In2.Cu) and RF100/RF100K (In2.Cu) routes.

2. Plane treatment for conductors on BOTH sides of In1.Cu.  The single-sided
   image method of inductance.py is invalid here, so two cases are computed:
     free   no plane: upper value for the modelled geometry (any induced
            current in nearby conductors can only lower loop inductance) -> 'high'
     solid  In1 as a perfect, unbroken plane (no voids, antipads ignored):
            each half-space sees its own currents and their images about its
            plane surface; currents on opposite sides do not couple.  Filling
            the real voids can only lower L further, so this is the lower value
            for the modelled geometry with a perfect plane -> 'low'
   A plane-aware nominal with the real In1 voids would need a field solve of
   the perforated plane; it is NOT computed.  The free-space value is used in
   the stability harness.

RF branch (per range, relay Kx, resistor R4x):
  U7.1 -> TIA_OUT copper -> Kx.8 pad -> pad-to-pad hop (up HOP_Z at pin 8,
  across 2.54 mm, down at pin 7) -> Kx.7 -> RFx copper -> R4x.2 -> 0603 body
  -> R4x.1 -> TIA_SUM copper -> U7.2, closed through the OPA2810 package as in
  inductance.py.  The relay's internal contact/spring path is NOT modelled; it
  stays the separate L_rel estimate (10 / 20 nH) in the stability harness.

Writes inductance_reve.json (LP_INDUCTANCE overrides).
"""
from __future__ import annotations

import heapq
import json
import os

import numpy as np
from shapely.geometry import Point

from common import HERE, MU0, NOMINAL_STACKUP, STACKUPS, SUM, TIA, THIN_STACKUP, geometry, item_shape, pad
from inductance import (A_LEAD, PARTS, T_CU, body, gmd_rect, mutual_sum, package_pair, subdivide,
                        validate)

RF = {'100R': ('K1', 'R43', 'RF100'), '5k': ('K2', 'R44', 'RF5K'), '100k': ('K3', 'R45', 'RF100K')}
# TQ2SA surface-mount terminal: gull-wing lead from the pad into the base.  The hop
# models only the lead pair from the pad up to the base and across; everything inside
# the base is L_rel.  Heights are ASSUMED (no published terminal drawing in sources/).
HOP_Z = {'low': 0.3, 'nom': 0.6, 'high': 1.0}
RELAY_LEAD = gmd_rect(0.5, 0.2)
GEOM = {'low': dict(pkg='low', hop='low', cap='low'),
        'nom': dict(pkg='nom', hop='nom', cap='nom'),
        'high': dict(pkg='high', hop='high', cap='high')}


def layer_z(stackup):
    """Copper centre z (mm) per layer; z = 0 is the top of the F.Cu dielectric."""
    st = STACKUPS[stackup]
    pp, ti, core = st['prepreg'], st['t_inner'], st['core']
    return {'F.Cu': T_CU / 2, 'In1.Cu': -(pp + ti / 2), 'In2.Cu': -(pp + ti + core + ti / 2),
            'B.Cu': -(2 * pp + 2 * ti + core + T_CU / 2)}


def plane_surfaces(stackup):
    st = STACKUPS[stackup]
    return -st['prepreg'], -(st['prepreg'] + st['t_inner'])   # In1 top, In1 bottom


def board_path_ml(net, a_ref, b_ref, zl):
    """Shortest copper path between two pads over all layers of `net`.

    Returns (vertices [(x, y, z)], radii per edge, planar length mm, layers used)."""
    its = [it for it in geometry()['items'] if it['net'] == net]
    segs = [it for it in its if it['kind'] == 'track']
    vias = [it for it in its if it['kind'] == 'via' or (it['kind'] == 'pad' and it.get('pth'))]
    pts = {}  # layer -> set of (x, y)
    for s in segs:
        pts.setdefault(s['layer'], set()).update({(round(s['x1'], 4), round(s['y1'], 4)),
                                                  (round(s['x2'], 4), round(s['y2'], 4))})
    for v in vias:
        for layer in (v['layers'] if v['kind'] == 'via' else v['polys']):
            pts.setdefault(layer, set()).add((round(v['x'], 4), round(v['y'], 4)))
    graph = {}

    def add(u, v, d, a, kind):
        graph.setdefault(u, []).append((v, d, a, kind))
        graph.setdefault(v, []).append((u, d, a, kind))

    for s in segs:
        L = s['layer']
        a = np.array([s['x1'], s['y1']]); b = np.array([s['x2'], s['y2']])
        ln = np.linalg.norm(b - a)
        if ln == 0:
            continue
        on = []
        for p in pts[L]:
            pv = np.array(p)
            t = np.dot(pv - a, b - a) / ln ** 2
            if -1e-9 <= t <= 1 + 1e-9 and np.linalg.norm(a + t * (b - a) - pv) < 2e-4:
                on.append((t, p))
        on.sort()
        t_cu = T_CU if L in ('F.Cu', 'B.Cu') else STACKUPS[NOMINAL_STACKUP]['t_inner']
        for (_, p1), (_, p2) in zip(on, on[1:]):
            if p1 != p2:
                add((L,) + p1, (L,) + p2, float(np.hypot(p1[0] - p2[0], p1[1] - p2[1])),
                    gmd_rect(s['w'], t_cu), 'planar')
    for v in vias:
        c = (round(v['x'], 4), round(v['y'], 4))
        layers = [L for L in zl if L in (v['layers'] if v['kind'] == 'via' else v['polys'])]
        r_ring = (v['dia'] if v['kind'] == 'via' else 0.0) / 2
        for L in layers:  # track ends landing inside the via ring join the via centre
            for p in pts.get(L, ()):
                if p != c and np.hypot(p[0] - c[0], p[1] - c[1]) <= max(r_ring, 1e-3):
                    add((L,) + c, (L,) + p, float(np.hypot(p[0] - c[0], p[1] - c[1])), 0.1, 'planar')
        for L1, L2 in zip(layers, layers[1:]):
            add((L1,) + c, (L2,) + c, abs(zl[L1] - zl[L2]), v['drill'] / 2, 'via')
    ends = {}
    for ref in (a_ref, b_ref):
        r, n = ref.split('.')
        pd = pad(r, n)
        L = 'F.Cu' if 'F.Cu' in pd['polys'] else next(iter(pd['polys']))  # path ends on the F.Cu land
        poly = item_shape(pd, L).buffer(1e-3)
        c = (L, round(pd['x'], 4), round(pd['y'], 4))
        ends[ref] = c
        bx = item_shape(pd, L).bounds
        wpad = min(bx[2] - bx[0], bx[3] - bx[1])
        for p in pts.get(L, ()):
            if (L,) + p != c and poly.contains(Point(p)):
                add(c, (L,) + p, float(np.hypot(p[0] - c[1], p[1] - c[2])), gmd_rect(wpad, T_CU), 'planar')
    src, dst = ends[a_ref], ends[b_ref]
    dist = {src: 0.0}; prev = {}
    q = [(0.0, src)]
    while q:
        d, u = heapq.heappop(q)
        if u == dst:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w, a, kind in graph.get(u, []):
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w; prev[v] = (u, a, kind); heapq.heappush(q, (d + w, v))
    if dst not in dist:
        raise RuntimeError(f'no path {net} {a_ref}->{b_ref}')
    path = [dst]; radii = []; planar_len = 0.0
    while path[-1] != src:
        u, a, kind = prev[path[-1]]
        radii.append(a)
        if kind == 'planar':
            planar_len += float(np.hypot(path[-1][1] - u[1], path[-1][2] - u[2]))
        path.append(u)
    path = path[::-1]; radii = radii[::-1]
    verts = [np.array([p[1], p[2], zl[p[0]]]) for p in path]
    return verts, radii, planar_len, sorted({p[0] for p in path})


def chain(verts, radii):
    return [(p, q, a) for p, q, a in zip(verts, verts[1:], radii) if np.linalg.norm(q - p) > 1e-9]


def build_loops(case, stackup):
    zl = layer_z(stackup)
    zc = zl['F.Cu']
    u1 = pad('U7', '1'); u2 = pad('U7', '2')
    pkg_out, pkg_in, die = package_pair((u1['x'], u1['y']), (u2['x'], u2['y']), zc,
                                        PARTS['pkg'][case['pkg']], 168.0)
    loops = {}
    v1, a1, l1, ly1 = board_path_ml(TIA, 'U7.1', 'C104.2', zl)
    v2, a2, l2, ly2 = board_path_ml(SUM, 'C104.1', 'U7.2', zl)
    c2 = pad('C104', '2'); c1 = pad('C104', '1')
    board = chain(v1, a1) + body((c2['x'], c2['y']), (c1['x'], c1['y']), PARTS['cap_mid_z'][case['cap']],
                                 gmd_rect(PARTS['cap_body_w'], 0.8), zc) + chain(v2, a2)
    loops['C104'] = dict(board=board, pkg=pkg_out + board + pkg_in + [die],
                         board_close=[(board[-1][1], board[0][0], A_LEAD)],
                         planar_mm=l1 + l2, layers=sorted(set(ly1) | set(ly2)))
    for rng, (k, rr, net) in RF.items():
        va, aa, la, lya = board_path_ml(TIA, 'U7.1', f'{k}.8', zl)
        vb, ab, lb, lyb = board_path_ml(net, f'{k}.7', f'{rr}.2', zl)
        vc, ac, lc, lyc = board_path_ml(SUM, f'{rr}.1', 'U7.2', zl)
        p8, p7 = pad(k, '8'), pad(k, '7')
        zh = HOP_Z[case['hop']]
        hop = [(np.array([p8['x'], p8['y'], zc]), np.array([p8['x'], p8['y'], zh]), RELAY_LEAD),
               (np.array([p8['x'], p8['y'], zh]), np.array([p7['x'], p7['y'], zh]), RELAY_LEAD),
               (np.array([p7['x'], p7['y'], zh]), np.array([p7['x'], p7['y'], zc]), RELAY_LEAD)]
        r2, r1 = pad(rr, '2'), pad(rr, '1')
        res = body((r2['x'], r2['y']), (r1['x'], r1['y']), PARTS['res_film_z'],
                   gmd_rect(PARTS['res_body_w'], 0.01), zc)
        board = chain(va, aa) + hop + chain(vb, ab) + res + chain(vc, ac)
        loops[f'RF_{rng}'] = dict(board=board, pkg=pkg_out + board + pkg_in + [die],
                                  board_close=[(board[-1][1], board[0][0], A_LEAD)],
                                  planar_mm=la + lb + lc, layers=sorted(set(lya) | set(lyb) | set(lyc)),
                                  path_mm={'TIA_OUT': la, net: lb, 'TIA_SUM': lc})
    return loops


def split_at(segs, z_top, z_bot):
    """Split segments at the plane surfaces; drop the part inside the plane copper."""
    up, lo = [], []
    for p0, p1, a in segs:
        pieces = [(p0, p1)]
        for zcut in (z_top, z_bot):
            nxt = []
            for q0, q1 in pieces:
                if (q0[2] - zcut) * (q1[2] - zcut) < 0:
                    t = (zcut - q0[2]) / (q1[2] - q0[2])
                    m = q0 + t * (q1 - q0)
                    nxt += [(q0, m), (m, q1)]
                else:
                    nxt.append((q0, q1))
            pieces = nxt
        for q0, q1 in pieces:
            zm = 0.5 * (q0[2] + q1[2])
            if zm >= z_top - 1e-9:
                up.append((q0, q1, a))
            elif zm <= z_bot + 1e-9:
                lo.append((q0, q1, a))
            # else: inside the plane copper (via barrel through the antipad): dropped
    return up, lo


def L_free(segs):
    P0, P1, A = subdivide(segs)
    return MU0 / (4 * np.pi) * mutual_sum(P0, P1, A, P0, P1, A, same=True) * 1e-3 * 1e9


def L_solid(segs, stackup):
    """Perfect unbroken In1 plane; conductors on both sides (see module docstring)."""
    z_top, z_bot = plane_surfaces(stackup)
    tot = 0.0
    for part, zp in zip(split_at(segs, z_top, z_bot), (z_top, z_bot)):
        if not part:
            continue
        P0, P1, A = subdivide(part)
        val = mutual_sum(P0, P1, A, P0, P1, A, same=True)
        I0 = P0.copy(); I1 = P1.copy()
        I0[:, 2] = 2 * zp - I0[:, 2]; I1[:, 2] = 2 * zp - I1[:, 2]
        val -= mutual_sum(P0, P1, A, I0, I1, A, same=False, regularize=False)
        tot += val
    return MU0 / (4 * np.pi) * tot * 1e-3 * 1e9


def validate_ml():
    """Two-sided image method: a strip under In1 (B.Cu side) must match the single-sided
    inductance.loop_L 'full' result for the mirrored strip at the same height above a plane."""
    from inductance import loop_L
    z_top, z_bot = plane_surfaces(NOMINAL_STACKUP)
    zb = layer_z(NOMINAL_STACKUP)['B.Cu']
    h = z_bot - zb
    out = {}
    per = []
    for fn in (lambda l: L_solid([(np.array([0, 0, zb]), np.array([l, 0, zb]), gmd_rect(0.2, T_CU))], NOMINAL_STACKUP),
               lambda l: loop_L([(np.array([0, 0, h]), np.array([l, 0, h]), gmd_rect(0.2, T_CU))], 0.0, None, 'full')):
        per.append((fn(40.0) - fn(20.0)) / 20)
    out[f'strip_w0.2_below_In1_h{h:.4f}_nH_per_mm'] = {'two_sided': per[0], 'single_sided_mirror': per[1],
                                                       'rel_err': per[0] / per[1] - 1}
    return out


def main():
    results = {'board_sha256': geometry()['board_sha256'], 'method': __doc__.strip().split('\n')[0],
               'assumptions': {**PARTS, 'relay_hop_z_mm': HOP_Z, 'relay_lead_gmd_mm': RELAY_LEAD},
               'validation': {**validate(), **validate_ml()}, 'loops': {}}
    for cname, case in GEOM.items():
        stack = THIN_STACKUP if cname == 'low' else NOMINAL_STACKUP
        loops = build_loops(case, stack)
        for lname, lp in loops.items():
            r = results['loops'].setdefault(lname, {'planar_board_path_mm': lp['planar_mm'],
                                                    'layers': lp['layers'],
                                                    'path_mm': lp.get('path_mm')})
            r[cname] = {'stackup': stack, 'geometry': case,
                        'free_with_package_nH': L_free(lp['pkg']),
                        'free_board_and_part_only_nH': L_free(lp['board'] + lp['board_close']),
                        'solid_plane_with_package_nH': L_solid(lp['pkg'], stack)}
    for lname, r in results['loops'].items():
        # high = free space, high geometry, nominal stackup (same convention as Rev C/D 'high')
        # low  = perfect solid plane, low geometry, thin 1080 stackup
        r['summary_nH'] = {'low': r['low']['solid_plane_with_package_nH'], 'nom': None,
                           'high': r['high']['free_with_package_nH'],
                           'nom_geometry_free': r['nom']['free_with_package_nH'],
                           'nom_geometry_solid_plane': r['nom']['solid_plane_with_package_nH']}
    out = HERE / os.environ.get('LP_INDUCTANCE', 'inductance_reve.json')
    out.write_text(json.dumps(results, indent=1, default=float))
    print(json.dumps(results['validation'], indent=1, default=float))
    for k, v in results['loops'].items():
        s = v['summary_nH']
        print(k, 'layers', v['layers'], 'planar %.2f mm' % v['planar_board_path_mm'],
              'low(solid) %.2f  nom-geom solid/free %.2f/%.2f  high(free) %.2f nH' %
              (s['low'], s['nom_geometry_solid_plane'], s['nom_geometry_free'], s['high']),
              'board-only free(high) %.2f' % v['high']['free_board_and_part_only_nH'])


if __name__ == '__main__':
    main()
