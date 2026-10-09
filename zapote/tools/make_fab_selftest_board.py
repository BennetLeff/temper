"""Build the fab pass's self-test board (KiCad 10 pcbnew Python).

Every gap on this board is far below any fab-house limit, so each rule the
fab pass emits must fire on it; a rule that does not was not applied by
KiCad (a malformed .kicad_dru is ignored silently). Four copper layers, so
inner-layer rules are exercised too. Measured gaps: copper 0.01 mm (track
pair, SMD pad pair, pad to track), via and PTH hole to copper 0.06 mm (PTH
also on In1.Cu), NPTH hole to copper 0.01 mm, silk text 0.3 mm high and
0.03 mm thick on both silk layers, silk line 0.01 mm from an SMD pad.

With --override-probe it instead builds the local-override probe: an SMD
pad with a 0.05 mm local clearance 0.10 mm from another net's track. KiCad
applies that override before any custom rule, so the fab pass must clear it
(tools/fab_board_copy.py) to report the gap.

Usage: <kicad python> make_fab_selftest_board.py OUT.kicad_pcb [--override-probe]
"""
import pathlib
import sys

import pcbnew

board = pcbnew.BOARD()
board.SetCopperLayerCount(4)


def xy(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def track(net, layer, y, x0, x1):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(xy(x0, y))
    t.SetEnd(xy(x1, y))
    t.SetWidth(pcbnew.FromMM(0.2))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)


edge = pcbnew.PCB_SHAPE(board)
edge.SetShape(pcbnew.SHAPE_T_RECT)
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetStart(xy(0, 0))
edge.SetEnd(xy(40, 30))
board.Add(edge)
a = pcbnew.NETINFO_ITEM(board, "A")
b = pcbnew.NETINFO_ITEM(board, "B")
board.Add(a)
board.Add(b)

if "--override-probe" in sys.argv:
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("J1")
    fp.SetPosition(xy(10, 10))
    board.Add(fp)
    pad = pcbnew.PAD(fp)
    pad.SetNumber("1")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(xy(1, 1))
    pad.SetPosition(xy(10, 10))
    pad.SetNet(a)
    pad.SetLocalClearance(pcbnew.FromMM(0.05))
    fp.Add(pad)
    track(b, pcbnew.F_Cu, 10.7, 5, 15)
    pcbnew.SaveBoard(sys.argv[1], board)
    for suffix in (".kicad_pro", ".kicad_prl"):
        pathlib.Path(sys.argv[1]).with_suffix(suffix).unlink(missing_ok=True)
    sys.exit(0)

# Copper to copper: 0.2 mm tracks 0.21 mm apart (0.01 mm gap).
track(a, pcbnew.F_Cu, 5.0, 5, 35)
track(b, pcbnew.F_Cu, 5.21, 5, 35)

# Via 0.4/0.3 mm; track edge 0.01 mm from its copper, 0.06 mm from its hole.
via = pcbnew.PCB_VIA(board)
via.SetPosition(xy(10, 15))
via.SetWidth(pcbnew.FromMM(0.4))
via.SetDrill(pcbnew.FromMM(0.3))
via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
via.SetNet(a)
board.Add(via)
track(b, pcbnew.B_Cu, 15.31, 5, 15)

fp = pcbnew.FOOTPRINT(board)
fp.SetReference("J1")
fp.SetPosition(xy(25, 15))
board.Add(fp)
# PTH pad 1.1/1.0 mm; track edge 0.01 mm from its copper, 0.06 mm from its hole.
pth = pcbnew.PAD(fp)
pth.SetNumber("1")
pth.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
pth.SetLayerSet(pcbnew.PAD.PTHMask())
pth.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
pth.SetSize(xy(1.1, 1.1))
pth.SetDrillSize(xy(1.0, 1.0))
pth.SetPosition(xy(20, 15))
pth.SetNet(a)
fp.Add(pth)
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
npth = pcbnew.PAD(fp)
npth.SetNumber("")
npth.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
npth.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
npth.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
npth.SetSize(xy(1.0, 1.0))
npth.SetDrillSize(xy(1.0, 1.0))
npth.SetPosition(xy(30, 15))
fp.Add(npth)
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

pcbnew.SaveBoard(sys.argv[1], board)
# SaveBoard also writes default project files; the self-test runs without one.
for suffix in (".kicad_pro", ".kicad_prl"):
    pathlib.Path(sys.argv[1]).with_suffix(suffix).unlink(missing_ok=True)
