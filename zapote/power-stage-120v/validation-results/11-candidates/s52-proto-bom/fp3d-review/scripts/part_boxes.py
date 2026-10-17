"""STEP-solid AABBs attributed to the stage-52 parts (smallest courtyard containing the XY centre, as body_collisions.py),
plus nearest neighbour bodies. Usage: python3 -I part_boxes.py BOXES.json COURTYARDS.json OUT.json"""
import json, sys
boxes = json.load(open(sys.argv[1]))["boxes"]
crt = json.load(open(sys.argv[2]))
boxes = [b for b in boxes if not ((b[5] - b[2] < 2) and (b[3] - b[0]) * (b[4] - b[1]) > 30000)]
def owner(b):
    cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
    best = None
    for r, c in crt.items():
        if c[0] <= cx <= c[2] and c[1] <= cy <= c[3]:
            a = (c[2] - c[0]) * (c[3] - c[1])
            if best is None or a < best[1]:
                best = (r, a)
    return best[0] if best else None
own = [(owner(b), b) for b in boxes]
REFS = ["C21", "C22", "C23", "C151", "C152", "L1", "C3", "C4"]
out = {}
def gap(a, b):
    # separation per axis (negative = overlap on that axis)
    return [max(b[0] - a[3], a[0] - b[3]), max(b[1] - a[4], a[1] - b[4]), max(b[2] - a[5], a[2] - b[5])]
for r in REFS:
    mine = [b for o, b in own if o == r]
    u = [min(b[i] for b in mine) for i in range(3)] + [max(b[i] for b in mine) for i in range(3, 6)] if mine else None
    near = []
    if u:
        for o, b in own:
            if o == r:
                continue
            g = gap(u, b)
            if g[2] < 0:  # z-overlapping: plan-view separation matters
                d = max(g[0], g[1])
                near.append((round(d, 3), o, [round(v, 3) for v in b]))
        near.sort()
    out[r] = {"solids": len(mine), "union": [round(v, 3) for v in u] if u else None,
              "solid_boxes": [[round(v, 3) for v in b] for b in mine], "nearest_z_overlapping": near[:6]}
json.dump(out, open(sys.argv[3], "w"), indent=1)
for r, v in out.items():
    print(r, v["solids"], v["union"], v["nearest_z_overlapping"][:3])
