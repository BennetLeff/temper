"""Free F.Cu area for a HOT5-domain trip block near the OCP chain on s51:
no footprint bbox; >= 8.0 mm from SELV copper (any layer, plan); >= 5.0 mm from F.Cu res_a / crbleed (tank rule);
>= 3.2 mm from F.Cu copper of other HOT potential groups; LS-group F.Cu copper (hot5, ocp_kelvin_p, ...) may be
displaced (pours) but tracks count as occupied. Reports the largest empty axis-aligned rectangles."""
import json, numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from shapely import contains_xy
from scipy import ndimage
T = "/Users/bennet/.claude/jobs/fbfc46b4/tmp/cert-prov/"
B = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s51/c51int"
c = json.load(open(B + "/copper-dump.json")); fp = json.load(open(T + "s51_fp.json"))
m = np.load(T + "barrier_map.npz"); res = float(m["res"]); crt = m["crt"]; ds = m["ds"]
LSP = ("ocp_", "ovp_", "hot5", "ref25", "monitor_ls", "bias_ls", "u_hot5", "u_ref", "u_ldo", "u_iso")
LS = {"n_ls", "leg_ret", "hv_ret", "v15_ls", "ls_v5", "vsense_in", "bus_fault_hot", "hb_tx", "hb_rc", "v24_raw"}
isls = lambda n: n in LS or n.startswith(LSP)
TANK = {"res_a", "crbleed_1", "crbleed_2", "crbleed_3"}
other, tank, lstr = [], [], []
for t in c["tracks"]:
    if t["layer"] != "F.Cu": continue
    g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2)
    (tank if t["net"] in TANK else lstr if isls(t["net"]) else other).append(g)
for p in c["pads"]:
    if "F.Cu" not in p["layers"] or len(p["pts"]) < 3: continue
    g = Polygon(p["pts"]).buffer(0)
    (tank if p["net"] in TANK else lstr if isls(p["net"]) else other).append(g)
for v in c["vias"]:
    g = Point(v["at"]).buffer(v["d"] / 2)
    (tank if v["net"] in TANK else lstr if isls(v["net"]) else other).append(g)
for z in c["zones"]:
    if z["layer"] != "F.Cu" or len(z["pts"]) < 3: continue
    g = Polygon(z["pts"]).buffer(0)
    if z["net"] in TANK: tank.append(g)
    elif not isls(z["net"]): other.append(g)
ny, nx = crt.shape
xs = (np.arange(nx) + 0.5) * res; ys = (np.arange(ny) + 0.5) * res; X, Y = np.meshgrid(xs, ys)
bad = crt | (ds < 8.0)
bad |= contains_xy(unary_union(tank).buffer(5.0), X, Y)
bad |= contains_xy(unary_union(other).buffer(3.2), X, Y)
bad |= contains_xy(unary_union(lstr).buffer(0.2), X, Y)
win = (X > 85) & (X < 140) & (Y > 38) & (Y < 100)
free = ~bad & win
print("free F.Cu-legal area in window x85-140 y38-100: %.0f mm2" % (free.sum() * res * res))
lab, n = ndimage.label(free)
sizes = ndimage.sum(free, lab, range(1, n + 1)) * res * res
for i in np.argsort(-sizes)[:6]:
    yy, xx = np.where(lab == i + 1)
    print("  blob %.0f mm2  x %.1f-%.1f  y %.1f-%.1f" % (sizes[i], xx.min() * res, xx.max() * res, yy.min() * res, yy.max() * res))
# largest empty rectangle >= 6 mm short side, by brute force on candidate sizes
for W, H in ((14, 8), (12, 8), (10, 8), (12, 6), (10, 6), (8, 6)):
    hits = []
    w, h = int(W / res), int(H / res)
    S = np.pad(np.cumsum(np.cumsum(bad | ~win, 0), 1), ((1, 0), (1, 0)))
    for j in range(0, ny - h):
        for i in range(0, nx - w):
            if S[j + h, i + w] - S[j, i + w] - S[j + h, i] + S[j, i] == 0: hits.append((i * res, j * res))
    print("%dx%d legal empty rectangles: %d" % (W, H, len(hits)), ("e.g. x %.1f y %.1f" % hits[len(hits) // 2]) if hits else "")
