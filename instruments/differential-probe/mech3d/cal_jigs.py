"""Calibration jigs: replicas of stage 53's probe-attachment region, stage-53 frame.

Each jig is a plate whose top face is stage 53's board-top plane, with the dock
standoff holes (H6, H7, H8, H10) and the three contacts where stage 53 has them:
J5 and J2 (M4 x 5 brass hex standoffs F-F, 7 mm across flats, standing in for the
7 mm REDCUBE studs, fixed by an M4 screw from below) and C22's free hole (a brass
turret, the probe-1 TIP- end soldered to it). Both probes dock on a jig exactly as
on stage 53, so the lead routing, and with it each tip's stray capacitance, is the
one calibrated.

  cal-cm-jig  all three contacts bused underneath to one CM terminal: drive the
              common-mode source between it and earth, trim CMRR (CT/RV) for
              zero output.
  cal-dc-jig  J5 (both TIP+) on the HI terminal; J2 and the C22 turret on LO:
              DC ratio and gain trim.

Underside wiring runs in channels to the terminal posts (M4 screws with ring
lugs); on the DC jig the HI and LO runs stay 15 mm apart. The plate stands on
four nylon M3 standoffs at the corners, the board-top plane 50 mm above the
bench as in the bench layout (leads.rs).

Resin: Tough 2000 (bench fixture, low-energy calibration sources only). Print
on edge, supports on the long bottom edge.
"""
import cadquery as cq

from geometry import G, M3_CLEAR, M3_NUT_AF, M3_NUT_T, box, export, hole_xy

J = G["jig"]
S53 = G["stage53"]
LO_, HI_ = J["region"]["lo"], J["region"]["hi"]
T = J["t"]
M4_CLEAR = 4.4
M4_HEAD = (7.5, 3.0)  # counterbore under each contact: pan head diameter, depth
TURRET_D = 2.4  # turret shank hole
CH_W, CH_D = 3.0, 2.0  # wiring channel underneath
CORNER = 6.0  # corner standoff hole inset


def contacts():
    return {"J5": S53["J5"][:2], "J2": S53["J2"][:2], "C22": S53["C22_hole"][:2]}


def channel(a, b):
    """Underside channel between two plan points (L-shaped, x then y)."""
    (x0, y0), (x1, y1) = a, b
    z0 = LO_[2] - 1
    s = box([min(x0, x1) - CH_W / 2, y0 - CH_W / 2, z0], [max(x0, x1) + CH_W / 2, y0 + CH_W / 2, LO_[2] + CH_D]).val()
    return s.fuse(box([x1 - CH_W / 2, min(y0, y1) - CH_W / 2, z0], [x1 + CH_W / 2, max(y0, y1) + CH_W / 2, LO_[2] + CH_D]).val())


def label(body, text, x, y, size=4.0):
    t = cq.Workplane("XY").workplane(offset=HI_[2]).center(x, y).text(text, size, -0.5, kind="bold", halign="center", valign="center")
    return body.cut(t.val())


def build(kind):
    body = box(LO_, HI_).val()
    # Dock standoff holes, nylon nut pocket underneath.
    for h in J["holes"]:
        x, y = hole_xy(h)
        body = body.cut(cq.Solid.makeCylinder(M3_CLEAR / 2, T + 2, cq.Vector(x, y, LO_[2] - 1), cq.Vector(0, 0, 1)))
        nut = cq.Workplane("XY").workplane(offset=LO_[2]).center(x, y).polygon(6, M3_NUT_AF / 0.8660254).extrude(M3_NUT_T).val()
        body = body.cut(nut)
    # Bench standoffs at the corners.
    for x in (LO_[0] + CORNER, HI_[0] - CORNER):
        for y in (LO_[1] + CORNER, HI_[1] - CORNER):
            body = body.cut(cq.Solid.makeCylinder(M3_CLEAR / 2, T + 2, cq.Vector(x, y, LO_[2] - 1), cq.Vector(0, 0, 1)))
    c = contacts()
    for k in ("J5", "J2"):
        x, y = c[k]
        body = body.cut(cq.Solid.makeCylinder(M4_CLEAR / 2, T + 2, cq.Vector(x, y, LO_[2] - 1), cq.Vector(0, 0, 1)))
        body = body.cut(cq.Solid.makeCylinder(M4_HEAD[0] / 2, M4_HEAD[1], cq.Vector(x, y, LO_[2]), cq.Vector(0, 0, 1)))
    x, y = c["C22"]
    body = body.cut(cq.Solid.makeCylinder(TURRET_D / 2, T + 2, cq.Vector(x, y, LO_[2] - 1), cq.Vector(0, 0, 1)))
    body = body.cut(cq.Solid.makeCylinder(3.0, M4_HEAD[1], cq.Vector(x, y, LO_[2]), cq.Vector(0, 0, 1)))
    # Terminals (M4 screw + ring lug underneath) on the west edge, clear of both docks.
    tx = LO_[0] + 8.0
    if kind == "cm":
        terms = {"CM": (tx, c["J5"][1] - 7.5)}
        runs = [("J5", "CM"), ("J2", "CM"), ("C22", "CM")]
    else:
        terms = {"HI": (tx, -60.0), "LO": (tx, -112.0)}
        runs = [("J5", "HI"), ("J2", "LO"), ("C22", "LO")]
    for name, (x, y) in terms.items():
        body = body.cut(cq.Solid.makeCylinder(M4_CLEAR / 2, T + 2, cq.Vector(x, y, LO_[2] - 1), cq.Vector(0, 0, 1)))
        body = label(body, name, x + 9, y)
    for a, b in runs:
        pa = c[a]
        pb = terms[b]
        body = body.cut(channel(pb, pa))
    for k, (x, y) in c.items():
        body = label(body, {"J5": "J5", "J2": "J2", "C22": "C22"}[k], x + (10 if k != "C22" else -7), y + 6, 3.0)
    body = label(body, kind.upper(), (LO_[0] + HI_[0]) / 2, HI_[1] - 8, 6.0)
    return cq.Workplane("XY").add(body.clean())


if __name__ == "__main__":
    export(build("cm"), "cal-cm-jig", "Tough 2000", "on edge, supports on the long bottom edge")
    export(build("dc"), "cal-dc-jig", "Tough 2000", "on edge, supports on the long bottom edge")
