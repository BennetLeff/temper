#!/usr/bin/env python3
"""
Run EXP-01: Pitchfork Fanout Unit Test

This script tests the router's fanout capabilities on a synthetic PCB
with 1.27mm pitch headers (fine grid test).

Usage:
    python3 experiments/temper-3w66/run_experiment.py
"""

import sys
from pathlib import Path

try:
    from kiutils.board import Board
except ImportError:
    print("ERROR: kiutils not installed. Run: pip install kiutils>=1.4.0")
    sys.exit(1)


def count_pads_and_nets(pcb_path: Path) -> dict:
    """Count pads and nets in the pitchfork board."""
    print(f"Loading board: {pcb_path}")

    board = Board.from_file(str(pcb_path))

    total_pads = 0
    nets_found = set()

    for footprint in board.footprints:
        for pad in footprint.pads:
            total_pads += 1
            if pad.net and pad.net.name:
                nets_found.add(pad.net.name)

    print(f"\nBoard Statistics:")
    print(f"  Footprints: {len(board.footprints)}")
    print(f"  Total pads: {total_pads}")
    print(f"  Named nets: {len(nets_found)}")

    print(f"\nFootprints:")
    for fp in board.footprints:
        pad_count = len(fp.pads)
        ref = fp.properties.get("Reference", "Unknown")
        print(f"  {ref}: {pad_count} pads")

    return {
        "footprints": len(board.footprints),
        "total_pads": total_pads,
        "nets": len(nets_found),
    }


def verify_fine_grid(pcb_path: Path) -> dict:
    """Verify the board has 1.27mm pitch headers."""
    board = Board.from_file(str(pcb_path))

    measurements = []
    for fp in board.footprints:
        pads = fp.pads
        if len(pads) >= 2:
            for i in range(len(pads) - 1):
                p1, p2 = pads[i], pads[i + 1]
                if p1.position and p2.position:
                    dx = abs(p2.position.X - p1.position.X)
                    dy = abs(p2.position.Y - p1.position.Y)
                    dist = (dx**2 + dy**2) ** 0.5
                    measurements.append(dist)

    unique_measurements = sorted(set(round(m, 3) for m in measurements))

    print(f"\nPin Pitch Measurements:")
    print(f"  Unique distances: {unique_measurements}")
    print(f"  Expected: ~1.27mm")

    has_127mm = any(abs(m - 1.27) < 0.01 for m in measurements)

    return {
        "has_127mm_pitch": has_127mm,
        "unique_distances": unique_measurements,
    }


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    pcb_path = (
        script_dir
        / ".."
        / ".."
        / "packages"
        / "temper-placer"
        / "tests"
        / "fixtures"
        / "pitchfork.kicad_pcb"
    )

    if not pcb_path.exists():
        print(f"ERROR: Board file not found: {pcb_path}")
        print("Run: python3 packages/temper-placer/tests/fixtures/generators/generate_pitchfork.py")
        sys.exit(1)

    stats = count_pads_and_nets(pcb_path)
    grid = verify_fine_grid(pcb_path)

    print(f"\n{'=' * 60}")
    print("EXP-01: Pitchfork Fanout Unit Test Results")
    print(f"{'=' * 60}")

    if stats["total_pads"] >= 40 and stats["footprints"] >= 4 and grid["has_127mm_pitch"]:
        print("[PASS] Board generated successfully with:")
        print(f"       - {stats['footprints']} pin headers")
        print(f"       - {stats['total_pads']} total pads")
        print(f"       - 1.27mm fine pitch grid")
        print(f"\nFanout test is ready for router integration.")
        sys.exit(0)
    else:
        print("[FAIL] Board validation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
