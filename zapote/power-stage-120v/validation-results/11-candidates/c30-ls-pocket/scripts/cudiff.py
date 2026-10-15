#!/usr/bin/env python3
"""Items in copper.json A missing from B and back (tracks / vias / zones by net, layer, geometry). Layout aid.

    python3 -I cudiff.py A.json B.json
"""
import json
import sys

A, B = (json.load(open(f)) for f in sys.argv[1:3])


def key(kind, it):
    if kind == "tracks":
        return (it["net"], it["layer"], it["width"], json.dumps(it["points"]))
    if kind == "vias":
        return (it["net"], tuple(round(v, 3) for v in it["at"]), it["size"])
    return (it["net"], it["layer"], it.get("name", ""), json.dumps(it["outline"])[:80])


for kind in ("tracks", "vias", "zones"):
    ka = {key(kind, i) for i in A.get(kind, [])}
    kb = {key(kind, i) for i in B.get(kind, [])}
    for k in sorted(ka - kb):
        print("-", kind, *k)
    for k in sorted(kb - ka):
        print("+", kind, *k)
