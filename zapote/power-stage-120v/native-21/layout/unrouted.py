#!/usr/bin/env python3
"""Per-net unrouted connection count of a (filled) board, from KiCad's ratsnest.

    KICAD_PY unrouted.py BOARD.kicad_pcb [OUT.json]
"""
import json
import sys

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
b.BuildConnectivity()
conn = b.GetConnectivity()
pads_by_net = {}
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetNetCode() > 0:
            pads_by_net.setdefault(p.GetNetname(), []).append(p)
out = {}
for net, pads in pads_by_net.items():
    seen, islands = set(), 0
    for p in pads:
        if p.m_Uuid.AsString() in seen:
            continue
        islands += 1
        seen.add(p.m_Uuid.AsString())
        for q in conn.GetConnectedPads(p):
            seen.add(q.m_Uuid.AsString())
    if islands > 1:
        out[net] = islands - 1
print("unrouted connections", sum(out.values()), "nets", len(out), "of", len(pads_by_net))
if len(sys.argv) > 2:
    json.dump(dict(sorted(out.items(), key=lambda kv: -kv[1])), open(sys.argv[2], "w"), indent=1)
