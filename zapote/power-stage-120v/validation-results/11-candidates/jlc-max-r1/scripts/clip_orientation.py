#!/usr/bin/env python3
"""Which end of JLC's C223911 (Littelfuse 01250003H) model carries the end-stop ears, at JLC rotation 0.

Reads reads/easyeda/footprint_C223911.json (EasyEDA Pro footprint, mil units) and reads/easyeda/model3d_C223911.obj
(git-ignored; fetched from https://modules.easyeda.com/3dmodel/dc904f908e284dc6b4f547c7a80a1a35 if missing; uuid from
reads/easyeda/component3d_C223911.json). Writes reads/easyeda/clip-orientation.json.
usage: python3 -I scripts/clip_orientation.py"""
import json, pathlib, subprocess
import numpy as np

E = pathlib.Path(__file__).resolve().parent.parent / "reads" / "easyeda"
MIL = 0.0254


def footprint():
    ds = json.loads((E / "footprint_C223911.json").read_text())["result"]["dataStr"]
    pads, marks = [], []
    for line in ds.splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not isinstance(r, list) or not r:
            continue
        if r[0] == "PAD":
            pads.append({"num": r[5], "x_mm": round(r[6] * MIL, 3), "y_mm": round(r[7] * MIL, 3)})
        if r[0] == "FILL" and isinstance(r[7], list) and r[7] and r[7][0] != "CIRCLE":   # filled squares (silk / assembly)
            nums = [v for v in r[7] if isinstance(v, (int, float))]
            if not nums:          # e.g. a nested ["CIRCLE", ...] pin-1 dot
                continue
            xs, ys = nums[0::2], nums[1::2]
            marks.append({"layer": r[4], "x_mm": [round(min(xs) * MIL, 2), round(max(xs) * MIL, 2)],
                          "y_mm": [round(min(ys) * MIL, 2), round(max(ys) * MIL, 2)]})
    return pads, marks


def model():
    obj = E / "model3d_C223911.obj"
    if not obj.exists():
        subprocess.run(["curl", "-s", "-m", "60", "-A", "temper-parts-check", "-o", str(obj),
                        "https://modules.easyeda.com/3dmodel/dc904f908e284dc6b4f547c7a80a1a35"], check=True)
    V = np.array([[float(x) for x in l.split()[1:4]] for l in obj.open() if l.startswith("v ")])
    M = V.copy(); M[:, 0] *= -1
    unpaired = V[np.array([np.min(np.linalg.norm(M - v, axis=1)) for v in V]) > 0.3]
    pins = V[V[:, 2] < -3]
    return {"vertices": len(V), "pin_x_mm": sorted({round(float(x), 1) for x in pins[:, 0]}),
            "unpaired_end_minus_x (x<-4)": int((unpaired[:, 0] < -4).sum()),
            "unpaired_end_plus_x (x>4)": int((unpaired[:, 0] > 4).sum())}


if __name__ == "__main__":
    pads, marks = footprint()
    m = model()
    ear = "-x (pad 1)" if m["unpaired_end_minus_x (x<-4)"] > m["unpaired_end_plus_x (x>4)"] else "+x (pad 2)"
    out = {"pads": pads, "filled_marks": marks, "model": m, "ear_end_at_rotation_0": ear,
           "rotation_for_ears_outboard": {"clip on F1's +x side (F1A)": 180 if ear.startswith("-") else 0,
                                          "clip on F1's -x side (F1B)": 0 if ear.startswith("-") else 180}}
    (E / "clip-orientation.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
