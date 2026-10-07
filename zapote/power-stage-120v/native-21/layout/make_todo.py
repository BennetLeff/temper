#!/usr/bin/env python3
"""Turn a DRC report's ratsnest into pad pairs for route21 (todo.json).

    python3 make_todo.py DRC.json [todo.json]
Non-pad endpoints (pours, tracks, vias) are replaced by the nearest pad of the same net.
Pairs are ordered: short local pairs first.
"""
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
pads = json.loads((HERE / "pads.json").read_text())
d = json.load(open(sys.argv[1]))


def name(net, item):
    m = re.search(r"Pad (\S+) \[[^\]]*\] of (\S+)", item["description"])
    if m:
        return f"{m.group(2)}.{m.group(1)}"
    t = re.search(r"^(Track|Via) \[[^\]]*\] on ([A-Za-z0-9.]+)", item["description"])
    if t:      # existing copper: route to the point KiCad names on it
        lay = t.group(2) if t.group(1) == "Track" else "*"
        return f"@{item['pos']['x']:.3f},{item['pos']['y']:.3f},{lay}"
    x, y = item["pos"]["x"], item["pos"]["y"]
    c = [p for p in pads if p["net"] == net]
    p = min(c, key=lambda p: math.hypot(p["x"] - x, p["y"] - y))
    return f"{p['ref']}.{p['pad']}"


out, seen = [], set()
for v in d.get("unconnected_items", []):
    a, b = v["items"]
    net = re.search(r"\[([^\]]*)\]", a["description"]).group(1)
    pa, pb = name(net, a), name(net, b)
    key = (net, *sorted((pa, pb)))
    if pa == pb or key in seen:
        continue
    seen.add(key)
    pp = {f"{p['ref']}.{p['pad']}": p for p in pads}

    def xy(n):
        if n.startswith("@"):
            x, y, _ = n[1:].split(",")
            return float(x), float(y)
        return pp[n]["x"], pp[n]["y"]
    try:
        dist = math.dist(xy(pa), xy(pb))
    except KeyError:
        dist = 99
    out.append((dist, net, pa, pb))
out.sort()
# Cumulative: route21 rebuilds all copper each run, so pairs joined in earlier runs stay listed
# (they route identically again); new open pairs are appended after them.
dest = Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "todo.json")
old = json.loads(dest.read_text()) if dest.exists() else []
have = {(n, *sorted((a, b))) for n, a, b in old}
new = [[n, a, b] for _, n, a, b in out if (n, *sorted((a, b))) not in have]
dest.write_text(json.dumps(old + new, indent=0) + "\n")
print(len(old), "kept,", len(new), "new pairs")
