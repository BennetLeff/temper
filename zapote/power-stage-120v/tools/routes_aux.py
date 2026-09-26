#!/usr/bin/env python3
"""Explicit HOT auxiliary routes for the four-layer power-stage board.

All paths are authored coordinates.  This module shares only the JSON writer
with routes.py; KiCad replays and checks the native copper separately.
"""

from __future__ import annotations

from routes import Batch


def batch_05_aux() -> Batch:
    b = Batch("Codex; explicit HOT auxiliary routes, no path search")

    # Earlier batches carry LEG_RET at the MOSFET source pads.  This batch
    # extends it from R5's Kelvin pad to the control electronics.  It must
    # preserve the earlier power and gate-return copper.
    b.nets["leg_ret"] = {"net": "leg_ret", "mode": "add", "paths": [], "vias": [], "zones": []}

    # U3 regulator: C26 (HOT5) sits left of U3, C24 (V15) sits right.
    b.track("hot5", "F.Cu", 0.4, "U3.1", "C26.1")
    b.track("hot5", "F.Cu", 0.4, "C26.1", [56.0, 22.0], [56.0, 29.0],
            [70.0, 29.0], [74.0, 33.0], "C35.1")
    b.track("hot5", "F.Cu", 0.4, [56.0, 26.0], [42.0, 26.0])
    b.via("hot5", 42.0, 26.0)
    b.track("leg_ret", "F.Cu", 0.3, "U3.2", [59.0, 16.0], "C26.2",
            [57.5, 14.5], [62.775, 14.5], "C25.2", [64.0, 14.5],
            [66.5, 14.5], "C24.2")
    b.track("leg_ret", "F.Cu", 0.3, "U3.2", [62.0, 22.0])
    b.via("leg_ret", 62.0, 22.0)
    b.track("v15_ls", "F.Cu", 0.3, "U3.3", "C24.1", [68.5, 21.5])
    b.via("v15_ls", 68.5, 21.5)
    b.track("v15_ls", "In1.Cu", 0.3, [68.5, 21.5], [65.0, 21.5],
            [65.0, 12.0], [61.225, 12.0], [61.225, 11.5])
    b.via("v15_ls", 61.225, 11.5)
    b.track("v15_ls", "F.Cu", 0.3, [61.225, 11.5], "C25.1")

    # Return and V15 from PS2 use the west side of C5 and avoid its live pads.
    b.track("leg_ret", "B.Cu", 0.4, "PS2.3", [47.0, 91.0], [47.0, 78.0],
            [42.0, 75.0], [42.0, 40.0],
            [54.0, 36.0], [56.0, 25.5], [62.0, 22.0])
    b.track("v15_ls", "B.Cu", 0.4, "PS2.4", [37.5, 80.0], [37.5, 41.0],
            [53.0, 35.0], [55.0, 24.0], [57.0, 20.0], [68.5, 20.0], [68.5, 21.5])
    # The U3-to-U8 control return crosses the HOT5 descent on In1.
    b.track("leg_ret", "In1.Cu", 0.3, [62.0, 22.0], [62.0, 24.5],
            [77.0, 24.5], [77.0, 35.0], [73.5, 41.7])
    b.via("leg_ret", 73.5, 41.7)
    b.track("leg_ret", "F.Cu", 0.3, [73.5, 41.7], "U8.3")
    b.track("leg_ret", "F.Cu", 0.3, "C35.2", [79.0, 31.0])
    b.via("leg_ret", 79.0, 31.0)
    b.track("leg_ret", "F.Cu", 0.3, "U9.7", [79.825, 39.1])
    b.via("leg_ret", 79.825, 39.1)
    b.track("leg_ret", "In1.Cu", 0.3, [73.5, 41.7], [79.825, 39.1])
    b.track("leg_ret", "In1.Cu", 0.3, [79.0, 31.0], [79.825, 39.1],
            [79.825, 41.7], [87.7, 41.7], [87.7, 37.0])
    b.track("leg_ret", "F.Cu", 0.3, "C36.2", [86.0, 35.0],
            [87.7, 35.0], [87.7, 37.0], "U9.1")
    b.via("leg_ret", 87.7, 37.0)

    # HOT5 descends between D3 and the island, then feeds U4/U7.  A separate
    # In2 lane takes it to U9 and the comparator side of the board.
    b.track("hot5", "In1.Cu", 0.4, [42.0, 26.0], [42.0, 70.0],
            [61.0, 72.0])
    b.via("hot5", 61.0, 72.0)
    b.track("hot5", "B.Cu", 0.4, [61.0, 72.0], [60.175, 80.6])
    b.via("hot5", 60.175, 80.6)
    b.track("hot5", "F.Cu", 0.3, [60.175, 80.6], "U4.1")
    b.track("hot5", "F.Cu", 0.3, "U4.1", "C28.1")
    b.track("hot5", "B.Cu", 0.3, [60.175, 80.6], [60.9, 90.0], [63.4, 92.8])
    b.via("hot5", 63.4, 92.8)
    b.track("hot5", "F.Cu", 0.3, [63.4, 92.8], "U7.5", "C34.1")
    b.track("hot5", "F.Cu", 0.3, "C35.1", "U8.5")
    # U9's input pad is reached from the east so the adjacent fault output
    # can leave to the west without crossing the HOT5 trace.
    b.track("hot5", "F.Cu", 0.3, "C36.1", [82.225, 36.0])
    b.track("hot5", "F.Cu", 0.3, "C35.1", [74.0, 33.0])
    b.via("hot5", 74.0, 33.0)
    b.track("hot5", "B.Cu", 0.3, [74.0, 33.0], [82.225, 33.0],
            [82.225, 36.0], [85.7, 39.0])
    b.via("hot5", 82.225, 36.0)
    b.via("hot5", 85.7, 39.0)
    b.track("hot5", "F.Cu", 0.3, [85.7, 39.0], "U9.3")
    b.track("hot5", "In2.Cu", 0.3, [74.0, 33.0], [72.0, 33.0],
            [72.0, 23.5], [79.8, 23.5], [79.8, 20.5])
    b.via("hot5", 79.8, 20.5)
    b.track("hot5", "F.Cu", 0.3, [79.8, 20.5], [80.0, 21.2], "R31.1")
    b.track("hot5", "In1.Cu", 0.3, [79.8, 20.5], [78.8, 19.5],
            [77.5, 19.5], [75.5, 19.0], [74.2, 16.0])
    b.via("hot5", 74.2, 16.0)
    b.track("hot5", "F.Cu", 0.3, [74.2, 16.0], "U6.5")
    b.track("hot5", "F.Cu", 0.3, [70.0, 29.0], [70.0, 24.0], "C32.1")

    # U4/U7 return island on In1.  PS2.3 is a through-hole anchor.  The
    # outline is 8 mm clear of the SELV-side U4 pads and nearby island pour.
    b.zone("leg_ret", "In1.Cu", [(41, 78), (61, 78), (61, 88), (63, 92),
                                   (66, 94.5), (68.5, 97), (68.5, 103), (41, 103)],
           priority=2)
    seen_vias: set[tuple[float, float]] = set()
    for pad, xy in (
        ("C28.2", (58.4, 80.4)), ("U4.3", (58.2, 85.3)),
        ("U4.4", (58.2, 85.3)), ("R30.2", (58.6, 87.2)),
        ("C27.2", (55.6, 91.9)), ("U7.2", (59.3, 95.0)),
        ("R37.2", (62.5, 98.2)), ("C33.2", (62.5, 98.2)),
        ("C34.2", (67.3, 96.6)),
    ):
        b.track("leg_ret", "F.Cu", 0.3, pad, list(xy))
        if xy not in seen_vias:
            b.via("leg_ret", *xy)
            seen_vias.add(xy)

    # The relocated comparator uses a paired top-edge Kelvin feed from R5.
    # The pair is distinct from the earlier LEG_RET current copper at R5.1.
    b.track("leg_ret", "F.Cu", 0.3, "R5.2", [121.5, 12.4],
            [119.6, 15.0])
    b.via("leg_ret", 119.6, 15.0)
    b.track("leg_ret", "In2.Cu", 0.3, [119.6, 15.0], [95.0, 15.0],
            [90.0, 14.5], [68.5, 14.5], [68.5, 17.0])
    b.via("leg_ret", 68.5, 17.0)
    b.track("leg_ret", "F.Cu", 0.3, [68.5, 17.0], [68.3, 19.0], "U6.2")
    b.track("leg_ret", "F.Cu", 0.3, "C24.2", [68.5, 17.0])
    b.track("leg_ret", "F.Cu", 0.3, "C32.2", [73.6, 25.0])
    b.via("leg_ret", 73.6, 25.0)
    b.track("leg_ret", "In1.Cu", 0.3, [73.6, 25.0], [72.0, 23.0],
            [68.5, 17.0])
    b.track("leg_ret", "F.Cu", 0.3, "C30.2", "U5.2", [81.2, 20.6])
    b.via("leg_ret", 81.2, 20.6)
    b.track("leg_ret", "F.Cu", 0.3, "R35.2", "C31.2", [84.4, 26.3])
    b.via("leg_ret", 84.4, 26.3)
    b.track("leg_ret", "In1.Cu", 0.3, [84.4, 26.3], [81.2, 23.0],
            [77.5, 23.0], [73.6, 25.0])
    b.track("leg_ret", "In1.Cu", 0.3, [81.2, 20.6], [81.2, 23.0])

    # Driver bypass returns stay local to their respective VSSB pins; they do
    # not join the control-return lane to R5.2.
    b.track("leg_ret", "F.Cu", 0.3, "C15.2", [112.275, 38.55], [114.9, 38.55])
    b.track("leg_ret", "F.Cu", 0.3, "C16.2", [113.0, 33.4])
    b.via("leg_ret", 113.0, 33.4)
    b.track("leg_ret", "In1.Cu", 0.3, [113.0, 33.4], [114.9, 35.0])
    b.via("leg_ret", 114.9, 35.0)
    b.track("leg_ret", "F.Cu", 0.3, "C9.2", "C8.2", [156.275, 41.6],
            [153.2, 41.6], [153.2, 38.6])

    # Bus-voltage input: high-impedance VSENSE stays apart from the divider
    # taps.  In2 visits U4, the RC filter and U7 without an F.Cu crossing.
    b.track("vsense_in", "F.Cu", 0.3, "R29.2", [52.0, 92.7],
            [54.0, 93.6], "C27.1", [58.3, 92.3])
    b.via("vsense_in", 58.3, 92.3)
    b.track("vsense_in", "F.Cu", 0.3, "R30.1", [58.4, 89.6])
    b.via("vsense_in", 58.4, 89.6)
    b.track("vsense_in", "F.Cu", 0.3, "U4.2", [58.6, 83.4])
    b.via("vsense_in", 58.6, 83.4)
    b.track("vsense_in", "F.Cu", 0.3, "U7.4", [63.1375, 96.9])
    b.via("vsense_in", 63.1375, 96.9)
    b.track("vsense_in", "In2.Cu", 0.3, [58.6, 83.4], [60.7, 83.4],
            [60.7, 96.9], [63.1375, 96.9])
    b.track("vsense_in", "In2.Cu", 0.3, [58.4, 89.6], [60.7, 89.6])
    b.track("vsense_in", "In2.Cu", 0.3, [58.3, 92.3], [60.7, 92.3])

    # U7 threshold and the two comparator status signals.
    b.track("ovp_thresh", "F.Cu", 0.3, "U7.3", "R36.2", [59.0, 98.2], "R37.1", "C33.1")
    b.track("ovp_ok_hot", "F.Cu", 0.3, "U7.1", [59.5, 93.0], [59.5, 90.8])
    b.via("ovp_ok_hot", 59.5, 90.8)
    b.track("ovp_ok_hot", "In1.Cu", 0.3, [59.5, 90.8], [54.5, 90.8],
            [54.5, 96.0], [53.5, 96.0])
    b.via("ovp_ok_hot", 53.5, 96.0)
    b.track("ovp_ok_hot", "B.Cu", 0.3, [53.5, 96.0], [53.5, 72.0],
            [46.0, 72.0], [46.0, 42.0])
    b.via("ovp_ok_hot", 46.0, 42.0)
    b.track("ovp_ok_hot", "In2.Cu", 0.3, [46.0, 42.0],
            [53.0, 39.0], [72.5, 38.8])
    b.via("ovp_ok_hot", 72.5, 38.8)
    b.track("ovp_ok_hot", "F.Cu", 0.3, [72.5, 38.8], "U8.2")
    b.track("ocp_ok_hot", "F.Cu", 0.3, "U8.1", [72.5, 36.0])
    b.via("ocp_ok_hot", 72.5, 36.0)
    b.track("ocp_ok_hot", "B.Cu", 0.3, [72.5, 36.0],
            [71.5, 35.0], [71.5, 17.0], [71.0, 16.0])
    b.via("ocp_ok_hot", 71.0, 16.0)
    b.track("ocp_ok_hot", "F.Cu", 0.3, [71.0, 16.0], "U6.1")
    b.track("bus_fault_hot", "F.Cu", 0.3, "U8.4", [78.5, 37.8])
    b.via("bus_fault_hot", 78.5, 37.8)
    b.track("bus_fault_hot", "B.Cu", 0.3, [78.5, 37.8], [81.0, 37.0],
            [81.0, 39.0])
    b.via("bus_fault_hot", 81.0, 39.0)
    b.track("bus_fault_hot", "F.Cu", 0.3, [81.0, 39.0], [83.635, 39.0], "U9.4")

    # REF25 uses an In2 lane east of the fault logic.  Its west-side B.Cu
    # descent steps around D3's BUS_P pin and the SELV boundary.
    b.track("ref25", "F.Cu", 0.3, "R36.1", [56.4, 99.8])
    b.via("ref25", 56.4, 99.8)
    b.track("ref25", "B.Cu", 0.3, [56.4, 99.8], [56.4, 74.5],
            [53.0, 70.0], [53.0, 41.2])
    b.via("ref25", 53.0, 41.2)
    b.track("ref25", "In2.Cu", 0.3, [53.0, 41.2],
            [56.0, 40.9], [75.5, 40.9], [75.5, 27.0])
    b.via("ref25", 75.5, 27.0)
    b.track("ref25", "F.Cu", 0.3, [75.5, 27.0], "R32.1", "R34.1")
    b.track("ref25", "B.Cu", 0.3, [75.5, 27.0], [82.825, 27.0],
            [82.825, 20.5])
    b.via("ref25", 82.825, 20.5)
    b.track("ref25", "F.Cu", 0.3, [82.825, 20.5], "R31.2",
            [84.2, 20.5], [84.2, 16.0], "U5.1")

    # R5.3 senses the shunt's other Kelvin pin.  It travels through the
    # channel between the local BUS_P capacitors without touching HV_RET.
    b.via("ocp_kelvin_n", 127.77, 16.03)
    b.track("ocp_kelvin_n", "In1.Cu", 0.3, [127.77, 16.03],
            [119.5, 16.6], [117.5, 19.1], [113.5, 19.1],
            [113.5, 16.5], [76.8, 16.5], [76.8, 18.0])
    b.via("ocp_kelvin_n", 76.8, 18.0)
    b.track("ocp_kelvin_n", "F.Cu", 0.3, [76.8, 18.0], "R33.2")
    b.track("ocp_node", "F.Cu", 0.3, "U6.3", [70.8625, 21.7],
            [75.5, 21.7], "R32.2", "R33.1", "C30.1")
    b.track("ocp_thresh", "F.Cu", 0.3, "U6.4", [74.5, 20.8])
    b.via("ocp_thresh", 74.5, 20.8)
    b.track("ocp_thresh", "In2.Cu", 0.3, [74.5, 20.8], [78.0, 21.3])
    b.via("ocp_thresh", 78.0, 21.3)
    b.track("ocp_thresh", "F.Cu", 0.3, [78.0, 21.3], "R34.2", "R35.1", "C31.1")

    # V15 crosses the vacated comparator corridor on In1, leaving the In2
    # BUS_P path continuous at the shunt.  At U2, a short In1 bridge
    # connects the 100 nF C15 bypass to U2.11 without crossing OUTB/VSSB on
    # F.Cu; the V15 portion of that local loop is about 6.2 mm.
    b.track("v15_ls", "In2.Cu", 0.4, [68.5, 21.5], [70.5, 17.0],
            [82.0, 17.0], [82.0, 28.0], [88.42, 28.0], "D2.2")
    b.track("v15_ls", "In1.Cu", 0.4, "D2.2", [88.42, 28.0],
            [118.0, 28.0], [118.0, 38.0], "D1.2")
    b.track("v15_ls", "In1.Cu", 0.4, [106.1, 28.0], [106.1, 34.0])
    b.via("v15_ls", 106.1, 34.0)
    b.track("v15_ls", "F.Cu", 0.3, [106.1, 34.0], [105.905, 37.0], "U2.11")
    b.track("v15_ls", "F.Cu", 0.3, "C16.1", [106.1, 34.0])
    b.track("v15_ls", "In1.Cu", 0.3, [106.1, 34.0], [106.1, 39.6],
            [109.5, 39.6])
    b.via("v15_ls", 106.1, 39.6)
    b.via("v15_ls", 109.5, 39.6)
    b.track("v15_ls", "F.Cu", 0.3, [106.1, 39.6], "U2.11")
    b.track("v15_ls", "F.Cu", 0.3, [109.5, 39.6], "C15.1")
    b.track("v15_ls", "In1.Cu", 0.3, [118.0, 28.0],
            [150.45, 28.0], [150.45, 39.5])
    b.via("v15_ls", 150.45, 39.5)
    b.track("v15_ls", "F.Cu", 0.3, [150.45, 39.5], "U1.11")
    b.track("v15_ls", "In2.Cu", 0.3, [150.45, 39.5],
            [150.45, 40.5], [154.725, 40.5])
    b.via("v15_ls", 154.725, 40.5)
    b.track("v15_ls", "F.Cu", 0.3, [154.725, 40.5], "C8.1", "C9.1")
    return b


if __name__ == "__main__":
    batch_05_aux().write("routes-05.json")
