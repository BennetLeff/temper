#!/usr/bin/env python3
"""
Quick script to verify copper zones in PCB files.
"""

import sys
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb


def check_copper_zones(pcb_path: str):
    """Check if PCB file has copper zones."""
    print(f"\n{'=' * 60}")
    print(f"Checking: {pcb_path}")
    print(f"{'=' * 60}")

    try:
        result = parse_kicad_pcb(Path(pcb_path))
        board = result.board

        print(f"Board parsed successfully")
        print(f"  Width: {board.width_mm:.1f} mm")
        print(f"  Height: {board.height_mm:.1f} mm")

        # Check board.zones
        if hasattr(board, "zones") and board.zones:
            print(f"\nBoard has {len(board.zones)} zone(s):")
            for zone in board.zones:
                name = zone.name if hasattr(zone, "name") else "unnamed"
                net_classes = zone.net_classes if hasattr(zone, "net_classes") else []
                bounds = zone.bounds if hasattr(zone, "bounds") else "no bounds"
                layers = zone.layers if hasattr(zone, "layers") else []
                print(f"  - {name}")
                print(f"      net_classes: {net_classes}")
                print(f"      bounds: {bounds}")
                print(f"      layers: {layers}")
        else:
            print("\nNo zones found in board.zones")

        # Check board.copper_zones
        if hasattr(board, "copper_zones") and board.copper_zones:
            print(f"\nBoard has {len(board.copper_zones)} copper_zone(s):")
            for zone in board.copper_zones:
                name = zone.name if hasattr(zone, "name") else "unnamed"
                print(f"  - {name}")
        else:
            print("\nNo zones found in board.copper_zones")

    except Exception as e:
        print(f"Error parsing {pcb_path}: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # Check multiple PCB files
    pcb_files = [
        "pcb/temper.kicad_pcb",
        "pcb/temper_with_planes.kicad_pcb",
    ]

    for pcb_file in pcb_files:
        check_copper_zones(pcb_file)

    print(f"\n{'=' * 60}")
    print("Done!")
    print(f"{'=' * 60}\n")
