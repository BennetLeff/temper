"""Free courtyard rectangles in the HOT5 / LS area near the OCP chain (U6-U8, R32-R35) on s51, for a
hardware average-current trip block (zero-drift amp + comparator + AND gate + ~8 x 0603)."""
import numpy as np, sys, json
from shapely.geometry import box, LineString, Point, Polygon
m = np.load(sys.argv[1]); res = float(m["res"]); crt = m["crt"]; ds = m["ds"]
ny, nx = crt.shape
B = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s51/c51int"
c = json.load(open(B + "/copper-dump.json"))
segs = [(t["net"], t["layer"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2)) for t in c["tracks"]]
segs += [(v["net"], "via", Point(v["at"]).buffer(v["d"] / 2)) for v in c["vias"]]
zones = [(z["net"], z["layer"], Polygon(z["pts"]).buffer(0)) for z in c["zones"] if len(z["pts"]) >= 3]
for W, H in ((12, 8), (10, 6)):
    found = []
    for y in np.arange(40, 100, 0.5):
        for x in np.arange(85, 140, 0.5):
            sl = (slice(int(y / res), int((y + H) / res)), slice(int(x / res), int((x + W) / res)))
            if crt[sl].any() or ds[sl].min() < 8.0: continue
            found.append((x, y))
    print("free %dx%d rects:" % (W, H), len(found))
    # report a few distinct ones nearest the OCP chain centre (110, 62)
    found.sort(key=lambda p: (p[0] + W / 2 - 110) ** 2 + (p[1] + H / 2 - 62) ** 2)
    shown = []
    for x, y in found:
        if any(abs(x - a) < W and abs(y - b) < H for a, b in shown): continue
        shown.append((x, y))
        r = box(x, y, x + W, y + H)
        tr = sorted(set((n, l) for n, l, g in segs if g.intersects(r)))
        zn = sorted(set((n, l) for n, l, g in zones if g.intersects(r)))
        print("  rect x %.1f-%.1f y %.1f-%.1f  tracks/vias:%s  zones:%s" % (x, x + W, y, y + H, tr, zn))
        if len(shown) == 6: break
