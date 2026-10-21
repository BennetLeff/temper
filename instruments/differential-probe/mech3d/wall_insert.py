"""Reference tip-end wall insert, box frame (for the owner to merge into the enclosure).

Replaces the FR4 tip plate in the Hammond 1455N2201 reference: the same outline and
screw pattern, two PG7 gland bosses (Essentra CG-PG7-1-BK with CGLN-PG7-BK locknuts
inside), the spine socket boss on the outside centre, and the ledge on the inside
that carries the lead bridge's insert end. Mirror-symmetric about the inter-leg axis
except the +/- legends.

No insulation credit: the lead's own rated insulation passes through the gland, and
the 20 mm setback to the extrusion is air distance (leads.rs). The insert only fixes
where the glands, and so the leads, are.

Resin: Flame Retardant, 3.0 mm wall (UL 94 V-0 at 3 mm). Print standing on its long
bottom edge, tilted 15 degrees, supports on the edge only, so neither gland seat
carries support marks.
"""
import cadquery as cq

from geometry import G, M3_CLEAR, FIT, export

I = G["box"]["insert"]
X_IN, T = I["inner_face_x"], I["t"]
X_OUT = X_IN - T
CY, CZ = I["centre_y"], I["centre_z"]  # right-handed centre (Y = -35)
BOSS_D = I["seat_d"] + 2.0  # gland boss outer diameter (print detail)
BOSS_PROUD = 1.0  # boss stands this far proud of the outer face


def yz_plate(x0, x1, y0, y1, z0, z1):
    from geometry import box

    return box([min(x0, x1), y0, z0], [max(x0, x1), y1, z1])


def build():
    w, h = I["w"], I["h"]
    body = yz_plate(X_OUT, X_IN, CY - w / 2, CY + w / 2, CZ - h / 2, CZ + h / 2)
    yz = cq.Workplane("YZ")
    # Gland bosses (outside), counterbored seats, through holes.
    seat_depth = T + BOSS_PROUD - I["seat_t"]
    for gx, gy, gz in I["glands"]:
        boss = yz.workplane(offset=X_OUT - BOSS_PROUD).center(gy, gz).circle(BOSS_D / 2).extrude(BOSS_PROUD)
        body = body.union(boss)
        cb = yz.workplane(offset=X_OUT - BOSS_PROUD).center(gy, gz).circle(I["seat_d"] / 2).extrude(seat_depth)
        hole = yz.workplane(offset=X_OUT - BOSS_PROUD - 1).center(gy, gz).circle(I["gland_hole"] / 2).extrude(T + BOSS_PROUD + 2)
        body = body.cut(cb).cut(hole)
    # Enclosure screws (Hammond pattern), u to the right seen from outside = -Y here.
    for u, v in I["screws_uv"]:
        y, z = CY - u, CZ + v
        body = body.cut(yz.workplane(offset=X_OUT - 1).center(y, z).circle(I["screw_d"] / 2).extrude(T + 2))
    # Spine socket boss on the outer face, centred between the glands at the lead height.
    zl = G["box"]["wire_z"]
    bw, bh = I["rod_w"] + 2 * I["boss_wall"], I["rod_h"] + 2 * I["boss_wall"]
    boss = yz.workplane(offset=X_OUT - I["boss_l"]).center(CY, zl).rect(bw, bh).extrude(I["boss_l"])
    sock = yz.workplane(offset=X_OUT - I["boss_l"] - 1).center(CY, zl).rect(I["rod_w"] + 2 * FIT, I["rod_h"] + 2 * FIT).extrude(I["boss_l"] + 1 - 1.0)
    pin = cq.Workplane("XY").workplane(offset=zl - bh).center(X_OUT - I["boss_l"] / 2, CY).circle(M3_CLEAR / 2).extrude(2 * bh)
    body = body.union(boss).cut(sock).cut(pin)
    # Ledge on the inner face for the lead bridge's insert end.
    from geometry import box

    lw = I["ledge_w"]
    ledge = box([X_IN, CY - lw / 2, I["ledge_top_z"] - I["ledge_t"]], [I["ledge_x1"], CY + lw / 2, I["ledge_top_z"]])
    body = body.union(ledge)
    # Legends, debossed 0.4 mm into the outer face above each gland, readable from
    # outside (viewer looks along +X with Z up, so the text's x axis is -Y).
    outside = cq.Plane(origin=(X_OUT, 0, 0), xDir=(0, -1, 0), normal=(-1, 0, 0))
    for (gx, gy, gz), txt in zip(I["glands"], ("TIP+", "TIP-")):
        t = cq.Workplane(outside).center(-gy, gz + 13.5).text(txt, 4.0, -0.4, kind="bold", halign="center", valign="center")
        body = body.cut(t)
    return body


if __name__ == "__main__":
    export(build(), "wall-insert", "Flame Retardant", "on its long bottom edge, tilted 15 deg, supports on that edge only")
