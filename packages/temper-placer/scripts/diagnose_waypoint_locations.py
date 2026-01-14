#!/usr/bin/env python3
"""
Diagnose waypoint locations vs THT pad locations.
Are waypoints landing on pads, or in free space?
"""

from pathlib import Path
import math

from temper_placer.io.kicad_parser import parse_kicad_pcb

def main():
    board_path = Path("tests/fixtures/external/.cache/piantor_left/keyboard_pcb.kicad_pcb")

    if not board_path.exists():
        print(f"Board not found: {board_path}")
        return

    result = parse_kicad_pcb(board_path)

    # Get all THT pad locations
    tht_pads = []
    for comp in result.netlist.components:
        if hasattr(comp, 'pads'):
            for pad in comp.pads:
                # Check if THT (has drill)
                if hasattr(pad, 'drill') and pad.drill:
                    pos = (pad.position[0] if hasattr(pad, 'position') else 0,
                           pad.position[1] if hasattr(pad, 'position') else 0)
                    tht_pads.append({
                        'ref': comp.ref,
                        'pad': pad.name if hasattr(pad, 'name') else '?',
                        'pos': pos,
                        'net': pad.net if hasattr(pad, 'net') else None,
                    })

    print(f"Found {len(tht_pads)} THT pads")

    # Get reference trace endpoints for failing nets
    failing_nets = ["/k02", "/k04", "/k25"]

    for net in failing_nets:
        print(f"\n{'='*60}")
        print(f"NET: {net}")
        print('='*60)

        # Find THT pads for this net
        net_pads = [p for p in tht_pads if p['net'] == net]
        print(f"\nTHT pads on this net: {len(net_pads)}")
        for p in net_pads:
            print(f"  {p['ref']}.{p['pad']}: ({p['pos'][0]:.1f}, {p['pos'][1]:.1f})")

        # Find reference trace endpoints
        net_traces = [t for t in result.traces if t.net == net]
        if net_traces:
            endpoints = set()
            for t in net_traces:
                endpoints.add((round(t.start[0], 1), round(t.start[1], 1)))
                endpoints.add((round(t.end[0], 1), round(t.end[1], 1)))

            print(f"\nReference trace endpoints: {len(endpoints)}")
            for ep in sorted(endpoints):
                # Check if this endpoint is at a THT pad
                is_at_pad = False
                for p in net_pads:
                    dist = math.sqrt((ep[0] - p['pos'][0])**2 + (ep[1] - p['pos'][1])**2)
                    if dist < 1.0:  # Within 1mm
                        is_at_pad = True
                        break

                status = "AT PAD" if is_at_pad else "FREE SPACE"
                print(f"  {ep}: {status}")

    # Summary: What percentage of reference trace endpoints are at pads?
    print(f"\n{'='*60}")
    print("SUMMARY: Reference Routing Strategy")
    print('='*60)

    all_endpoints = set()
    pad_endpoints = 0

    for t in result.traces:
        for ep in [t.start, t.end]:
            ep_rounded = (round(ep[0], 1), round(ep[1], 1))
            if ep_rounded not in all_endpoints:
                all_endpoints.add(ep_rounded)

                # Check if at any THT pad
                for p in tht_pads:
                    dist = math.sqrt((ep_rounded[0] - p['pos'][0])**2 +
                                   (ep_rounded[1] - p['pos'][1])**2)
                    if dist < 1.0:
                        pad_endpoints += 1
                        break

    print(f"Total unique trace endpoints: {len(all_endpoints)}")
    print(f"Endpoints at THT pads: {pad_endpoints}")
    print(f"Percentage at pads: {100 * pad_endpoints / len(all_endpoints):.1f}%")

    if pad_endpoints / len(all_endpoints) > 0.5:
        print("\n→ Reference routing is PIN-CENTRIC (routes through pads)")
        print("→ Your skeleton-based waypoints may need to include pad locations")
    else:
        print("\n→ Reference routing uses free-space waypoints (like your skeleton)")

if __name__ == "__main__":
    main()
