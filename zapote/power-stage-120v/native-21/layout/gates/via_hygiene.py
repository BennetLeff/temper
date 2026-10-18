#!/usr/bin/env python3
"""Stranded-via check on a built board, from its all-copper export (tools/export_power_copper.py).

    python3 -I native-21/layout/gates/via_hygiene.py BOARD-all-copper.json.gz [--json OUT]

A through via carries current or a reference only if its net has copper (a track end or crossing, a pad, or a pour of the
same net) on at least two copper layers at the via centre. One layer means the via goes nowhere:
  stranded_vias   vias whose net touches copper on fewer than two layers (listed with centre and the one layer, if any).
Not counted: plane-stitching vias that land in a pour on two layers (they have copper on both). Vias are taken as
through-hole (the exporter records no layer span); a blind/buried via would need that span added here.
"""
import argparse
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

TOL = 0.01                                  # mm slack on the centre-in-copper tests


def load(path):
    p = Path(path)
    return json.loads((gzip.open(p) if p.suffix == ".gz" else p.open()).read())["primitives"]


def _in_poly(pt, poly):
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _seg_dist(pt, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / n))
    return math.hypot(pt[0] - (ax + t * dx), pt[1] - (ay + t * dy))


def measure(prims):
    layers = sorted({p["layer"] for p in prims if p["kind"] in ("track", "zone") and p.get("layer")})
    by_net = defaultdict(lambda: defaultdict(list))        # net -> layer -> primitives
    for p in prims:
        if p["kind"] in ("track", "pad", "zone") and p.get("net"):
            by_net[p["net"]][p["layer"]].append(p)
    stranded = []
    vias = [p for p in prims if p["kind"] == "via"]
    for v in vias:
        c = tuple(v["centre"])
        hit = set()
        for layer, items in by_net.get(v["net"], {}).items():
            for p in items:
                if p["kind"] == "track":
                    if _seg_dist(c, p["start"], p["end"]) <= p["width_mm"] / 2 + TOL:
                        hit.add(layer)
                        break
                elif _in_poly(c, p["shell"]):
                    hit.add(layer)
                    break
        if len(hit) < 2:
            stranded.append({"net": v["net"], "at": [round(c[0], 3), round(c[1], 3)], "layers_touched": sorted(hit)})
    return {"vias": len(vias), "stranded_vias": len(stranded), "stranded": stranded, "copper_layers": layers}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--json")
    a = ap.parse_args()
    r = measure(load(a.export))
    print("vias %d, stranded %d" % (r["vias"], r["stranded_vias"]))
    for s in r["stranded"][:20]:
        print("  ", s)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1) + "\n")
    raise SystemExit(1 if r["stranded_vias"] else 0)
