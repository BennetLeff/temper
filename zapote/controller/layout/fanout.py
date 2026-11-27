"""Plane fan-out: a via beside every SMD pad on selv_gnd (In1 plane) or v3v3 (In2 plane).

Called by layout/build_board.py after placement. Each SMD pad on a plane net gets a short stub
(no wider than the pad, <= 0.4 mm) to a 0.6/0.3 mm via at the nearest legal spot: 0.2 mm from
every other-net pad, track and via on F.Cu and B.Cu, 0.5 mm drill-to-drill from every hole,
outside rule areas and >= 0.5 mm from the board edge. Plane nets are then complete through the
planes, so the autorouter (layout/route.py) routes signal nets only. Through-hole pads reach the
planes directly (thermal relief). Decoupling capacitors therefore return through one via each,
next to the pad, into the adjacent plane.
"""
from __future__ import annotations

import math

import pcbnew

CLR = 0.2          # copper clearance (Default net class)
VIA_D, VIA_DRILL = 0.6, 0.3
HOLE_GAP = 0.5     # board rule min_hole_to_hole
EDGE = 0.55        # board rule min_copper_edge_clearance 0.5 + margin
PLANE_NETS = ("selv_gnd", "v3v3")


def _mm(v):
    return pcbnew.ToMM(v)


def _seg_rect_dist(a, b, r):
    """Distance between segment a-b and axis-aligned rect r (x0, y0, x1, y1); sampled."""
    best = 1e9
    n = max(2, int(math.dist(a, b) / 0.05) + 1)
    for k in range(n + 1):
        x = a[0] + (b[0] - a[0]) * k / n
        y = a[1] + (b[1] - a[1]) * k / n
        dx = max(r[0] - x, 0, x - r[2])
        dy = max(r[1] - y, 0, y - r[3])
        best = min(best, math.hypot(dx, dy))
    return best


def _seg_seg_dist(a, b, c, d):
    def pt(p, s0, s1):
        dx, dy = s1[0] - s0[0], s1[1] - s0[1]
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((p[0] - s0[0]) * dx + (p[1] - s0[1]) * dy) / L))
        return math.hypot(p[0] - s0[0] - t * dx, p[1] - s0[1] - t * dy)
    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def run(board, forbid_rects, edge_rect, stitch=None):
    """forbid_rects: KiCad-frame mm rects (rule areas: antenna, hole keep-outs) vias must avoid.
    stitch: optional (rects, pitch, avoid_rects) in KiCad mm: after the pad fan-out, a selv_gnd plane
    via at every legal node of a pitch grid inside the rects (outside avoid_rects) that has no
    selv_gnd via within pitch / 2 already (C34: return transitions beside the RTD analog vias)."""
    obstacles = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}    # (kind, geom, net)
    drills = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            r = (_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom()))
            for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                if p.IsOnLayer(lay):
                    obstacles[lay].append(("rect", r, p.GetNetname()))
            if p.GetDrillSize().x > 0:
                drills.append(((_mm(p.GetPosition().x), _mm(p.GetPosition().y)), _mm(p.GetDrillSize().x) / 2))
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            c = (_mm(t.GetPosition().x), _mm(t.GetPosition().y))
            for lay in obstacles:
                obstacles[lay].append(("circle", (c, _mm(t.GetWidth(pcbnew.F_Cu)) / 2), t.GetNetname()))
            drills.append((c, _mm(t.GetDrillValue()) / 2))
        else:
            seg = ((_mm(t.GetStart().x), _mm(t.GetStart().y)), (_mm(t.GetEnd().x), _mm(t.GetEnd().y)), _mm(t.GetWidth()) / 2)
            if t.GetLayer() in obstacles:
                obstacles[t.GetLayer()].append(("seg", seg, t.GetNetname()))
    # copper pours on F.Cu (buck SW/VIN) are obstacles for other nets too
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetLayer() not in obstacles:
            continue
        bb = z.GetBoundingBox()
        obstacles[z.GetLayer()].append(("rect", (_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom())),
                                        z.GetNetname()))

    def clear_circle(c, rad, net, layers):
        for lay in layers:
            for kind, g, n in obstacles[lay]:
                if n == net:
                    continue
                if kind == "rect":
                    dx = max(g[0] - c[0], 0, c[0] - g[2])
                    dy = max(g[1] - c[1], 0, c[1] - g[3])
                    d = math.hypot(dx, dy) - rad
                elif kind == "circle":
                    d = math.dist(c, g[0]) - g[1] - rad
                else:
                    d = _seg_seg_dist(c, c, g[0], g[1]) - g[2] - rad
                if d < CLR - 1e-6:
                    return False
        return True

    def clear_seg(a, b, half, net):
        for kind, g, n in obstacles[pcbnew.F_Cu]:
            if n == net:
                continue
            if kind == "rect":
                d = _seg_rect_dist(a, b, g) - half
            elif kind == "circle":
                d = _seg_seg_dist(a, b, g[0], g[0]) - g[1] - half
            else:
                d = _seg_seg_dist(a, b, g[0], g[1]) - g[2] - half
            if d < CLR - 1e-6:
                return False
        return True

    def legal_via(c, net):
        x0, y0, x1, y1 = edge_rect
        if not (x0 + EDGE + VIA_D / 2 <= c[0] <= x1 - EDGE - VIA_D / 2 and y0 + EDGE + VIA_D / 2 <= c[1] <= y1 - EDGE - VIA_D / 2):
            return False
        for r in forbid_rects:
            if r[0] - VIA_D / 2 <= c[0] <= r[2] + VIA_D / 2 and r[1] - VIA_D / 2 <= c[1] <= r[3] + VIA_D / 2:
                return False
        for dc, dr in drills:
            if math.dist(c, dc) - dr - VIA_DRILL / 2 < HOLE_GAP:
                return False
        return clear_circle(c, VIA_D / 2, net, (pcbnew.F_Cu, pcbnew.B_Cu))

    # escape lanes: every signal pin of a multi-pin package keeps a pad-wide lane 1.6 mm straight out
    # from its pad, so a neighbouring plane pin's via cannot box it in (tried first; dropped only
    # if a pad has no legal spot otherwise)
    lanes = []
    for fp in board.GetFootprints():
        fpads = list(fp.Pads())
        if len(fpads) < 5:
            continue
        fc = (_mm(fp.GetPosition().x), _mm(fp.GetPosition().y))
        for q in fpads:
            if q.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or q.GetNetname() in PLANE_NETS or not q.GetNetname():
                continue
            bb = q.GetBoundingBox()
            r = [_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom())]
            qc = (_mm(q.GetPosition().x), _mm(q.GetPosition().y))
            if r[2] - r[0] >= r[3] - r[1]:          # long in x: lane along x, outward side
                if qc[0] >= fc[0]:
                    r[2] += 1.6
                else:
                    r[0] -= 1.6
            else:
                if qc[1] >= fc[1]:
                    r[3] += 1.6
                else:
                    r[1] -= 1.6
            lanes.append(("rect", tuple(r), q.GetNetname()))

    done, missed = 0, []
    pads = [(fp, p) for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() in PLANE_NETS and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and p.IsOnLayer(pcbnew.F_Cu)]
    # smallest pads first: they have the fewest legal spots
    pads.sort(key=lambda fp_p: min(fp_p[1].GetSize(pcbnew.F_Cu).x, fp_p[1].GetSize(pcbnew.F_Cu).y))
    for fp, p in pads:
        net = p.GetNetname()
        if fp.GetFPID().GetLibItemName().wx_str().startswith("ESP32-S3-WROOM") and p.GetNumber() == "41":
            continue                     # exposed pad: its own thermal vias reach In1
        c0 = (_mm(p.GetPosition().x), _mm(p.GetPosition().y))
        bb = p.GetBoundingBox()
        pr = (_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom()))
        width = min(0.4, min(pr[2] - pr[0], pr[3] - pr[1]))
        def search():
            found = None
            for reach in [0.45 + 0.1 * k for k in range(0, 30)]:
                for k in range(16):
                    ang = 2 * math.pi * k / 16
                    # start the ray at the pad edge in that direction
                    ex = (pr[2] - pr[0]) / 2 * abs(math.cos(ang))
                    ey = (pr[3] - pr[1]) / 2 * abs(math.sin(ang))
                    c = (c0[0] + (ex + reach) * math.cos(ang), c0[1] + (ey + reach) * math.sin(ang))
                    if not legal_via(c, net) or not clear_seg(c0, c, width / 2, net):
                        continue
                    d = math.dist(c0, c)
                    if found is None or d < found[0]:
                        found = (d, c)
                if found is not None:
                    return found
            return None
        n_before = len(obstacles[pcbnew.F_Cu])
        obstacles[pcbnew.F_Cu].extend(lanes)
        best = search()
        del obstacles[pcbnew.F_Cu][n_before:]
        if best is None:
            best = search()
        if best is None:
            missed.append(f"{fp.GetReference()}.{p.GetNumber()}")
            continue
        c = best[1]
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(p.GetPosition())
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(c[0]), pcbnew.FromMM(c[1])))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(p.GetNet())
        t.SetLocked(True)
        board.Add(t)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(c[0]), pcbnew.FromMM(c[1])))
        v.SetWidth(pcbnew.FromMM(VIA_D))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetNet(p.GetNet())
        v.SetLocked(True)
        board.Add(v)
        obstacles[pcbnew.F_Cu].append(("seg", (c0, c, width / 2), net))
        for lay in obstacles:
            obstacles[lay].append(("circle", (c, VIA_D / 2), net))
        drills.append((c, VIA_DRILL / 2))
        done += 1
    n_stitch = 0
    stitches = stitch if isinstance(stitch, list) else ([stitch] if stitch else [])   # C53: several grids
    if stitches:
        gnd_vias = [g[0] for g in (o[1] for o in obstacles[pcbnew.B_Cu] if o[0] == "circle" and o[2] == "selv_gnd")]
        obstacles[pcbnew.F_Cu].extend(lanes)
    for rects, pitch, avoid in stitches:
        for x0, y0, x1, y1 in rects:
            nx_, ny_ = int((x1 - x0) / pitch) + 1, int((y1 - y0) / pitch) + 1
            for i in range(nx_):
                for j in range(ny_):
                    c = (x0 + i * pitch, y0 + j * pitch)
                    if any(a[0] - VIA_D / 2 - CLR <= c[0] <= a[2] + VIA_D / 2 + CLR and
                           a[1] - VIA_D / 2 - CLR <= c[1] <= a[3] + VIA_D / 2 + CLR for a in avoid):
                        continue
                    if any(math.dist(c, g) < pitch / 2 for g in gnd_vias) or not legal_via(c, "selv_gnd"):
                        continue
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(c[0]), pcbnew.FromMM(c[1])))
                    v.SetWidth(pcbnew.FromMM(VIA_D))
                    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
                    v.SetNet(board.FindNet("selv_gnd"))
                    v.SetLocked(True)
                    board.Add(v)
                    for lay in obstacles:
                        obstacles[lay].append(("circle", (c, VIA_D / 2), "selv_gnd"))
                    drills.append((c, VIA_DRILL / 2))
                    gnd_vias.append(c)
                    n_stitch += 1
    return done + n_stitch, missed
