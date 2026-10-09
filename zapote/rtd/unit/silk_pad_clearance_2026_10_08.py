"""Clear J2's silkscreen from its pads (JLC "Pad To Silkscreen 0.15mm").

J2's body outline ran 0.075 mm from pads 1, 2, 9 and 10, and its pin-1
chamfer and marker sat as close to pad 1. The outline's top and bottom edges
and the chamfer move 0.1 mm away from the pad field and the marker 0.1 mm
left: every gap becomes at least 0.175 mm and the outline still traces the
body. The same change is made to the vendored library footprint in
candidate-libs, so KiCad's footprint-vs-library check stays clean. The board is
written through a temporary directory so the project files are untouched.

Usage: <kicad python> silk_pad_clearance_2026_10_08.py BOARD.kicad_pcb
"""
import pathlib
import shutil
import sys
import tempfile

import pcbnew

STEP = pcbnew.FromMM(0.1)
LIBRARY = "candidate-libs/Temper_RTD.pretty"
NAME = "FTSH-105-01-F-D_2x5_P1.27mm"
# The same 0.1 mm moves in footprint coordinates (pads span y -3.065..3.065).
LIBRARY_EDITS = [
    ("(fp_rect (start -1.75 -3.2) (end 1.75 3.2)", "(fp_rect (start -1.75 -3.3) (end 1.75 3.3)"),
    ("(fp_line (start -1.75 -3.2) (end -1.15 -3.2)", "(fp_line (start -1.75 -3.3) (end -1.15 -3.3)"),
    ("(fp_circle (center -1.42 -2.54) (end -1.27 -2.54)", "(fp_circle (center -1.52 -2.54) (end -1.37 -2.54)"),
]


def clear(footprint):
    pads = [p.GetBoundingBox() for p in footprint.Pads()]
    top = min(b.GetTop() for b in pads)
    for shape in footprint.GraphicalItems():
        if shape.GetLayer() != pcbnew.F_SilkS:
            continue
        kind = shape.GetShape()
        if kind == pcbnew.SHAPE_T_RECT:
            start, end = shape.GetStart(), shape.GetEnd()
            y0, y1 = sorted((start.y, end.y))
            shape.SetStart(pcbnew.VECTOR2I(start.x, y0 - STEP if start.y == y0 else y1 + STEP))
            shape.SetEnd(pcbnew.VECTOR2I(end.x, y0 - STEP if end.y == y0 else y1 + STEP))
        elif kind == pcbnew.SHAPE_T_SEGMENT and shape.GetBoundingBox().GetBottom() < top:
            shape.Move(pcbnew.VECTOR2I(0, -STEP))
        elif kind == pcbnew.SHAPE_T_CIRCLE:
            shape.Move(pcbnew.VECTOR2I(-STEP, 0))
        else:
            sys.exit(f"unexpected J2 silk shape {shape.GetShapeStr()}")


board_path = pathlib.Path(sys.argv[1])
board = pcbnew.LoadBoard(str(board_path))
clear(next(fp for fp in board.GetFootprints() if fp.GetReference() == "J2"))
# The vendored footprint gets the same change as a text edit; re-saving it
# through pcbnew would reformat the whole file.
mod = board_path.parent / LIBRARY / f"{NAME}.kicad_mod"
text = mod.read_text()
for old, new in LIBRARY_EDITS:
    if text.count(old) != 1:
        sys.exit(f"{mod}: expected exactly one {old!r}")
    text = text.replace(old, new)
mod.write_text(text)
with tempfile.TemporaryDirectory() as tmp:
    out = pathlib.Path(tmp) / board_path.name
    pcbnew.SaveBoard(str(out), board)
    shutil.copyfile(out, board_path)
print(f"J2 silk moved clear of its pads on the board and in {LIBRARY}/{NAME}")
