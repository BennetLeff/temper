#!/usr/bin/env python3
"""Controls for layers21.py (stage 33 refactor: native-21/stackup.json is the single layer-stack source).

    python3 native-21/layout/test_layers21.py          (Miniforge python: the sheet-solver check needs numpy / scipy)

1. On today's stack every export equals the four-layer literals it replaced (CU / OUTER / INNER tuples, KiCad ids,
   70 / 61 um, the sheet solver's LAYER_Z_MM bit for bit, return_path19's hand-written ADJ table).
2. PLANE_ROLE matches the committed copper: each role net has its pour on that inner layer.
3. The sheet solver's own stackup loader agrees with layers21 on native-21, and with LAYER_Z_MM on native-20.
4. A synthetic six-layer stack loads (In3 / In4 ids 8 / 10, ADJ nearest first from z); malformed stacks and unknown
   layer names raise.
"""
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import layers21 as L  # noqa: E402

fails = 0


def check(ok, what, detail=""):
    global fails
    print("ok  " if ok else "FAIL", what, "" if ok else detail)
    fails += not ok


# 1. four-layer literals
check(L.CU == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), "CU", L.CU)
check(L.OUTER == ("F.Cu", "B.Cu") and L.INNER == ("In1.Cu", "In2.Cu"), "OUTER / INNER", (L.OUTER, L.INNER))
check(L.KICAD_ID == {"F.Cu": 0, "In1.Cu": 4, "In2.Cu": 6, "B.Cu": 2}, "KICAD_ID", L.KICAD_ID)
check(L.T_UM == {"F.Cu": 70, "In1.Cu": 61, "In2.Cu": 61, "B.Cu": 70}
      and all(type(v) is int for v in L.T_UM.values()), "T_UM (ints, as the 70 / 61 literals)", L.T_UM)
check(L.T_MM == {"F.Cu": 0.070, "In1.Cu": 0.061, "In2.Cu": 0.061, "B.Cu": 0.070}, "T_MM", L.T_MM)
LEGACY_Z = {"F.Cu": 0.035, "In1.Cu": 0.07 + 0.4355 + 0.0305,          # sheet_solver.LAYER_Z_MM before stage 33
            "In2.Cu": 0.07 + 0.4355 + 0.061 + 0.5 + 0.0305,
            "B.Cu": 0.07 + 0.4355 + 0.061 + 0.5 + 0.061 + 0.4355 + 0.035}
check(L.Z_MM == LEGACY_Z and all(L.Z_MM[k].hex() == LEGACY_Z[k].hex() for k in L.CU), "Z_MM bit-identical", L.Z_MM)
LEGACY_ADJ = {"F.Cu": ["In1.Cu", "In2.Cu", "B.Cu"], "In1.Cu": ["F.Cu", "In2.Cu", "B.Cu"],   # return_path19.py
              "In2.Cu": ["B.Cu", "In1.Cu", "F.Cu"], "B.Cu": ["In2.Cu", "In1.Cu", "F.Cu"]}
check(L.ADJ == LEGACY_ADJ, "ADJ == return_path19's hand table", L.ADJ)
check(L.index("In2.Cu") == 2, "index")
try:
    L.layer("In3.Cu")
    check(False, "unknown layer raises")
except KeyError:
    check(True, "unknown layer raises")

# 2. plane roles against the committed copper
cu = json.loads((HERE / "copper.json").read_text())
inner = {(z["net"], z["layer"]) for z in cu["zones"] if z["layer"] in L.INNER and "heat-spread" not in z.get("name", "")}
check({n for n, _ in inner} == set(L.PLANE_ROLE) and all(L.PLANE_ROLE[n] == lay for n, lay in inner),
      "PLANE_ROLE == the committed inner-layer pours", sorted(inner))

# 3. the sheet solver's loader
spec = importlib.util.spec_from_file_location("kit", UNIT / "validation-plan/sim-kit/04-current/sheet_solver.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)
s21 = kit.stackup_layers(UNIT / "native-21/stackup.json")
check(s21["z_mm"] == L.Z_MM and s21["t_um"] == L.T_UM, "sheet_solver.stackup_layers(native-21) == layers21", s21)
s20 = kit.stackup_layers(UNIT / "native-20/stackup.json")
check(s20["z_mm"] == kit.LAYER_Z_MM, "sheet_solver.stackup_layers(native-20) == LAYER_Z_MM", s20)

# 4. a six-layer stack, and malformed ones
st = json.loads(L.STACKUP_PATH.read_text())
six = copy.deepcopy(st)
cu_t, d_t = 0.035, 0.2
masks = [e for e in st["layers"] if "Mask" in e["type"]]
names = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
body = []
for i, n in enumerate(names):
    body.append({"name": n, "type": "copper", "thickness_mm": cu_t})
    if i < len(names) - 1:
        body.append({"name": f"dielectric {i + 1}", "type": "prepreg", "thickness_mm": d_t})
six["layers"] = [masks[0]] + body + [masks[1]]
six["board_thickness_mm"] = sum(e["thickness_mm"] for e in six["layers"])
six["plane_roles"] = {"hv_ret": "In1.Cu", "bus_p": "In4.Cu"}
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "stackup.json"
    p.write_text(json.dumps(six))
    s6 = L.load(p)
    check(s6["CU"] == tuple(names) and s6["INNER"] == tuple(names[1:-1]), "six-layer CU", s6["CU"])
    check([s6["KICAD_ID"][n] for n in names] == [0, 4, 6, 8, 10, 2], "six-layer KiCad ids", s6["KICAD_ID"])
    check(s6["ADJ"]["In2.Cu"] == ["In1.Cu", "In3.Cu", "F.Cu", "In4.Cu", "B.Cu"], "six-layer ADJ (ties: upper first)",
          s6["ADJ"]["In2.Cu"])
    bad = copy.deepcopy(six)
    bad["layers"] = [e for e in bad["layers"] if e["name"] != "dielectric 3"]
    bad["board_thickness_mm"] = sum(e["thickness_mm"] for e in bad["layers"])
    p.write_text(json.dumps(bad))
    try:
        L.load(p)
        check(False, "non-alternating stack raises")
    except ValueError:
        check(True, "non-alternating stack raises")
    bad = copy.deepcopy(st)
    next(e for e in bad["layers"] if e["name"] == "In2.Cu")["z_mm"] = 1.0975
    p.write_text(json.dumps(bad))
    try:
        L.load(p)
        check(False, "stated z_mm off the computed one raises")
    except ValueError:
        check(True, "stated z_mm off the computed one raises")
    bad = copy.deepcopy(st)
    bad["plane_roles"]["bus_p"] = "B.Cu"
    p.write_text(json.dumps(bad))
    try:
        L.load(p)
        check(False, "a plane role on an outer layer raises")
    except ValueError:
        check(True, "a plane role on an outer layer raises")

print("PASS" if not fails else f"FAIL ({fails})")
sys.exit(1 if fails else 0)
