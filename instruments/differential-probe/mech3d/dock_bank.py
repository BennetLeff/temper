"""Dock for probe 1 (bank): TIP+ ring on J5, TIP- soldered into C22's free hole,
stage-53 frame.

Built from the envelope boxes leads.rs gates (parts_s53 "dock-bank"):
  posts, cross member, arm  on nylon M3 standoffs in H10 and H8 ("M3 NYLON ONLY"),
                the arm 3.5 mm over the bank-cap tops, a north foot resting on
                the board;
  spine-1 seat  carries the spine rod's dock end (nylon M3 screw, nut trapped);
  guide plate   half-depth grooves along both plan S-bends, open upward, two ties
                per lead through the plate and the arm;
  riser bridge  slots, open outward, for the two risers where they turn down;
  fork legs     two per riser, each pair joined by a riser clip that the riser
                snaps into (mouth narrower than the wire);
  TIP- clamp    between the east legs: the lead lies in a channel open to the
                east and a cable tie round the legs at the clamp band presses it
                in, so the solder joint in C22's hole carries no tension.
Mirror-symmetric about x = 174.25 except the two posts and the clamp (leads.rs
gates their stray-C asymmetry).

Resin: Flame Retardant. Print with the arm vertical (cross member down), so the
fork legs print along their length; supports on the cross member and the posts.
"""
import math

import cadquery as cq

from geometry import G, M3_CLEAR, M3_NUT_AF, M3_NUT_T, R_G, TIE_SLOT, box, export, gbox, hole_xy, lead, part_boxes, path_frame, tagged, tube

B = part_boxes("dock-bank")
SP = G["spine"]
OD_MIN, OD = G["wire"]["od_min"], G["wire"]["od_nom"]
X_AX, Y_END, Z_SP = SP["probe1_axis"][1]
H_SO = G["bench"]["standoff_h"]
R_GRIP = OD_MIN / 2 - 0.1  # clamp channel: squeezes the silicone 0.1..0.24 mm
TIE_FRACTIONS = (0.3, 0.75)  # along each plan S-bend (print detail)
TIE_BAND = 2.6  # tie notch height round the clamp band
TIE_NOTCH = 0.4  # and depth
W_OPEN = R_G - 0.05  # open-slot half-width (a hair under the groove: OCCT fails on tangency)
SNAP = OD_MIN - 0.35  # snap mouth, narrower than the thinnest wire


def check(s, what):
    assert s.isValid(), f"invalid solid after {what}"
    return s


def build():
    body = None
    for b in B.values():
        s = gbox(b).val()
        body = s if body is None else body.fuse(s)
    body = body.clean()  # (the groove cuts fail on the unmerged box faces)
    cuts = []  # one boolean with every tool: OCCT fails on some sequential cuts here
    gp, rb = B["guide plate"], B["riser bridge"]
    for name, out in (("TIP+", -1), ("TIP-", 1)):
        l = lead(1, name)
        pts = tagged(l, (1,))
        # Guide plate: half-depth groove along the plan S-bend and the start of the
        # turn-down arc, opened from above where the arc dips below the plate top.
        upper = [p for p in pts if p[2] >= rb["hi"][2] + 1]  # (the riser cut below covers the rest)
        # (axis lifted 0.02 mm off the plate-top plane: OCCT fails on the coincidence)
        cuts.append(tube([[p[0], p[1], p[2] + 0.02] for p in upper], R_G))
        dip = [p for p in upper if p[2] < gp["hi"][2] - 0.01 and p[1] >= gp["lo"][1] - R_G]
        xr = dip[-1][0]
        cuts.append(box([xr - W_OPEN, gp["lo"][1] - 1, min(p[2] for p in dip)], [xr + W_OPEN, max(p[1] for p in dip), gp["hi"][2] + 1]).val())
        # Riser bridge: slot open outward (away from the axis); the riser is
        # within 0.6 mm of its plane here.
        yr = pts[-1][1]
        xo = rb["lo"][0] - 1 if out < 0 else rb["hi"][0] + 1
        cuts.append(box([xr, yr - W_OPEN, rb["lo"][2] - 1], [xo, yr + W_OPEN + 0.6, rb["hi"][2] + 1]).val())
        cuts.append(tube([p for p in pts if rb["lo"][2] - 3 <= p[2] <= rb["hi"][2] + 3], R_G))
        # Riser clip band: a snap groove, mouth narrower than the wire. TIP+ is
        # vertical here and the clip face is 1 mm past its axis; TIP- is mid-jog,
        # so its mouth is cut to the clip's east face.
        clip = B["riser clip W" if out < 0 else "riser clip E"]
        band = [p for p in pts if clip["lo"][2] - 3 <= p[2] <= clip["hi"][2] + 3]
        cuts.append(tube(band, R_G))
        if out > 0:
            yc = band[0][1]
            cuts.append(box([min(p[0] for p in band), yc - SNAP / 2, clip["lo"][2] - 1], [clip["hi"][0] + 1, yc + SNAP / 2, clip["hi"][2] + 1]).val())
        # Ties through the guide plate and the arm, a pair straddling the lead.
        plan = [p for p in pts if p[2] >= Z_SP - 0.01]
        sl, sw = TIE_SLOT
        off = OD / 2 + G["box"]["bridge"]["tie_gap"] + sw / 2
        for f in TIE_FRACTIONS:
            p, t = path_frame(plan, f)
            ang = math.degrees(math.atan2(t[1], t[0]))
            for sgn in (1, -1):
                c = cq.Vector(p[0] - sgn * t[1] * off, p[1] + sgn * t[0] * off, (B["arm"]["lo"][2] + gp["hi"][2]) / 2)
                slot = cq.Solid.makeBox(sl, sw, 30, cq.Vector(-sl / 2, -sw / 2, -15))
                cuts.append(slot.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), ang).translate(c))
    # TIP- clamp: grip channel open to the east, tie notch round the legs.
    cl = B["TIP- clamp"]
    pts = tagged(lead(1, "TIP-"), (1,))
    band = [p for p in pts if cl["lo"][2] - 2 <= p[2] <= cl["hi"][2] + 2]
    x_c = max(p[0] for p in band)
    y_c = band[0][1]
    z0, z1 = cl["lo"][2] - 1, cl["hi"][2] + 1
    cuts.append(cq.Solid.makeCylinder(R_GRIP, z1 - z0, cq.Vector(x_c, y_c, z0), cq.Vector(0, 0, 1)))
    cuts.append(box([x_c, y_c - SNAP / 2, z0], [cl["hi"][0] + 1, y_c + SNAP / 2, z1]).val())
    zt = (cl["lo"][2] + cl["hi"][2]) / 2
    legs = [B[k] for k in ("fork E1", "fork E2")]
    y0, y1 = min(b["lo"][1] for b in legs), max(b["hi"][1] for b in legs)
    x0, x1 = cl["lo"][0], cl["hi"][0]
    ring = box([x0 - 1, y0 - 1, zt - TIE_BAND / 2], [x1 + 1, y1 + 1, zt + TIE_BAND / 2]).val()
    core = box([x0 + TIE_NOTCH, y0 + TIE_NOTCH, zt - TIE_BAND], [x1 - TIE_NOTCH, y1 - TIE_NOTCH, zt + TIE_BAND]).val()
    cuts.append(ring.cut(core))
    # Spine pin: nylon M3 down through the rod and the seat, nut trapped below,
    # loaded from the seat's south face.
    seat = B["spine-1 seat"]
    py = Y_END + 5.0
    st = seat["hi"][2]
    cuts.append(cq.Solid.makeCylinder(M3_CLEAR / 2, 14, cq.Vector(X_AX, py, st - 13), cq.Vector(0, 0, 1)))
    zn = st - 6.0
    nut = cq.Workplane("XY").workplane(offset=zn).center(X_AX, py).polygon(6, M3_NUT_AF / math.cos(math.pi / 6)).extrude(M3_NUT_T).val()
    trap = box([X_AX - M3_NUT_AF / 2, py, zn], [X_AX + M3_NUT_AF / 2, seat["hi"][1] + 1, zn + M3_NUT_T]).val()
    cuts += [nut, trap]
    # Post holes: nylon M3 screw from the cross-member top into the standoff.
    top = B["cross member"]["hi"][2]
    for h in ("H10", "H8"):
        x, y = hole_xy(h)
        cuts.append(cq.Solid.makeCylinder(M3_CLEAR / 2, top - H_SO + 2, cq.Vector(x, y, H_SO - 1), cq.Vector(0, 0, 1)))
    body = check(body.cut(*cuts), "the cuts")
    return cq.Workplane("XY").add(body.clean())


if __name__ == "__main__":
    export(build(), "dock-bank", "Flame Retardant", "arm vertical, cross member down; supports on the cross member and posts")
