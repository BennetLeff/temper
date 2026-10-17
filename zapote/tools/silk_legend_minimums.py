"""Raise visible silkscreen text to a fab profile's legend minimums, in place.

Height goes up to minimum_silk_text_height_mm and stroke to
minimum_silk_line_width_mm; each text keeps its character width (the vendor
limit is on height), so a legend grows no wider and keeps clear of its
neighbours. --move-field REF X Y moves a footprint's reference field (mm)
where the taller text would collide. pcbnew writes into a temporary
directory and only the .kicad_pcb is copied back: SaveBoard would otherwise
rewrite the board's project files.

Usage: <kicad python> silk_legend_minimums.py BOARD.kicad_pcb PROFILE.json
       [--move-field REF X Y]...
"""
import json
import pathlib
import shutil
import sys
import tempfile

import pcbnew

board_path = pathlib.Path(sys.argv[1])
limits = json.loads(pathlib.Path(sys.argv[2]).read_text())["limits"]
moves = {}
rest = sys.argv[3:]
while rest:
    if rest[0] != "--move-field" or len(rest) < 4:
        sys.exit(__doc__)
    moves[rest[1]] = (float(rest[2]), float(rest[3]))
    rest = rest[4:]

board = pcbnew.LoadBoard(str(board_path))
height = pcbnew.FromMM(limits["minimum_silk_text_height_mm"])
stroke = pcbnew.FromMM(limits["minimum_silk_line_width_mm"])
texts = [t for t in board.GetDrawings() if isinstance(t, pcbnew.PCB_TEXT)]
footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
for fp in footprints.values():
    texts += list(fp.GetFields()) + [t for t in fp.GraphicalItems() if isinstance(t, pcbnew.PCB_TEXT)]
changed = 0
for t in texts:
    if t.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS) or not t.IsVisible():
        continue
    if t.GetTextHeight() < height or t.GetTextThickness() < stroke:
        t.SetTextHeight(max(t.GetTextHeight(), height))
        t.SetTextThickness(max(t.GetTextThickness(), stroke))
        changed += 1
for ref, (x, y) in moves.items():
    footprints[ref].Reference().SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
with tempfile.TemporaryDirectory() as tmp:
    out = pathlib.Path(tmp) / board_path.name
    pcbnew.SaveBoard(str(out), board)
    shutil.copyfile(out, board_path)
print(json.dumps({"board": str(board_path), "texts_changed": changed, "moved": sorted(moves)}))
