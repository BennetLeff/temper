#!/usr/bin/env python3
"""Candidate 43 control: did the cleanup bring any gate-network track closer to other-net copper, or lengthen it?

    python3 -I gate_net_spacing.py BEFORE/copper-dump.json AFTER/copper-dump.json [--json OUT]

For every net of the four CFD7 gate networks (leg_{a,b}-{gate,off,out}_{h,l}), per layer: total track length and the
minimum edge-to-edge distance from the net's tracks to any other net's track, via, pad or zone fill on that layer, and to
copper of another HOT potential group (rules21.clearance >= 3.2 mm; shapely buffers of the track centrelines by w/2).
Prints both boards side by side; exit 1 if any minimum spacing falls by more than 0.005 mm, if an other-group spacing
falls below 3.4 mm (the c39 hand-laid runs keep >= 3.4 mm from the other group's R_off / OUT copper), or if any switch's
gate-loop track (gate + off + out nets, every layer) gets longer by more than 0.05 mm. A single net or layer that gets
longer is listed as a note.
"""
import json
import sys
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "native-21/layout"))
import rules21  # noqa: E402

NETS = [f"leg_{l}-{k}_{s}" for l in "ab" for k in ("gate", "off", "out") for s in "hl"]


def shapes(d, layer):
    out = []
    for t in d["tracks"]:
        if t["layer"] == layer:
            out.append((t["net"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2, cap_style=1)))
    for v in d["vias"]:
        out.append((v["net"], Point(v["at"]).buffer(v["d"] / 2)))
    for p in d["pads"]:
        if layer in p["layers"] and len(p["pts"]) >= 3:
            out.append((p["net"], Polygon(p["pts"]).buffer(0)))
    for z in d["zones"]:
        if z["layer"] == layer and len(z["pts"]) >= 3:
            out.append((z["net"], Polygon(z["pts"]).buffer(0)))
    return out


def measure(path):
    d = json.load(open(path))
    res = {}
    layers = sorted({t["layer"] for t in d["tracks"] if t["net"] in NETS})
    for layer in layers:
        sh = shapes(d, layer)
        geoms = [g for _, g in sh]
        tree = STRtree(geoms)
        for net in NETS:
            mine = [LineString([t["a"], t["b"]]).buffer(t["w"] / 2, cap_style=1)
                    for t in d["tracks"] if t["net"] == net and t["layer"] == layer]
            if not mine:
                continue
            u = unary_union(mine)
            length = sum(LineString([t["a"], t["b"]]).length for t in d["tracks"] if t["net"] == net and t["layer"] == layer)
            best = cross = 99.0
            for i in tree.query(u.buffer(6.0)):
                n, g = sh[i]
                if n != net:
                    dd = u.distance(g)
                    best = min(best, dd)
                    if rules21.clearance(net, n) >= 3.2:      # another HOT potential group (or the tank / barrier)
                        cross = min(cross, dd)
            res[f"{net} {layer}"] = {"length_mm": round(length, 3), "min_other_net_mm": round(best, 3),
                                     "min_other_group_mm": round(cross, 3)}
    return res


def main():
    a, b = measure(sys.argv[1]), measure(sys.argv[2])
    bad, notes = [], []
    loops = {}
    for sw in [f"leg_{l}_{h}" for l in "ab" for h in "hl"]:
        leg, side = sw[:5], sw[-1]
        ks = [k for k in set(a) | set(b) if k.split()[0] in (f"{leg}-gate_{side}", f"{leg}-off_{side}", f"{leg}-out_{side}")]
        la = round(sum(a[k]["length_mm"] for k in ks if k in a), 3)
        lb = round(sum(b[k]["length_mm"] for k in ks if k in b), 3)
        loops[sw] = {"before_mm": la, "after_mm": lb}
        print(f"loop {sw}: {la} -> {lb} mm")
        if lb > la + 0.05:
            bad.append(f"loop {sw}: {la} -> {lb} mm")
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        print(f"{k:28s} {x} -> {y}")
        if x and y:
            if y["min_other_net_mm"] < x["min_other_net_mm"] - 0.005:
                bad.append(f"{k}: spacing {x['min_other_net_mm']} -> {y['min_other_net_mm']}")
            if y["min_other_group_mm"] < x["min_other_group_mm"] - 0.005 and y["min_other_group_mm"] < 3.4:
                bad.append(f"{k}: other-group spacing {x['min_other_group_mm']} -> {y['min_other_group_mm']}")
            if y["length_mm"] > x["length_mm"] + 0.05:
                notes.append(f"{k}: length {x['length_mm']} -> {y['length_mm']}")
        elif x and not y:
            bad.append(f"{k}: no tracks after")
    out = {"before": sys.argv[1], "after": sys.argv[2], "nets": {k: {"before": a.get(k), "after": b.get(k)} for k in sorted(set(a) | set(b))},
           "loops": loops, "failures": bad, "notes": notes, "verdict": "FAIL" if bad else "PASS"}
    if "--json" in sys.argv:
        json.dump(out, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    print(out["verdict"], bad, "notes", notes)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
