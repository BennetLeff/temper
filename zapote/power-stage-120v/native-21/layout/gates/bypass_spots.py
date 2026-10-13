#!/usr/bin/env python3
"""Candidate spots for a 0603 bypass cap beside an IC supply pin (stage 19, review N1).

    KiCad-python bypass_spots.py BOARD.kicad_pcb REF SUPPLY_PAD RETURN_PAD [--top N]
                                 [--radius MM] [--clear MM] [--keepout x0,y0,x1,y1 ...]

Scans F.Cu positions / four rotations of a C_0603 (courtyard 3.05 x 1.55 mm, pad centres 1.55 mm apart,
pads 0.95 x 0.9 mm) around the IC's supply pad. A candidate must (a) not overlap any other footprint's F
courtyard (0.1 mm gap), (b) keep its pads `--clear` (default 0.35 mm) from every other-net pad, F.Cu track
and via, and (c) stay out of any --keepout rectangle. Candidates are ranked by straight-line pad-centre
distance to the IC's supply pad plus half the distance to its return pad. It prints the pose
(courtyard centre, KiCad angle) with pad-1 / pad-2 nets assigned so pad 1 is the supply net; it does not
check isolation domains: the barrier gate and DRC do that on the routed board.
"""
import argparse
import math

import pcbnew

PAD_W, PAD_H, PITCH = 0.95, 0.90, 1.55
CY_W, CY_H = 3.05, 1.55


def mm(v):
    return pcbnew.ToMM(v)


def rect_gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def seg_rect_gap(p, q, r, w):
    """Gap between a segment of width w and an axis-aligned rect (sampled every 0.05 mm)."""
    n = max(1, int(math.dist(p, q) / 0.05))
    best = 1e9
    for i in range(n + 1):
        x, y = p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n
        best = min(best, rect_gap((x, y, x, y), r))
    return best - w / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("ref")
    ap.add_argument("supply_pad")
    ap.add_argument("return_pad")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--radius", type=float, default=6.0)
    ap.add_argument("--clear", type=float, default=0.35)
    ap.add_argument("--keepout", action="append", default=[])
    ap.add_argument("--return-weight", type=float, default=0.5)
    ap.add_argument("--ignore-net", action="append", default=[], help="nets whose F.Cu tracks will be re-routed")
    ap.add_argument("--rules", action="store_true", help="use rules21.clearance per net pair (isolation groups) instead of a flat --clear")
    a = ap.parse_args()
    b = pcbnew.LoadBoard(a.board)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    ic = fps[a.ref]
    pads = {p.GetNumber(): p for p in ic.Pads()}
    sp, rp = pads[a.supply_pad], pads[a.return_pad]
    sxy = (mm(sp.GetPosition().x), mm(sp.GetPosition().y))
    rxy = (mm(rp.GetPosition().x), mm(rp.GetPosition().y))
    snet, rnet = sp.GetNetname(), rp.GetNetname()
    cys, copper = [], []
    for ref, f in fps.items():
        if f.IsFlipped():
            continue
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount():
            bb = cy.BBox()
            cys.append((ref, (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))))
    for f in fps.values():
        for p in f.Pads():
            c = p.GetPosition()
            sz = p.GetBoundingBox()
            if p.IsOnLayer(pcbnew.F_Cu):
                copper.append(("pad", p.GetNetname(), (mm(sz.GetLeft()), mm(sz.GetTop()), mm(sz.GetRight()), mm(sz.GetBottom())), 0))
    tracks, vias = [], []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            c = t.GetPosition()
            vias.append((t.GetNetname(), (mm(c.x), mm(c.y)), mm(t.GetWidth(pcbnew.F_Cu)) / 2))
        elif t.GetLayer() == pcbnew.F_Cu:
            s, e = t.GetStart(), t.GetEnd()
            tracks.append((t.GetNetname(), (mm(s.x), mm(s.y)), (mm(e.x), mm(e.y)), mm(t.GetWidth())))
    keep = [tuple(map(float, k.split(","))) for k in a.keepout]
    if a.rules:
        import os, sys as _s
        _s.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import rules21
        need = lambda n1, n2: max(a.clear, rules21.clearance(n1, n2)) if n1 and n2 else a.clear
    else:
        need = lambda n1, n2: a.clear
    lim = a.radius + 4.0 + (5.0 if a.rules else 0.0)
    win = (sxy[0] - lim, sxy[1] - lim, sxy[0] + lim, sxy[1] + lim)
    hit = lambda x0, y0, x1, y1: x0 < win[2] and win[0] < x1 and y0 < win[3] and win[1] < y1
    copper = [c for c in copper if hit(*c[2])]
    tracks = [t for t in tracks if hit(min(t[1][0], t[2][0]), min(t[1][1], t[2][1]),
                                       max(t[1][0], t[2][0]), max(t[1][1], t[2][1]))]
    vias = [v for v in vias if hit(v[1][0], v[1][1], v[1][0], v[1][1])]
    cys = [c for c in cys if hit(*c[1])]
    out = []
    n = int(a.radius / 0.1)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            cx, cy_ = sxy[0] + i * 0.1, sxy[1] + j * 0.1
            if math.hypot(cx - sxy[0], cy_ - sxy[1]) > a.radius:
                continue
            for ang in (0, 90, 180, 270):
                horiz = ang in (0, 180)
                cyb = (cx - (CY_W if horiz else CY_H) / 2, cy_ - (CY_H if horiz else CY_W) / 2,
                       cx + (CY_W if horiz else CY_H) / 2, cy_ + (CY_H if horiz else CY_W) / 2)
                if any(cyb[0] < k[2] + 0.1 and k[0] - 0.1 < cyb[2] and cyb[1] < k[3] + 0.1 and k[1] - 0.1 < cyb[3]
                       for _, k in cys):
                    continue
                # pad 1 offset by rotation (KiCad, y down): 0 -> left, 90 -> below, 180 -> right, 270 -> above
                off = {0: (-PITCH / 2, 0), 90: (0, PITCH / 2), 180: (PITCH / 2, 0), 270: (0, -PITCH / 2)}[ang]
                p1, p2 = (cx + off[0], cy_ + off[1]), (cx - off[0], cy_ - off[1])
                pb = [(q[0] - (PAD_W if horiz else PAD_H) / 2, q[1] - (PAD_H if horiz else PAD_W) / 2,
                       q[0] + (PAD_W if horiz else PAD_H) / 2, q[1] + (PAD_H if horiz else PAD_W) / 2) for q in (p1, p2)]
                nets = (snet, rnet)
                bad = False
                for k, (box, net) in enumerate(zip(pb, nets)):
                    if any(rect_gap(box, kk) < 1e-9 for kk in keep):
                        bad = True
                        break
                    for kind, pn, r, _ in copper:
                        if pn != net and rect_gap(box, r) < need(net, pn):
                            bad = True
                            break
                    if bad:
                        break
                    for tn, s, e, w in tracks:
                        if tn != net and tn not in a.ignore_net and seg_rect_gap(s, e, box, w) < need(net, tn):
                            bad = True
                            break
                    if bad:
                        break
                    for vn, c, r in vias:
                        if vn != net and rect_gap(box, (c[0], c[1], c[0], c[1])) - r < need(net, vn):
                            bad = True
                            break
                    if bad:
                        break
                if bad:
                    continue
                score = math.dist(p1, sxy) + a.return_weight * math.dist(p2, rxy)
                out.append((score, round(cx, 2), round(cy_, 2), ang, math.dist(p1, sxy), math.dist(p2, rxy)))
    out.sort()
    seen = 0
    print(f"{a.ref}: supply pad {a.supply_pad} {snet} at {sxy[0]:.3f},{sxy[1]:.3f}; return pad {a.return_pad} {rnet} "
          f"at {rxy[0]:.3f},{rxy[1]:.3f}; {len(out)} legal poses")
    last = None
    for s, x, y, ang, d1, d2 in out:
        if last and math.dist(last, (x, y)) < 0.3:
            continue
        last = (x, y)
        print(f"  centre ({x}, {y}) angle {ang}: supply pad {d1:.2f} mm, return pad {d2:.2f} mm")
        seen += 1
        if seen >= a.top:
            break


main()
