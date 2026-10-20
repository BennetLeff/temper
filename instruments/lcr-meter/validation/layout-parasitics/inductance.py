"""Loop inductance of the C104 branch and each RF/jumper branch.

Method: partial-inductance (Neumann) double integral over the actual 3-D
current path, thin-wire reduced kernel 1/sqrt(R^2 + a^2) with a = geometric
mean distance of each conductor's cross-section (uniform current, i.e. the
low-frequency / maximum value).  The In1.Cu GND plane is represented by image
currents at mirror depth.  Three plane treatments:

  free   no plane at all                         -> upper bound (any induced
         current in nearby conductors can only reduce loop inductance)
  partial images only where In1 copper exists (morphological closing 1.1 mm,
         so small antipads count as plane, the deliberate voids do not) -> nominal
  full   images everywhere (as if no voids)      -> lower bound for a perfect plane

Board copper paths come from native track/pad geometry (graph walk over
F.Cu segments, split at T-junctions).  Package, resistor, capacitor and
header/shunt geometry is modelled from stated dimensions (see PARTS).

Writes inductance.json.
"""
from __future__ import annotations

import heapq
import json
from itertools import product

import numpy as np
from shapely import contains_xy, prepare
from shapely.geometry import Point

from common import (HERE, MU0, NOMINAL_STACKUP, RF_JP, RF_NETS, RF_RES, STACKUPS, SUM, TIA,
                    THIN_STACKUP, geometry, item_shape, pad, plane_in1)

T_CU = 0.035

# --------------------------------------------------------------------------
# Part geometry assumptions (mm).  low/nom/high refer to resulting inductance.
# --------------------------------------------------------------------------
PARTS = {
    # Samtec TSW-102-07-G-S: 0.635 mm square post, 2.54 mm insulator, 5.84 mm
    # mating post -> tip 8.38 mm above board.  SNT-100-BK-G shunt: 6.10 mm tall,
    # seated on the insulator (top 8.64 mm); 4.32 mm minimum insertion.  Height
    # at which current crosses between posts (contact bridge) is not published:
    'header_bridge_z': {'low': 4.5, 'nom': 6.9, 'high': 8.4},
    'post_side': 0.635,
    'shunt_strip_w': 0.8,       # bridging contact strip width (assumed)
    # 0603 thin-film resistor (Yageo RT0603, 0.45 mm thick): film on top face.
    'res_film_z': 0.45, 'res_body_w': 0.8,
    # 0603 C0G MLCC (Samsung CL10C101JB8NNNC, 0.8 mm thick): mean electrode height
    'cap_mid_z': {'low': 0.3, 'nom': 0.4, 'high': 0.5}, 'cap_body_w': 0.8,
    # OPA2810IDGKR VSSOP-8 (DGK, JEDEC MO-187): body 3.0 mm, lead 0.3 x 0.15 mm,
    # standoff/lead-entry height ~0.45 mm; leadframe tip -> die by bond wire
    # (25 um).  Die bond-pad spacing for pins 1/2 and wire length are assumed.
    'pkg': {
        'low': dict(lead_tip_dx=0.75, bond_dx=0.35, die_z=0.55, pad_pitch_frac=0.6),
        'nom': dict(lead_tip_dx=0.95, bond_dx=0.6, die_z=0.6, pad_pitch_frac=0.8),
        'high': dict(lead_tip_dx=1.05, bond_dx=0.9, die_z=0.65, pad_pitch_frac=1.0),
    },
}


def gmd_rect(w, t):
    return 0.2235 * (w + t)


A_POST = 0.447 * PARTS['post_side']
A_BOND = 0.7788 * 0.0125
A_LEAD = gmd_rect(0.30, 0.15)


# --------------------------------------------------------------------------
# Native board paths
# --------------------------------------------------------------------------
def board_path(net, a_ref, b_ref):
    """Shortest F.Cu centreline path between two pads of `net`.

    Returns list of (x, y, width) vertices starting at pad a centre and ending
    at pad b centre."""
    its = [it for it in geometry()['items'] if it['net'] == net]
    segs = [it for it in its if it['kind'] == 'track' and it['layer'] == 'F.Cu']
    pts = set()
    for s in segs:
        pts.add((round(s['x1'], 4), round(s['y1'], 4)))
        pts.add((round(s['x2'], 4), round(s['y2'], 4)))
    graph = {}

    def add(u, v, w):
        d = float(np.hypot(u[0] - v[0], u[1] - v[1]))
        graph.setdefault(u, []).append((v, d, w))
        graph.setdefault(v, []).append((u, d, w))

    for s in segs:
        a = np.array([s['x1'], s['y1']]); b = np.array([s['x2'], s['y2']])
        L = np.linalg.norm(b - a)
        on = []
        for p in pts:
            pv = np.array(p)
            if L == 0:
                continue
            tpar = np.dot(pv - a, b - a) / L**2
            if -1e-9 <= tpar <= 1 + 1e-9 and np.linalg.norm(a + tpar * (b - a) - pv) < 2e-4:
                on.append((tpar, p))
        on.sort()
        for (t1, p1), (t2, p2) in zip(on, on[1:]):
            if p1 != p2:
                add(p1, p2, s['w'])
    pads = {}
    for ref in (a_ref, b_ref):
        r, n = ref.split('.')
        pd = pad(r, n)
        poly = item_shape(pd, 'F.Cu')
        c = (round(pd['x'], 4), round(pd['y'], 4))
        pads[ref] = c
        bx = poly.bounds
        wpad = min(bx[2] - bx[0], bx[3] - bx[1])
        for p in pts:
            if poly.buffer(1e-3).contains(Point(p)) and p != c:
                add(c, p, wpad)
    src, dst = pads[a_ref], pads[b_ref]
    dist = {src: 0.0}; prev = {}
    q = [(0.0, src)]
    while q:
        d, u = heapq.heappop(q)
        if u == dst:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w, width in graph.get(u, []):
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd; prev[v] = (u, width); heapq.heappush(q, (nd, v))
    if dst not in dist:
        raise RuntimeError(f'no path {net} {a_ref}->{b_ref}')
    path = [dst]; widths = []
    while path[-1] != src:
        u, w = prev[path[-1]]
        widths.append(w); path.append(u)
    path = path[::-1]; widths = widths[::-1]
    return path, widths, dist[dst]


# --------------------------------------------------------------------------
# Filament loop representation: list of (p0, p1, a)
# --------------------------------------------------------------------------
def planar(path, widths, z):
    segs = []
    for (p, q), w in zip(zip(path, path[1:]), widths):
        segs.append((np.array([p[0], p[1], z]), np.array([q[0], q[1], z]), gmd_rect(w, T_CU)))
    return segs


def body(p_from, p_to, z_top, a, z0):
    """Two-terminal SMD part: up at p_from, across at z_top, down at p_to."""
    A = np.array([p_from[0], p_from[1], z0]); B = np.array([p_from[0], p_from[1], z_top])
    C = np.array([p_to[0], p_to[1], z_top]); D = np.array([p_to[0], p_to[1], z0])
    return [(A, B, a), (B, C, a), (C, D, a)]


def package_pair(pin_out_xy, pin_in_xy, z0, cfg, pkg_center_x):
    """Lead/bond/die path from the TIA-output land to the -IN land, through die."""
    sgn = np.sign(pkg_center_x - pin_out_xy[0])
    body_edge = pkg_center_x - sgn * 1.5
    ymid = 0.5 * (pin_out_xy[1] + pin_in_xy[1])
    segs = []

    def lead(pxy):
        x0, y0 = pxy
        foot_in = (x0 + sgn * 0.25, y0, z0)
        edge = (body_edge, y0, 0.45)
        tip = (body_edge + sgn * (cfg['lead_tip_dx'] - 0.5), y0, 0.45)
        yb = ymid + (y0 - ymid) * cfg['pad_pitch_frac']
        bond = (tip[0] + sgn * cfg['bond_dx'], yb, cfg['die_z'])
        return [np.array(p) for p in ((x0, y0, z0), foot_in, edge, tip, bond)]

    lo, li = lead(pin_out_xy), lead(pin_in_xy)
    a_list = [A_LEAD, A_LEAD, A_LEAD, A_BOND]
    # current leaves die at output bond pad, runs out the output lead to the land
    for k in range(4, 0, -1):
        segs.append((lo[k], lo[k - 1], a_list[k - 1]))
    in_from_land = []
    for k in range(4):
        in_from_land.append((li[k], li[k + 1], a_list[k]))
    die = (li[4], lo[4], A_BOND * 3)
    return segs, in_from_land, die


def subdivide(segs, max_ds=0.05):
    P0, P1, A = [], [], []
    for p0, p1, a in segs:
        L = np.linalg.norm(p1 - p0)
        if L < 1e-9:
            continue
        ds = min(max_ds, max(a, 0.008))
        n = max(1, int(np.ceil(L / ds)))
        ts = np.linspace(0, 1, n + 1)
        for t0, t1 in zip(ts, ts[1:]):
            P0.append(p0 + (p1 - p0) * t0); P1.append(p0 + (p1 - p0) * t1); A.append(a)
    return np.array(P0), np.array(P1), np.array(A)


GL_X, GL_W = np.polynomial.legendre.leggauss(4)
GL_X = 0.5 * (GL_X + 1); GL_W = 0.5 * GL_W


def mutual_sum(P0, P1, A, Q0, Q1, B, same, regularize=True):
    """Sum over all piece pairs of (t_i . t_j) * int int ds ds' / sqrt(R^2 + a^2)  [mm]."""
    dP = P1 - P0; dQ = Q1 - Q0
    total = 0.0
    n = len(P0)
    chunk = 200
    for i0 in range(0, n, chunk):
        i1 = min(n, i0 + chunk)
        dot = dP[i0:i1] @ dQ.T  # (ci, m)
        acc = np.zeros_like(dot)
        a2 = ((A[i0:i1, None] ** 2 + B[None, :] ** 2) / 2) if regularize else 0.0
        for xa, wa in zip(GL_X, GL_W):
            pa = P0[i0:i1] + xa * dP[i0:i1]
            for xb, wb in zip(GL_X, GL_W):
                qb = Q0 + xb * dQ
                R2 = ((pa[:, None, :] - qb[None, :, :]) ** 2).sum(-1)
                acc += wa * wb / np.sqrt(R2 + a2)
        val = dot * acc
        if same:
            # replace diagonal (self) terms by the exact analytic integral
            for k in range(i0, i1):
                l = np.linalg.norm(dP[k]); a = A[k]
                val[k - i0, k] = 2 * (l * np.arcsinh(l / a) - np.sqrt(l * l + a * a) + a)
        total += val.sum()
    return total


def loop_L(segs, zp, plane_mask_fn, mode):
    """Loop inductance in nH. zp = plane surface z; mode free/partial/full."""
    P0, P1, A = subdivide(segs)
    L = mutual_sum(P0, P1, A, P0, P1, A, same=True)
    if mode != 'free':
        mid = 0.5 * (P0 + P1)
        if mode == 'full':
            keep = np.ones(len(P0), bool)
        else:
            keep = plane_mask_fn(mid[:, 0], mid[:, 1])
        I0 = P0[keep].copy(); I1 = P1[keep].copy()
        I0[:, 2] = 2 * zp - I0[:, 2]; I1[:, 2] = 2 * zp - I1[:, 2]
        # image current: horizontal components reversed, vertical kept
        # (= mirrored segment traversed with negated tangent)
        L -= mutual_sum(P0, P1, A, I0, I1, A[keep], same=False, regularize=False)
    return MU0 / (4 * np.pi) * L * 1e-3 * 1e9  # mm -> m, H -> nH


def mutual_L(segs1, segs2):
    P0, P1, A = subdivide(segs1); Q0, Q1, B = subdivide(segs2)
    return MU0 / (4 * np.pi) * mutual_sum(P0, P1, A, Q0, Q1, B, same=False) * 1e-3 * 1e9


# --------------------------------------------------------------------------
def build_loops(case):
    """case: dict with pkg cfg key, header bridge z, cap z.  Returns dict of loops."""
    zc = T_CU / 2
    u1 = pad('U7', '1'); u2 = pad('U7', '2')
    pkg_out, pkg_in, die = package_pair((u1['x'], u1['y']), (u2['x'], u2['y']), zc,
                                        PARTS['pkg'][case['pkg']], 168.0)
    loops = {}
    # ---- C104 branch: U7.1 -> C104.2 -> body -> C104.1 -> U7.2
    p1, w1, l1 = board_path(TIA, 'U7.1', 'C104.2')
    p2, w2, l2 = board_path(SUM, 'C104.1', 'U7.2')
    c2 = pad('C104', '2'); c1 = pad('C104', '1')
    board = planar(p1, w1, zc) + body((c2['x'], c2['y']), (c1['x'], c1['y']),
                                      PARTS['cap_mid_z'][case['cap']],
                                      gmd_rect(PARTS['cap_body_w'], 0.8), zc) + planar(p2, w2, zc)
    loops['C104'] = dict(board=board, pkg=pkg_out + board + pkg_in + [die],
                         board_close=[(board[-1][1], board[0][0], A_LEAD)],
                         planar_mm=l1 + l2)
    for rng, net in RF_NETS.items():
        jp, rr = RF_JP[rng], RF_RES[rng]
        pa, wa, la = board_path(TIA, 'U7.1', f'{jp}.1')
        pb, wb, lb = board_path(net, f'{jp}.2', f'{rr}.2')
        pc, wc, lc = board_path(SUM, f'{rr}.1', 'U7.2')
        j1, j2 = pad(jp, '1'), pad(jp, '2')
        r2, r1 = pad(rr, '2'), pad(rr, '1')
        zb = PARTS['header_bridge_z'][case['hdr']]
        hdr = [(np.array([j1['x'], j1['y'], zc]), np.array([j1['x'], j1['y'], zb]), A_POST),
               (np.array([j1['x'], j1['y'], zb]), np.array([j2['x'], j2['y'], zb]),
                gmd_rect(PARTS['shunt_strip_w'], 0.2)),
               (np.array([j2['x'], j2['y'], zb]), np.array([j2['x'], j2['y'], zc]), A_POST)]
        res = body((r2['x'], r2['y']), (r1['x'], r1['y']), PARTS['res_film_z'],
                   gmd_rect(PARTS['res_body_w'], 0.01), zc)
        board = planar(pa, wa, zc) + hdr + planar(pb, wb, zc) + res + planar(pc, wc, zc)
        loops[f'RF_{rng}'] = dict(board=board, pkg=pkg_out + board + pkg_in + [die],
                                  board_close=[(board[-1][1], board[0][0], A_LEAD)],
                                  planar_mm=la + lb + lc)
    return loops


def plane_mask():
    closed = plane_in1().buffer(1.1, 16).buffer(-1.1, 16)
    prepare(closed)
    return lambda x, y: contains_xy(closed, x, y)


def validate():
    """Self-tests against textbook closed forms."""
    out = {}
    # circular loop R=5 mm, round wire r=0.1 mm: L = mu0 R (ln(8R/r) - 1.75)
    R, r = 5.0, 0.1
    th = np.linspace(0, 2 * np.pi, 721)
    pts = np.stack([R * np.cos(th), R * np.sin(th), 0 * th], 1)
    segs = [(pts[i], pts[i + 1], 0.7788 * r) for i in range(720)]
    P0, P1, A = subdivide(segs, 0.05)
    num = MU0 / (4 * np.pi) * mutual_sum(P0, P1, A, P0, P1, A, same=True) * 1e-3 * 1e9
    ana = MU0 * R * 1e-3 * (np.log(8 * R / r) - 1.75) * 1e9
    out['circle_R5_r0.1_nH'] = {'numeric': num, 'analytic': ana, 'rel_err': num / ana - 1}
    # microstrip per-length inductance vs Hammerstad-Jensen air-line impedance
    st = STACKUPS[NOMINAL_STACKUP]
    for w in (0.2, 0.3):
        h = st['prepreg']
        zp = -h
        Ls = []
        for l in (20.0, 40.0):
            segs = [(np.array([0, 0, T_CU / 2]), np.array([l, 0, T_CU / 2]), gmd_rect(w, T_CU))]
            Ls.append(loop_L(segs, zp, None, 'full'))
        per_mm = (Ls[1] - Ls[0]) / 20
        from closed_form import microstrip
        z_air = microstrip(w, h, T_CU, 1.0)[0]
        out[f'microstrip_w{w}_nH_per_mm'] = {'numeric': per_mm, 'hammerstad_air_Z0_over_c': z_air / 299792458 * 1e6,
                                             'rel_err': per_mm / (z_air / 299792458 * 1e6) - 1}
    return out


def main():
    mask = plane_mask()
    results = {'board_sha256': geometry()['board_sha256'], 'method': __doc__.strip().split('\n')[0],
               'assumptions': PARTS, 'validation': validate(), 'loops': {}}
    cases = {'nom': dict(pkg='nom', hdr='nom', cap='nom'),
             'low': dict(pkg='low', hdr='low', cap='low'),
             'high': dict(pkg='high', hdr='high', cap='high')}
    stack = {'nom': NOMINAL_STACKUP, 'low': THIN_STACKUP, 'high': NOMINAL_STACKUP}
    for cname, case in cases.items():
        loops = build_loops(case)
        zp = -STACKUPS[stack[cname]]['prepreg']
        mode = {'nom': 'partial', 'low': 'full', 'high': 'free'}[cname]
        for lname, lp in loops.items():
            r = results['loops'].setdefault(lname, {'planar_board_path_mm': lp['planar_mm']})
            r[cname] = {
                'stackup': stack[cname], 'plane_mode': mode,
                'with_package_nH': loop_L(lp['pkg'], zp, mask, mode),
                'board_and_part_only_nH': loop_L(lp['board'] + lp['board_close'], zp, mask, mode),
            }
            if cname == 'nom':
                for m2 in ('free', 'full'):
                    r[f'nom_geometry_plane_{m2}_nH'] = loop_L(lp['pkg'], zp, mask, m2)
        if cname == 'nom':
            # shared-path decomposition: M between C104 loop and each RF loop
            for rng in RF_NETS:
                m = mutual_L(loops['C104']['pkg'], loops[f'RF_{rng}']['pkg'])
                results['loops'][f'RF_{rng}']['mutual_with_C104_loop_free_space_nH'] = m
    (HERE / 'inductance.json').write_text(json.dumps(results, indent=1, default=float))
    print(json.dumps(results['validation'], indent=1, default=float))
    for k, v in results['loops'].items():
        print(k, {c: (round(v[c]['with_package_nH'], 2), round(v[c]['board_and_part_only_nH'], 2))
                  for c in ('low', 'nom', 'high')},
              'nom free/full', round(v['nom_geometry_plane_free_nH'], 2), round(v['nom_geometry_plane_full_nH'], 2))


if __name__ == '__main__':
    main()
