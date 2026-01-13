#!/usr/bin/env python3
"""
Export Router V6 routing results to KiCad PCB format.

This script runs Router V6 and exports the routing to a .kicad_pcb file
that can be opened in KiCad and validated with DRC.
"""

import argparse
import json
import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.router_v6.pipeline import RouterV6Pipeline
from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position
import uuid
import math


def simplify_path_coords(
    coords: list[tuple[float, float]], tolerance: float = 0.01
) -> list[tuple[float, float]]:
    """
    Simplify path using Douglas-Peucker algorithm.

    Args:
        coords: List of (x, y) coordinates
        tolerance: Simplification tolerance in mm

    Returns:
        Simplified list of coordinates
    """
    if len(coords) < 3:
        return coords

    def perpendicular_distance(point, line_start, line_end):
        """Calculate perpendicular distance from point to line."""
        x, y = point
        x1, y1 = line_start
        x2, y2 = line_end

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            return math.sqrt((x - x1) ** 2 + (y - y1) ** 2)

        # Calculate perpendicular distance
        num = abs(dy * x - dx * y + x2 * y1 - y2 * x1)
        den = math.sqrt(dx**2 + dy**2)
        return num / den

    def douglas_peucker(points, tolerance):
        if len(points) < 3:
            return points

        # Find point with maximum distance
        dmax = 0
        index = 0
        for i in range(1, len(points) - 1):
            d = perpendicular_distance(points[i], points[0], points[-1])
            if d > dmax:
                dmax = d
                index = i

        # If max distance is greater than tolerance, recursively simplify
        if dmax > tolerance:
            # Recursive call
            left = douglas_peucker(points[: index + 1], tolerance)
            right = douglas_peucker(points[index:], tolerance)

            # Combine results
            return left[:-1] + right
        else:
            return [points[0], points[-1]]

    return douglas_peucker(coords, tolerance)


def export_router_v6_to_kicad(input_pcb: Path, output_pcb: Path, verbose: bool = True):
    """
    Run Router V6 and export results to KiCad PCB.

    Args:
        input_pcb: Input .kicad_pcb file (unrouted)
        output_pcb: Output .kicad_pcb file (with routes)
        verbose: Enable verbose output
    """

    if verbose:
        print(f"Running Router V6 on {input_pcb}...")

    # Run Router V6
    pipeline = RouterV6Pipeline(verbose=verbose)
    result = pipeline.run(input_pcb)

    if verbose:
        print(f"\nRouter V6 complete:")
        print(
            f"  Success: {result.success_count}/{result.success_count + result.failure_count} nets"
        )
        print(f"  Runtime: {result.runtime_seconds:.1f}s")
        print()

    # Load template PCB
    if verbose:
        print(f"Loading template PCB from {input_pcb}...")
    board = KiBoard.from_file(str(input_pcb))

    # Layer mapping
    layer_map = {
        "F.Cu": "F.Cu",
        "In1.Cu": "In1.Cu",
        "In2.Cu": "In2.Cu",
        "In3.Cu": "In3.Cu",
        "B.Cu": "B.Cu",
    }

    # Get net name to net code mapping
    net_codes = {}
    for net in board.nets:
        net_codes[net.name] = net.number

    # Export routing
    pathfinding = result.stage4.pathfinding_result
    via_placement = result.stage4.via_placement
    width_assignment = result.stage4.width_assignment

    segment_count = 0
    via_count = 0

    if verbose:
        print(f"Exporting {len(pathfinding.routed_paths)} routed nets...")

    # Add Escape Vias (from Stage 1)
    if result.escape_vias:
        for via_info in result.escape_vias:
            net_code = net_codes.get(via_info.net_name)
            if not net_code:
                continue

            via = Via(
                position=Position(X=via_info.position[0], Y=via_info.position[1]),
                size=via_info.diameter,
                drill=via_info.drill,
                net=net_code,
                # Escape vias usually span all layers (THT)
                layers=["F.Cu", "B.Cu"],
                tstamp=str(uuid.uuid4()),
            )
            board.traceItems.append(via)
            via_count += 1

    for net_name, path3d in pathfinding.routed_paths.items():
        if net_name not in net_codes:
            print(f"Warning: Net '{net_name}' not found in board nets, skipping")
            continue

        net_code = net_codes[net_name]

        # Get trace width for this net
        trace_width = 0.2  # Default 0.2mm
        if hasattr(width_assignment, "widths") and net_name in width_assignment.widths:
            trace_width = width_assignment.widths[net_name]

        # Convert RoutePath3D to KiCad segments with simplification
        # Group segments by layer and simplify
        current_layer = None
        layer_segments = []

        for x, y, layer in path3d.segments:
            if layer != current_layer:
                # Flush previous layer segments
                if layer_segments:
                    simplified = simplify_path_coords(layer_segments)
                    for i in range(len(simplified) - 1):
                        x1, y1 = simplified[i]
                        x2, y2 = simplified[i + 1]
                        segment = Segment(
                            start=Position(X=x1, Y=y1),
                            end=Position(X=x2, Y=y2),
                            width=trace_width,
                            layer=layer_map.get(current_layer, "F.Cu"),
                            net=net_code,
                            tstamp=str(uuid.uuid4()),
                        )
                        board.traceItems.append(segment)
                        segment_count += 1

                # Start new layer
                current_layer = layer
                layer_segments = [(x, y)]
            else:
                layer_segments.append((x, y))

        # Flush final layer
        if layer_segments:
            simplified = simplify_path_coords(layer_segments)
            for i in range(len(simplified) - 1):
                x1, y1 = simplified[i]
                x2, y2 = simplified[i + 1]
                segment = Segment(
                    start=Position(X=x1, Y=y1),
                    end=Position(X=x2, Y=y2),
                    width=trace_width,
                    layer=layer_map.get(current_layer, "F.Cu"),
                    net=net_code,
                    tstamp=str(uuid.uuid4()),
                )
                board.traceItems.append(segment)
                segment_count += 1

        # Add vias at layer transitions
        if hasattr(via_placement, "vias"):
            for via_info in via_placement.vias:
                if via_info.net_name != net_name:
                    continue

                via = Via(
                    position=Position(X=via_info.position[0], Y=via_info.position[1]),
                    size=via_info.diameter,
                    drill=via_info.drill,
                    net=net_code,
                    layers=[via_info.from_layer, via_info.to_layer],
                    tstamp=str(uuid.uuid4()),
                )
                board.traceItems.append(via)
                via_count += 1

    # Save output PCB
    if verbose:
        print(f"\nExporting to {output_pcb}...")
        print(f"  Segments: {segment_count}")
        print(f"  Vias: {via_count}")

    board.to_file(str(output_pcb))

    if verbose:
        print(f"\n✅ Export complete: {output_pcb}")

    return {
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "segment_count": segment_count,
        "via_count": via_count,
        "runtime_seconds": result.runtime_seconds,
    }


def main():
    parser = argparse.ArgumentParser(description="Export Router V6 routing to KiCad PCB format")
    parser.add_argument("input", type=Path, help="Input .kicad_pcb file (unrouted)")
    parser.add_argument("-o", "--output", type=Path, help="Output .kicad_pcb file (routed)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    parser.add_argument("--metrics", type=Path, help="Save metrics to JSON file")

    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    if not args.output:
        args.output = args.input.with_name(args.input.stem + "_router_v6_output.kicad_pcb")

    try:
        metrics = export_router_v6_to_kicad(
            input_pcb=args.input, output_pcb=args.output, verbose=not args.quiet
        )

        if args.metrics:
            with open(args.metrics, "w") as f:
                json.dump(metrics, f, indent=2)
            if not args.quiet:
                print(f"Metrics saved to: {args.metrics}")

        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
