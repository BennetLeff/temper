#!/usr/bin/env python3
"""Create a documentation-only board with legible reference labels."""
from pathlib import Path
import pcbnew as k

root = Path(__file__).resolve().parent.parent
board = k.LoadBoard(str(root / "cad/temper-lcr.kicad_pcb"))
for footprint in board.GetFootprints():
    footprint.GetField('Value').SetVisible(False)
    ref = footprint.GetField('Reference')
    ref.SetLayer(k.F_Fab)
    ref.SetPosition(footprint.GetPosition())
    passive = footprint.GetReference().startswith(("R", "C"))
    ref.SetTextAngle(footprint.GetOrientation() if passive else k.EDA_ANGLE(0, k.DEGREES_T))
    size = .5 if passive else .8
    ref.SetTextSize(k.VECTOR2I(k.FromMM(size), k.FromMM(size)))
    ref.SetTextThickness(k.FromMM(.10))
    for item in list(footprint.GraphicalItems()):
        if isinstance(item, k.PCB_TEXT) and not isinstance(item, k.PCB_FIELD):
            item.SetLayer(k.Dwgs_User)
k.SaveBoard(str(root / "build/assembly-preview.kicad_pcb"), board)
