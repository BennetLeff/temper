"""Accept solder-mask gang relief on the interlock's 0.5 mm-pitch VSSOP-8 (U4).

Decision 2026-10-08: U4's pads are 0.15 mm apart, and at 2 oz JLC makes no
mask dam below 0.20 mm ("2oz: Min. pad spacing: 0.20 mm (any color)"), so
the pads share one mask opening. Gang relief on a fine-pitch IC is standard
for reflow; the 0.15 mm copper gap itself meets "SMD pad to pad clearance
(different nets) 0.15mm". The footprint records the acceptance with KiCad's
allow_soldermask_bridges attribute, on the board instance and in the vendored
library, so the fab pass's solder-mask check and the library check agree.

Usage: <kicad python> gang_relief_2026_10_08.py BOARD.kicad_pcb
"""
import pathlib
import shutil
import sys
import tempfile

import pcbnew

NAME = "VSSOP-8_2.3x2mm_P0.5mm"
board_path = pathlib.Path(sys.argv[1])
board = pcbnew.LoadBoard(str(board_path))
marked = []
for footprint in board.GetFootprints():
    if footprint.GetFPID().GetUniStringLibItemName() == NAME:
        footprint.SetAllowSolderMaskBridges(True)
        marked.append(footprint.GetReference())
if marked != ["U4"]:
    sys.exit(f"expected only U4 to use {NAME}, found {marked}")
with tempfile.TemporaryDirectory() as tmp:
    out = pathlib.Path(tmp) / board_path.name
    pcbnew.SaveBoard(str(out), board)
    shutil.copyfile(out, board_path)
mod = board_path.parent / "candidate-libs/Package_SO.pretty" / f"{NAME}.kicad_mod"
text = mod.read_text()
if text.count("(attr smd)") != 1:
    sys.exit(f"{mod}: expected exactly one (attr smd)")
mod.write_text(text.replace("(attr smd)", "(attr smd allow_soldermask_bridges)"))
print(f"gang relief accepted on {marked} and in {mod.name}")
