"""Floorplan (R31): explicit poses for connectors, ICs and the power stages, plus anchor rules for passives.

World mm (layout/world.py holds every enclosure-owned number; the connector, J4 and WROOM poses
below are read from it, so an enclosure revision is one edit there). Each explicit entry is
(X, Y, rotation_deg[, "fab"|"crtyd"]): by default (X, Y) is the footprint origin (the body centre
for every SMD part used here); "fab" places the F.Fab outline centre there (connector centres)
and "crtyd" the courtyard centre (J4's body envelope). Everything not listed is a passive placed
by layout/build_board.py next to its anchor pin (ANCHOR below, else the IC/connector pin on its
most specific net).

Regions (R31, world X-38..168; LAYOUT.md "Floorplan" has the picture):
  left edge    J4 (mating -X, pins 9/10 at the front end); the PERMIT gate U37 in the strip between
               J4 and the WROOM, at J4.9
  left         D-11 receiver at J4.11/12, ct_mon buffer at J4.14 (Y41..56)
  front-mid    AD8436 + MCP3202 right of the module (the area behind the module stays a routing
               highway for the module's rear-row pins)
  left-rear    interlock block (Y57..70) and trip glue; U9 read-back buffer towards the MCU; the
               encoder buffer/LDO beside J5
  front-left   ESP32-S3-WROOM-1 behind the lens window (fixed); expander behind it
  rear-mid     thermal-sense block between J2 (X-20) and J1 (X55)
  front-mid    3.3 V buck (X 28..50, outside the antenna keep-out)
  right        12 V fan buck beside J10; RTD front end beside J3 (L2 >= 10 mm from the RTD analog parts)
"""
from __future__ import annotations

import world

PLACE = {
    # ---- connectors, J4 and the module: from the parameter table
    **{ref: (x, y, 0, "fab") for ref, (x, y) in world.CONNECTORS.items()},
    "J4": ((world.J4_BODY[0] + world.J4_BODY[2]) / 2, (world.J4_BODY[1] + world.J4_BODY[3]) / 2,
           90 if world.J4_MATING == "-X" else -90, "crtyd"),
    "U4": ((world.WROOM[0] + world.WROOM[2]) / 2, world.WROOM[1] + 12.8, 180, "fab"),
    "J11": (84.0, 19.5, 90, "fab"),
    # ---- PERMIT gate at J4.9: in front of J4 (the strip between J4 and the module is the escape
    #      channel for the module's left-side pins)
    "U37": (-32.0, 24.5, 90),
    "U9": (-4.5, 66.5, 0),         # read-back buffer: inside the interlock block row, outputs to the MCU
    # ---- J4 analog
    "U5": (-13.0, 44.0, 0),
    "U13": (-19.4, 48.4, 90),
    "U6": (-13.0, 52.5, 0),
    "U14": (18.0, 25.5, 0),
    "U15": (8.0, 24.5, 0),
    # ---- MCU support

    "U8": (36.0, 50.0, 0),
    # ---- interlock block and trip glue
    "U20": (-18.0, 59.5, 0),
    "U21": (-10.0, 59.5, 0),
    "U25": (-2.0, 59.5, 0),
    "U23": (-16.0, 67.0, 90),
    "U22": (8.0, 67.0, 90),
    "U24": (18.5, 66.0, 90),
    "U3": (28.0, 58.0, 0),
    "U11": (28.0, 62.5, 0),
    "U12": (34.0, 62.5, 0),
    # ---- encoder buffer / 5 V LDO beside J5
    "U17": (-18.0, 74.0, 0),
    "U16": (-12.0, 76.0, 0),
    # ---- thermal-sense block
    "U18": (-6.0, 81.0, 0),
    "U26": (2.0, 81.0, 0),
    "U28": (-6.0, 86.5, 0),
    "U19": (30.0, 81.0, 0),
    "U27": (21.0, 81.0, 0),
    "U29": (30.0, 86.5, 0),
    "U7": (11.0, 76.0, 0),
    # ---- 3.3 V buck (cluster: L right of U, SW pour band below; input caps and bulk to the left)
    "U1": (40.0, 22.75, 0),
    "L1": (46.3, 18.4, 0),
    "C3": (42.1, 21.7, -90),
    "C5": (37.8, 20.1, -90),
    "C4": (35.8, 19.9, -90),
    "C1": (28.0, 21.0, 180),
    # ---- 12 V fan buck beside J10 (same cluster)
    "U2": (115.0, 80.75, 0),
    "L2": (121.3, 76.4, 0),
    "C10": (117.1, 79.7, -90),
    "C12": (112.8, 78.1, -90),
    "C11": (110.8, 77.9, -90),
    # ---- RTD front end (rtd_pan) and the runaway comparator beside J3
    "U30": (152.0, 72.0, 90),
    "U31": (142.0, 66.0, 0),
    "U32": (160.0, 58.0, 0),
    "U33": (152.0, 58.0, 0),
    "U34": (160.0, 50.0, 0),
    "U36": (152.0, 50.0, 0),
    "U35": (143.0, 54.0, 0),
    "U10": (142.0, 74.0, 0),
}

# Board text (world mm, size): ID and SELV mark on F.Silkscreen in the free front-right area
SILK = [("TEMPER CONTROLLER", 110.0, 24.0, 2.5), ("SELV  15 V max  -  NO MAINS", 110.0, 20.0, 1.5),
        ("zapote/controller  rev L1 (enclosure R31)", 110.0, 30.0, 1.2)]

# Passive -> anchor IC/connector (pin chosen automatically: the anchor pin on the passive's
# non-ground net). Listed where the automatic "most specific net" choice would pick the wrong
# end (decoupling, ADC RC filters at the MCU, interlock pull-ups at the interlock, etc.).
ANCHOR = {
    # decoupling at every IC supply pin
    "C6": "L1", "C7": "L1", "C8": "L1",
    "C13": "L2", "C14": "L2",
    "C16": "U3", "C18": "U18", "C20": "U19", "C21": "U26", "C22": "U27", "C23": "U28", "C24": "U29",
    "C25": "U30", "C26": "U30", "C28": "U31", "C29": "U32", "C30": "U33", "C31": "U34", "C32": "U35",
    "C33": "U36", "C34": "U23", "C35": "U24", "C36": "U22", "C37": "U20", "C38": "U21", "C39": "U25",
    "C40": "U12", "C41": "U11", "C43": "U10", "C44": "U9", "C46": "U5", "C48": "U6", "C50": "U7",
    "C59": "U14", "C60": "U14", "C62": "U15", "C63": "U4", "C64": "U4", "C66": "U8", "C69": "U17",
    "C67": "U16", "C68": "U16",
    # thermal-sense node parts stay in the block (the net also reaches U6 at J4)
    "R23": "U18", "C17": "U18", "R27": "U19", "C19": "U19",
    # series / pull parts at the connector end
    "R9": "J4", "R10": "J4", "R20": "J10", "R17": "Q1", "Q1": "U2",
    # RTD SPI 33 ohm series resistors belong to the RTD block (at the MAX31865)
    "R36": "U30", "R37": "U30", "R38": "U30", "R39": "U30",
    "R99": "J8", "R100": "J8", "R101": "J8",
    # ADC anti-kick RC at the ESP32 pad
    "R72": "U4", "R75": "U4", "R76": "U4", "R79": "U4",
    # interlock pull-ups / pull-downs in the interlock region
    "R51": "U23", "R52": "U23", "R53": "U23", "R54": "U23", "R55": "U23", "R56": "U23",
    "R57": "U24", "R58": "U24", "R60": "U24", "R61": "U20", "R59": "U21",
    "R22": "U3", "R21": "U3",
    # PERMIT gate (C23): bypass at the gate, RUN_EN pull-down at the gate, PERMIT pull-down at J4.9
    "C70": "U37", "R102": "U37", "R103": "U37",
    # 5 V encoder LDO droppers next to the LDO
    "R92": "U16", "R91": "R92",
    "R88": "U8", "R89": "U8", "R87": "U4", "R86": "U4", "R85": "U15", "D2": "U15", "R83": "U15",
}

# Routing channels kept free of auto-placed parts (world rects): the strip between J4 and the
# module is the only escape for the module's left-side pins.
CHANNELS = [(-24.3, 27.8, -20.5, 40.0),    # J4 - module strip
            (-9.0, 40.2, 8.0, 55.0)]      # behind the module: highway for its rear-row pins
