#!/usr/bin/env python3
"""Stage 53 S10 planning aid: apply candidate copper edits (s10edits53.EDITS, the same ones patches21.edit_base53 makes
to the frozen base) to a built board's copper dump, re-fill the touched pours approximately (shapely: outline minus
other-net copper + 0.2 mm, other-net fills + 0.2 mm, 0.2 mm minimum width, islands without a same-net item dropped),
and write a dump that return_path19.py can gate.

    python3 -I s10sim53.py IN_DUMP.json OUT_DUMP.json

A planning model only: the board's own KiCad fill (passes, then the chain's return_path19 run) is the evidence.
"""
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s10edits53 import EDITS  # noqa: E402

CLR, MINW = 0.2, 0.2
R3 = lambda q: (round(q[0], 3), round(q[1], 3))


def tgeom(t, extra=0.0):
    w = t["w"] / 2 + extra
    return LineString([t["a"], t["b"]]).buffer(w) if t["a"] != t["b"] else Point(t["a"]).buffer(w)


def pieces(g):
    return [] if g.is_empty else (list(g.geoms) if hasattr(g, "geoms") else [g])


def zpoly(z):
    return Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0)


def onlayer(p, lay):
    return p.get("tht") or lay in p.get("layers", ["F.Cu"])


def seg_hits(d, net, lay, a, b):
    return [t for t in d["tracks"] if t["net"] == net and t["layer"] == lay and {R3(t["a"]), R3(t["b"])} == {R3(a), R3(b)}]


def main():
    d = json.load(open(sys.argv[1]))
    for net, lay, a, b in EDITS.get("remove_tracks", []):
        hit = seg_hits(d, net, lay, a, b)
        if len(hit) != 1:
            raise SystemExit(f"remove {net} {lay} {a} {b}: {len(hit)} hits")
        d["tracks"].remove(hit[0])
    for net, (l0, l1), a, b in EDITS.get("relayer_tracks", []):
        hit = seg_hits(d, net, l0, a, b)
        if len(hit) != 1:
            raise SystemExit(f"relayer {net} {a} {b}: {len(hit)} hits")
        hit[0]["layer"] = l1
    for net, lay, w, pts in EDITS.get("add_tracks", []):
        for a, b in zip(pts, pts[1:]):
            d["tracks"].append({"net": net, "layer": lay, "w": w, "a": list(a), "b": list(b)})
    # every fill on a layer whose tracks changed loses the new other-net copper's clearance
    changed = {t["layer"] for t in d["tracks"]}
    newt = [(lay, net, w, pts) for net, lay, w, pts in EDITS.get("add_tracks", [])] + \
           [(l1, net, 0.25, [a, b]) for net, (l0, l1), a, b in EDITS.get("relayer_tracks", [])]
    for lay, net, w, pts in newt:
        cut = unary_union([tgeom({"a": a, "b": b, "w": w}, CLR) for a, b in zip(pts, pts[1:])])
        for z in d["zones"]:
            if z["layer"] == lay and z["net"] != net and len(z["pts"]) > 2:
                g = zpoly(z)
                if g.intersects(cut):
                    z["_g"] = g.difference(cut)
    for net, lay, poly in EDITS.get("take", []):
        P = Polygon(poly).buffer(CLR)
        for z in d["zones"]:
            if z["net"] == net and z["layer"] == lay and len(z["pts"]) > 2:
                g = z.get("_g", zpoly(z))
                if g.intersects(P):
                    z["_g"] = g.difference(P)
    zs = []
    for z in d["zones"]:
        if "_g" not in z:
            zs.append(z)
            continue
        for p in pieces(z["_g"].buffer(-MINW / 2).buffer(MINW / 2)):
            if p.geom_type == "Polygon" and p.area > 0.05:
                zs.append({"net": z["net"], "layer": z["layer"], "pts": [list(c) for c in p.exterior.coords],
                           "holes": [[list(c) for c in i.coords] for i in p.interiors]})
    d["zones"] = zs
    # removed tracks free their clearance in other fills only if a refill would grow into it: added pours below do
    for net, lay, poly in EDITS.get("add", []):
        P = Polygon(poly)
        near = P.buffer(1.0)
        obst = [tgeom(t, CLR) for t in d["tracks"] if t["layer"] == lay and t["net"] != net]
        obst += [Point(v["at"]).buffer(v["d"] / 2 + CLR) for v in d["vias"] if v["net"] != net]
        obst += [Polygon(p["pts"]).buffer(0).buffer(CLR) for p in d["pads"] if p["net"] != net and onlayer(p, lay)]
        obst += [zpoly(z).buffer(CLR) for z in d["zones"] if z["layer"] == lay and z["net"] != net and len(z["pts"]) > 2]
        f = P.difference(unary_union([o for o in obst if o.intersects(near)]))
        f = f.buffer(-MINW / 2).buffer(MINW / 2)
        own = [tgeom(t) for t in d["tracks"] if t["layer"] == lay and t["net"] == net]
        own += [Point(v["at"]).buffer(v["d"] / 2) for v in d["vias"] if v["net"] == net]
        own += [Polygon(p["pts"]).buffer(0) for p in d["pads"] if p["net"] == net and onlayer(p, lay)]
        own += [zpoly(z) for z in d["zones"] if z["layer"] == lay and z["net"] == net and len(z["pts"]) > 2]
        ownu = unary_union([o for o in own if o.intersects(near)])
        for p in pieces(f):
            if p.geom_type != "Polygon" or p.area < 0.05:
                continue
            if p.buffer(0.01).intersects(ownu):
                d["zones"].append({"net": net, "layer": lay, "pts": [list(c) for c in p.exterior.coords],
                                   "holes": [[list(c) for c in i.coords] for i in p.interiors]})
                print(f"  fill {net} {lay} {p.area:.2f} mm2 {[round(v, 2) for v in p.bounds]}")
            else:
                print(f"  island dropped {net} {lay} {p.area:.2f} mm2 {[round(v, 2) for v in p.bounds]}")
    json.dump(d, open(sys.argv[2], "w"))


if __name__ == "__main__":
    main()
