"""Enclosure geometry for the controller board and the world <-> KiCad transform: THE parameter table.

Every enclosure-owned number the layout uses is in this file; layout/floorplan.py places the
circuit against it and layout/check_layout.py checks the built board against it.

Sources (read-only):
- output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md, "R31" section: outline, holes,
  J1-J4, J9, J10 (R31 mirrors the assembly about X = 0, so J4 mates toward -X).
- output/temper-manufacturing-r33/design/r33/DECISIONS.md section 3 (R33 controller delta,
  restated unchanged in the R35 HANDOFF "Controller layout"): J5/J6/J8 deleted; 12-way J7 at
  X29.8..62.2, Y57.1..62.9; ESP32-S3-WROOM-1U at X141..159, Y50..69.5 with its U.FL at (150, 67);
  no antenna keep-out (off-board chip antenna on a 150 mm coax).
- R30 still sets the mounting (snap-in nylon supports in Ø4.0 holes, Ø8 free of copper and parts)
  and the height (board bottom Z23, top Z24.6).
All coordinates are appliance world mm: X right, Y rear, Z up.

Transform (recorded in LAYOUT.md): the board is drawn in KiCad's frame, viewed from above (top
side), front edge (world Y14) at the bottom of the screen:

    kx = X + OX        ky = OY - Y        (OX = 58, OY = 110)

so world (-38, 90) (rear-left corner) is KiCad (20, 20) and world (168, 14) (front-right
corner) is KiCad (226, 96). This is a translation plus the y-flip of KiCad's y-down screen; it
is not a mirror (the top side stays the top side). A world angle (CCW about +Z seen from
above) equals a KiCad orientation angle (CCW on screen).
"""
from __future__ import annotations

REVISION = "R33"
OX, OY = 58.0, 110.0


def to_k(x: float, y: float) -> tuple[float, float]:
    return x + OX, OY - y


def to_w(kx: float, ky: float) -> tuple[float, float]:
    return kx - OX, OY - ky


# Outline (R31): 206 x 76 x 1.6 mm at world X-38..168, Y14..90.
BOARD = (-38.0, 14.0, 168.0, 90.0)
THICKNESS = 1.6
# C53: six copper layers (C51's rule: route 3 of the four-layer board closed on 1 of 3 clean runs)
COPPER_LAYERS = 6
# Height (R30): components and mated connectors below Z40; board bottom Z23 -> 15.4 mm above the top face.
BOARD_BOTTOM_Z = 23.0
Z_LIMIT = 40.0
# Local allowances (enclosure-granted): (ref, world centre, half-size mm, Z limit, source).
# J13: 16.5 mm mated VH (JST eVH p.1) plus the 18 AWG bend.
LOCAL_Z = [("J13", (88.0, 86.0), 6.0, 54.0, "R41 enclosure: J13 local, Z <= 54 within +-6 mm of (88, 86)")]

# Holes (R31 positions, R30 diameter): six 4.0 mm holes for dual-locking snap-in nylon supports,
# an 8 mm area free of copper and parts around each. The (-34, 18) support is all-nylon 6/6 V-0
# (R33 coordinator note): no action.
HOLES = [(164.0, 18.0), (164.0, 80.0), (65.0, 18.0), (75.0, 86.0), (-34.0, 18.0), (-26.0, 74.0)]
HOLE_D = 4.0
HOLE_KEEPOUT_D = 8.0

# Connector centres (R31 table "Centre"; J7 = centre of its R33 body box); body centre = F.Fab
# outline centre.
CONNECTORS = {
    "J1": (55.0, 84.0),     # coil NTC, JST B2B-XH-A
    "J2": (-20.0, 84.0),    # sink NTC, JST B2B-XH-A
    "J3": (152.0, 86.0),    # pan RTD, JST B4B-XH-A
    "J7": (46.0, 60.0),     # UI bus, JST B12B-XH-A (R33)
    # C53 (R45 request, revised): J9 food probe, JST B4B-XH-A, moved from X-31.5 (C51 request) to X43.5 so the
    # MAX31865 channel sits in the free field in front of it; rotated 180 (CONNECTOR_ROT) so its pin order
    # F-/S-/S+/F+ (left to right) meets U50's pin 10/11 end without crossing the sense pair
    "J9": (43.5, 86.0),
    "J10": (139.0, 86.0),   # fan, JST B3B-XH-A
    "J14": (66.0, 86.0),    # C51 bay NTC, JST B2B-PH-K (R45 request)
    "J15": (104.5, 86.0),   # C51 face fan, JST B5B-XH-A (R45 request)
    "J12": (126.0, 86.0),   # rim NTC, JST B2B-XH-A (R36; accepted R38)
    # J13 PS3 blower feed, JST B2P-VH top entry, posts along X (stage 16, C33). Enclosure R41
    # approved body centre (88, 86); the VH body is 8.5 mm deep (JST eVH p.3), so at Y86 it would
    # overhang the rear edge. Its F.Fab outline is 8.70 mm deep, so the body centre is pulled 0.35 mm
    # forward to sit flush with Y90.
    "J13": (88.0, 85.65),
}
# Connector rotations other than 0 (KiCad orientation, degrees)
CONNECTOR_ROT = {"J9": 180}
# Enclosure-approved spot for J13 (R41) and its local height allowance (below).
J13_R41 = (88.0, 86.0)

CONNECTOR_TOL = 0.5
# R33 gives J7 as a body box: checked edge by edge as well.
J7_BODY = (29.8, 57.1, 62.2, 62.9)

# J4: right-angle Molex 43045-1600 on the LEFT edge, mating -X (R31). Body (courtyard) envelope
# X-38..-24.3 / Y27.8..57.0 (R31 spec: header X-38..-26, Y29.6..54.4, plug to X-50; it mates
# native-21's J4 at X-109..-83, Y51..58.4, Z37.6..47.4 through the 1:1 harness).
J4_BODY = (-38.0, 27.8, -24.3, 57.0)
J4_MATING = "-X"

# ESP32-S3-WROOM-1U-N8 (R33): body box X141..159, Y50..69.5. The module is 18.0 x 19.2 (Espressif
# WROOM-1/-1U DS v1.8 Table 1-2), so it sits with its U.FL end on the box's rear edge (Y69.5).
WROOM = (141.0, 50.0, 159.0, 69.5)
WROOM_BODY_YSPAN = 19.2
# U.FL: R33 gives (150, 67). Espressif DS v1.8 Figure 10-2 puts the receptacle 3.0 mm from the
# module's right edge and 2.46 mm from its antenna-end edge (KiCad footprint: (+6.0, -7.14) from
# the body centre), so with the body on the R33 box it lands at about (156.0, 67.0); the 6 mm X
# difference is reported to the enclosure (LAYOUT.md). Nothing else within UFL_CLEAR_R of it.
UFL_SPEC = (150.0, 67.0)
UFL_FP = (6.0, -7.14)
UFL_CLEAR_R = 3.0
