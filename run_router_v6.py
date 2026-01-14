#!/usr/bin/env python3
"""
Run Router V6 on temper PCB and generate baseline metrics.
"""

import json
import sys
from pathlib import Path
from dataclasses import dataclass

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_writer import (
    write_placements_to_pcb,
    write_routes_to_pcb,
    write_zones_to_pcb,
    PlacementUpdate,
)
from temper_placer.router_v6.pipeline import RouterV6Pipeline
from temper_placer.router_v6.astar_pathfinding import RoutePath3D


@dataclass(frozen=True)
class SimpleTrace:
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: str


@dataclass(frozen=True)
class SimpleVia:
    position: tuple[float, float]
    width: float
    drill: float
    layers: tuple[str, ...]  # Expects tuple for frozen set
    net: str


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run Router V6 on temper PCB")
    parser.add_argument(
        "--pcb", type=Path, default=Path("pcb/temper.kicad_pcb"), help="Input PCB file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("pcb/temper_router_v6_output.kicad_pcb"),
        help="Output PCB file",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("pcb/temper_router_v6_metrics.json"),
        help="Metrics JSON file",
    )
    parser.add_argument(
        "--theta-star", action="store_true", help="Enable Theta* any-angle routing (Experiment F)"
    )
    parser.add_argument(
        "--lazy-theta", action="store_true", help="Enable Lazy Theta* (Experiment O4)"
    )
    parser.add_argument(
        "--smoothing", action="store_true", help="Enable force-directed smoothing (Experiment G)"
    )
    parser.add_argument(
        "--no-legalize",
        action="store_true",
        help="Disable automatic placement legalization (Phase 6)",
    )
    parser.add_argument(
        "--placement-mode",
        type=str,
        default="physics",
        choices=["physics", "analytical"],
        help="Placement strategy: 'physics' (Force-Directed) or 'analytical' (Spectral+LP)",
    )
    parser.add_argument(
        "--max-nets", type=int, default=None, help="Limit number of nets to route (for profiling)"
    )
    parser.add_argument(
        "--nets", type=str, default=None, help="Comma-separated list of nets to route"
    )
    args = parser.parse_args()

    pcb_path = args.pcb
    output_path = args.output
    metrics_path = args.metrics
    target_nets = args.nets.split(",") if args.nets else None

    if not pcb_path.exists():
        print(f"ERROR: PCB file not found: {pcb_path}")
        sys.exit(1)

    print("=" * 80)
    print("Router V6 - Temper Board Baseline Run")
    print("=" * 80)
    print(f"Input: {pcb_path}")
    print(f"Output: {output_path}")
    if args.theta_star:
        print("Experiment F: Theta* any-angle routing ENABLED")
    if args.lazy_theta:
        print("Experiment O4: Lazy Theta* ENABLED")
    if args.smoothing:
        print("Experiment G: Force-directed smoothing ENABLED")
    if not args.no_legalize:
        print(f"Experiment P2: Placement Legalization ENABLED (Mode: {args.placement_mode})")
    if target_nets:
        print(f"Profiling Mode: Targeting {len(target_nets)} nets: {', '.join(target_nets)}")
    elif args.max_nets:
        print(f"Profiling Mode: Limiting to first {args.max_nets} nets")
    print()

    # Run Router V6
    try:
        pipeline = RouterV6Pipeline(
            verbose=True,
            enable_theta_star=args.theta_star,
            enable_lazy_theta_star=args.lazy_theta,
            enable_smoothing=args.smoothing,
            enable_legalization=not args.no_legalize,
            placement_mode=args.placement_mode,
            max_nets=args.max_nets,
            target_nets=target_nets,
        )
        result = pipeline.run(pcb_path)

        # Print results
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        print(f"Runtime: {result.runtime_seconds:.1f}s")
        print(f"Success: {result.success_count}/{result.success_count + result.failure_count} nets")
        print(f"Completion: {result.completion_rate * 100:.1f}%")
        print()

        # Print Detailed Failures
        if result.failure_count > 0:
            result.stage4.pathfinding_result.print_failure_analysis()

        # Export metrics
        metrics = {
            "runtime_seconds": result.runtime_seconds,
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "completion_rate": result.completion_rate,
            "escape_vias": len(result.escape_vias),
        }

        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        print(f"Metrics written to: {metrics_path}")

        # Export Routed PCB
        print(f"\nExporting to {output_path}...")

        # 1. Export Placement (Legalized)
        placements = {}
        for comp in result.pcb.components:
            if comp.initial_position is None:
                continue

            # Convert rotation index to degrees if needed, or use stored value
            rot = comp.initial_rotation * 90.0 if comp.initial_rotation is not None else 0.0

            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref, x=comp.initial_position[0], y=comp.initial_position[1], rotation=rot
            )

        # Write placement first (Template -> Output)
        write_placements_to_pcb(
            template_pcb=pcb_path,
            output_pcb=output_path,
            placements=placements,
            preserve_unmatched=True,
        )

        # 2. Export Routes
        routes = set()
        vias = set()

        for net_name, compiled_route in result.stage4.routing_results.compiled_routes.items():
            # Convert RoutePath (polyline) to segments
            path = compiled_route.path

            # Handle 3D path
            if isinstance(path, RoutePath3D):
                # RoutePath3D: segments is list of (x, y, layer)
                if len(path.segments) < 2:
                    continue
                for i in range(len(path.segments) - 1):
                    p1 = path.segments[i]
                    p2 = path.segments[i + 1]

                    if p1[2] == p2[2]:
                        routes.add(
                            SimpleTrace(
                                start=(p1[0], p1[1]),
                                end=(p2[0], p2[1]),
                                width=compiled_route.width_mm,
                                layer=p1[2],
                                net=net_name,
                            )
                        )
            else:
                # 2D RoutePath: coordinates is list of (x, y)
                coords = path.coordinates
                layer = path.layer_name
                for i in range(len(coords) - 1):
                    routes.add(
                        SimpleTrace(
                            start=coords[i],
                            end=coords[i + 1],
                            width=compiled_route.width_mm,
                            layer=layer,
                            net=net_name,
                        )
                    )

            # Add Vias
            for via in compiled_route.vias:
                # via is SimpleVia compatible structure or just object with attributes
                # ViaPlacement.place_vias returns list of Via objects (dataclass in via_placement.py)

                vias.add(
                    SimpleVia(
                        position=via.position,
                        width=via.diameter,
                        drill=via.drill,
                        layers=tuple(via.layers),  # Tuple for hashability
                        net=net_name,
                    )
                )

        # Write routes (Output -> Output)
        write_routes_to_pcb(
            template_pcb=output_path,  # Read the file we just wrote placements to
            output_pcb=output_path,
            routes=frozenset(routes),
            vias=frozenset(vias),
            clear_existing=True,  # Remove old ratsnests/traces
        )
        print(f"Exported {len(routes)} segments and {len(vias)} vias.")

        # 3. Export Power Planes (Zones)
        if result.stage4.power_planes:
            print(f"Exporting {len(result.stage4.power_planes)} Power Planes...")
            write_zones_to_pcb(
                template_pcb=output_path, output_pcb=output_path, zones=result.stage4.power_planes
            )
        else:
            print("No Power Planes generated.")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
