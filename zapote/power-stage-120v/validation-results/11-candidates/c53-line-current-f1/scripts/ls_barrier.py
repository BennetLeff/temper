"""Where does LS-domain (HOT5 / R5 Kelvin) copper face SELV copper across the 8 mm barrier on s51?"""
import json, numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
B = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s51/c51int"
c = json.load(open(B + "/copper-dump.json"))
SELV = set(json.load(open("/Users/bennet/.claude/jobs/fbfc46b4/tmp/cert-prov/barrier_map.npz.selv.json")))
LS = {"ocp_kelvin_p", "ocp_kelvin_n", "hot5", "n_ls", "leg_ret", "v15_ls", "ls_v5", "vsense_in", "bus_fault_hot", "hb_tx", "hb_rc", "hv_ret"}
def geoms(pred):
    g = []
    for t in c["tracks"]:
        if pred(t["net"]): g.append(LineString([t["a"], t["b"]]).buffer(t["w"] / 2))
    for v in c["vias"]:
        if pred(v["net"]): g.append(Point(v["at"]).buffer(v["d"] / 2))
    for p in c["pads"]:
        if pred(p["net"]) and len(p["pts"]) >= 3: g.append(Polygon(p["pts"]).buffer(0))
    for z in c["zones"]:
        if pred(z["net"]) and len(z["pts"]) >= 3: g.append(Polygon(z["pts"]).buffer(0))
    return unary_union(g)
S = geoms(lambda n: n in SELV); L = geoms(lambda n: n in LS)
band = L.buffer(10.0).intersection(S)   # SELV copper within 10 mm of LS copper
print("SELV copper within 10 mm of LS-domain copper: bounds", [round(v, 1) for v in band.bounds], "area %.0f mm2" % band.area)
parts = list(band.geoms) if hasattr(band, "geoms") else [band]
for p in sorted(parts, key=lambda p: -p.area)[:10]:
    print("  piece bounds", [round(v, 1) for v in p.bounds], "area %.1f" % p.area, "min dist to LS %.2f" % p.distance(L))
