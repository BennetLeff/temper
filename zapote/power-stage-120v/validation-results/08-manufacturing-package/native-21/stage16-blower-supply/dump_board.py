#!/usr/bin/env python3
"""Stage-16 board model: native-21 stage 15b placement + copper, read-only from the unit.

    KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $KP dump_board.py board/dump.json

Inputs (never written; the board is copied to a temp file before KiCad loads it):
  UNIT/native-21/section.kicad_pcb    placed, unrouted board (place.py output; stage-15b poses: no part
                                      has moved since stage 14, DECISIONS items 13/14 "no part moves")
  UNIT/native-21/layout/board_only21.json  mounting holes (H1 metal, H2-H7 nylon), test points, fiducials
  UNIT/native-21/layout/copper.json   authored copper, sha256 a831e90c... = the stage-15b copper of record
                                      (verification/final-manifest.json copper_json_sha256)
Pour OUTLINES are used, not KiCad's fills. A fill is a subset of its outline, so every copper distance
from this model is a lower bound on the routed board's (conservative for clearance checks).
"""
import hashlib
import json
import shutil
import sys
import tempfile

import pcbnew

UNIT = "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v"
out = sys.argv[1]
src = UNIT + "/native-21/section.kicad_pcb"
tmp = tempfile.mkdtemp() + "/board.kicad_pcb"
shutil.copy(src, tmp)
b = pcbnew.LoadBoard(tmp)
mm = pcbnew.ToMM

fps, pads, padpos = [], [], {}
for f in b.GetFootprints():
    ref = f.GetReference()
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
    fps.append({"ref": ref, "value": f.GetValue(), "at": [mm(f.GetPosition().x), mm(f.GetPosition().y)],
                "rot": f.GetOrientationDegrees(),
                "crtyd": [mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())]})
    for p in f.Pads():
        lay = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        sp = p.GetEffectivePolygon(lay)
        o = sp.Outline(0) if sp.OutlineCount() else None
        pts = [(mm(o.CPoint(k).x), mm(o.CPoint(k).y)) for k in range(o.PointCount())] if o else []
        at = [mm(p.GetPosition().x), mm(p.GetPosition().y)]
        padpos[f"{ref}.{p.GetNumber()}"] = at
        pads.append({"ref": ref, "pad": p.GetNumber(), "net": p.GetNetname(), "at": at, "pts": pts,
                     "tht": p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                     "npth": p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH})
bo = json.load(open(UNIT + "/native-21/layout/board_only21.json"))
for h in bo["mounting_holes"]:          # 7 mm courtyard, as the routed board's MountingHole_3.2mm_M3
    x, y = h["at"]
    fps.append({"ref": h["ref"], "value": h["kind"], "at": [x, y], "rot": 0, "crtyd": [x - 3.5, y - 3.5, x + 3.5, y + 3.5]})
for t in bo["test_points"]:
    x, y = t["at"]
    fps.append({"ref": t["ref"], "value": "TP " + t["net"], "at": [x, y], "rot": 0, "crtyd": [x - 1, y - 1, x + 1, y + 1]})
for f in bo["fiducials"]:
    x, y = f["at"]
    fps.append({"ref": f.get("ref", "FID"), "value": "fiducial", "at": [x, y], "rot": 0, "crtyd": [x - 1.8, y - 1.8, x + 1.8, y + 1.8]})
raw = open(UNIT + "/native-21/layout/copper.json", "rb").read()
cu = json.loads(raw)
tracks = []
for t in cu["tracks"]:
    pts = [padpos[q] if isinstance(q, str) else q for q in t["points"] if not isinstance(q, str) or q in padpos]
    for a, c in zip(pts, pts[1:]):
        tracks.append({"a": a, "b": c, "w": t["width"], "layer": t["layer"], "net": t["net"]})
vias = [{"at": v["at"], "d": v["size"], "net": v["net"]} for v in cu["vias"]]
zones = [{"net": z["net"], "layer": z["layer"], "pts": z["outline"], "holes": z.get("holes", [])} for z in cu["zones"]]
json.dump({"board": src, "copper_json_sha256": hashlib.sha256(raw).hexdigest(), "zones_are": "outlines (lower-bound distances)",
           "footprints": fps, "pads": pads, "tracks": tracks, "vias": vias, "zones": zones}, open(out, "w"))
print(len(fps), "footprints", len(pads), "pads", len(tracks), "track segments", len(vias), "vias", len(zones),
      "zone outlines; copper.json", hashlib.sha256(raw).hexdigest()[:8])
