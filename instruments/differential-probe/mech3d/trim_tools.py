"""Trimmer tool guides (lid inserts) and the tool handle.

Guides: a sleeve that snaps into a GUIDE_OD hole in the lid over each trimmer and
stops `gap` above it, so the tool lands on the trimmer without the tip wandering
across the divider. trim-guide-ct sits over CT1/CT2 (GKG60015); trim-guide-rv over
RV1/RV2 (Bourns 3296W) and carries a collar so the shoulder-to-tip depth is the
same for all four: one handle serves both.

Handle: holds a Vessel CA-18 zirconia blade (non-conductive tip, the only part
that enters the box); the printed handle is not an insulation barrier (no resin
gets insulation credit) - trim on the calibration jig or with stage 53
de-energised, never live (docs/hv-leads.md).

Lid: dimensions follow the Hammond 1455N2201 reference in leads.rs (lid_t); the
owner's own enclosure lid must give the same lid-underside height or the sleeve
length changes (it is computed from geometry.json, so rebuild).

Resin: Tough 2000. Guides print flange down; the handle prints standing on its
grip end, nose up.
"""
import math

import cadquery as cq

from geometry import G, export

T = G["trim"]
GD = T["guide"]
BL = T["blade"]
LID_T = T["lid_t"]
SNAP_FINGER_L = 5.0  # slotted length under the lid (print detail)
BARB = 0.35  # barb height that holds the sleeve in the lid hole
SLIT_W = 1.0
REACH = max(t["reach_from_flange_top"] for t in T["trimmers"])  # shoulder to trimmer
ENGAGE = 0.3  # blade tip below the trimmer top when the shoulder lands
GRIP_AF, GRIP_L = 12.0, 60.0


def guide(kind):
    trims = [t for t in T["trimmers"] if t["ref"].startswith(kind.upper())]
    t0 = trims[0]
    below = t0["sleeve_below_lid"]
    collar = REACH - t0["reach_from_flange_top"]
    r_od, r_bore = GD["od"] / 2, GD["bore"] / 2
    # z = 0 at the lid's outer face; the sleeve runs down (negative z).
    body = cq.Workplane("XY").workplane(offset=-(LID_T + below)).circle(r_od).extrude(LID_T + below)
    body = body.union(cq.Workplane("XY").circle(GD["flange_d"] / 2).extrude(GD["flange_t"]))
    if collar > 0.01:
        body = body.union(cq.Workplane("XY").workplane(offset=GD["flange_t"]).circle(r_od + 1.5).extrude(collar))
    # Barb under the lid and two slits, so the sleeve snaps in from above.
    zb = -LID_T
    barb = cq.Workplane("XY").workplane(offset=zb - 1.5).circle(r_od + BARB).circle(r_od - 0.1).extrude(1.5)
    barb = barb.edges("<Z").chamfer(0.3)
    body = body.union(barb)
    for a in (0, 90):
        slit = cq.Workplane("XY").workplane(offset=zb - SNAP_FINGER_L).rect(GD["od"] + 2, SLIT_W).extrude(SNAP_FINGER_L + 0.01)
        body = body.cut(slit.rotate((0, 0, 0), (0, 0, 1), a))
    top = GD["flange_t"] + max(collar, 0.0)
    body = body.cut(cq.Workplane("XY").workplane(offset=-(LID_T + below) - 1).circle(r_bore).extrude(LID_T + below + top + 2))
    # Lead-in chamfer at the top of the bore.
    body = body.faces(">Z").edges("not %LINE").edges(cq.selectors.RadiusNthSelector(0)).chamfer(0.5)
    print(f"guide {kind}: sleeve {below:.2f} below the lid, collar {collar:.2f}, shoulder-to-trimmer {REACH:.2f}")
    return body


def handle():
    nose_l = REACH - T["blade_out"] + ENGAGE
    sock = BL["l"] - T["blade_out"]
    assert sock + 2.0 <= nose_l + GRIP_L, "blade socket deeper than the handle"
    grip = cq.Workplane("XY").polygon(6, GRIP_AF / math.cos(math.pi / 6)).extrude(GRIP_L).edges("|Z").fillet(1.5)
    grip = grip.faces("<Z").edges().chamfer(1.0)
    nose = cq.Workplane("XY").workplane(offset=GRIP_L).circle(T["nose_d"] / 2).extrude(nose_l)
    body = grip.union(nose)
    # Blade socket: shank bore plus the flat blade's slot at the nose end.
    z_tip = GRIP_L + nose_l
    body = body.cut(cq.Workplane("XY").workplane(offset=z_tip - sock).circle(BL["shank_d"] / 2 + 0.05).extrude(sock + 1))
    body = body.cut(cq.Workplane("XY").workplane(offset=z_tip - 3).rect(BL["w"] + 0.1, BL["t"] + 0.1).extrude(4))
    # Index flat on the grip in line with the blade, so the slot angle is visible.
    body = body.cut(cq.Workplane("XY").workplane(offset=5).center(0, GRIP_AF / 2).rect(4, 1.2).extrude(GRIP_L - 10))
    print(f"handle: nose {nose_l:.2f} mm, blade out {T['blade_out']} mm, socket {sock:.1f} mm")
    return body


if __name__ == "__main__":
    export(guide("ct"), "trim-guide-ct", "Tough 2000", "flange down, no supports")
    export(guide("rv"), "trim-guide-rv", "Tough 2000", "flange down, no supports")
    export(handle(), "trim-handle", "Tough 2000", "grip end down, nose up, no supports")
