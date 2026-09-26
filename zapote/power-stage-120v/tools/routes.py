#!/usr/bin/env python3
"""Author the explicit route batches (routes/routes-NN.json).

Every track bend, via and zone outline below is an explicit coordinate
chosen by the designer; nothing here searches for a path. Pad endpoints are
written as "REF.PAD" so the replayer (tools/apply_routes.py) refuses any
pad whose net differs. Duplicate-number pads (studs, fuse clips) use
coordinates. Zones are filled by KiCad under the board's insulation rules.

Layer plan (4 layers, D3 2026-09-26):
  In2.Cu  BUS_P plane under the power stage, left to C5/J8/D3, right to C6.
  In1.Cu  HV_RET plane (capacitor row, trunks to J10/C5/D3 and C6) and a
          separate LEG_RET region across the low-side sources.
  F.Cu    SW_A pour and run to T1, tank (coil feed, RES_A), gate drive,
          mains, signals.
  B.Cu    SW_B band from leg B to the resonant bank, SW_A pour, signals.
Inner planes stay >= 8 mm (plan view) from SELV copper on every layer.

    python3 tools/routes.py      # rewrites routes/routes-*.json
"""

from __future__ import annotations

import json
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
OUT = UNIT / "routes"

POWER_VIA = {"diameter_mm": 1.6, "drill_mm": 0.8}
SIGNAL_VIA = {"diameter_mm": 0.8, "drill_mm": 0.4}


class Batch:
    def __init__(self, author: str):
        self.author = author
        self.nets: dict[str, dict] = {}

    def _net(self, net: str) -> dict:
        return self.nets.setdefault(net, {"net": net, "mode": "replace", "paths": [], "vias": [], "zones": []})

    def track(self, net: str, layer: str, width: float, *points) -> None:
        self._net(net)["paths"].append({"layer": layer, "width_mm": width, "points": list(points)})

    def via(self, net: str, x: float, y: float, power: bool = False) -> None:
        spec = POWER_VIA if power else SIGNAL_VIA
        self._net(net)["vias"].append({"position_mm": [x, y], **spec})

    def zone(self, net: str, layer: str, outline, priority: int = 0, clearance: float = 0.3) -> None:
        self._net(net)["zones"].append({"layer": layer, "outline_mm": [list(p) for p in outline],
                                        "clearance_mm": clearance, "priority": priority})

    def write(self, name: str) -> None:
        OUT.mkdir(exist_ok=True)
        payload = {"author": self.author, "nets": list(self.nets.values())}
        (OUT / name).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def rect(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def batch_01_power() -> Batch:
    """Commutation planes, switch-node pours, bulk and link connections."""
    b = Batch("Claude Opus 5.5; explicit power planes and pours, no search")

    # BUS_P plane on In2: legs, left trunk to C5/J8/D3, right to C6.
    b.zone("bus_p", "In2.Cu", rect(86, 0.6, 170, 42), priority=1)
    b.zone("bus_p", "In2.Cu", [(54, 0.6), (86, 0.6), (86, 31), (69.5, 31), (69.5, 60),
                                (61, 60), (61, 67.5), (55, 67.5), (55, 60), (18, 60), (18, 68), (8, 68), (8, 25),
                                (18, 25), (18, 48.0), (54, 48.0)], priority=2)
    b.zone("bus_p", "In2.Cu", rect(166, 20, 200, 53.5), priority=3)
    # Parallel outer copper around the TVS return pin; the auxiliary routes
    # reserve this corridor. Stitch the upper end and terminate on D3.1.
    b.zone("bus_p", "B.Cu", [(63, 28), (69.4, 28), (69.4, 60), (61, 63),
                              (61, 67.5), (55, 67.5), (55, 63), (63, 60)], priority=2)
    # Keep exposed via annuli clear of the bring-up negative cable lug.
    for x, y in ((67.2, 32.2), (67.2, 34.0), (68.5, 47.0), (68.5, 48.8),
                 (68.5, 53), (68.5, 54.8), (68.5, 56.6), (68.5, 58.4)):
        b.via("bus_p", x, y, power=True)
    # Surface links: high-side drains to their snubbers; D3 to the bleed
    # string and the divider head.
    b.track("bus_p", "F.Cu", 0.8, "Q5.2", [98.0, 9.7], "C19.1")
    b.track("bus_p", "F.Cu", 0.8, "Q2.2", [156.0, 9.7], "C12.1")
    # String links end at the far side of the end pads so the 3.2 mm spacing
    # to the next node holds outside the parts' bodies.
    b.track("bus_p", "F.Cu", 0.4, "D3.1", [61.0, 64.95], [63.5, 64.1], [63.5, 63.4])
    b.track("bus_p", "F.Cu", 0.4, [63.5, 64.1], [60.5, 66.5], [54.5, 69.5], [52.0, 72.0])
    b.track("bus_p", "F.Cu", 0.4, [52.0, 72.0], [52.0, 73.4], [52.0, 74.2])

    # HV_RET plane on In1: capacitor row and trunks.
    b.zone("hv_ret", "In1.Cu", rect(100, 10, 170, 42), priority=1)
    b.zone("hv_ret", "In1.Cu", [(40, 10), (100, 10), (100, 42), (66, 42), (66, 48),
                                 (56, 48), (56, 68), (44, 68), (44, 48), (40, 48)], priority=2)
    b.zone("hv_ret", "In1.Cu", rect(166, 8, 200, 18), priority=3)
    # Parallel return across the narrow filled-plane sections by D2.
    # The V15 trunk is at y=27.2 here so these stitches retain HV_RET.
    b.track("hv_ret", "F.Cu", 5.0, [83.5, 29.9], [90.0, 29.9])
    for x, y in ((83.5, 28.6), (83.5, 30.4), (85.3, 29.5),
                 (90.0, 28.6), (90.0, 30.4), (91.5, 29.5)):
        b.via("hv_ret", x, y, power=True)
    # Shunt HV_RET current pad 4 down to the plane.
    b.track("hv_ret", "F.Cu", 2.0, "R5.4", [124.4, 18.2])
    b.track("hv_ret", "F.Cu", 2.0, "R5.4", [126.2, 18.6])
    b.track("hv_ret", "F.Cu", 2.0, "R5.4", [122.6, 18.2])
    b.via("hv_ret", 124.4, 18.2, power=True)
    b.via("hv_ret", 126.2, 18.6, power=True)
    b.via("hv_ret", 122.6, 18.2, power=True)
    b.track("hv_ret", "F.Cu", 0.4, [63.5, 46.6], [63.5, 45.9], [61, 44.95], "D3.2")

    # LEG_RET on In1 across the low-side sources, into R5's current pad 1
    # (Kelvin pad 2 is kept off this copper).
    b.zone("leg_ret", "In1.Cu", rect(104, 0.6, 148, 10.8), priority=2)
    b.zone("leg_ret", "F.Cu", [(126.2, 6.6), (130.6, 6.6), (130.6, 12.0), (128.4, 12.0),
                               (128.4, 10.8), (126.2, 10.8)], priority=2)
    for x in (126.9, 128.4, 129.9):
        b.via("leg_ret", x, 7.4, power=True)
    b.track("leg_ret", "F.Cu", 0.8, "C20.2", [121.45, 9.7], "Q6.3")
    b.track("leg_ret", "F.Cu", 0.8, "C13.2", [143.45, 9.7], "Q3.3")

    # SW_B: bottom-layer link between the leg B pins, then a full-width band
    # under leg A to the resonant bank and C23.
    # The column to C21/C22 passes right of C6.2's BUS_P pad (the pour's
    # 3.2 mm clearance closes the gap on its left), then back to x >= 192,
    # 8 mm clear of T1's SELV pins.
    b.zone("sw_b", "B.Cu", [(86.5, 0.6), (118.5, 0.6), (118.5, 26.5), (205, 26.5), (205, 41),
                             (204, 41), (204, 57), (197, 60), (197, 128), (186, 128), (186, 92), (192, 92), (192, 41),
                             (86.5, 41)], priority=1)
    b.zone("sw_b", "B.Cu", rect(207, 6, 215, 41), priority=2)
    b.track("sw_b", "B.Cu", 4.0, [199.0, 30.0], [209.0, 30.0])
    # One continuous outline includes the high-side gate return. Separate
    # abutting zones leave KiCad's connectivity dependent on their seam.
    b.track("sw_b", "F.Cu", 0.8, "Q5.3", [103.45, 9.7], "C19.2")
    b.track("sw_b", "F.Cu", 0.8, "Q6.2", [116.0, 9.7], "C20.1")
    # Bleed-string foot: via 5 mm clear of the string's tank nodes.
    b.track("sw_b", "B.Cu", 1.0, [191.75, 128], [191.75, 140], [213.2, 140], [213.2, 151.5])
    b.via("sw_b", 213.2, 151.5)
    b.track("sw_b", "F.Cu", 0.3, [213.2, 151.5], [214.57, 148.8],
            [214.57, 145.0], "R25.2")

    # SW_A: top and bottom pours joining Q3's drain to Q2's source, then the
    # tank run to T1 on F.Cu.
    for layer in ("F.Cu", "B.Cu"):
        b.zone("sw_a", layer, rect(136.2, 0.6, 165.5, 19.8), priority=1)
    # Leg A high-side gate return: SW_A pour down to U1's VSSA and boot caps.
    b.zone("sw_a", "F.Cu", rect(136.2, 19.8, 147.0, 41.5), priority=3)
    b.zone("sw_a", "F.Cu", [(163.0, 14.0), (171.0, 14.0), (171.0, 18.2), (204.0, 18.2), (204.0, 58), (199.0, 58), (199.0, 23.2),
                             (163.0, 23.2)], priority=2)
    # Run to T1 P1: 4 mm on F.Cu, clear of C6's BUS_P pad and T1's coil-feed
    # pad, with a parallel In1 strap for current.
    # T1's pads are 9 mm wide in x at 270 deg: enter P1 from the left after
    # clearing C6's BUS_P pad (y ~51) and T1's coil-feed pad (x >= 202).
    b.track("sw_a", "F.Cu", 4.0, [201.5, 56.0], [201.5, 58.0], [198.5, 60.5], [198.5, 76.08], "T1.1")
    b.track("sw_a", "In1.Cu", 3.0, [201.5, 22.0], [201.5, 58.0], [198.5, 60.5], [198.5, 72.0])
    # Strap stitched at its ends only: mid vias would block SW_B's column.
    for x, y in ((201.5, 22.0), (198.5, 72.0)):
        b.via("sw_a", x, y, power=True)
    b.track("sw_a", "F.Cu", 0.8, "Q3.2", [138.0, 9.7], "C13.1")
    b.track("sw_a", "F.Cu", 0.8, "Q2.3", [161.45, 9.7], "C12.2")

    # Coil feed T1 P2 -> J2 stud; RES_A trunk C23 -> C21 -> C22 -> J5.
    b.zone("coil_feed", "F.Cu", [(204.0, 60.4), (224, 60.4), (224, 64.5), (237, 64.5),
                                 (237, 76.5), (224, 76.5), (224, 69.4), (204.0, 69.4)], priority=1)
    # RES_A crosses under the coil-feed run on B.Cu, then rises to the F.Cu
    # trunk along the right edge.
    b.zone("res_a", "B.Cu", rect(209, 50, 221, 92), priority=3)
    b.zone("res_a", "F.Cu", rect(219, 86, 238, 158), priority=1)
    for x, y in ((217.0, 88.5), (217.0, 91.0), (219.5, 89.5)):
        b.via("res_a", x, y, power=True)
    b.track("res_a", "F.Cu", 3.0, [217.0, 88.5], [217.0, 91.0], [221.0, 91.0])
    b.track("res_a", "F.Cu", 0.3, [228.0, 138.5], [185.7, 138.5], [185.7, 145.0], "R22.1")

    # Rectifier to link studs.
    # Stop before the removable-link gap, including the bench lug envelope
    # when the straps are removed (lug begins at y=25.5).
    b.zone("rect_p", "F.Cu", rect(7.5, 1.0, 19.5, 22.2), priority=1)
    b.zone("rect_n", "F.Cu", [(38.5, 1.0), (44.5, 1.0), (44.5, 11.0), (52.5, 11.0),
                              (52.5, 22.2), (41.0, 22.2), (41.0, 8.0), (38.5, 8.0)], priority=1)
    return b


def batch_02_mains() -> Batch:
    """Mains entry, filter and the L_FILT/N_FILT corridor to the bridge."""
    b = Batch("Claude Opus 5.5; explicit mains routes, no search")
    # Line: J1.1 -> F1 input clip, with an inner-layer parallel.
    b.track("ac_l_in", "F.Cu", 2.4, [6.7, 150.455], [10.5, 148.5])
    b.track("ac_l_in", "F.Cu", 4.0, [10.5, 148.5], [17.5, 148.5], [19.15, 153.0])
    b.track("ac_l_in", "F.Cu", 4.0, [19.15, 153.0], [26.75, 153.0])
    b.track("ac_l_in", "In1.Cu", 2.4, [6.7, 150.455], [10.5, 148.5])
    b.track("ac_l_in", "In1.Cu", 3.0, [10.5, 148.5], [17.5, 148.5], [19.15, 153.0])
    # Fused line: F1 output clips -> L1 line input, RV1, C1, R1.
    b.track("l_f", "F.Cu", 4.0, [46.25, 153.0], [53.85, 153.0])
    b.track("l_f", "F.Cu", 4.0, [46.25, 153.0], [46.25, 144.0], [31.0, 139.0], "L1.1")
    b.track("l_f", "F.Cu", 4.0, [53.85, 153.0], "RV1.1")
    b.track("l_f", "F.Cu", 2.0, [46.25, 144.0], [52.75, 131.0], "C1.1")
    b.track("l_f", "F.Cu", 0.4, "C1.1", [56.0, 120.5], [82.0, 120.5],
            [82.0, 121.4], [82.0, 122.1])
    # Neutral: J1.2 up the channel between J1 and F1 to L1's neutral input
    # (B.Cu, main current); MOV/X-cap branch on both inner layers.
    # Main current on B.Cu with an In2 parallel (In1 carries the line).
    for layer in ("B.Cu", "In2.Cu"):
        b.track("ac_n_in", layer, 2.4, [6.7, 155.535], [6.7, 157.0], [13.0, 157.0])
        b.track("ac_n_in", layer, 3.6, [13.0, 157.0], [13.0, 139.0], "L1.2")
    # MOV/X-cap branch on both inner layers: above L1's line pin, below
    # RV1's line pin, clear of the line trace on In1.
    for layer in ("In1.Cu", "In2.Cu"):
        b.track("ac_n_in", layer, 2.5, "L1.2", [19.0, 142.2], [56.0, 142.2], [58.0, 141.0],
                [72.0, 141.0], "RV1.2")
        b.track("ac_n_in", layer, 2.0, [72.0, 141.0], [75.25, 138.0], "C1.2")
    b.track("ac_n_in", "F.Cu", 0.4, "C1.2", [75.25, 132.0], [81.0, 132.0],
            [82.0, 131.8], "R2.2")
    b.track("xbleed_mid", "F.Cu", 0.4, [82.0, 125.8], [82.0, 126.6], [82.0, 127.4])

    # L_FILT on F.Cu up the corridor under PS2 and C5 to C2 and BR1.
    b.track("l_filt", "F.Cu", 4.0, "L1.4", [29.7, 105.0], [29.7, 36.0], "C2.1")
    b.track("l_filt", "F.Cu", 4.0, "C2.1", [23.5, 28.5], [23.5, 9.0], "BR1.2")
    b.track("l_filt", "F.Cu", 1.0, [29.7, 106.2], [36.45, 106.2])
    b.track("l_filt", "F.Cu", 1.5, "L1.4", [33.0, 108.0], [74.0, 108.0], [76.0, 112.0], "PS1.1")
    b.track("l_filt", "F.Cu", 1.0, [74.0, 108.0], [138.5, 108.0], "C3.1")
    # N_FILT on B.Cu directly under it, to C2, BR1, PS2, PS1 and the Y cap.
    b.track("n_filt", "B.Cu", 4.0, "L1.3", [21.3, 108.0], [21.3, 101.0],
            [23.4, 99.0], [23.4, 12.35], "C2.2")
    b.track("n_filt", "B.Cu", 4.0, "C2.2", [33.8, 8.0], "BR1.3")
    b.track("n_filt", "B.Cu", 1.5, [23.4, 84.0], "PS2.1")
    b.track("n_filt", "B.Cu", 1.5, "L1.3", [21.0, 113.0], [21.0, 122.0], [96.8, 122.0], "PS1.2")
    b.track("n_filt", "F.Cu", 1.0, "PS1.2", [96.8, 113.5], [145.5, 113.5], "C4.1")
    # Thermal-cutoff loop feed: J3 beside the corridor; TCO_L to PS2 on In1.
    b.track("tco_l", "In1.Cu", 1.0, [36.45, 100.35], [34.5, 99.8], [8.0, 99.8], "PS2.2")
    return b


# SELV island. Planes: In1 = V3V3, In2 = SELV_GND (also a B.Cu pour). The
# outline keeps >= 8 mm plan-view from every HOT item on any layer.
ISLAND = [(77.8, 50.2), (158, 50.2), (158, 84), (90, 84), (90, 88.0), (73.2, 88.0), (69.2, 85),
          (69.2, 74), (77.8, 68)]

# Plane ties: pad -> via position (stub on F.Cu).
TIES = {
    "v3v3": {"U2.3": (102.095, 53.3), "U2.8": (108.445, 52.9), "U1.3": (146.095, 53.3),
             "U1.8": (152.445, 52.9), "U9.14": (84.905, 53.0), "C14.1": (95.725, 54.6),
             "C7.1": (139.725, 54.6), "C37.1": (82.225, 54.6), "R16.2": (113.0, 56.5),
             "R8.2": (157.0, 56.5), "U4.8": (73.0, 82.095), "C29.1": (70.0, 79.6)},
    "selv_gnd": {"U2.4": (103.365, 53.3), "U1.4": (147.365, 53.3), "U9.9": (78.555, 53.0),
                 "U9.16": (87.445, 53.0), "C14.2": (97.275, 58.4), "C7.2": (141.275, 58.4),
                 "C37.2": (83.775, 58.4), "Q4.2": (101.8, 60.3), "Q1.2": (145.8, 60.3),
                 "R15.2": (107.325, 61.2), "R17.2": (111.325, 61.2), "R7.2": (151.325, 61.2),
                 "R9.2": (155.325, 61.2), "U4.5": (73.0, 85.905), "C29.2": (72.0, 76.225),
                 "R38.2": (104.325, 81.0)},
}


def batch_03_selv() -> Batch:
    """SELV island: planes, per-leg DIS/DT/PERMIT networks, controller lines, PE."""
    b = Batch("Claude Opus 5.5; explicit SELV island routes, no search")
    b.zone("v3v3", "In1.Cu", ISLAND, priority=1)
    b.zone("selv_gnd", "In2.Cu", ISLAND, priority=1)
    b.zone("selv_gnd", "B.Cu", ISLAND, priority=1)
    for net, ties in TIES.items():
        for pad, (x, y) in ties.items():
            b.track(net, "F.Cu", 0.4, pad, [x, y])
            b.via(net, x, y)

    # Per leg (U2/Q4 at dx = -44 from U1/Q1): PERMIT_GATE on F.Cu, DIS on
    # B.Cu, dead time on In1, PERMIT on the B.Cu trunk.
    for dx, leg, q, rp, rpd, rdis, rdt, drv in (
        (0.0, "leg_a", "Q1", "R6", "R7", "R8", "R9", "U1"),
        (-44.0, "leg_b", "Q4", "R14", "R15", "R16", "R17", "U2"),
    ):
        pg = f"{leg}-permit_gate"
        b.track(pg, "F.Cu", 0.3, f"{q}.1", [145.2 + dx, 55.3], [151.325 + dx, 55.3], f"{rp}.2")
        b.track(pg, "F.Cu", 0.3, [148.0 + dx, 55.3], [148.0 + dx, 59.5], f"{rpd}.1")
        dis = f"{leg}-dis"
        b.track(dis, "F.Cu", 0.3, f"{drv}.5", [148.635 + dx, 53.5])
        b.via(dis, 148.635 + dx, 53.5)
        b.track(dis, "B.Cu", 0.3, [148.635 + dx, 53.5], [146.44 + dx, 55.7], [146.44 + dx, 58.9])
        b.via(dis, 146.44 + dx, 58.9)
        b.track(dis, "F.Cu", 0.3, [146.44 + dx, 58.9], f"{q}.3")
        b.track(dis, "B.Cu", 0.3, [148.635 + dx, 53.5], [149.3 + dx, 54.2], [153.675 + dx, 54.2],
                [153.675 + dx, 55.1])
        b.via(dis, 153.675 + dx, 55.1)
        b.track(dis, "F.Cu", 0.3, [153.675 + dx, 55.1], f"{rdis}.1")
        dt = f"{leg}.driver-dt"
        b.track(dt, "F.Cu", 0.3, f"{drv}.6", [149.905 + dx, 52.4])
        b.via(dt, 149.905 + dx, 52.4)
        b.track(dt, "In1.Cu", 0.3, [149.905 + dx, 52.4], [153.675 + dx, 58.0])
        b.via(dt, 153.675 + dx, 58.0)
        b.track(dt, "F.Cu", 0.3, [153.675 + dx, 58.0], f"{rdt}.1")
        b.track("permit", "F.Cu", 0.3, f"{rp}.1", [150.5 + dx, 58.0])
        b.via("permit", 150.5 + dx, 58.0)
        b.track("permit", "B.Cu", 0.3, [150.5 + dx, 58.0], [150.5 + dx, 62.3])
    b.track("permit", "B.Cu", 0.3, [106.5, 62.3], [150.5, 62.3])
    b.track("permit", "B.Cu", 0.3, "J4.9", [110.8, 65.6], [110.8, 62.3])

    # PWM lines: HA on F.Cu, LA via In1, HB on In1, LB on In2.
    b.track("pwm_ha", "F.Cu", 0.3, "J4.5", [124.5, 61.9], [142.3, 61.9], [142.3, 52.5],
            [143.555, 52.5], "U1.1")
    b.track("pwm_la", "F.Cu", 0.3, "J4.6", [127.5, 62.7], [143.2, 62.7], [143.2, 63.6])
    b.via("pwm_la", 143.2, 63.6)
    b.track("pwm_la", "In1.Cu", 0.3, [143.2, 63.6], [144.825, 61.8], [144.825, 54.4])
    b.via("pwm_la", 144.825, 54.4)
    b.track("pwm_la", "F.Cu", 0.3, [144.825, 54.4], "U1.2")
    b.track("pwm_hb", "F.Cu", 0.3, "U2.1", [99.555, 53.0])
    b.via("pwm_hb", 99.555, 53.0)
    b.track("pwm_hb", "In1.Cu", 0.3, [99.555, 53.0], [99.555, 62.5], [130.5, 62.5], "J4.7")
    b.track("pwm_lb", "F.Cu", 0.3, "U2.2", [100.825, 54.3])
    b.via("pwm_lb", 100.825, 54.3)
    b.track("pwm_lb", "In2.Cu", 0.3, [100.825, 54.3], [100.825, 62.5], [133.5, 62.5], "J4.8")

    # Isolator fault line (In2), bus sense (F.Cu pair), SELV 15 V, CT pair.
    b.track("bus_fault", "F.Cu", 0.3, "U9.13", [83.0, 53.2])
    b.via("bus_fault", 83.0, 53.2)
    b.track("bus_fault", "In2.Cu", 0.3, [83.0, 53.2], [91.0, 61.0], [91.0, 65.58], [113.9, 65.58], "J4.10")
    b.track("vbus_p", "F.Cu", 0.3, "U4.7", [78.0, 83.365], [86.0, 73.5], [116.0, 73.5], [118.5, 71.0], "J4.11")
    b.track("vbus_n", "F.Cu", 0.3, "U4.6", [79.0, 84.635], [87.0, 74.5], [117.0, 74.5], [121.5, 71.0], "J4.12")
    b.track("v15_selv", "F.Cu", 0.8, "J4.1", [110.5, 66.0], [92.0, 66.0], [88.8, 69.2], "PS1.4")
    b.track("ct_s1", "F.Cu", 0.4, "J4.13", [124.5, 72.0], [170.0, 72.0], [170.0, 63.62], "T1.3")
    b.track("ct_s2", "B.Cu", 0.4, "J4.14", [127.5, 71.0], [172.0, 71.0], [172.0, 75.5])
    b.via("ct_s2", 172.0, 75.5)
    b.track("ct_s2", "F.Cu", 0.4, [172.0, 75.5], [172.0, 77.38], "T1.4")

    # PE branch: functional-earth link R38, J6, Y1 capacitor PE pads.
    b.track("pe", "F.Cu", 2.0, "R38.1", [102.675, 77.0], [110.6, 77.0], "J6.1")
    b.track("pe", "F.Cu", 2.0, "J6.1", "J6.2")
    b.track("pe", "F.Cu", 2.0, "J6.2", [135.0, 79.5], "C3.2")
    b.track("pe", "F.Cu", 2.0, "C3.2", "C4.2")
    return b


def batch_04_drive() -> Batch:
    """Gate drive, bootstrap, gate hold-offs and the small resistor strings."""
    b = Batch("Claude Opus 5.5; explicit gate-drive routes, no search")
    for net in ("sw_a", "sw_b", "leg_ret"):
        b.nets.setdefault(net, {"net": net, "mode": "add", "paths": [], "vias": [], "zones": []})

    # Gates: MOSFET gate -> series resistor -> hold-off.
    for gate, q, r, pd in (("leg_b-gate_h", "Q5", "R18", "R19"), ("leg_b-gate_l", "Q6", "R20", "R21"),
                           ("leg_a-gate_h", "Q2", "R10", "R11"), ("leg_a-gate_l", "Q3", "R12", "R13")):
        b.track(gate, "F.Cu", 0.8, f"{q}.1", f"{r}.2")
        b.track(gate, "F.Cu", 0.5, f"{r}.2", f"{pd}.1")
    # Hold-off source ends: R19 -> SW_B pour (B.Cu), R21 -> LEG_RET (In1).
    b.track("sw_b", "F.Cu", 0.5, "R19.2", [88.3, 10.6])
    b.via("sw_b", 88.3, 10.6)
    b.track("leg_ret", "F.Cu", 0.5, "R21.2", [107.6, 10.2])
    b.via("leg_ret", 107.6, 10.2)

    # Leg B high side: OUTA between C41's pads; return is the SW_B pour below.
    b.track("leg_b-out_h", "F.Cu", 0.8, "U2.15", [100.825, 30.0], [96.0, 25.0], [96.0, 16.5], "R18.1")
    b.track("sw_b", "F.Cu", 0.6, "U2.14", [102.095, 33.0])
    b.via("sw_b", 102.095, 33.0)
    # Leg B low side: OUTB right of C40's BUS_P pad, VSSB return beside it.
    # Both lanes pass between U2's VDDB capacitors (C16 above, C15 below),
    # then right of C40's BUS_P pad and left of U6; VSSB drops to In1 LEG_RET.
    b.track("leg_b-out_l", "F.Cu", 0.5, "U2.10", [107.175, 37.55], [114.0, 37.55], [114.0, 17.2], "R20.1")
    b.track("leg_ret", "F.Cu", 0.6, "U2.9", [108.445, 38.55], [114.9, 38.55], [114.9, 17.8])
    b.via("leg_ret", 114.9, 17.8)
    # Short In1 hop into the LEG_RET region; it notches, not splits, HV_RET.
    b.track("leg_ret", "In1.Cu", 0.6, [114.9, 17.8], [114.9, 10.2])

    # Leg A high side: OUTA over C9, down the channel between C39's pads.
    b.track("leg_a-out_h", "F.Cu", 0.8, "U1.15", [144.825, 38.5], [147.5, 28.5], [155.5, 28.5],
            [155.5, 17.0], "R10.1")
    # Dedicated VSSA return follows OUTA all the way to the source pour.
    b.track("sw_a", "F.Cu", 0.6, "U1.14", [146.095, 38.5], [148.5, 29.5],
            [156.5, 29.5], [156.5, 17.0])
    # Leg A low side: OUTB and VSSB cross to Q3 on In1 (same group as HV_RET).
    b.track("leg_a-out_l", "F.Cu", 0.6, "U1.10", [151.8, 38.8])
    b.via("leg_a-out_l", 151.8, 38.8)
    b.track("leg_a-out_l", "In1.Cu", 0.5, [151.8, 38.8], [151.8, 26.9], [136.5, 26.9], [134.8, 17.5])
    b.via("leg_a-out_l", 134.8, 17.5)
    b.track("leg_a-out_l", "F.Cu", 0.6, [134.8, 17.5], "R12.1")
    b.track("leg_ret", "F.Cu", 0.6, "U1.9", [153.2, 38.6])
    b.via("leg_ret", 153.2, 38.6)
    # VSSB beside OUTB on In1, ending at a via inside the band (a full
    # crossing would split HV_RET), then F.Cu between R5's sense pad and R13 into the LEG_RET pour.
    b.track("leg_ret", "In1.Cu", 0.5, [153.2, 38.6], [152.6, 37.8], [152.6, 26.1], [137.3, 26.1],
            [136.0, 18.6])
    b.via("leg_ret", 136.0, 18.6)
    b.track("leg_ret", "F.Cu", 0.5, [136.0, 18.6], [128.72, 18.6], [128.72, 11.6])

    # Bootstrap: diode cathode, boot caps and VDDA pin on each leg.
    for dx, boot, sw, d, cb, chf, drv in ((0.0, "leg_b-boot", "sw_b", "D2", "C17", "C18", "U2"),
                                          (44.0, "leg_a-boot", "sw_a", "D1", "C10", "C11", "U1")):
        if d == "D1":
            b.track(boot, "F.Cu", 0.8, f"{d}.1", f"{cb}.1")
        else:
            b.track(boot, "F.Cu", 0.8, f"{d}.1", [99.3 + dx, 36.0], [99.3 + dx, 40.3], f"{drv}.16")
        b.track(boot, "F.Cu", 0.6, f"{drv}.16", [98.4 + dx, 41.7], [97.4 + dx, 41.7], f"{chf}.1")
        b.track(boot, "F.Cu", 0.8, [97.4 + dx, 41.7], [92.525 + dx, 41.7], f"{cb}.1")
        b.track(sw, "F.Cu", 0.8, f"{cb}.2", [95.475 + dx, 37.6], f"{chf}.2")
    # Two short local returns above the auxiliary trunk; merging them on
    # F.Cu would cross OUTA. Both vias leave In2 y=37..41 clear.
    b.track("sw_b", "F.Cu", 0.6, "C18.2", [96.5, 36.8], [96.5, 35.5])
    b.via("sw_b", 96.5, 35.5)

    # Resistor strings.
    # Links span only the gap between adjacent end pads.
    b.track("busbleed_mid", "F.Cu", 0.4, [63.5, 50.3], [63.5, 51.1], [63.5, 58.9], [63.5, 59.6])
    b.track("vdiv_1", "F.Cu", 0.3, [52.0, 77.8], [52.0, 78.2], [52.0, 78.5], [52.0, 78.9])
    b.track("vdiv_2", "F.Cu", 0.3, [52.0, 82.5], [52.0, 82.9], [52.0, 83.2], [52.0, 83.6])
    b.track("vdiv_3", "F.Cu", 0.3, [52.0, 87.2], [52.0, 87.6], [52.0, 87.9], [52.0, 88.3])
    b.track("crbleed_1", "F.Cu", 0.3, [191.85, 145.0], [194.35, 145.0], [195.15, 145.0])
    b.track("crbleed_2", "F.Cu", 0.3, [198.85, 145.0], [199.5, 145.0], [201.5, 145.0], [202.15, 145.0])
    b.track("crbleed_3", "F.Cu", 0.3, [205.85, 145.0], [206.0, 145.0], [206.5, 145.0], [209.15, 145.0])
    return b


def main() -> None:
    batch_01_power().write("routes-01.json")
    batch_02_mains().write("routes-02.json")
    batch_03_selv().write("routes-03.json")
    batch_04_drive().write("routes-04.json")
    print("routes written")


if __name__ == "__main__":
    main()
