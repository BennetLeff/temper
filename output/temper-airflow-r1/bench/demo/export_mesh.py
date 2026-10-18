#!/usr/bin/env python3
"""Tessellate the jet-bench rig (cad/rig_cad.py, same geometry) into one compact mesh file for the web demo.

    ../../.venv/bin/python export_mesh.py     # build123d 0.11.1 -> rig-mesh.json (regenerable; not committed)

Positions are int16 in units of 0.01 mm (rig frame of rig_cad.py: native-21 model x/y, z above the plate top),
indices uint16/uint32, both base64. build_demo.py embeds this file into jet-bench-demo.html.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cad"))
import rig_cad as rc  # noqa: E402


def mesh(shape, tol=0.02, ang=0.2):
    verts, tris = [], []
    for f in shape.faces():
        v, t = f.tessellate(tol, ang)
        base = len(verts)
        verts += [(p.X, p.Y, p.Z) for p in v]
        tris += [(a + base, b + base, c + base) for a, b, c in t]
    p = np.round(np.asarray(verts) * 100).astype("<i2")
    i = np.asarray(tris, dtype="<u2" if len(verts) < 65536 else "<u4")
    return {"n": len(verts), "pos": base64.b64encode(p.tobytes()).decode(), "idx": base64.b64encode(i.tobytes()).decode(),
            "i32": bool(i.dtype.itemsize == 4)}


def main():
    d = rc.duct()
    lower, upper = rc.halves(d)
    tr = rc.tray()
    hd, lid = rc.hood()
    parts = {"duct_lower": lower, "duct_upper": upper, "wall_minus_y": rc.wall(),
             **{f"film_cap_{i + 1}": c for i, c in enumerate(rc.caps())},
             "plate": rc.plate(), "guard_tray": tr, "deck": rc.deck(tr), "hood_box": hd, "hood_lid": lid}
    # bonded parts that rig_cad.py does not model (RIG.md section 3): TO-220 bodies under plate and tray, KSD9700 cut-out
    parts["heater_plate_1"] = rc.abox(25.0, 35.0, 11.0, 19.5, -7.5, -3.0)
    parts["heater_plate_2"] = rc.abox(55.0, 65.0, 11.0, 19.5, -7.5, -3.0)
    parts["cutout"] = rc.abox(3.0, 12.0, 12.0, 18.5, -5.5, -3.0)
    parts["heater_guard_1"] = rc.abox(15.0, 25.0, 11.0, 19.5, -16.5, -12.0)
    parts["heater_guard_2"] = rc.abox(65.0, 75.0, 11.0, 19.5, -16.5, -12.0)
    out = {"units": "0.01 mm", "parts": {}}
    for n, s in parts.items():
        out["parts"][n] = mesh(s)
        print(n, out["parts"][n]["n"])
    (HERE / "rig-mesh.json").write_text(json.dumps(out))
    print((HERE / "rig-mesh.json").stat().st_size, "bytes")


if __name__ == "__main__":
    main()
