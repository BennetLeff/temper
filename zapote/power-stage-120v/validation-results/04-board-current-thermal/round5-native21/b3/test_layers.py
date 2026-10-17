#!/usr/bin/env python3
"""Controls for the stage-33 layer-stack refactor of B3 (thermal.py) and the A4 summary (../summarize.py).

    python3 test_layers.py        (Miniforge python)

1. thermal.py's default stack (native-21/stackup.json) gives the seven sheets and copper indices it hard-coded, and the
   same thicknesses as native-17/stackup.json, which it read before; the analytic self-test still passes.
2. Copper on a layer the stack does not have raises (grid_geometry dropped the whole layer; barrel_edges dropped the
   barrel's link); summarize.barrel_index raises on it too (order.get returned None).
3. A six-layer stack loads: eleven sheets, copper at 0, 2, ..., 10.
"""
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


th = load("thermal", HERE / "thermal.py")
sm = load("summarize", HERE.parent / "summarize.py")
fails = 0


def check(ok, what, detail=""):
    global fails
    print("ok  " if ok else "FAIL", what, "" if ok else detail)
    fails += not ok


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    return False


check(th.LAYER_NAMES == ("F.Cu", "dielectric 1", "In1.Cu", "dielectric 2", "In2.Cu", "dielectric 3", "B.Cu"),
      "LAYER_NAMES", th.LAYER_NAMES)
check(th.CU_INDEX == {"F.Cu": 0, "In1.Cu": 2, "In2.Cu": 4, "B.Cu": 6}, "CU_INDEX", th.CU_INDEX)
n17 = [e["thickness_mm"] for e in json.loads((UNIT / "native-17/stackup.json").read_text())["layers"]
       if "Mask" not in e["type"]]
check(th.THICK_MM.tolist() == n17, "THICK_MM == native-17/stackup.json (the stack B3 read before)", th.THICK_MM)
check(th.analytic_selftest()["status"] == "PASS", "analytic self-test")

outline = {"shell": [[0, 0], [10, 0], [10, 10], [0, 10]], "holes": []}
sq = {"shell": [[1, 1], [3, 1], [3, 3], [1, 3]], "holes": []}
good = {"outline": outline, "primitives": [{"kind": "zone", "layer": "In2.Cu", "net": "x", **sq}]}
bad = copy.deepcopy(good)
bad["primitives"].append({"kind": "zone", "layer": "In3.Cu", "net": "x", **sq})
check(not raises(ValueError, lambda: th.grid_geometry(good, 1.0)), "grid_geometry: known layers pass")
check(raises(ValueError, lambda: th.grid_geometry(bad, 1.0)), "grid_geometry: copper on In3.Cu raises (was dropped)")
x = y = [0.5 + i for i in range(10)]
import numpy as np  # noqa: E402
board = np.ones((10, 10), bool)
check(raises(KeyError, lambda: th.barrel_edges([{"xy_mm": [2, 2], "drill_mm": 0.3, "layers": {"F.Cu", "In3.Cu"}}],
                                                 np.array(x), np.array(y), board)),
      "barrel_edges: a barrel on In3.Cu raises (was dropped)")
via = {"kind": "via", "net": "n", "centre": [1, 1], "drill_mm": 0.3}
check(sm.barrel_index({"primitives": [{**via, "layer": "B.Cu"}, {**via, "layer": "F.Cu"}]})["n"][0]["layers"]
      == ["F.Cu", "B.Cu"], "summarize.barrel_index orders F..B")
check(raises(KeyError, lambda: sm.barrel_index({"primitives": [{**via, "layer": "In3.Cu"}, {**via, "layer": "F.Cu"}]})),
      "summarize.barrel_index: In3.Cu raises (order.get gave None)")

st = json.loads((UNIT / "native-21/stackup.json").read_text())
masks = [e for e in st["layers"] if "Mask" in e["type"]]
body = []
for i, n in enumerate(["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]):
    body.append({"name": n, "type": "copper", "thickness_mm": 0.035})
    if i < 5:
        body.append({"name": f"dielectric {i + 1}", "type": "prepreg", "thickness_mm": 0.2})
six = {**st, "layers": [masks[0]] + body + [masks[1]]}
six["board_thickness_mm"] = sum(e["thickness_mm"] for e in six["layers"])
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "stackup.json"
    p.write_text(json.dumps(six))
    th.use_stackup(p)
    check(len(th.LAYER_NAMES) == 11 and sorted(th.CU_INDEX.values()) == [0, 2, 4, 6, 8, 10], "six-layer stack loads",
          th.CU_INDEX)
    check(not raises(ValueError, lambda: th.grid_geometry(bad, 1.0)), "six-layer: In3.Cu copper accepted")
    th.use_stackup(th.STACKUP_DEFAULT)

print("PASS" if not fails else f"FAIL ({fails})")
sys.exit(1 if fails else 0)
