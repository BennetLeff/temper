#!/usr/bin/env python3
"""
Analyze Layer Usage.

Reads the output PCB and counts segments on each layer.
"""

from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6


def main():
    pcb_path = Path("pcb/temper_router_v6_output.kicad_pcb")
    if not pcb_path.exists():
        print("PCB not found")
        return

    print(f"Loading {pcb_path}...")
    pcb = parse_kicad_pcb_v6(pcb_path)

    # We loaded tracks in Phase 5 update?
    # Yes, ParsedPCB has .tracks

    layer_counts = {}
    total_len = 0.0

    if hasattr(pcb, "tracks") and pcb.tracks:
        for track in pcb.tracks:
            l = track.layer
            # Calculate length
            length = (
                (track.end[0] - track.start[0]) ** 2 + (track.end[1] - track.start[1]) ** 2
            ) ** 0.5
            layer_counts[l] = layer_counts.get(l, 0.0) + length
            total_len += length

    print("\nLayer Usage (Length in mm):")
    print("-" * 30)
    for l, length in layer_counts.items():
        ratio = length / total_len if total_len > 0 else 0
        print(f"{l:<10} | {length:>8.1f} mm | {ratio * 100:>5.1f}%")


if __name__ == "__main__":
    main()
