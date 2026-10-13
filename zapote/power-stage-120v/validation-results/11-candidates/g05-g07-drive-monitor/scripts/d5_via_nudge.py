#!/usr/bin/env python3
"""D5 (HOT-SELV 8.047 mm) sits on the two DIS layer-change vias; how far does a nudge move the metric?

    python3 -I validation-results/11-candidates/g05-g07-drive-monitor/scripts/d5_via_nudge.py
Reads the 19c all-copper dump (read-only). Recomputes the HOT-SELV minimum over the nets that carry the pair
(n_ha/n_hb zones etc. vs the SELV nets of G05/G07), then moves the leg_a-dis / leg_b-dis stub vias and recomputes.
HOT set: n_ha p_ha sw_a n_hb p_hb sw_b n_ls v15_ls leg_ret. SELV set: v3v3 selv_gnd permit bias_bad pwm_* *-dis *-driver_dis *-permit_gate
bias_bad_raw bias_bad_flt (the nets of the two groups; the board's own audit is native-21/verification/d5-audit.json = 8.047).
"""
import gzip, json, os, sys
from shapely.geometry import LineString, Point, Polygon
sys.dont_write_bytecode = True
PS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../.."))
d = json.load(gzip.open(f"{PS}/native-21/verification/native21s19c-all-copper.json.gz"))
HOT = {"n_ha", "p_ha", "sw_a", "n_hb", "p_hb", "sw_b", "n_ls", "v15_ls", "leg_ret"}
def selv(n):
    return n in ("v3v3", "selv_gnd", "permit", "bias_bad", "bias_bad_raw", "bias_bad_flt") or n.startswith("pwm_") or n.endswith(("-dis", "-driver_dis", "-permit_gate"))
def geom(p, dx=0.0, dy=0.0):
    k = p["kind"]
    if k == "via": return Point(p["centre"][0] + dx, p["centre"][1] + dy).buffer(p["diameter_mm"] / 2)
    if k == "track": return LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2)
    if k == "pad": return Polygon(p["shell"]).buffer(0)
    return Polygon(p["shell"], p.get("holes") or []).buffer(0)
from shapely.strtree import STRtree
hot = [(p, geom(p)) for p in d["primitives"] if p["net"] in HOT]
tree = STRtree([g for _, g in hot])
sel = [p for p in d["primitives"] if selv(p["net"])]
STUBS = {"leg_a-dis": (75.544, 58.797), "leg_b-dis": (28.544, 58.797)}
def is_stub(p):
    return p["kind"] == "via" and p["net"] in STUBS and abs(p["centre"][0] - STUBS[p["net"]][0]) < 1e-3 and abs(p["centre"][1] - STUBS[p["net"]][1]) < 1e-3
def dist(g):
    i = tree.nearest(g)
    return g.distance(tree.geometries[i])
fixed = sorted((dist(geom(q)), q["net"], q["kind"], q["layer"]) for q in sel if not is_stub(q))
stubs = [q for q in sel if is_stub(q)]
base_stub = min(dist(geom(q)) for q in stubs)
print(f"HOT-SELV minimum (this script): {min(base_stub, fixed[0][0]):.3f} mm (stub vias {base_stub:.3f}); board audit says 8.047")
print(f"closest item that is not a stub via: {fixed[0][0]:.3f} mm ({fixed[0][1]} {fixed[0][2]} {fixed[0][3]})")
best = None
for dx, dy in [(0.1, 0), (0.15, 0), (0.2, 0), (-0.1, 0), (0, 0.1), (0, -0.1), (0.1, 0.1), (0.1, -0.1)]:
    m = min(min(dist(geom(q, dx, dy)) for q in stubs), fixed[0][0])
    print(f"  shift the stub vias by ({dx:+.2f},{dy:+.2f}) mm -> HOT-SELV minimum {m:.3f} mm")
    if best is None or m > best[0]: best = (m, dx, dy)
print(f"best simple nudge: {best}; gain {best[0]-min(base_stub, fixed[0][0]):+.3f} mm, capped by the next item at {fixed[0][0]:.3f} mm")
