"""Rev F study: dump the Rev E board's per-part geometry once, so the floorplan script runs without KiCad.

<kicad-python> cad/tools/rev_f_inventory.py [BOARD.kicad_pcb] [OUT.json]

Writes, per footprint: reference, sheet (block), position, rotation, side, courtyard area and the
courtyard bounding box relative to the footprint origin (board orientation), pad count and the
nets on its pads; plus every net's pad list and track length per layer. Read-only on the board.
Default input is cad/temper-lcr.kicad_pcb (Rev E at the branch point), default output
validation/rev-f-floorplan/rev-e-inventory.json.
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
MM = 1e-6
src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'temper-lcr.kicad_pcb'
dest = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT.parent / 'validation/rev-f-floorplan/rev-e-inventory.json'
board = k.LoadBoard(str(src))
design = json.loads((ROOT / 'design.json').read_text())
sheet = {p['ref']: p['sheet'] for p in design['parts']}

parts = {}
for f in board.GetFootprints():
    ref = f.GetReference()
    x, y = f.GetPosition().x * MM, f.GetPosition().y * MM
    cy = f.GetCourtyard(k.F_CrtYd if not f.IsFlipped() else k.B_CrtYd)
    if cy.OutlineCount():
        bb = cy.BBox()
        box = [bb.GetX() * MM - x, bb.GetY() * MM - y, bb.GetRight() * MM - x, bb.GetBottom() * MM - y]
        area = cy.Area() * MM * MM
    else:
        bb = f.GetBoundingBox(False)
        box = [bb.GetX() * MM - x, bb.GetY() * MM - y, bb.GetRight() * MM - x, bb.GetBottom() * MM - y]
        area = (box[2] - box[0]) * (box[3] - box[1])
    parts[ref] = {'sheet': sheet.get(ref, 'mechanical'), 'at': [round(x, 3), round(y, 3)],
                  'rot': f.GetOrientationDegrees(), 'side': 'B' if f.IsFlipped() else 'F',
                  'courtyard_mm2': round(area, 3), 'courtyard_box_rel': [round(v, 3) for v in box],
                  'tht': any(p.GetAttribute() == k.PAD_ATTRIB_PTH for p in f.Pads()),
                  'pads': {p.GetNumber(): [round(p.GetPosition().x * MM, 3), round(p.GetPosition().y * MM, 3),
                                           p.GetNetname()] for p in f.Pads() if p.GetNumber()}}

tracks = defaultdict(lambda: defaultdict(float))
vias = defaultdict(int)
for t in board.GetTracks():
    if isinstance(t, k.PCB_VIA):
        vias[t.GetNetname()] += 1
    else:
        tracks[t.GetNetname()][board.GetLayerName(t.GetLayer())] += t.GetLength() * MM
edge = board.GetBoardEdgesBoundingBox()
out = {'board': str(src.name), 'board_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
       'edge_mm': [edge.GetX() * MM, edge.GetY() * MM, edge.GetRight() * MM, edge.GetBottom() * MM],
       'parts': parts,
       'track_mm': {n: {l: round(v, 2) for l, v in d.items()} for n, d in sorted(tracks.items())},
       'vias': dict(sorted(vias.items()))}
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, indent=1) + '\n')
print(f'{len(parts)} footprints, {len(tracks)} routed nets -> {dest}')
