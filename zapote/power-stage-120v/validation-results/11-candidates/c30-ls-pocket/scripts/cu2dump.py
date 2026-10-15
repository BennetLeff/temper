#!/usr/bin/env python3
"""copper.json (+ layout/pads.json) -> the copper-dump shape view.py / probe.py read (outlines stand in for fills).

    python3 -I cu2dump.py COPPER.json PADS.json OUT.json
"""
import json
import sys

cu, pads = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
at = {f"{p['ref']}.{p['pad']}": (p["x"], p["y"]) for p in pads}
xy = lambda q: list(at[q]) if isinstance(q, str) else q
tracks = [{"net": t["net"], "layer": t["layer"], "w": t["width"], "a": xy(a), "b": xy(b)}
          for t in cu["tracks"] for a, b in zip(t["points"], t["points"][1:])]
vias = [{"net": v["net"], "at": v["at"], "d": v["size"]} for v in cu["vias"]]
zones = [{"net": z["net"], "layer": z["layer"], "pts": z["outline"], "holes": z.get("holes", [])} for z in cu["zones"]]
pd = [{"net": p["net"], "ref": p["ref"], "tht": p["tht"], "layers": ["F.Cu"] if not p["tht"] else ["*"],
       "pts": [[p["box"][0], p["box"][1]], [p["box"][2], p["box"][1]], [p["box"][2], p["box"][3]], [p["box"][0], p["box"][3]]]}
      for p in pads]
json.dump({"zones": zones, "tracks": tracks, "vias": vias, "pads": pd, "edges": []}, open(sys.argv[3], "w"))
