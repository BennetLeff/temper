"""External lead spines, one per probe, stage-53 frame.

One shared design: a rectangular rod on the spine axis (between the two leads)
carrying snap saddles at the stations leads.rs lists (pitch <= saddle_pitch). Each saddle is oriented to the two lead
positions at its station, so the same construction holds probe 2's converging half
twist (the pair turns 180 degrees about the rod while closing from the 29 mm gland
pitch to the 15 mm spine pitch) and probe 1's plain convergence.

Symmetry: every saddle is symmetric under the 180-degree rotation about the rod that
swaps the two leads (probe 2) or under the mirror about the rod's centre plane
(probe 1), so both legs see the same resin.

The rod's box end enters the wall insert's socket boss (nylon M3 pin, vertical);
its dock end rests on the dock's seat, held by a nylon M3 screw down through the
rod into a nut trapped in the seat. Leads snap into the saddle slots (opening
narrower than the minimum OD) and a cable tie round each saddle's notched ends
closes them.

Resin: Flame Retardant. Print with the rod vertical (box end down), supports on the
box-end face and under each saddle's lower edge.
"""
import math

import cadquery as cq

from geometry import G, M3_CLEAR, export, lead

S = G["spine"]
OD_MIN, OD_MAX = G["wire"]["od_min"], G["wire"]["od_max"]
R_G = OD_MAX / 2 + 0.15
SNAP = OD_MIN - 0.35  # slot mouth narrower than the thinnest wire
WALL = S["r_resin"] - R_G  # saddle material to the R_RESIN envelope leads.rs models
NOTCH = (3.0, 0.8)  # cable-tie notch (axial length, depth) over each lead wing
I = G["box"]["insert"]


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def oriented_box(centre, ax, u, la, lu, lv):
    """Box of size (la along ax, lu along u, lv along ax x u) centred at centre."""
    d = sum(u[k] * ax[k] for k in range(3))
    u = unit([u[k] - d * ax[k] for k in range(3)])
    v = cross(ax, u)
    pl = cq.Plane(origin=tuple(centre), xDir=tuple(ax), normal=tuple(v))
    b = cq.Solid.makeBox(la, lu, lv, cq.Vector(-la / 2, -lu / 2, -lv / 2))
    return b.moved(cq.Location(pl))


def at_station(l, a0, ax, s):
    """Point and tangent of lead l where its axial coordinate equals s."""
    pts = [p for p, t in zip(l["pts"], l["tags"]) if t in (0, 2)]
    ts = [sum((p[k] - a0[k]) * ax[k] for k in range(3)) for p in pts]
    for i in range(len(pts) - 1):
        if ts[i] <= s <= ts[i + 1] and ts[i + 1] > ts[i]:
            f = (s - ts[i]) / (ts[i + 1] - ts[i])
            p = [pts[i][k] + f * (pts[i + 1][k] - pts[i][k]) for k in range(3)]
            tan = unit([pts[i + 1][k] - pts[i][k] for k in range(3)])
            return p, tan
    return None, None


def build(probe):
    a0, a1 = S[f"probe{probe}_axis"]
    ax = unit([a1[k] - a0[k] for k in range(3)])
    length = math.dist(a0, a1)
    up = [0.0, 0.0, 1.0]
    across = cross(up, ax)  # horizontal, perpendicular to the axis
    tp, tm = lead(probe, "TIP+"), lead(probe, "TIP-")
    # Rod: from the socket bottom (1 mm off the insert face) to the dock end.
    r0 = 1.0
    c = [a0[k] + ax[k] * (r0 + length) / 2 for k in range(3)]
    rod = oriented_box(c, ax, across, length - r0, S["rod_w"], S["rod_h"])
    body = rod
    # Pin holes: box end at the boss centre, dock end 5 mm from the end.
    for s in (I["boss_l"] / 2, length - 5.0):
        pc = [a0[k] + ax[k] * s for k in range(3)]
        pin = cq.Solid.makeCylinder(M3_CLEAR / 2, 2 * S["rod_h"], cq.Vector(pc[0], pc[1], pc[2] - S["rod_h"]), cq.Vector(0, 0, 1))
        body = body.cut(pin)
    # Saddles at the stations leads.rs places (and models as 0.75 wraps).
    n = 0
    for st in S[f"probe{probe}_saddles"]:
        pa, ta = at_station(tp, a0, ax, st)
        pb, tb = at_station(tm, a0, ax, st)
        assert pa is not None and pb is not None, f"no lead points at station {st}"
        mid = [(pa[k] + pb[k]) / 2 for k in range(3)]
        u = unit([pa[k] - pb[k] for k in range(3)])
        span = math.dist(pa, pb)
        saddle = oriented_box(mid, ax, u, S["saddle_l"], span + 2 * (R_G + WALL), 2 * (R_G + WALL))
        body = body.fuse(saddle)
        for p, t, sgn in ((pa, ta, 1), (pb, tb, -1)):
            groove = cq.Solid.makeCylinder(R_G, S["saddle_l"] + 4, cq.Vector(*[p[k] - t[k] * (S["saddle_l"] / 2 + 2) for k in range(3)]), cq.Vector(*t))
            mouth_c = [p[k] + sgn * u[k] * (R_G + WALL) / 2 for k in range(3)]
            mouth = oriented_box(mouth_c, ax, u, S["saddle_l"] + 4, R_G + WALL + 0.2, SNAP)
            body = body.cut(groove).cut(mouth)
        # Tie notches on the two faces normal to v, over each lead's wing only (the
        # rod in the middle keeps its full section); 1.7 mm of resin stays over the groove.
        v = cross(ax, u)
        wing = R_G + WALL + 1.0
        for p in (pa, pb):
            sgn = 1 if p is pa else -1
            for sv in (1, -1):
                nc = [p[k] + sgn * u[k] * wing / 2 + sv * v[k] * (R_G + WALL) for k in range(3)]
                body = body.cut(oriented_box(nc, ax, u, NOTCH[0], wing, 2 * NOTCH[1]))
        n += 1
    print(f"spine probe {probe}: rod {length - r0:.1f} mm, {n} saddles")
    return cq.Workplane("XY").add(body.clean())


if __name__ == "__main__":
    export(build(2), "spine-coil", "Flame Retardant", "rod vertical, box end down; supports on the box-end face and saddle undersides")
    export(build(1), "spine-bank", "Flame Retardant", "rod vertical, box end down; supports on the box-end face and saddle undersides")
