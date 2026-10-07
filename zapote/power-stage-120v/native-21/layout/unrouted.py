#!/usr/bin/env python3
"""Per-net unrouted connections from a KiCad DRC JSON report (its ratsnest edges).

    python3 unrouted.py DRC.json [OUT.json]
"""
import collections
import json
import re
import sys

d = json.load(open(sys.argv[1]))
c = collections.Counter()
for v in d.get("unconnected_items", []):
    m = re.search(r"\[([^\]]*)\]", v["items"][0]["description"])
    c[m.group(1) if m else "?"] += 1
print("unrouted connections", sum(c.values()), "nets", len(c))
if len(sys.argv) > 2:
    json.dump(dict(c.most_common()), open(sys.argv[2], "w"), indent=1)
