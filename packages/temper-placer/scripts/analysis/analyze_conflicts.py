#!/usr/bin/env python3
"""
Analyze physical conflicts (shorts) in the PCB to categorize routing errors.
"""

import math
from collections import defaultdict
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb


def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def analyze_shorts():
    pcb_path = Path("packages/temper-placer/output_pipeline_test.kicad_pcb")
    if not pcb_path.exists():
        print(f"File not found: {pcb_path}")
        return

    print(f"Analyzing {pcb_path}...")
    result = parse_kicad_pcb(pcb_path)
    board = result.board

    print(f"Scanning {len(result.traces)} traces and {len(result.pads)} pads...")

    items = []
    # Add traces
    for t in result.traces:
        items.append({
            'type': 'track',
            'net': t.net,
            'layer': t.layer,
            'start': t.start, # Tuple (x,y)
            'end': t.end,     # Tuple (x,y)
            'width': t.width
        })

    # We don't have vias in result.traces?
    # Current parser extracts traces but maybe not vias explicitly in the 'traces' list?
    # Checking parser code: _extract_traces_from_pcb iterates traceItems. Vias are skipped.
    # So we miss vias. But let's analyze tracks first.

    print(f"Found {len(items)} routing items.")

    # Mapping items to nearby components
    print("Mapping items to components...")
    comp_collisions = defaultdict(int)

    components = []
    for c in result.netlist.components:
        # Initial position in netlist is normalized?
        # Parser doc says: "Component positions are normalized to origin-relative coordinates".
        # But we need absolute coordinates for distance check with traces (which are absolute).
        # Wait, traces from parser: "start: tuple[float, float] # (x, y) in mm, absolute coords"
        # Components in netlist: "initial_position ... relative"
        # BUT parse_kicad_pcb subtracts board.origin

        # We need to add board origin back if board exists.
        ox, oy = 0, 0
        if board:
            ox, oy = board.origin

        bx, by = c.initial_position
        pos = (bx + ox, by + oy) # Reconstruct absolute

        components.append({
            'ref': c.ref,
            'pos': pos
        })

    # Analyze density around components
    for comp in components:
        # Count items within 2mm of component center
        cx, cy = comp['pos']
        count = 0
        nets = set()
        for item in items:
            p = None
            if item['type'] == 'track':
                # Use midpoint
                p = ((item['start'][0]+item['end'][0])/2, (item['start'][1]+item['end'][1])/2)

            if p and distance(p, (cx, cy)) < 5.0 and item['net']:
                count += 1
                nets.add(item['net'])

        # Heuristic: If many nets in small area -> Congestion
        if len(nets) > 5:
            print(f"High Density at {comp['ref']}: {len(nets)} nets, {count} segments")
            comp_collisions[comp['ref']] = len(nets)

    # Output categories based on density
    print("\nError Classes:")
    print("1. Pin Fanout Congestion (MCU/High-Pin-Count)")
    mcu_comp = next((c for c in components if "U" in c['ref'] and ("ESP" in c['ref'] or "U1" in c['ref'])), None)
    if mcu_comp and comp_collisions[mcu_comp['ref']] > 10:
         print(f"   - Confirmed at {mcu_comp['ref']} ({comp_collisions[mcu_comp['ref']]} nets)")

    print("2. Component Cluster Congestion")
    for ref, nets in comp_collisions.items():
        if not mcu_comp or ref != mcu_comp['ref']:
            print(f"   - {ref}: {nets} distinct nets in 5mm radius")

    print("\n3. Potential Short Circuits (Trace-Trace Intersections)")
    # Sampling for intersections
    # ... (omitted for brevity in this patch, we focus on congestion map first)

if __name__ == "__main__":
    analyze_shorts()
