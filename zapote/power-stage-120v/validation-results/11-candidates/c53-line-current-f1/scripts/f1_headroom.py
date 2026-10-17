import sys, json
E = "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-plan/enclosure-fit"
sys.path.insert(0, E)
import fit_gate as g
items = g.catalog_names(g.R4)
crt = json.load(open(E + "/native21-courtyards.json"))
print("F1 courtyard", crt["F1"], "J1", crt.get("J1"), "RV1", crt.get("RV1"))
def pose(b, p, x0, y0, zb=26.0):
    if p == "mirror-legacy": return [x0-b[3], y0-b[4], zb+b[2], x0-b[0], y0-b[1], zb+b[5]]
    return [x0+b[0], y0-b[4], zb+b[2], x0+b[3], y0-b[1], zb+b[5]]
for p, x0, y0 in (("mirror-legacy", 141, 236), ("translate", -149, 236)):
    for name, rect in (("F1 courtyard", crt["F1"][:4]), ):
        last_ok = None
        for h in [x*0.5 for x in range(10, 161)]:
            b = [rect[0], rect[1], 1.6, rect[2], rect[3], 1.6 + h]
            if g.box_hits(pose(b, p, x0, y0), items): print(p, name, "first hit at h", h, g.box_hits(pose(b,p,x0,y0), items)[:3]); break
            last_ok = h
        print(p, name, "max clear height above board (mm)", last_ok)
    # footprint growth: how far can F1 rect grow in +y (into board) / -y (off edge) at 20 mm height
    for grow in (5, 10, 15, 20, 30):
        b = [crt["F1"][0], crt["F1"][1], 1.6, crt["F1"][2], crt["F1"][3] + grow, 1.6 + 25]
        print(p, "F1 rect +%d mm in y, 25 mm tall:" % grow, g.box_hits(pose(b, p, x0, y0), items)[:3])
