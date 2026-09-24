"""Hand-authored copper for the isolated SELV programming coupon.

Run after build_board.py with KiCad's bundled pcbnew Python. The short paths
are intentionally explicit so the PCB can be reviewed net by net.
"""

from pathlib import Path

import pcbnew


BOARD_PATH = Path(__file__).resolve().parent / "native/service_coupon.kicad_pcb"
BOARD = pcbnew.LoadBoard(str(BOARD_PATH))
assert not list(BOARD.GetTracks()), "regenerate the placed board before routing"
NETS = {name: BOARD.FindNet(name) for name in (
    "service_txd0", "target_txd0", "rxd0", "en_n", "io0",
    "target_3v3_sense", "selv_return",
)}


def pt(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def track(name, layer, points):
    for a, b in zip(points, points[1:]):
        segment = pcbnew.PCB_TRACK(BOARD)
        segment.SetStart(pt(*a))
        segment.SetEnd(pt(*b))
        segment.SetWidth(pcbnew.FromMM(0.25))
        segment.SetLayer(layer)
        segment.SetNet(NETS[name])
        BOARD.Add(segment)


def via(name, x, y):
    hole = pcbnew.PCB_VIA(BOARD)
    hole.SetPosition(pt(x, y))
    hole.SetWidth(pcbnew.FromMM(0.8))
    hole.SetDrill(pcbnew.FromMM(0.4))
    hole.SetViaType(pcbnew.VIATYPE_THROUGH)
    hole.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    hole.SetNet(NETS[name])
    BOARD.Add(hole)


# Target output TXD0 has the source's 499 R resistor. Route separately on
# either side; D1 shunts at the programmer contact, before R1.
track("service_txd0", pcbnew.F_Cu, [
    (20.73, 25.635), (20.73, 27), (17, 27), (17, 15), (33.3, 15),
])
track("service_txd0", pcbnew.F_Cu, [
    (33.3, 15), (32, 15), (32, 12.5), (41, 12.5), (43.175, 14.675), (43.175, 16),
])
track("target_txd0", pcbnew.F_Cu, [
    (44.825, 16), (53, 16), (56, 19),
])

# Receive line crosses to B.Cu immediately outside the programmer footprint.
track("rxd0", pcbnew.F_Cu, [(20.73, 24.365), (20.73, 22.5), (19, 20.5)])
via("rxd0", 19, 20.5)
track("rxd0", pcbnew.B_Cu, [
    (19, 20.5), (19, 18), (54, 18), (54, 21.54), (56, 21.54),
])
track("rxd0", pcbnew.F_Cu, [(34.3, 20), (32.5, 20)])
via("rxd0", 32.5, 20)
track("rxd0", pcbnew.B_Cu, [(32.5, 20), (32.5, 18)])

# EN and IO0 are just requests to the already-owned target pull-ups. This
# coupon does not prove a reset safely removes power-stage permission.
track("en_n", pcbnew.F_Cu, [(22, 25.635), (22, 28)])
via("en_n", 22, 28)
track("en_n", pcbnew.B_Cu, [
    (22, 28), (29, 28), (29, 24.08), (56, 24.08),
])
track("en_n", pcbnew.F_Cu, [(35.3, 25), (33.5, 25)])
via("en_n", 33.5, 25)
track("en_n", pcbnew.B_Cu, [(33.5, 25), (33.5, 24.08)])

track("io0", pcbnew.F_Cu, [(22, 24.365), (22, 21.5)])
via("io0", 22, 21.5)
track("io0", pcbnew.B_Cu, [(22, 21.5), (49, 21.5)])
via("io0", 49, 21.5)
track("io0", pcbnew.F_Cu, [
    (49, 21.5), (53, 21.5), (53, 26.62), (56, 26.62),
])
track("io0", pcbnew.F_Cu, [(36.3, 30), (34.5, 30)])
via("io0", 34.5, 30)
track("io0", pcbnew.B_Cu, [
    (34.5, 30), (34.5, 28), (47, 28), (47, 26.62), (56, 26.62),
])

# 3V3 is an intended target reference. This pass-through cannot prevent an
# externally powered programmer from injecting current onto that rail.
track("target_3v3_sense", pcbnew.F_Cu, [(23.27, 25.635), (23.27, 29)])
via("target_3v3_sense", 23.27, 29)
track("target_3v3_sense", pcbnew.B_Cu, [
    (23.27, 29), (23.27, 35), (51, 35), (51, 29.16), (56, 29.16),
])

# Return is a traced spine, no blanket plane. That makes all four ESD return
# paths and the single SELV return connection visible during review.
track("selv_return", pcbnew.F_Cu, [
    (23.27, 24.365), (23.27, 22), (30, 22), (30, 18), (38, 18),
])
track("selv_return", pcbnew.F_Cu, [
    (34.7, 15), (38, 15), (38, 20), (35.7, 20),
])
track("selv_return", pcbnew.F_Cu, [
    (38, 20), (40, 20), (40, 25), (36.7, 25),
])
track("selv_return", pcbnew.F_Cu, [
    (40, 25), (42, 25), (42, 30), (37.7, 30),
])
track("selv_return", pcbnew.F_Cu, [
    (42, 30), (47, 30), (47, 31.7), (56, 31.7),
])

for footprint in BOARD.GetFootprints():
    footprint.Reference().SetLayer(pcbnew.F_Fab)
    footprint.Reference().SetVisible(False)


def silk(text, x, y, height=0.8):
    label = pcbnew.PCB_TEXT(BOARD)
    label.SetText(text)
    label.SetPosition(pt(x, y))
    label.SetTextSize(pt(height, height))
    label.SetTextThickness(pcbnew.FromMM(0.15))
    label.SetLayer(pcbnew.F_SilkS)
    BOARD.Add(label)


silk("UART0 SELV LAB ONLY", 38, 38, 1.0)
silk("P1", 15, 25, 0.9)
for legend, y in (
    ("TX", 19.0), ("RX", 21.54), ("EN", 24.08),
    ("IO0", 26.62), ("3V3", 29.16), ("GND", 31.7),
):
    silk(legend, 61, y)

pcbnew.SaveBoard(str(BOARD_PATH), BOARD)
