"""Native-21 copper layer stack, read from native-21/stackup.json (the single source; stage 33 refactor).

    CU          copper layer names, top to bottom (KiCad names): ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu") today
    OUTER       (F.Cu, B.Cu)
    INNER       inner copper layers, top to bottom
    KICAD_ID    name -> KiCad layer id (KiCad 9/10: F.Cu 0, B.Cu 2, InN.Cu 2 + 2N)
    T_UM        name -> copper thickness, um (an int when whole: 70 / 61, as the models' literals were)
    T_MM        name -> copper thickness, mm (the stackup.json value)
    Z_MM        name -> copper-centre depth below the top copper surface, mm (masks excluded)
    ADJ         name -> the other copper layers, nearest first by copper-centre distance (equal to 1 nm: the upper layer)
    PLANE_ROLE  net -> the inner layer carrying that net's reference / return plane (hv_ret -> In1.Cu, bus_p -> In2.Cu, ...)
    STACKUP_PATH, STACKUP   the file and its parsed content

The stack file is native-21/stackup.json unless $NATIVE21_STACKUP names another one (for a study such as the six-layer
pass: every consumer of this module, the board builder, B3 and the sheet-solver callers then follow it, no code change).

Stdlib only, so the gates, the KiCad Python scripts and the physics models (python3 -I) can all import it:
    sys.path.insert(0, str(UNIT / "native-21/layout")); import layers21

An unknown layer name is an error everywhere (layer(name) raises), never silently dropped.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

STACKUP_DEFAULT = Path(__file__).resolve().parents[1] / "stackup.json"
STACKUP_PATH = Path(os.environ.get("NATIVE21_STACKUP") or STACKUP_DEFAULT).resolve()


def kicad_id(name: str) -> int:
    """KiCad 9/10 copper layer id from its canonical name."""
    if name == "F.Cu":
        return 0
    if name == "B.Cu":
        return 2
    m = re.fullmatch(r"In([1-9][0-9]?)\.Cu", name)
    if not m:
        raise ValueError(f"not a KiCad copper layer name: {name!r}")
    return 2 + 2 * int(m.group(1))


def load(path=STACKUP_PATH) -> dict:
    """Parse a stackup.json and derive the layer tables (validated). Returns a dict of the module constants."""
    path = Path(path)
    st = json.loads(path.read_text())
    layers = st["layers"]
    solid = [e for e in layers if e["type"] not in ("Top Solder Mask", "Bottom Solder Mask")]
    copper = [e for e in solid if e["type"] == "copper"]
    cu = tuple(e["name"] for e in copper)
    if len(cu) < 2 or cu[0] != "F.Cu" or cu[-1] != "B.Cu" or len(set(cu)) != len(cu):
        raise ValueError(f"{path}: copper must run F.Cu ... B.Cu without repeats, got {cu}")
    inner = cu[1:-1]
    if inner != tuple(f"In{k}.Cu" for k in range(1, len(inner) + 1)):
        raise ValueError(f"{path}: inner copper must be In1.Cu ... In{len(inner)}.Cu in order, got {inner}")
    # copper and dielectric must alternate (one dielectric entry between two copper layers)
    kinds = ["cu" if e["type"] == "copper" else "d" for e in solid]
    if kinds != ["cu", "d"] * (len(cu) - 1) + ["cu"]:
        raise ValueError(f"{path}: copper and dielectric layers must alternate, got {kinds}")
    if abs(sum(e["thickness_mm"] for e in layers) - st["board_thickness_mm"]) > 1e-9:
        raise ValueError(f"{path}: layer thicknesses do not sum to board_thickness_mm")
    ids, t_um, t_mm, z_mm = {}, {}, {}, {}
    above = None                    # running depth of the top of the current solid layer below the top copper surface
    for e in solid:
        t = e["thickness_mm"]
        if e["type"] == "copper":
            # same summation order as the former sheet_solver.LAYER_Z_MM literals, so z is bit-identical
            z_mm[e["name"]] = t / 2 if above is None else above + t / 2
            um = round(t * 1000, 6)
            t_um[e["name"]] = int(um) if um == int(um) else um
            t_mm[e["name"]] = t
            ids[e["name"]] = kicad_id(e["name"])
            if e.get("kicad_id", ids[e["name"]]) != ids[e["name"]]:
                raise ValueError(f"{path}: {e['name']} kicad_id {e['kicad_id']} != {ids[e['name']]}")
            if "z_mm" in e and abs(e["z_mm"] - z_mm[e["name"]]) > 1e-9:
                raise ValueError(f"{path}: {e['name']} z_mm {e['z_mm']} != computed {z_mm[e['name']]}")
        above = t if above is None else above + t
    adj = {a: sorted((b for b in cu if b != a), key=lambda b: (round(abs(z_mm[b] - z_mm[a]), 9), cu.index(b))) for a in cu}
    roles = {k: v for k, v in st.get("plane_roles", {}).items() if not k.startswith("_")}
    for net, lay in roles.items():
        if lay not in inner:
            raise ValueError(f"{path}: plane role {net} -> {lay} is not an inner copper layer")
    return {"STACKUP": st, "CU": cu, "OUTER": (cu[0], cu[-1]), "INNER": inner, "KICAD_ID": ids, "T_UM": t_um, "T_MM": t_mm,
            "Z_MM": z_mm, "ADJ": adj, "PLANE_ROLE": roles}


_S = load()
STACKUP = _S["STACKUP"]
CU = _S["CU"]
OUTER = _S["OUTER"]
INNER = _S["INNER"]
KICAD_ID = _S["KICAD_ID"]
T_UM = _S["T_UM"]
T_MM = _S["T_MM"]
Z_MM = _S["Z_MM"]
ADJ = _S["ADJ"]
PLANE_ROLE = _S["PLANE_ROLE"]


def layer(name: str) -> str:
    """Return `name` if it is one of this board's copper layers, else raise (never drop an unknown layer)."""
    if name not in CU:
        raise KeyError(f"unknown copper layer {name!r}: native-21/stackup.json has {CU}")
    return name


def index(name: str) -> int:
    """Position of a copper layer, top to bottom (raises on an unknown layer)."""
    return CU.index(layer(name))
