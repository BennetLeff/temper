"""Printed lead bridge (replaces the FR4 lead bridge), box frame.

Same function as the FR4 part: carries both internal leads from the tip-end
wall insert to the board, three cable ties per lead, clamped to the board top by
the H3/H4 nylon screws. Its insert end rests on the insert's inner ledge. The
lead lies in a groove GROOVE deep, so it sits 1.5 mm above the board-top plane
(leads.rs gates the 5.5 mm loop height). Mirror-symmetric about the inter-leg
axis (y = 35).

Resin: Flame Retardant (it sits 6 mm from the W_HV joints). Print flat, groove
side up, supports on the underside only, so the groove and tie slots stay clean.
"""
import math

import cadquery as cq

from geometry import G, M3_CLEAR, export

B = G["box"]["bridge"]
T, GROOVE, Z0 = B["t"], B["groove"], B["board_top_z"]
OD_MAX = G["wire"]["od_max"]
R_G = OD_MAX / 2 + 0.15


def build():
    body = cq.Workplane("XY").workplane(offset=Z0).polyline([tuple(p) for p in B["outline"]]).close().extrude(T)
    for x, y in B["h34"]:
        body = body.cut(cq.Workplane("XY").workplane(offset=Z0 - 1).center(x, y).circle(M3_CLEAR / 2).extrude(T + 2))
    floor = Z0 + T - GROOVE
    for path in G["box"]["internal_leads"]:
        pts2 = [(p[0], p[1]) for p in path]
        slot = cq.Workplane("XY").workplane(offset=floor).polyline(pts2).offset2D(R_G).extrude(GROOVE + 1)
        body = body.cut(slot)
    # Tie-slot pairs straddling each lead, square to the lead.
    sl, sw = B["tie_slot"]
    for path in G["box"]["internal_leads"]:
        pts2 = [(p[0], p[1]) for p in path]
        for tx, ty in B["tie_points"]:
            seg = next(((a, b) for a, b in zip(pts2, pts2[1:]) if a[0] <= tx <= b[0]), None)
            if seg is None:
                continue
            (ax, ay), (bx, by) = seg
            if abs((ay + (tx - ax) / (bx - ax) * (by - ay)) - ty) > 0.01:
                continue  # tie point belongs to the other lead
            ang = math.atan2(by - ay, bx - ax)
            off = G["wire"]["od_nom"] / 2 + B["tie_gap"] + sw / 2
            for sgn in (-1, 1):
                cx, cy = tx - sgn * off * math.sin(ang), ty + sgn * off * math.cos(ang)
                cut = cq.Workplane("XY").workplane(offset=Z0 - 1).center(cx, cy).rect(sl, sw).extrude(T + 2)
                cut = cut.rotate((cx, cy, 0), (cx, cy, 1), math.degrees(ang))
                body = body.cut(cut)
    return body


if __name__ == "__main__":
    export(build(), "lead-bridge", "Flame Retardant", "flat, groove side up; supports on the underside")
