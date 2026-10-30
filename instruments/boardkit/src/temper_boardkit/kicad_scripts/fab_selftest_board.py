"""Build the fab pass's self-test board (KiCad 10 pcbnew Python).

From zapote/tools/make_fab_selftest_board.py (origin/main, 2026-10-29), extended for the rules boardkit adds
(track width, rings, drill sizes, hole-to-hole, copper to edge).  Every feature below is far outside any
fab-house limit, so each rule temper_boardkit.fab emits must fire on this board; a rule that does not was not
applied by KiCad (a malformed .kicad_dru is ignored silently).  Four copper layers, so inner-layer rules are
exercised too.

  copper 0.01 mm (track pair, SMD pad pair, pad to track); via and PTH hole to copper 0.06 mm (PTH also on
  In1.Cu); NPTH hole to copper 0.01 mm; silk text 0.3 mm high, 0.03 mm thick on both silk layers; silk line
  0.01 mm from an SMD pad; a 0.05 mm track; a via with a 0.01 mm ring and one with a 0.1 mm drill; a PTH with
  a 0.05 mm ring, one with a 0.1 mm drill and one with a 6.5 mm drill; a 0.3 mm NPTH; PTH holes 0.3 mm apart; via holes 0.15 mm apart;
  a track 0.05 mm from the board edge.

Usage: <kicad python> fab_selftest_board.py OUT.kicad_pcb
"""
import pathlib
import sys

import pcbnew

board = pcbnew.BOARD()
board.SetCopperLayerCount(4)


def xy(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def track(net, layer, y, x0, x1, width=0.2):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(xy(x0, y))
    t.SetEnd(xy(x1, y))
    t.SetWidth(pcbnew.FromMM(width))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)


def via(net, x, y, d, drill):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(xy(x, y))
    v.SetWidth(pcbnew.FromMM(d))
    v.SetDrill(pcbnew.FromMM(drill))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net)
    board.Add(v)


def hole_pad(fp, number, x, y, size, drill, net=None, plated=True):
    p = pcbnew.PAD(fp)
    p.SetNumber(number)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if plated else pcbnew.PAD_ATTRIB_NPTH)
    p.SetLayerSet(pcbnew.PAD.PTHMask() if plated else pcbnew.PAD.UnplatedHoleMask())
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(xy(size, size))
    p.SetDrillSize(xy(drill, drill))
    p.SetPosition(xy(x, y))
    if net is not None:
        p.SetNet(net)
    fp.Add(p)
    return p


edge = pcbnew.PCB_SHAPE(board)
edge.SetShape(pcbnew.SHAPE_T_RECT)
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetStart(xy(0, 0))
edge.SetEnd(xy(60, 40))
board.Add(edge)
a = pcbnew.NETINFO_ITEM(board, "A")
b = pcbnew.NETINFO_ITEM(board, "B")
board.Add(a)
board.Add(b)

# Copper to copper: 0.2 mm tracks 0.21 mm apart (0.01 mm gap).
track(a, pcbnew.F_Cu, 5.0, 5, 35)
track(b, pcbnew.F_Cu, 5.21, 5, 35)

# Via 0.4/0.3 mm; track edge 0.01 mm from its copper, 0.06 mm from its hole.
via(a, 10, 15, 0.4, 0.3)
track(b, pcbnew.B_Cu, 15.31, 5, 15)

fp = pcbnew.FOOTPRINT(board)
fp.SetReference("J1")
fp.SetPosition(xy(25, 15))
board.Add(fp)
# PTH pad 1.1/1.0 mm (0.05 mm ring); track edge 0.01 mm from its copper, 0.06 mm from its hole.
hole_pad(fp, "1", 20, 15, 1.1, 1.0, a)
track(b, pcbnew.B_Cu, 15.66, 17, 23)
# The same PTH on In1.Cu: track edge 0.01 mm from its copper, 0.06 mm from its hole.
in1_x = 20 + 0.55 + 0.01 + 0.1
t = pcbnew.PCB_TRACK(board)
t.SetStart(xy(in1_x, 12))
t.SetEnd(xy(in1_x, 18))
t.SetWidth(pcbnew.FromMM(0.2))
t.SetLayer(pcbnew.In1_Cu)
t.SetNet(b)
board.Add(t)
# SMD pads 0.5 x 1 mm, 0.01 mm apart.
for number, x, net in (("2", 10.0, a), ("3", 10.51, b)):
    smd = pcbnew.PAD(fp)
    smd.SetNumber(number)
    smd.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    smd.SetLayerSet(pcbnew.PAD.SMDMask())
    smd.SetShape(pcbnew.PAD_SHAPE_RECT)
    smd.SetSize(xy(0.5, 1.0))
    smd.SetPosition(xy(x, 20))
    smd.SetNet(net)
    fp.Add(smd)
# Silk line 0.12 mm wide, its edge 0.01 mm from SMD pad 2 (top edge y = 19.5).
silk = pcbnew.PCB_SHAPE(board)
silk.SetShape(pcbnew.SHAPE_T_SEGMENT)
silk.SetLayer(pcbnew.F_SilkS)
silk.SetStart(xy(9.6, 19.43))
silk.SetEnd(xy(10.4, 19.43))
silk.SetWidth(pcbnew.FromMM(0.12))
board.Add(silk)
# NPTH 1.0 mm; track edge 0.01 mm from the hole.
hole_pad(fp, "", 30, 15, 1.0, 1.0, plated=False)
track(b, pcbnew.B_Cu, 15.61, 27, 33)

for layer, x in ((pcbnew.F_SilkS, 10), (pcbnew.B_SilkS, 30)):
    text = pcbnew.PCB_TEXT(board)
    text.SetText("FAB")
    text.SetLayer(layer)
    text.SetPosition(xy(x, 25))
    text.SetTextSize(xy(0.3, 0.3))
    text.SetTextThickness(pcbnew.FromMM(0.03))
    if layer == pcbnew.B_SilkS:
        text.SetMirrored(True)
    board.Add(text)

# boardkit additions, right half of the board, clear of the features above.
track(a, pcbnew.F_Cu, 30, 40, 50, width=0.05)               # track width 0.05 mm
via(a, 42, 34, 0.32, 0.3)                                   # via ring 0.01 mm
via(a, 46, 34, 0.4, 0.1)                                    # via drill 0.1 mm
via(b, 50, 34, 0.4, 0.3)                                    # via holes 0.15 mm apart (same net)
via(b, 50.45, 34, 0.4, 0.3)
fp2 = pcbnew.FOOTPRINT(board)
fp2.SetReference("J2")
fp2.SetPosition(xy(48, 15))
board.Add(fp2)
hole_pad(fp2, "1", 42, 10, 1.6, 1.0, a)                     # PTH holes 0.3 mm apart, same net
hole_pad(fp2, "2", 43.3, 10, 1.6, 1.0, a)
hole_pad(fp2, "3", 51, 12, 6.8, 6.5, b)                     # PTH drill 6.5 mm (> 6.3)
hole_pad(fp2, "4", 46, 20, 0.6, 0.1, a)                     # PTH drill 0.1 mm
hole_pad(fp2, "", 42, 20, 0.3, 0.3, plated=False)           # NPTH drill 0.3 mm
track(b, pcbnew.B_Cu, 39.875, 20, 30)                       # 0.2 mm track, edge 0.025 mm from the board edge

pcbnew.SaveBoard(sys.argv[1], board)
# SaveBoard also writes default project files; the self-test runs without one.
for suffix in (".kicad_pro", ".kicad_prl"):
    pathlib.Path(sys.argv[1]).with_suffix(suffix).unlink(missing_ok=True)
