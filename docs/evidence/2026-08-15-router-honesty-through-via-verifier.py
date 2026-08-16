#!/usr/bin/env python3
"""Recompute pad connectivity with CORRECT KiCad via semantics.

Per the KiCad .kicad_pcb file-format spec, a via whose block has no
`blind` or `micro` type attribute is a THROUGH via: it connects every
copper layer the board has, regardless of the (layers ...) pair written.
The pad_connectivity_audit (and earlier revisions of this verifier)
modeled via.layers as the restricted pair -- which under-reports
connectivity whenever a net's pads sit on a layer outside that pair.

This script parses the file independently and treats every untyped via
as connecting ALL copper layers. Verdicts: connected / zone_dependent /
broken.
"""
import re
import sys
from collections import defaultdict

import indep_connectivity as ic  # reuse parser + union-find

content = open(sys.argv[1]).read()
n, pads, segs, vias, zones = ic.parse(content)

all_copper = sorted(
    {s.layer for s in segs}
    | {l for v in vias for l in v.layers}
    | {l for z in zones for l in z.layers}
)
for p in pads:
    if p.layer != "*":
        all_copper.append(p.layer)
all_copper = sorted(set(all_copper))

# Which vias carry an explicit blind/micro type attribute?
raw = re.findall(r"\(via\s+(blind|micro)\s+\(at", content)
print("vias with explicit type attr (blind/micro):", len(raw))
print("total vias:", len(vias))
print("copper layers:", all_copper)

pads_by_net = defaultdict(list)
for p in pads:
    pads_by_net[n.get(p.net, f"#{p.net}")].append(p)
segs_by_net = defaultdict(list)
for s in segs:
    segs_by_net[n.get(s.net, f"#{s.net}")].append(s)
vias_by_net = defaultdict(list)
for v in vias:
    vias_by_net[n.get(v.net, f"#{v.net}")].append(v)
zones_by_net = defaultdict(list)
for z in zones:
    zones_by_net[n.get(z.net, f"#{z.net}")].append(z)


def layers_of_pad(p):
    return all_copper if p.layer == "*" else [p.layer]


results = {}
for net, plist in sorted(pads_by_net.items()):
    if len(plist) <= 1:
        results[net] = ("connected", len(plist), len(plist), ())
        continue
    uf = ic.UF()

    def node(pt, layer):
        return (ic.cluster_key(pt), layer)

    for s in segs_by_net.get(net, []):
        uf.union(node(s.p1, s.layer), node(s.p2, s.layer))
    for v in vias_by_net.get(net, []):
        # THROUGH semantics: untyped via connects every copper layer.
        ks = [node(v.pos, l) for l in all_copper]
        for k in ks[1:]:
            uf.union(ks[0], k)
    reprs = []
    for p in plist:
        ns = [node(p.pos, l) for l in layers_of_pad(p)]
        for k in ns[1:]:
            uf.union(ns[0], k)
        reprs.append(ns[0])
    roots = [uf.find(r) for r in reprs]
    counts = defaultdict(int)
    for r in roots:
        counts[r] += 1
    largest = max(counts.values())
    majority_root = max(counts, key=counts.get) if counts and largest > 1 else None
    unreached = [
        p for p, r in zip(plist, roots) if majority_root is None or r != majority_root
    ]
    zone_layers = set()
    for z in zones_by_net.get(net, []):
        zone_layers |= z.layers
    zone_dep = False
    if unreached and zone_layers:
        zone_dep = all(p.layer == "*" or p.layer in zone_layers for p in unreached)
    cat = "connected" if largest == len(plist) else ("zone_dependent" if zone_dep else "broken")
    results[net] = (cat, largest, len(plist), tuple(p.ref for p in unreached))

from collections import Counter

cats = Counter(v[0] for v in results.values())
print("TOTAL nets with pads:", len(results))
print("categories:", dict(cats))
print()
conn = [net for net, v in results.items() if v[0] == "connected"]
zd = [net for net, v in results.items() if v[0] == "zone_dependent"]
br = [net for net, v in results.items() if v[0] == "broken"]
print(f"CONNECTED: {len(conn)}")
print(f"ZONE-DEPENDENT: {len(zd)}")
print(f"BROKEN: {len(br)}")
print()
print("=== broken nets ===")
for net in sorted(br):
    c, l, t, u = results[net]
    print(f"  {net}: {l}/{t}")
print()
print("=== zone-dependent ===")
for net in sorted(zd):
    c, l, t, u = results[net]
    print(f"  {net}: {l}/{t}")

with open(sys.argv[1] + ".through-via-verdicts.txt", "w") as f:
    for net in sorted(results):
        c, l, t, u = results[net]
        f.write(f"{net}\t{c}\t{l}/{t}\n")
