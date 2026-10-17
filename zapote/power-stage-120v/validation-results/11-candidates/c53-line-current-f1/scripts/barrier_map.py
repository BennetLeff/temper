"""Domain map of s51 c51int (plan view, all copper layers) and courtyard occupancy.
Reads copper-dump.json + s51_fp.json; writes barrier_map.npz and prints the HOT-SELV gap census."""
import json, sys, numpy as np
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from scipy import ndimage
B = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s51/c51int"
c = json.load(open(B + "/copper-dump.json"))
fp = json.load(open(sys.argv[1]))
ISO = {"U1","U2","U4","U9","U32","U36","T1","U41","U42","PS2","R38","J6","U43","U44"}
import collections
adj = collections.defaultdict(set)
for f in fp["footprints"]:
    if f["ref"] in ISO: continue
    nets = [p[1] for p in f["pads"] if p[1]]
    for a in nets:
        for b in nets: adj[a].add(b)
SELV = set(); st = ["selv_gnd", "v3v3", "ct_s1", "ct_s2", "pwm_ha", "pwm_la", "pwm_hb", "pwm_lb", "vbus_p", "vbus_n", "bus_fault_iso", "hb_rx"]
while st:
    n = st.pop()
    if n in SELV or n == "pe": continue
    SELV.add(n); st += list(adj[n])
assert "hot5" not in SELV and "n_ls" not in SELV and "bus_p" not in SELV, sorted(SELV)
PE = {"pe"}
def dom(n):
    if n == "" or "nc" in n.split("-")[-1] or n.endswith("_nc"): return "NONE"
    if n in PE: return "PE"
    if n in SELV: return "SELV"
    return "HOT"
geo = {"HOT": [], "SELV": [], "PE": [], "NONE": []}
for t in c["tracks"]:
    geo[dom(t["net"])].append(LineString([t["a"], t["b"]]).buffer(t["w"] / 2))
for v in c["vias"]:
    geo[dom(v["net"])].append(Point(v["at"]).buffer(v["d"] / 2))
for p in c["pads"]:
    if len(p["pts"]) >= 3: geo[dom(p["net"])].append(Polygon(p["pts"]).buffer(0))
for z in c["zones"]:
    if len(z["pts"]) >= 3: geo[dom(z["net"])].append(Polygon(z["pts"]).buffer(0))
U = {k: unary_union(v) for k, v in geo.items()}
from shapely.ops import nearest_points
a,b = nearest_points(U["HOT"], U["SELV"]); print("closest HOT-SELV at", a, b)
a,b = nearest_points(U["HOT"], U["PE"]); print("closest HOT-PE at", a, b)
print("min HOT-SELV plan distance %.3f mm" % U["HOT"].distance(U["SELV"]))
print("min HOT-PE plan distance %.3f mm" % U["HOT"].distance(U["PE"]))
res = 0.25
nx, ny = int(290 / res), int(190 / res)
def raster(geom):
    from shapely import contains_xy
    xs = (np.arange(nx) + 0.5) * res; ys = (np.arange(ny) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    return contains_xy(geom, X, Y)
R = {k: raster(U[k]) for k in U}
dist = {k: ndimage.distance_transform_edt(~R[k]) * res for k in R}
crt = np.zeros((ny, nx), bool)
for f in fp["footprints"]:
    x0, y0, x1, y1 = f["bbox"]
    crt[max(0, int(y0 / res)):int(y1 / res) + 1, max(0, int(x0 / res)):int(x1 / res) + 1] = True
np.savez_compressed(sys.argv[2], hot=R["HOT"], selv=R["SELV"], pe=R["PE"], dh=dist["HOT"], ds=dist["SELV"], dp=dist["PE"], crt=crt, res=res)
json.dump(sorted(SELV), open(sys.argv[2] + ".selv.json", "w"))
