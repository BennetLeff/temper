"""Scan s51 for spots where a second DWV SOIC-8 isolated amplifier (AMC1301DWV, U4's land pattern)
could straddle the HOT-SELV barrier: HOT pads >= 8.0 mm from all SELV copper, SELV pads >= 8.0 mm from all
HOT copper (plan view, every layer), body + 2.5 mm end strips for decoupling/RC clear of every footprint bbox."""
import numpy as np, sys
m = np.load(sys.argv[1]); res = float(m["res"])
dh, ds, crt = m["dh"], m["ds"], m["crt"]
ny, nx = crt.shape
def cells(x0, y0, x1, y1):
    return slice(max(0, int(y0 / res)), min(ny, int(np.ceil(y1 / res)))), slice(max(0, int(x0 / res)), min(nx, int(np.ceil(x1 / res))))
# U4-relative geometry (rows along x): pad row extents x +-2.2, HOT row y -6.225..-4.425, SELV row +4.425..+6.225
out = []
for rot in (0, 90):
    for flip in (1, -1):
        for cy in np.arange(8, 186, 0.5):
            for cx in np.arange(8, 286, 0.5):
                def R(x0, y0, x1, y1):
                    y0, y1 = sorted((flip * y0, flip * y1))
                    if rot == 90: x0, y0, x1, y1 = y0, x0, y1, x1
                    return cx + x0, cy + y0, cx + x1, cy + y1
                hp = cells(*R(-2.2, -6.225, 2.2, -4.425)); sp = cells(*R(-2.2, 4.425, 2.2, 6.225))
                if ds[hp].min() < 8.0 or dh[sp].min() < 8.0: continue
                if dh[hp].min() > 3.0 or ds[sp].min() > 3.0: continue   # must be reachable: own-domain copper within 3 mm
                body = cells(*R(-3.2, -6.5, 3.2, 6.5))                 # body courtyard only (relaxed)
                if crt[body].any(): continue
                out.append((rot, flip, cx, cy, round(float(ds[hp].min()), 2), round(float(dh[sp].min()), 2)))
print(len(out))
# cluster
import collections
cl = collections.defaultdict(list)
for o in out: cl[(o[0], o[1], int(o[2] // 10), int(o[3] // 10))].append(o)
for k, v in sorted(cl.items(), key=lambda kv: -len(kv[1]))[:25]:
    xs = [o[2] for o in v]; ys = [o[3] for o in v]
    print(k[:2], "n=%d" % len(v), "x %.1f-%.1f y %.1f-%.1f" % (min(xs), max(xs), min(ys), max(ys)), "best", max(v, key=lambda o: min(o[4], o[5])))
