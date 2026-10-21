"""Dock for probe 2 (coil): J5 (TIP+) and J2 (TIP-), stage-53 frame.

Built from the envelope boxes leads.rs gates (parts_s53 "dock-coil"):
  cradle block  between the two lead planes; the S-bends lie in half-depth grooves
                on its two faces, tied through slots that cross the block, so one
                tie holds both leads at each station (mirror-symmetric);
  spine-2 seat  carries the spine rod's dock end (nylon M3 screw, nut trapped);
  guard web     channels that capture both ring sleeves, so neither ring can turn
                towards the other stud or the coil Litz;
  guard plate   over the two stud stacks (no tool can reach a screw head with the
                dock fitted);
  posts / arms  on nylon M3 standoffs in H6 and H7 (both "M3 NYLON ONLY"),
                with mirror stubs so the resin near each lead is the same.

Resin: Flame Retardant. Print upside down (seat face on the platform side
tilted 20 degrees), supports on the post ends and the seat top only; no support
inside the grooves or the sleeve channels.
"""
import math

import cadquery as cq

from geometry import G, M3_CLEAR, M3_NUT_AF, M3_NUT_T, R_G, TIE_GAP, TIE_SLOT, box, export, gbox, hole_xy, lead, part_boxes, path_frame, tagged, tube

B = part_boxes("dock-coil")
SP = G["spine"]
RING = G["stage53"]["ring"]
OD = G["wire"]["od_nom"]
X_DOCK, Y_AX, Z_SP = SP["probe2_axis"][1]
R_RES = SP["r_resin"]
H_SO = G["bench"]["standoff_h"]
TIE_FRACTIONS = (0.2, 0.5, 0.8)  # stations along each S-bend (print detail)


def build():
    body = None
    for b in B.values():
        s = gbox(b).val()
        body = s if body is None else body.fuse(s)
    cb = B["cradle block"]
    y_lo, y_hi = cb["lo"][1], cb["hi"][1]
    pts = tagged(lead(2, "TIP+"), (1,))
    total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    f_sleeve = 1 - RING["sleeve_on_wire"] / total
    p_sleeve, _ = path_frame(pts, f_sleeve)
    # Lightening pocket, open at the bottom (drains in the printer), leaving
    # R_RESIN of resin behind each face (the shell leads.rs models), the seat solid
    # and full walls where the deeper sleeve groove runs.
    pocket = box([cb["lo"][0] + 3, y_lo + R_RES, cb["lo"][2] - 1], [p_sleeve[0] - 3, y_hi - R_RES, B["spine-2 seat"]["lo"][2] - 6])
    body = body.cut(pocket.val())
    # Half-depth lead grooves on the two faces (lead axis on the face plane); the
    # last sleeve_on_wire mm carry the ring's heat-shrink, so that groove is wider.
    rs = RING["sleeve_d"] / 2 + 0.5
    for name in ("TIP+", "TIP-"):
        lp = tagged(lead(2, name), (1,))
        body = body.cut(tube(lp, R_G))
        tail = [p for p in lp if math.dist(p, lp[-1]) <= RING["sleeve_on_wire"] + 1.0]
        body = body.cut(tube(tail, rs))
    # Tie slots crossing the block in y, a pair straddling the lead at each station.
    sl, sw = TIE_SLOT
    off = OD / 2 + TIE_GAP + sw / 2
    for f in TIE_FRACTIONS:
        p, t = path_frame(pts, f)
        n = [-t[2], 0.0, t[0]]  # in-plane normal (xz)
        ang = math.degrees(math.atan2(t[2], t[0]))
        for sgn in (1, -1):
            c = cq.Vector(p[0] + sgn * n[0] * off, (y_lo + y_hi) / 2, p[2] + sgn * n[2] * off)
            slot = cq.Solid.makeBox(sl, y_hi - y_lo + 2, sw, cq.Vector(-sl / 2, -(y_hi - y_lo + 2) / 2, -sw / 2))
            slot = slot.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), -ang).translate(c)
            body = body.cut(slot)
    # Ring sleeve channels through the guard web, open below, 0.5 mm all round.
    gw = B["guard web"]
    for name in ("TIP+", "TIP-"):
        y = lead(2, name)["pts"][-1][1]
        z = RING["z_probe2"]
        ch = cq.Solid.makeCylinder(rs, gw["hi"][0] - gw["lo"][0] + 2, cq.Vector(gw["lo"][0] - 1, y, z), cq.Vector(1, 0, 0))
        below = box([gw["lo"][0] - 1, y - rs, gw["lo"][2] - 1], [gw["hi"][0] + 1, y + rs, z]).val()
        # The ring tongue (RING w wide) also passes under the web's stud end.
        tongue = box([gw["lo"][0] - 1, y - RING["w"] / 2 - 0.5, gw["lo"][2] - 1], [gw["hi"][0] + 1, y + RING["w"] / 2 + 0.5, z - RING["barrel_dz"] + 1.0]).val()
        body = body.cut(ch).cut(below).cut(tongue)
    # Spine pin: nylon M3 down through the rod and the seat, nut trapped below,
    # loaded from the block's west end.
    px = X_DOCK - 5.0
    seat_top = B["spine-2 seat"]["hi"][2]
    body = body.cut(cq.Solid.makeCylinder(M3_CLEAR / 2, 14, cq.Vector(px, Y_AX, seat_top - 13), cq.Vector(0, 0, 1)))
    zn = seat_top - 8.0
    nut = cq.Workplane("XY").workplane(offset=zn).center(px, Y_AX).polygon(6, M3_NUT_AF / math.cos(math.pi / 6)).extrude(M3_NUT_T).val()
    trap = box([cb["lo"][0] - 1, Y_AX - M3_NUT_AF / 2, zn], [px, Y_AX + M3_NUT_AF / 2, zn + M3_NUT_T]).val()
    body = body.cut(nut).cut(trap)
    # Post holes: nylon M3 screw from the arm top into the standoff.
    for h, top in (("H6", B["H6 arm"]["hi"][2]), ("H7", B["H7 post"]["hi"][2])):
        x, y = hole_xy(h)
        body = body.cut(cq.Solid.makeCylinder(M3_CLEAR / 2, top - H_SO + 2, cq.Vector(x, y, H_SO - 1), cq.Vector(0, 0, 1)))
    return cq.Workplane("XY").add(body.clean())


if __name__ == "__main__":
    export(build(), "dock-coil", "Flame Retardant", "upside down, seat side tilted 20 deg; supports on post ends and the seat top")
