"""Datasheet-envelope boxes of the stage-52 parts, posed into an enclosure catalog, with the nearest catalog items.
Pose (a) of DECISIONS 2026-10-09 / R31+: world = (x - 141, 236 - y, 26 + z) by default (R43 catalog board slab
x -141..149, y 46..236, z 26..27.5). Usage: python3 -I enclosure_clear.py CATALOG.json OUT.json [--mirror-legacy]"""
import json, sys
cat = json.load(open(sys.argv[1]))
mirror = "--mirror-legacy" in sys.argv
T = 1.653  # native-21/stackup.json board_thickness_mm
# local board frame (x right, y down, z up from board bottom); datasheet maximum envelopes
env = {}
for r, y0 in [("C21", 53.2), ("C22", 68.2), ("C23", 83.2), ("C151", 98.2), ("C152", 113.2)]:
    env[r] = [161.0, y0 - 7.25, T, 187.5, y0 + 7.25, T + 29.5]       # B3264*H p.14 14.5 x 29.5 x 26.5, pin 1 at x 163
env["L1"] = [214.5, 31.0, T, 259.5, 56.0, T + 41.0]                  # 07/12 sheet p.3: 45 x 25 x 41 max
env["C3"] = [215.5, 100.8, T, 224.5, 104.8, T + 12.0]                # Murata p.9 J4: D 9.0, T 4.0, crimp <= 3.0
env["C4"] = [215.5, 107.1, T, 224.5, 111.1, T + 12.0]
def pose(b):
    if mirror:
        return [141 - b[3], 236 - b[4], 26 + b[2], 141 - b[0], 236 - b[1], 26 + b[5]]
    return [b[0] - 141, 236 - b[4], 26 + b[2], b[3] - 141, 236 - b[1], 26 + b[5]]
def sep(a, b):
    g = [max(b[0] - a[3], a[0] - b[3]), max(b[1] - a[4], a[1] - b[4]), max(b[2] - a[5], a[2] - b[5])]
    return max(g), g
out = {}
for r, b in env.items():
    w = pose(b)
    rows = []
    for x in cat:
        bb = x.get("bbox")
        if not bb or x["name"] == "electronics_native21_board":
            continue
        d, g = sep(w, bb)
        rows.append((round(d, 2), x["name"], [round(v, 1) for v in bb], [round(v, 2) for v in g]))
    rows.sort()
    out[r] = {"world": [round(v, 2) for v in w], "nearest": rows[:5]}
    print(r, out[r]["world"])
    for row in rows[:4]:
        print("    ", row)
json.dump(out, open(sys.argv[2], "w"), indent=1)
