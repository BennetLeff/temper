#!/usr/bin/env python3
"""Controls for copper_baseline.py.   python3 -I native-21/layout/gates/test_copper_baseline.py"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("cb", Path(__file__).resolve().parent / "copper_baseline.py")
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)


def trk(net, w):
    return {"kind": "track", "net": net, "layer": "F.Cu", "start": [0, 0], "end": [1, 0], "width_mm": w}


def via(net, d=0.6):
    return {"kind": "via", "net": net, "centre": [0, 0], "diameter_mm": d, "drill_mm": 0.3}


def pour(net, side):
    return {"kind": "zone", "net": net, "layer": "In1.Cu", "shell": [[0, 0], [side, 0], [side, side], [0, side]]}


BASE = cb.record([trk("a", 0.8), trk("a", 2.0), via("a"), via("a"), pour("a", 10), trk("b", 0.3)])
CASES = [
    ("identical", [trk("a", 0.8), trk("a", 2.0), via("a"), via("a"), pour("a", 10), trk("b", 0.3)], []),
    ("power net narrowed 0.8 -> 0.4", [trk("a", 0.4), trk("a", 2.0), via("a"), via("a"), pour("a", 10), trk("b", 0.3)], ["narrowed"]),
    ("a via dropped", [trk("a", 0.8), trk("a", 2.0), via("a"), pour("a", 10), trk("b", 0.3)], ["fewer_vias"]),
    ("pour shrunk 10 mm -> 8 mm side (36 % of area)", [trk("a", 0.8), trk("a", 2.0), via("a"), via("a"), pour("a", 8), trk("b", 0.3)], ["zone_shrunk"]),
    ("net b removed", [trk("a", 0.8), trk("a", 2.0), via("a"), via("a"), pour("a", 10)], ["net_vanished"]),
    ("widened, more vias, bigger pour: information only", [trk("a", 1.0), trk("a", 2.0), via("a"), via("a"), via("a"), pour("a", 12), trk("b", 0.3)], []),
]
bad = 0
for name, prims, want in CASES:
    got = sorted(f["kind"] for f in cb.diff(BASE, cb.record(prims))["fail"])
    ok = got == sorted(want)
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"(want {want}, got {got})")
sys.exit(1 if bad else 0)
