#!/usr/bin/env python3
"""Add native-21's board-only parts (board_only21.json) to a built board, in place.

    KICAD_PY native-21/layout/board_only21.py <board.kicad_pcb>

Bring-up test points (TestPoint_Pad_D1.0mm on their net), fiducials (Fiducial_1mm_Mask3mm) and
mounting holes (MountingHole_3.2mm_M3; nylon-only holes carry a NYLON note on F.Fab). All are board-only
and excluded from the BOM and position files, so schematic parity, the BOM and the CPL are unchanged.
Chosen by plan_board_only21.py.
"""
import json
import sys
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]

HERE = Path(__file__).resolve().parent
LIB = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
spec = json.loads((HERE / "board_only21.json").read_text())
if sys.argv[1] == "--fix-labels":
    # bottom-side test points have no top legend spot: designator on the assembly drawing (F.Fab) at the pad
    labels_path = HERE.parent / "reference-labels.json"
    lab = json.loads(labels_path.read_text())
    for t in spec["test_points"]:
        e = lab["references"].get(t["ref"])
        if e is not None and t.get("side") == "B":
            e.update(at=[round(t["at"][0], 3), round(t["at"][1], 3)], layer="F.Fab")
    labels_path.write_text(json.dumps(lab, indent=1) + "\n")
    sys.exit(0)
if sys.argv[1] == "--unmirror":
    # after the labels are applied: a flipped (bottom) footprint's designator moved to F.Fab reads mirrored
    board = pcbnew.LoadBoard(sys.argv[2])
    bottom = {t["ref"] for t in spec["test_points"] if t.get("side") == "B"}
    for fp in board.GetFootprints():
        if fp.GetReference() in bottom and fp.Reference().GetLayer() in (pcbnew.F_Fab, pcbnew.F_SilkS):
            fp.Reference().SetMirrored(False)
    pcbnew.SaveBoard(sys.argv[2], board)
    sys.exit(0)
board = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.FromMM


def place(lib, name, ref, value, at, net=None, bottom=False):
    fp = pcbnew.FootprintLoad(str(LIB / f"{lib}.pretty"), name)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(pcbnew.VECTOR2I(mm(at[0]), mm(at[1])))
    fp.SetBoardOnly(True)
    fp.SetExcludedFromBOM(True)
    fp.SetExcludedFromPosFiles(True)
    fp.SetField("SourceInstance", f"board-only:{ref}")     # the label tool's provenance fields
    fp.SetField("MPN", "board-only (no part)")
    board.Add(fp)
    if bottom:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    if net:
        n = board.FindNet(net)
        if n is None:
            raise SystemExit(f"{ref}: net {net} not on the board")
        for pad in fp.Pads():
            pad.SetNet(n)
    return fp


for t in spec["test_points"]:
    place("TestPoint", "TestPoint_Pad_D1.0mm", t["ref"], t["net"], t["at"], t["net"], bottom=t.get("side") == "B")
for f in spec["fiducials"]:
    place("Fiducial", "Fiducial_1mm_Mask3mm", f["ref"], "FIDUCIAL", f["at"])
for h in spec["mounting_holes"]:
    fp = place("MountingHole", "MountingHole_3.2mm_M3", h["ref"], "M3 NYLON ONLY" if h["kind"] == "nylon" else "M3", h["at"])
    if h["kind"] == "nylon":
        txt = pcbnew.PCB_TEXT(board)
        txt.SetText("NYLON")
        txt.SetLayer(pcbnew.F_Fab)                       # assembly drawing (silk legend spots belong to designators)
        txt.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
        txt.SetTextThickness(mm(0.15))
        txt.SetPosition(pcbnew.VECTOR2I(mm(h["at"][0]), mm(h["at"][1] + 4.6)))
        board.Add(txt)
# silk marks (review M12): board ID, HV warning, nylon legend, PE, nylon washer rings, BR1 outline
for m in spec.get("silk", []):
    if m["kind"] == "text":
        txt = pcbnew.PCB_TEXT(board)
        txt.SetText("\n".join(m["lines"]))
        txt.SetLayer(pcbnew.F_SilkS)
        txt.SetTextSize(pcbnew.VECTOR2I(mm(m["size"]), mm(m["size"])))
        txt.SetTextThickness(mm(max(0.15, m["size"] * 0.15)))
        txt.SetPosition(pcbnew.VECTOR2I(mm(m["at"][0]), mm(m["at"][1])))
        board.Add(txt)
    elif m["kind"] == "ring":
        c = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_CIRCLE)
        c.SetLayer(pcbnew.F_SilkS)
        c.SetWidth(mm(0.15))
        c.SetCenter(pcbnew.VECTOR2I(mm(m["at"][0]), mm(m["at"][1])))
        c.SetEnd(pcbnew.VECTOR2I(mm(m["at"][0] + m["r"]), mm(m["at"][1])))
        board.Add(c)
    elif m["kind"] == "rect":
        r = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
        r.SetLayer(pcbnew.F_SilkS)
        r.SetWidth(mm(0.15))
        r.SetStart(pcbnew.VECTOR2I(mm(m["box"][0]), mm(m["box"][1])))
        r.SetEnd(pcbnew.VECTOR2I(mm(m["box"][2]), mm(m["box"][3])))
        board.Add(r)
pcbnew.SaveBoard(sys.argv[1], board)
# keep the designator file in step with the spec: drop labels of board-only parts no longer placed
import re  # noqa: E402
labels_path = HERE.parent / "reference-labels.json"
if labels_path.exists():
    lab = json.loads(labels_path.read_text())
    keep = {x["ref"] for k in ("test_points", "fiducials", "mounting_holes") for x in spec[k]}
    stale = [r for r in lab["references"] if re.fullmatch(r"(TP|FID|H)\d+", r) and r not in keep]
    for r in stale:
        del lab["references"][r]
    if stale:
        labels_path.write_text(json.dumps(lab, indent=1) + "\n")
print(json.dumps({"test_points": len(spec["test_points"]), "fiducials": len(spec["fiducials"]),
                  "mounting_holes": len(spec["mounting_holes"])}))
