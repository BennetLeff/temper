"""Write cad/tools/rev_d_pads.json from the Rev D board (run with KiCad's Python).

python3 cad/tools/dump_rev_d_pads.py REV_D.kicad_pcb   (git show 79f4edbba:./cad/temper-lcr.kicad_pcb)
Per ref: pad -> [x, y, net, half-width, half-height] (axis-aligned pad bounding box, mm) and
'_courtyard' -> [x0, y0, x1, y1].  cad/tools/rev_e.py prunes Rev D copper against these.
"""
import json
import sys
from pathlib import Path

import pcbnew as k

board = k.LoadBoard(sys.argv[1])
out = {}
for fp in board.GetFootprints():
    rec = {}
    for p in fp.Pads():
        if not p.GetNumber():
            continue
        c, bb = p.GetPosition(), p.GetBoundingBox()
        rec[p.GetNumber()] = [round(k.ToMM(c.x), 4), round(k.ToMM(c.y), 4), p.GetNetname(),
                              round(k.ToMM(bb.GetWidth()) / 2, 4), round(k.ToMM(bb.GetHeight()) / 2, 4)]
    cy = fp.GetCourtyard(k.F_CrtYd).BBox() if fp.GetCourtyard(k.F_CrtYd).OutlineCount() else fp.GetBoundingBox()
    rec['_courtyard'] = [round(k.ToMM(v), 4) for v in (cy.GetLeft(), cy.GetTop(), cy.GetRight(), cy.GetBottom())]
    out[fp.GetReference()] = rec
path = Path(__file__).resolve().parent / 'rev_d_pads.json'
path.write_text(json.dumps(out, separators=(',', ':')) + '\n')
print('wrote', path, len(out))
