#!/usr/bin/env python3
"""D-22 inlet-module volume against the R43 enclosure parts (read-only; R45 does not exist yet).

    python3 neighbours_r43.py [R43 folder]   -> results/neighbours-r43.json

Part meshes are tested triangle by triangle: a triangle counts when its bounding box meets the candidate box (so a hit is
conservative near the surface, and 0 hits is exact up to mesh tessellation). Parts that belong to the module itself are
excluded by name. Clearances are to bare bodies: no creepage, service or bend-radius allowance is in this check."""
import gzip, json, sys, pathlib
import numpy as np
HERE = pathlib.Path(__file__).resolve().parents[1]
R43 = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/bennet/Desktop/temper/output/temper-manufacturing-r43")
OWN = ("EMI", "enclosure_bottom_chassis")   # module, its stand, nuts and the harness ends that move with it


def tris(p):
    P = np.array(p["positions"], float).reshape(-1, 3)
    I = np.array(p["indices"], int).reshape(-1, 3)
    return P[I].min(1), P[I].max(1)


def hits(lo, hi, box):
    b0, b1 = np.array(box[:3]), np.array(box[3:])
    return int(((lo < b1) & (hi > b0)).all(1).sum())


def main():
    parts = json.load(gzip.open(R43 / "assembly.json.gz"))
    geo = {p["name"]: tris(p) for p in parts}
    emi = next(p for p in parts if p["name"] == "electronics_inlet_EMI_module_ENVELOPE")
    lo, hi = geo[emi["name"]]
    env = np.concatenate([lo.min(0), hi.max(0)])
    out = {"r43_envelope": [round(float(v), 2) for v in env], "cases": []}
    def run(box, label):
        r = {"case": label, "box": [round(float(v), 1) for v in box], "hits": {}}
        for p in parts:
            n = p["name"]
            if any(o in n for o in OWN):
                continue
            k = hits(*geo[n], box)
            if k:
                r["hits"][n] = k
        out["cases"].append(r)
        print(label, r["box"], r["hits"] or "clear")
    z0 = env[2]
    for dz, zt in (("z0..+50", env[2] + 50.0), ("z0..R43 top", env[5])):
        run([*env[:3], *env[3:5], zt], "as R43 envelope, " + dz)
    for x0, x1, y0, y1, lab in (
            (env[0], env[0] + 130, env[1], env[1] + 85, "130x85 from the same -X/-Y corner"),
            (env[3] - 130, env[3], env[1], env[1] + 85, "130x85 from the +X/-Y corner"),
            (env[0], env[0] + 130, env[4] - 85, env[4], "130x85 from the -X/+Y corner"),
            (env[3] - 130, env[3], env[4] - 85, env[4], "130x85 from the +X/+Y corner"),
            (env[0] - 10, env[0] + 120, env[1], env[1] + 85, "130x85 shifted 10 mm -X")):
        for h in (50.0, 60.0):
            run([x0, y0, z0, x1, y1, z0 + h], f"{lab}, height {h:g}")
    for lab, box in (("R43 today 110x80x50", list(env)), ("130x85x50, grown to -X and +Y", [env[3] - 130, env[1], env[2], env[3], env[1] + 85, env[2] + 50]),
                     ("130x80x50, grown to -X", [env[3] - 130, env[1], env[2], env[3], env[1] + 80, env[2] + 50])):
        b0, b1, r = np.array(box[:3], float), np.array(box[3:], float), []
        for p in parts:
            if any(o in p["name"] for o in OWN):
                continue
            lo, hi = geo[p["name"]]
            d = np.maximum(np.maximum(lo - b1, b0 - hi), 0)
            r.append((round(float(np.sqrt((d ** 2).sum(1)).min()), 1), p["name"], p["material"]))
        r = [x for x in sorted(r, key=lambda x: (x[0], x[1])) if x[0] < 12.0]
        out.setdefault("gaps", []).append({"case": lab, "box": [round(float(v), 1) for v in box], "under_12mm": r})
        print(lab, [(a, b) for a, b, _ in r])
    # the JV choke: 42 mm tall on a PCB 1.6 mm + standoff + solder-side clearance
    out["jv_stack_mm"] = {"choke": 42.0, "pcb": 1.6, "note": "top of JV above the PCB bottom: 43.6 + standoff height"}
    (HERE / "results/neighbours-r43.json").write_text(json.dumps(out, indent=1) + "\n")


main()
