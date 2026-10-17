import json, sys
from shapely.geometry import Polygon, LineString, Point, box
B = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s51/c51int"
c = json.load(open(B + "/copper-dump.json"))
items = []
for t in c["tracks"]: items.append((t["net"], t["layer"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2)))
for v in c["vias"]: items.append((v["net"], "via", Point(v["at"]).buffer(v["d"] / 2)))
for p in c["pads"]:
    if len(p["pts"]) >= 3: items.append((p["net"], "pad:" + p["ref"], Polygon(p["pts"]).buffer(0)))
for z in c["zones"]:
    if len(z["pts"]) >= 3: items.append((z["net"], "zone:" + z["layer"], Polygon(z["pts"]).buffer(0)))
spots = [(71.0, 110.0), (47.0, 123.0), (50.0, 123.0)]
for cx, cy in spots:
    for side, x in (("left", cx - 5.3), ("right", cx + 5.3)):
        pt = Point(x, cy)
        near = sorted(((g.distance(pt), n, l) for n, l, g in items), key=lambda r: r[0])
        seen = []; 
        for d, n, l in near:
            if n not in [s[1] for s in seen]: seen.append((round(d, 2), n, l))
            if len(seen) == 5: break
        print((cx, cy), side, seen)
    # copper crossing the courtyard (vertical orientation: 13 x 6.4 rotated -> 13 wide in x, 6.4 tall)
    crt = box(cx - 6.5, cy - 3.2, cx + 6.5, cy + 3.2)
    inside = sorted(set((n, l) for n, l, g in items if g.intersects(crt) and not l.startswith("zone")))
    zones = sorted(set((n, l) for n, l, g in items if g.intersects(crt) and l.startswith("zone")))
    print("   tracks/pads/vias in courtyard:", inside)
    print("   zones in courtyard:", zones)
