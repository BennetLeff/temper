#!/usr/bin/env python3
"""Spatial region analysis of the 52 Stage-4 A* failures.

Combines:
  - rcm_blocking_diag.json (net, blockers, netclass) -- from the real
    combined-config production route (scripts/rcm_blocking_diag.py).
  - pin_positions.json (net -> pad positions) -- from
    temper_placer.io.kicad_parser on pcb/temper.kicad_pcb.
  - component_meta.json (component ref -> position, sheetpath) -- text
    property extraction (not copper) from pcb/temper.kicad_pcb.

For each failing net, computes a centroid of its own pins (a reasonable
proxy for "where this net needed to route") and buckets it into a coarse
board region. Read-only, no board writes.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--blocking-diag", type=Path, required=True, help="rcm_blocking_diag.json path")
parser.add_argument("--pin-positions", type=Path, required=True, help="pin_positions.json path (see rcm_pin_positions.py)")
parser.add_argument("--output", type=Path, required=True, help="Where to write the combined spatial analysis JSON")
args = parser.parse_args()

diag = json.load(open(args.blocking_diag))
pins = json.load(open(args.pin_positions))

net_pins = pins["net_pins"]
bx, by, bw, bh = pins["board_origin"][0], pins["board_origin"][1], pins["board_width"], pins["board_height"]

# Coarse 3x3 region grid over the board extent.
def region_of(x, y):
    col = min(2, int((x - bx) / bw * 3))
    row = min(2, int((y - by) / bh * 3))
    col_name = ["LEFT", "MID", "RIGHT"][col]
    row_name = ["TOP", "MID", "BOTTOM"][row]
    return f"{row_name}-{col_name}"


def centroid_for_net(net_name):
    p = net_pins.get(net_name)
    if not p:
        return None
    xs = [pt["x"] for pt in p]
    ys = [pt["y"] for pt in p]
    return (sum(xs) / len(xs), sum(ys) / len(ys), p)


rows_out = []
region_counts = Counter()
region_nets = defaultdict(list)
missing_pins = []

for r in diag["rows"]:
    net = r["net"]
    c = centroid_for_net(net)
    if c is None:
        missing_pins.append(net)
        continue
    cx, cy, p = c
    reg = region_of(cx, cy)
    region_counts[reg] += 1
    region_nets[reg].append(net)
    rows_out.append(
        {
            "net": net,
            "own_class": r["own_class"],
            "blocker_count": r["blocker_count"],
            "large_blockers": r["large_clearance_blocker_count"],
            "centroid": (round(cx, 2), round(cy, 2)),
            "region": reg,
            "pin_refs": sorted({pt["ref"] for pt in p}),
            "blocker_names": [b["name"] for b in r["blockers"]],
        }
    )

print("Board extent:", bx, by, bx + bw, by + bh, f"({bw}x{bh}mm)")
print("\nRegion counts (failing nets, by own-pin centroid):")
for reg, cnt in sorted(region_counts.items(), key=lambda kv: -kv[1]):
    print(f"  {reg}: {cnt}")
print("\nMissing pin data for:", missing_pins)

# Also compute where the BLOCKERS live (union across all failing nets) --
# this is the actual congestion signature, not just the failing net's own
# location.
blocker_region_counts = Counter()
blocker_name_counts = Counter()
for r in diag["rows"]:
    for b in r["blockers"]:
        blocker_name_counts[b["name"]] += 1
        c = centroid_for_net(b["name"])
        if c:
            blocker_region_counts[region_of(c[0], c[1])] += 1

print("\nBlocker-net region counts (blocker occurrences across all failing nets, by blocker's own centroid):")
for reg, cnt in sorted(blocker_region_counts.items(), key=lambda kv: -kv[1]):
    print(f"  {reg}: {cnt}")

print("\nTop 20 most-frequent blocker nets (appearing in the most failing nets' blocker lists):")
for name, cnt in blocker_name_counts.most_common(20):
    c = centroid_for_net(name)
    reg = region_of(c[0], c[1]) if c else "?"
    print(f"  {name}: blocks {cnt} failing nets, region {reg}, centroid {c[:2] if c else None}")

json.dump(
    {
        "region_counts": dict(region_counts),
        "region_nets": dict(region_nets),
        "rows": rows_out,
        "blocker_region_counts": dict(blocker_region_counts),
        "blocker_name_counts": dict(blocker_name_counts.most_common()),
    },
    open(args.output, "w"),
    indent=2,
)
print(f"\nWrote {args.output}")
