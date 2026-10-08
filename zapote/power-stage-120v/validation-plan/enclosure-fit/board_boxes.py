#!/usr/bin/env python3
"""Populated-board part boxes from a KiCad STEP export (CadQuery, or bare OCP).

    python board_boxes.py BOARD.step OUT.json

Writes one axis-aligned box per solid in BOARD-LOCAL coordinates: x right
(KiCad x), y down (KiCad y; the STEP's y is negated), z up from the board's
bottom face. Boxes are conservative for fit (AABB >= solid). Uses CadQuery when
installed, otherwise the OpenCascade bindings (cadquery-ocp) directly: same reader
(STEPControl), same per-solid bounding boxes.
"""
import hashlib
import json
import sys

step, out = sys.argv[1], sys.argv[2]


def solid_boxes(path):
    try:
        import cadquery as cq
        for s in cq.importers.importStep(path).val().Solids():
            b = s.BoundingBox()
            yield b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax
        return
    except ImportError:
        pass
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != 1:
        raise SystemExit(f"cannot read {path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        bb = Bnd_Box()
        BRepBndLib.Add_s(ex.Current(), bb)
        yield bb.Get()
        ex.Next()


boxes = []
for xmin, ymin, zmin, xmax, ymax, zmax in solid_boxes(step):
    boxes.append([round(xmin, 3), round(-ymax, 3), round(zmin, 3),
                  round(xmax, 3), round(-ymin, 3), round(zmax, 3)])
json.dump({"step_sha256": hashlib.sha256(open(step, "rb").read()).hexdigest(),
           "frame": "board-local: x right, y down (KiCad), z up from board bottom; mm",
           "boxes": boxes}, open(out, "w"), indent=0)
