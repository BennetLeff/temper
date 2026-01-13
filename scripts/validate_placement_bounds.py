#!/usr/bin/env python3
"""
Validate all component placements are within board bounds.

This script checks that all footprint positions in a KiCad PCB file
are within the board boundaries (with configurable margin).

Usage:
    python scripts/validate_placement_bounds.py <pcb_file> [--margin 5.0]

Examples:
    python scripts/validate_placement_bounds.py pcb/temper_deterministic_final.kicad_pcb
    python scripts/validate_placement_bounds.py /tmp/iteration_1.kicad_pcb --margin 3.0

Exit codes:
    0 - All components within bounds
    1 - One or more components outside bounds
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple, Optional


def get_board_dimensions(pcb_path: Path) -> Tuple[float, float, float, float]:
    """
    Extract board dimensions from KiCad PCB file.

    Returns:
        (x_min, y_min, x_max, y_max) - Board bounding box in mm
    """
    from kiutils.board import Board

    board = Board.from_file(str(pcb_path))

    # Look for Edge.Cuts outline
    # First, check for gr_rect
    for item in board.graphicItems:
        if hasattr(item, "layer") and item.layer == "Edge.Cuts":
            if hasattr(item, "start") and hasattr(item, "end") and item.start and item.end:
                # gr_rect
                x1, y1 = item.start.X, item.start.Y
                x2, y2 = item.end.X, item.end.Y
                return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    # Fallback: collect all Edge.Cuts lines and compute bbox
    edge_points = []
    for item in board.graphicItems:
        if hasattr(item, "layer") and item.layer == "Edge.Cuts":
            if hasattr(item, "start") and item.start:
                edge_points.append((item.start.X, item.start.Y))
            if hasattr(item, "end") and item.end:
                edge_points.append((item.end.X, item.end.Y))

    if edge_points:
        xs = [p[0] for p in edge_points]
        ys = [p[1] for p in edge_points]
        return (min(xs), min(ys), max(xs), max(ys))

    # Ultimate fallback: use footprint bbox
    if board.footprints:
        xs = [fp.position.X for fp in board.footprints]
        ys = [fp.position.Y for fp in board.footprints]
        margin = 10.0
        return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)

    # Default
    return (0.0, 0.0, 100.0, 150.0)


def get_footprint_positions(pcb_path: Path) -> List[Tuple[str, float, float]]:
    """
    Extract all footprint positions from KiCad PCB file.

    Returns:
        List of (reference, x, y) tuples
    """
    from kiutils.board import Board

    board = Board.from_file(str(pcb_path))
    positions = []

    for fp in board.footprints:
        ref = fp.properties.get("Reference", "Unknown")
        x = fp.position.X
        y = fp.position.Y
        positions.append((ref, x, y))

    return positions


def validate_placements(
    pcb_path: Path, margin: float = 5.0
) -> Tuple[int, int, List[Tuple[str, float, float, str]]]:
    """
    Check exported PCB for out-of-bounds components.

    Args:
        pcb_path: Path to KiCad PCB file
        margin: Edge margin in mm

    Returns:
        (total_count, violation_count, violations_list)
        Where each violation is (ref, x, y, reason)
    """
    # Get board dimensions
    x_min, y_min, x_max, y_max = get_board_dimensions(pcb_path)
    board_width = x_max - x_min
    board_height = y_max - y_min

    # Valid placement area (with margin)
    valid_x_min = x_min + margin
    valid_x_max = x_max - margin
    valid_y_min = y_min + margin
    valid_y_max = y_max - margin

    # Get footprint positions
    positions = get_footprint_positions(pcb_path)

    violations = []
    for ref, x, y in positions:
        reasons = []

        if x < valid_x_min:
            reasons.append(f"x={x:.2f} < {valid_x_min:.2f} (left edge)")
        elif x > valid_x_max:
            reasons.append(f"x={x:.2f} > {valid_x_max:.2f} (right edge)")

        if y < valid_y_min:
            reasons.append(f"y={y:.2f} < {valid_y_min:.2f} (top edge)")
        elif y > valid_y_max:
            reasons.append(f"y={y:.2f} > {valid_y_max:.2f} (bottom edge)")

        if reasons:
            violations.append((ref, x, y, "; ".join(reasons)))

    return len(positions), len(violations), violations


def main():
    parser = argparse.ArgumentParser(
        description="Validate component placement bounds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pcb_file", type=Path, help="KiCad PCB file to validate")
    parser.add_argument(
        "--margin", type=float, default=5.0, help="Edge margin in mm (default: 5.0)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show board dimensions")
    args = parser.parse_args()

    if not args.pcb_file.exists():
        print(f"Error: File not found: {args.pcb_file}", file=sys.stderr)
        sys.exit(1)

    # Get board dimensions for verbose output
    if args.verbose:
        x_min, y_min, x_max, y_max = get_board_dimensions(args.pcb_file)
        print(f"Board dimensions: ({x_min:.2f}, {y_min:.2f}) to ({x_max:.2f}, {y_max:.2f})")
        print(
            f"Valid area (with {args.margin}mm margin): "
            f"({x_min + args.margin:.2f}, {y_min + args.margin:.2f}) to "
            f"({x_max - args.margin:.2f}, {y_max - args.margin:.2f})"
        )
        print()

    total, violation_count, details = validate_placements(args.pcb_file, args.margin)

    if args.json:
        result = {
            "pcb_file": str(args.pcb_file),
            "margin": args.margin,
            "total": total,
            "violations": violation_count,
            "details": [{"ref": d[0], "x": d[1], "y": d[2], "reason": d[3]} for d in details],
        }
        print(json.dumps(result, indent=2))
    else:
        if violation_count == 0:
            print(f"✓ All {total} components within bounds (margin={args.margin}mm)")
        else:
            print(f"✗ Found {violation_count}/{total} components outside bounds:")
            for ref, x, y, reason in sorted(details, key=lambda d: d[0]):
                print(f"  {ref}: ({x:.2f}, {y:.2f}) - {reason}")

    sys.exit(0 if violation_count == 0 else 1)


if __name__ == "__main__":
    main()
