"""Dump native copper (pads, tracks, vias, zone fills, keepouts) to JSON for hand-routing views.

Run with KiCad's bundled Python:  <kicad-python> cad/tools/dump_copper.py OUT.json [board]
Read-only: the board file is never saved.
"""
import json
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
out_path = Path(sys.argv[1])
board = k.LoadBoard(str(Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "temper-lcr.kicad_pcb"))
MM = 1e-6
LAYERS = {k.F_Cu: "F.Cu", k.In1_Cu: "In1.Cu", k.In2_Cu: "In2.Cu", k.B_Cu: "B.Cu"}


def polys(ps):
    res = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        res.append([[o.CPoint(j).x * MM, o.CPoint(j).y * MM] for j in range(o.PointCount())])
    return res


items = []
for t in board.GetTracks():
    if isinstance(t, k.PCB_VIA):
        items.append({"kind": "via", "net": t.GetNetname(), "x": t.GetPosition().x * MM,
                      "y": t.GetPosition().y * MM, "d": t.GetWidth(k.F_Cu) * MM})
    else:
        items.append({"kind": "track", "net": t.GetNetname(), "layer": LAYERS[t.GetLayer()],
                      "a": [t.GetStart().x * MM, t.GetStart().y * MM],
                      "b": [t.GetEnd().x * MM, t.GetEnd().y * MM], "w": t.GetWidth() * MM})
for f in board.GetFootprints():
    cy = f.GetCourtyard(k.F_CrtYd)
    items.append({"kind": "fp", "ref": f.GetReference(), "x": f.GetPosition().x * MM,
                  "y": f.GetPosition().y * MM, "courtyard": polys(cy) if cy.OutlineCount() else []})
    for p in f.Pads():
        for lid, name in LAYERS.items():
            if p.IsOnLayer(lid):
                sh = p.GetEffectivePolygon(lid, k.ERROR_INSIDE)
                items.append({"kind": "pad", "ref": f.GetReference(), "num": p.GetNumber(),
                              "net": p.GetNetname(), "layer": name, "polys": polys(sh),
                              "pth": p.GetAttribute() == k.PAD_ATTRIB_PTH})
for z in board.Zones():
    if z.GetIsRuleArea():
        for lid, name in LAYERS.items():
            if z.IsOnLayer(lid):
                items.append({"kind": "keepout", "layer": name, "name": z.GetZoneName(),
                              "polys": polys(z.Outline())})
    else:
        for lid, name in LAYERS.items():
            if z.IsOnLayer(lid) and z.HasFilledPolysForLayer(lid):
                items.append({"kind": "fill", "layer": name, "net": z.GetNetname(),
                              "polys": polys(z.GetFilledPolysList(lid))})
out_path.write_text(json.dumps({"items": items}))
print(f"{len(items)} items -> {out_path}")
