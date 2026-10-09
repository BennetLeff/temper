"""Build the fab pass's self-test board (KiCad 10 pcbnew Python).

Every gap on this board is far below any fab-house limit, so each rule the
fab pass emits must fire on it; a rule that does not was not applied by
KiCad (a malformed .kicad_dru is ignored silently). Measured gaps:
copper 0.01 mm, via and PTH hole to copper 0.06 mm, NPTH hole to copper
0.01 mm, silk text 0.3 mm high and 0.03 mm thick on both silk layers.

Usage: <kicad python> make_fab_selftest_board.py OUT.kicad_pcb
"""
import pathlib
import sys

import pcbnew

board = pcbnew.BOARD()


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
