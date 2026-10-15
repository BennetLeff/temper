#!/usr/bin/env python3
"""Controls for track_geometry.py.   python3 -I native-21/layout/gates/test_track_geometry.py"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("tg", Path(__file__).resolve().parent / "track_geometry.py")
tg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tg)


def trk(net, a, b, layer="F.Cu"):
    return {"kind": "track", "net": net, "layer": layer, "start": list(a), "end": list(b), "width_mm": 0.25}


CASES = [
    ("45 deg mitred bend", [trk("n", (0, 0), (1, 0)), trk("n", (1, 0), (2, 1))],
     {"right_angle_corners": 0, "acute_corners": 0, "fold_backs": 0, "any_angle_mm": 0.0}),
    ("right angle", [trk("n", (0, 0), (1, 0)), trk("n", (1, 0), (1, 1))],
     {"right_angle_corners": 1, "acute_corners": 0, "fold_backs": 0, "any_angle_mm": 0.0}),
    ("acute 45 deg interior", [trk("n", (0, 0), (1, 0)), trk("n", (1, 0), (0, 1))],
     {"right_angle_corners": 0, "acute_corners": 1, "fold_backs": 0, "any_angle_mm": 0.0}),
    ("fold-back", [trk("n", (0, 0), (2, 0)), trk("n", (2, 0), (1, 0))],
     {"right_angle_corners": 0, "acute_corners": 1, "fold_backs": 1, "any_angle_mm": 0.0}),
    ("any-angle segment (30 deg, 2 mm)", [trk("n", (0, 0), (3 ** 0.5, 1))],
     {"right_angle_corners": 0, "acute_corners": 0, "fold_backs": 0, "any_angle_mm": 2.0}),
    ("T-junction is not a corner", [trk("n", (0, 0), (1, 0)), trk("n", (1, 0), (2, 0)), trk("n", (1, 0), (1, 1))],
     {"right_angle_corners": 0, "acute_corners": 0, "fold_backs": 0, "any_angle_mm": 0.0}),
    ("different nets / layers do not form corners",
     [trk("n", (0, 0), (1, 0)), trk("m", (1, 0), (1, 1)), trk("n", (1, 0), (1, 1), layer="B.Cu")],
     {"right_angle_corners": 0, "acute_corners": 0, "fold_backs": 0, "any_angle_mm": 0.0}),
]
fails = 0
for name, prims, want in CASES:
    got = tg.measure(prims)
    ok = got == want
    fails += not ok
    print("ok  " if ok else "FAIL", name, got if not ok else "")
print("PASS" if not fails else f"FAIL ({fails})")
raise SystemExit(1 if fails else 0)
