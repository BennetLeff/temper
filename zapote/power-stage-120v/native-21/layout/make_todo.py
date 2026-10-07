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
    dist = math.hypot(pp[pa]["x"] - pp[pb]["x"], pp[pa]["y"] - pp[pb]["y"]) if pa in pp and pb in pp else 99
    out.append((dist, net, pa, pb))
out.sort()
Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "todo.json").write_text(
    json.dumps([[n, a, b] for _, n, a, b in out], indent=0) + "\n")
print(len(out), "pairs")
