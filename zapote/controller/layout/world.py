"""Enclosure geometry for the controller board and the world <-> KiCad transform: THE parameter table.

Every enclosure-owned number the layout uses is in this file; layout/floorplan.py places the
circuit against it and layout/check_layout.py checks the built board against it.

Source (read-only): output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md, "R31" section
(authority over R27-R30). R31 mirrors the assembly about X = 0 so native-21 sits in its true
pose; the controller moves with it, J4 mates toward -X, J7 merges into a 4-pin J8, and the
ESP32 sits behind the fixed lens window. R30 still sets the mounting (snap-in nylon supports in
Ø4.0 holes, Ø8 free of copper and parts) and the height (board bottom Z23, top Z24.6).
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

REVISION = "R31"
OX, OY = 58.0, 110.0


def to_k(x: float, y: float) -> tuple[float, float]:
    return x + OX, OY - y


def to_w(kx: float, ky: float) -> tuple[float, float]:
    return kx - OX, OY - ky


# Outline (R31): 206 x 76 x 1.6 mm at world X-38..168, Y14..90.
BOARD = (-38.0, 14.0, 168.0, 90.0)
THICKNESS = 1.6
# Height (R30): components and mated connectors below Z40; board bottom Z23 -> 15.4 mm above the top face.
BOARD_BOTTOM_Z = 23.0
Z_LIMIT = 40.0

# Holes (R31 positions, R30 diameter): six 4.0 mm holes for dual-locking snap-in nylon supports,
# an 8 mm area free of copper and parts around each.
HOLES = [(164.0, 18.0), (164.0, 80.0), (65.0, 18.0), (75.0, 86.0), (-34.0, 18.0), (-26.0, 74.0)]
HOLE_D = 4.0
HOLE_KEEPOUT_D = 8.0

# Connector centres (R31 table, "Centre"); body centre = F.Fab outline centre.
CONNECTORS = {
    "J1": (55.0, 84.0),     # coil NTC, JST B2B-XH-A
    "J2": (-20.0, 84.0),    # sink NTC, JST B2B-XH-A
    "J3": (152.0, 86.0),    # pan RTD, JST B4B-XH-A
    "J5": (-32.0, 64.0),    # encoder, TE Micro-MaTch 7-215079-6
    "J6": (35.0, 70.0),     # OLED, JST B8B-XH-A
    "J8": (15.0, 41.0),     # all three buttons + common, JST B4B-XH-A (R31: J7 deleted)
    "J9": (-33.0, 86.0),    # M12 probe, JST B3B-XH-A
    "J10": (139.0, 86.0),   # fan, JST B3B-XH-A
}
CONNECTOR_TOL = 0.5

# J4: right-angle Molex 43045-1600 on the LEFT edge, mating -X (R31). Body (courtyard) envelope
# X-38..-24.3 / Y27.8..57.0 (R31 spec: header X-38..-26, Y29.6..54.4, plug to X-50; it mates
# native-21's J4 at X-109..-83, Y51..58.4, Z37.6..47.4 through the 1:1 harness).
J4_BODY = (-38.0, 27.8, -24.3, 57.0)
J4_MATING = "-X"

# ESP32-S3-WROOM-1 (R31): X-20..-2, Y14..39.5, antenna end at the front edge (Y14), behind the
# fixed lens window (X-89..19).
WROOM = (-20.0, 14.0, -2.0, 39.5)
# Espressif antenna keep-out as carried by KiCad's RF_Module:ESP32-S3-WROOM-1 rule area: 15 mm beyond
# the module's antenna end and both sides, back to 6.05 mm from the antenna end (module frame
# -24..24 x -27.75..-6.75 about the module centre, module body 18 x 25.6).
WROOM_KEEPOUT_FP = (-24.0, -27.75, 24.0, -6.75)
