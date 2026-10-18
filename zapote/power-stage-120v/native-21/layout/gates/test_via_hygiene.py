#!/usr/bin/env python3
"""Controls for via_hygiene.py.   python3 -I native-21/layout/gates/test_via_hygiene.py"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("vh", Path(__file__).resolve().parent / "via_hygiene.py")
vh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vh)


def trk(net, a, b, layer, w=0.25):
    return {"kind": "track", "net": net, "layer": layer, "start": list(a), "end": list(b), "width_mm": w}


def via(net, c):
    return {"kind": "via", "net": net, "centre": list(c), "diameter_mm": 0.6, "drill_mm": 0.3}


def pour(net, layer, x0, y0, x1, y1):
    return {"kind": "zone", "net": net, "layer": layer, "shell": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def pad(net, layer, x0, y0, x1, y1):
    return {"kind": "pad", "ref": "R1.1", "net": net, "layer": layer, "centre": [(x0 + x1) / 2, (y0 + y1) / 2],
            "shell": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


# (name, primitives, expected stranded count). Each stranded case is a real defect; the good cases must not flag.
CASES = [
    ("track end on F.Cu and a track end on B.Cu", [trk("n", (0, 0), (1, 0), "F.Cu"), trk("n", (1, 0), (2, 0), "B.Cu"), via("n", (1, 0))], 0),
    ("track on F.Cu, pour on In1.Cu (stitch to a plane)", [trk("n", (0, 0), (1, 0), "F.Cu"), pour("n", "In1.Cu", -5, -5, 5, 5), via("n", (1, 0))], 0),
    ("pad on F.Cu, pour on B.Cu", [pad("n", "F.Cu", 0.5, -0.5, 1.5, 0.5), pour("n", "B.Cu", -5, -5, 5, 5), via("n", (1, 0))], 0),
    ("track on F.Cu only (dead via)", [trk("n", (0, 0), (1, 0), "F.Cu"), via("n", (1, 0))], 1),
    ("via in nothing", [trk("n", (0, 0), (1, 0), "F.Cu"), via("n", (4, 4))], 1),
    ("pour of another net does not count", [trk("n", (0, 0), (1, 0), "F.Cu"), pour("m", "B.Cu", -5, -5, 5, 5), via("n", (1, 0))], 1),
    ("track passing 0.5 mm beside the via does not count", [trk("n", (0, 0.5), (2, 0.5), "F.Cu"), trk("n", (0, 0.5), (2, 0.5), "B.Cu"), via("n", (1, 0))], 1),
]

bad = 0
for name, prims, want in CASES:
    got = vh.measure(prims)["stranded_vias"]
    ok = got == want
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"(want {want}, got {got})")
sys.exit(1 if bad else 0)
