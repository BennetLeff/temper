#!/usr/bin/env python3
"""
Internal PCB router script.
Routes a placed PCB using the internal MazeRouter and exports traces.
"""

import argparse
import sys
import time
import math
from pathlib import Path

import jax.numpy as jnp
from rich.console import Console

# Add packages to path if needed (uv handle this usually)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
from temper_placer.routing.maze_router import MazeRouter, compute_completion_rate
from temper_placer.routing.net_ordering import order_nets
from temper_placer.routing.layer_assignment import assign_layers
from temper_placer.io.trace_writer import write_traces_to_pcb
from temper_placer.core.loop import LoopCollection
from temper_placer.io.zone_manager import add_power_planes
from temper_placer.routing.fanout import fanout_power_nets
from temper_placer.routing.constraints.spatial_index import (
    Pad as GeoPad,
    Track as GeoTrack,
    Via as GeoVia,
)
from temper_placer.routing.constraints.geometry import Point


def populate_oracle_from_board(oracle, board):
    """
    Populate DRCOracle with geometry from a KiBoard object.

    Args:
        oracle: DRCOracle instance
        board: kiutils.board.Board instance
    """
    # 1. Register Pads
    for fp in board.footprints:
        fp_x = fp.position.X
        fp_y = fp.position.Y
        ref = fp.properties.get("Reference", "")

        for pad in fp.pads:
            # Transform to absolute coordinates
            abs_x = fp_x + pad.position.X
            abs_y = fp_y + pad.position.Y

            # Simple shape approximation: Circle with diameter = max dimension
            # TODO: Handle rectangular pads better if needed (geometry.py supports Circle mostly?)
            # Pad size
            w = pad.size.X
            h = pad.size.Y
            size = (w, h)

            # Determine Net Name
            net_name = pad.net.name if pad.net and hasattr(pad.net, "name") else str(pad.net)

            # Create GeoPad
            geo_pad = GeoPad(
                center=Point(abs_x, abs_y),
                shape="circle" if pad.shape == "circle" else "rect",  # simplified
                size=size,
                net=net_name,
                layer=0,  # Placeholder, pads usually multi-layer or F.Cu
            )
            oracle.register_pad(geo_pad)

    # 2. Register Existing Tracks/Vias
    # Note: For pre-routing, we might want to register pre-routed tracks (like fanouts we just added)
    for item in board.traceItems:
        if hasattr(item, "start") and hasattr(item, "end"):
            # Segment/Track
            net_name = item.net.name if item.net and hasattr(item.net, "name") else str(item.net)

            # Map layer name to index if possible, or just string?
            # GeoTrack expects integer layer usually? Let's check spatial_index.py
            # Actually GeoTrack uses integer layer in __init__?
            # Looking at existing code: layer=neighbor.layer (int).
            # We need a map.
            layer_map = {"F.Cu": 0, "B.Cu": 1, "In1.Cu": 2, "In2.Cu": 3, "In3.Cu": 4, "In4.Cu": 5}
            layer_idx = layer_map.get(item.layer, 0)  # Default to 0?

            geo_track = GeoTrack(
                start=Point(item.start.X, item.start.Y),
                end=Point(item.end.X, item.end.Y),
                width=item.width,
                layer=layer_idx,
                net=net_name,
            )
            oracle.register_track(geo_track)

        elif hasattr(item, "position") and hasattr(item, "drill"):
            # Via
            net_name = item.net.name if item.net and hasattr(item.net, "name") else str(item.net)

            geo_via = GeoVia(
                center=Point(item.position.X, item.position.Y),
                diameter=item.size,
                drill=item.drill,
                net=net_name,
            )
            oracle.register_via(geo_via)


def save_congestion_report(router, results, output_path: Path):
    """Save routing congestion data for feedback loop."""
    import numpy as np

    # 1. Extract History Cost (Accumulated Congestion)
    # history_cost is (W, H, L)
    # We sum over layers to get 2D "Total Difficulty" map
    # We subtract 1.0 (base cost) to get only the added penalty
    congestion_3d = np.array(router.history_cost)
    congestion_2d = np.sum(np.maximum(0, congestion_3d - 1.0), axis=2)

    # 2. Add Failed Net locations (as Point Clouds)
    # For now, we trust the history map adds cost where failures happened (because they were searched)
    # But explicitly adding a splash of cost at failed net pins might help.
    # Let's start with just the router's internal state.

    # 3. Save as NPZ
    np.savez_compressed(
        output_path,
        congestion_grid=congestion_2d,
        origin=np.array(router.origin),
        cell_size=router.cell_size,
        grid_size=np.array(router.grid_size),
        failed_nets=[net for net, res in results.items() if not res.success],
    )


console = Console()


def main():
    parser = argparse.ArgumentParser(description="Internal Maze Router")
    parser.add_argument("input_pcb", type=Path, help="Input placed .kicad_pcb file")
    parser.add_argument("-o", "--output", type=Path, help="Output routed .kicad_pcb file")
    parser.add_argument("-c", "--config", type=Path, help="PCL constraints file")
    parser.add_argument("--cell-size", type=float, default=1.0, help="Grid cell size in mm")
    parser.add_argument("--layers", type=int, default=2, help="Number of routing layers")
    parser.add_argument("--rrr-iters", type=int, default=5, help="Number of RRR iterations")
    parser.add_argument(
        "--via-cost",
        type=float,
        default=50.0,
        help="Via penalty (default 50.0, higher = fewer vias)",
    )
    parser.add_argument(
        "--region-size",
        type=int,
        default=0,
        help="Enable region-based routing with this min region size (0=disabled)",
    )
    parser.add_argument(
        "--soft-blocking",
        action="store_true",
        help="Enable negotiated congestion (allow routing through occupied cells)",
    )
    parser.add_argument(
        "--history-increment",
        type=float,
        default=1.0,
        help="History cost increment per conflict (default 1.0, use 2.0 for aggressive)",
    )
    parser.add_argument(
        "--exclude-power-nets",
        action="store_true",
        help="Exclude power nets (GND, VCC, etc.) from routing",
    )
    parser.add_argument(
        "--strict-drc", action="store_true", help="Enable DRC-enforced routing (temper-mado)"
    )
    parser.add_argument(
        "--geometric-nudge",
        action="store_true",
        help="Enable geometric post-processing to fix sub-grid DRC violations",
    )
    parser.add_argument(
        "--add-power-planes",
        action="store_true",
        help="Generate power planes and fanout power nets before routing",
    )
    parser.add_argument(
        "--dump-congestion",
        type=Path,
        help="Path to save congestion heatmap (.npz) for placer feedback",
    )
    parser.add_argument(
        "--smooth-paths",
        action="store_true",
        help="Apply Funnel Algorithm to smooth jagged grid paths",
    )

    args = parser.parse_args()

    if not args.output:
        args.output = args.input_pcb.with_name(args.input_pcb.stem + "_internally_routed.kicad_pcb")

    console.print(f"[bold blue]Starting Internal Maze Router[/]")
    console.print(f"Input: {args.input_pcb}")
    console.print(f"Output: {args.output}")
    console.print(f"Cell size: {args.cell_size}mm")

    # 1. Parse PCB
    console.print("\n[bold cyan]Step 1:[/] Parsing PCB...")
    try:
        parse_result = parse_kicad_pcb(args.input_pcb)
        netlist = parse_result.netlist
        board = parse_result.board

        # Extract positions into JAX array
        positions_list = []

        for comp in netlist.components:
            # component initial_position is already normalized to board origin in parse_kicad_pcb
            positions_list.append(comp.initial_position)
        positions = jnp.array(positions_list)

        console.print(f"  ✓ Loaded {netlist.n_components} components")
    except Exception as e:
        console.print(f"[red]Error parsing PCB: {e}[/]")
        sys.exit(1)

    # 2. Handle Constraints/Loops (Early Init for Step 1.5)
    loops = LoopCollection()

    # 1.5 Power Planes & Fanout (Pre-processing)
    working_pcb_path = args.input_pcb

    if args.add_power_planes:
        console.print("\n[bold cyan]Step 1.5:[/] Generating Power Planes and Fanouts...")
        from kiutils.board import Board as KiBoard

        # Load KiUtils Board
        ki_board = KiBoard.from_file(str(args.input_pcb))

        # Identify Power Nets using original netlist (from Step 1)
        net_order_temp = order_nets(netlist, loops)  # Get basic order to filter power nets
        power_keywords = ["GND", "VCC", "VDD", "VSS", "+", "3V3", "5V", "12V"]
        power_nets = [
            name for name in net_order_temp if any(k in name.upper() for k in power_keywords)
        ]

        gnd_candidates = [n for n in power_nets if "GND" in n.upper()]
        vcc_candidates = [n for n in power_nets if n not in gnd_candidates]

        console.print(f"  GND Candidate Nets: {gnd_candidates}")
        console.print(f"  VCC Candidate Nets: {vcc_candidates}")

        # Add Planes
        zone_res = add_power_planes(ki_board, gnd_nets=gnd_candidates, vcc_nets=vcc_candidates)
        console.print(f"  Added {zone_res.zones_added} zones ({', '.join(zone_res.nets_covered)})")
        for w in zone_res.warnings:
            console.print(f"  [yellow]Zone Warning: {w}[/]")

        # Fanout
        # Fanout needs netlist (already loaded) and ki_board (loaded)
        # Create temporary DRCOracle for fanout checks.
        # Note: We need a temporary 'internal' board for DRCOracle, but we only have 'board' from original parse.
        # That 'board' doesn't have the new zones yet, but that's fine for fanout (zones are on inner layers).
        # We use strict-drc rules or default.
        fanout_oracle = None
        if args.strict_drc:
            from temper_placer.routing.constraints import DRCOracle, DesignRulesParser

            fanout_oracle = DRCOracle(DesignRulesParser.create_default())
            populate_oracle_from_board(fanout_oracle, ki_board)

        console.print(f"  Fanning out {len(power_nets)} power nets...")
        fanouts = fanout_power_nets(ki_board, netlist, power_nets, drc_oracle=fanout_oracle)
        console.print(f"  ✓ Created {fanouts} fanout connections")

        # Save intermediate state
        working_pcb_path = args.output.with_suffix(".pre_route.kicad_pcb")
        ki_board.to_file(str(working_pcb_path))
        console.print(f"  Saved intermediate PCB with planes/fanouts to {working_pcb_path}")

        # RE-PARSE to update internal model (board, netlist, geometry) with new fanouts
        console.print(f"  [bold cyan]Reloading to sync internal model...[/]")
        parse_result = parse_kicad_pcb(working_pcb_path)
        netlist = parse_result.netlist
        board = parse_result.board

        # Update positions array
        positions_list = []
        for comp in netlist.components:
            positions_list.append(comp.initial_position)
        positions = jnp.array(positions_list)

        # Force exclusion of power nets for main routing
        # (Since we handled them via planes/fanout)
        args.exclude_power_nets = True

    # 3. Routing Order and Layer Assignment
    console.print("\n[bold cyan]Step 3:[/] Pre-routing analysis...")

    # NEW: Build Hypergraph for Physics-Aware Strategy Inference
    from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
    from temper_placer.routing.bridge.api import get_routing_context, get_cost_map_for_net

    hg = netlist_to_hypergraph(netlist)
    routing_ctx = get_routing_context(hg, positions, board, netlist)

    net_order = order_nets(netlist, loops)

    # Check if we should exclude power nets here (if not already handled/forced)
    if args.exclude_power_nets:
        power_keywords = ["GND", "VCC", "VDD", "VSS", "+", "3V3", "5V", "12V"]
        original_count = len(net_order)
        # Identify them and remove
        power_nets_to_exclude = [
            name for name in net_order if any(k in name.upper() for k in power_keywords)
        ]
        net_order = [name for name in net_order if name not in power_nets_to_exclude]
        console.print(
            f"  [yellow]Excluded {original_count - len(net_order)} power nets from main routing[/]"
        )

    assignments = assign_layers(netlist)  # Use default constraints from layer_assignment.py
    console.print(f"  ✓ Determined routing order for {len(net_order)} nets")
    console.print(f"  ✓ Inferred strategies for {len(routing_ctx.strategies)} nets")

    # 4. Routing
    console.print("\n[bold cyan]Step 4:[/] Running Maze Router (RRR)...")

    if args.region_size > 0:
        # Region-based routing with quadtree decomposition
        from temper_placer.routing.region_router import RoutingQuadTree

        console.print(f"  Using region-based routing (min_region_size={args.region_size})")
        tree = RoutingQuadTree(
            grid_size=(int(board.width / args.cell_size), int(board.height / args.cell_size)),
            min_region_size=args.region_size,
            halo=3,
        )
        console.print(f"  Quadtree: {tree.leaf_count()} regions")

    # Create DRC Oracle if strict mode enabled (temper-mado.3)
    drc_oracle = None
    # Create DRC Oracle if strict mode enabled OR if geometric nudge is requested
    drc_oracle = None
    if args.strict_drc or args.geometric_nudge:
        from temper_placer.routing.constraints import DRCOracle, DesignRulesParser

        drc_oracle = DRCOracle(DesignRulesParser.create_default())
        # Register geometry including newly created fanouts
        # Note: 'board' here is the temper-placer Board, not KiBoard.
        # But populate_oracle_from_board expects KiBoard.
        # We need to load KiBoard again for this? Or does it matter?
        # The 'working_pcb_path' has the latest geometry.
        # Let's verify if we need to load it.
        # Actually parse_kicad_pcb returns 'traces' and 'pads' in ParseResult but we often ignore them.
        # Simplest is to load KiUtils board quickly here just for Oracle population.
        from kiutils.board import Board as KiBoard

        temp_ki_board = KiBoard.from_file(str(working_pcb_path))
        populate_oracle_from_board(drc_oracle, temp_ki_board)

        if args.strict_drc:
            console.print("  [bold magenta]Strict DRC mode enabled[/]")
        else:
            console.print("  [bold magenta]DRC Oracle enabled for Geometric Nudge[/]")

    router = MazeRouter.from_board(
        board,
        cell_size_mm=args.cell_size,
        num_layers=args.layers,
        via_cost=args.via_cost,
        soft_blocking=args.soft_blocking,
        drc_oracle=drc_oracle,
        strict_mode=args.strict_drc,
    )
    console.print(f"  Via cost: {args.via_cost}")
    if args.soft_blocking:
        console.print(f"  [bold green]Soft blocking enabled[/] (negotiated congestion)")
    console.print(f"  History increment: {args.history_increment}")

    # Block component areas to prevent routing through them
    router.block_components(netlist.components, positions, margin=0.5)

    # Block pads to prevent track-through-pad DRC violations (temper-hdu8)
    # In strict mode, we rely on precise geometry checks, so we reduce margin to opening channels
    pad_margin = 0.01 if args.strict_drc else 0.1
    router.block_pads(netlist.components, positions, netlist, margin=pad_margin)
    console.print(f"  ✓ Blocked {len(router._pad_net_map)} pad cells")

    # Pre-compute cost maps for RRR
    cost_maps = {}
    for net_name in net_order:
        cm = get_cost_map_for_net(
            grid_size=router.grid_size,
            cell_size_mm=router.cell_size,
            context=routing_ctx,
            net_id=net_name,
        )
        if cm is not None:
            cost_maps[net_name] = cm

    start_time = time.time()
    results = router.rrr_route_all_nets(
        netlist,
        positions,
        net_order,
        assignments,
        cost_maps=cost_maps,
        max_iterations=args.rrr_iters,
        history_increment=args.history_increment,
    )
    elapsed = time.time() - start_time

    # Calculate stats
    successful = sum(1 for r in results.values() if r.success)
    completion = (successful / len(net_order)) * 100 if net_order else 100

    console.print(f"  ✓ Routing complete in {elapsed:.2f}s")
    console.print(f"  ✓ Completion rate: {completion:.2f}%")

    # NEW: Conflict Location Reporting
    conflict_locs = router.get_conflict_locations()
    if conflict_locs:
        console.print(f"\n[bold yellow]Conflict Locations ({len(conflict_locs)}):[/]")
        # Group by coordinate to see severe bottlenecks
        for loc in conflict_locs[:10]:
            console.print(
                f"  ({loc['world_x']:.1f}, {loc['world_y']:.1f}, L{loc['layer'] + 1}): {', '.join(loc['nets'])}"
            )
        if len(conflict_locs) > 10:
            console.print(f"  ... and {len(conflict_locs) - 10} more")

    # NEW: Dump Congestion (Step 4.2)
    if args.dump_congestion:
        console.print(
            f"\n[bold cyan]Step 4.2:[/] Saving congestion report to {args.dump_congestion}..."
        )
        save_congestion_report(router, results, args.dump_congestion)
        console.print(f"  ✓ Saved congestion heatmap")

    # 4.5 Geometric Post-Processing
    if args.geometric_nudge:
        console.print("\n[bold cyan]Step 4.5:[/] Running Geometric Nudging...")
        from temper_placer.routing.post_processing.nudger import GeometricNudger
        from temper_placer.io.kicad_exporter import export_from_geometry

        nudger = GeometricNudger(router.drc_oracle)
        nudger.optimize()

        console.print("\n[bold cyan]Step 5:[/] Exporting geometric traces to KiCad...")
        try:
            res = export_from_geometry(
                template_pcb=working_pcb_path,
                output_pcb=args.output,
                tracks=router.drc_oracle.geometry.tracks,
                vias=router.drc_oracle.geometry.vias,
            )
            console.print(
                f"  ✓ Wrote {res.segments_added} geometric traces, {res.vias_added} vias to {args.output}"
            )
            console.print("\n[bold green]Success![/]")
            sys.exit(0)
        except Exception as e:
            console.print(f"[red]Error exporting geometric traces: {e}[/]")
            sys.exit(1)

    # 4.6 Path Smoothing (Funnel Algorithm)
    if args.smooth_paths:
        console.print("\n[bold cyan]Step 4.6:[/] Applying Funnel Algorithm for path smoothing...")
        from temper_placer.routing.post_processing.funnel_smoother import FunnelSmoother

        smoother = FunnelSmoother(resolution_mm=args.cell_size)

        class RouterCSpaceGrid:
            def __init__(self, router):
                self.router = router
                self.resolution = router.cell_size
                self.origin = router.origin

            def pixel_to_world(self, px, py):
                return (
                    px * self.resolution + self.resolution / 2 + self.origin[0],
                    py * self.resolution + self.resolution / 2 + self.origin[1],
                )

            def world_to_pixel(self, x_mm, y_mm):
                px = int((x_mm - self.origin[0] - self.resolution / 2) / self.resolution)
                py = int((y_mm - self.origin[1] - self.resolution / 2) / self.resolution)
                px = max(0, min(px, self.router.grid_size[0] - 1))
                py = max(0, min(py, self.router.grid_size[1] - 1))
                return px, py

            def is_free(self, x_mm, y_mm):
                px, py = self.world_to_pixel(x_mm, y_mm)
                occ = self.router.occupancy[px, py, 0]
                return occ >= 0

        c_space_grid = RouterCSpaceGrid(router)

        total_reduction = 0.0
        smoothed_count = 0
        validation_failures = 0

        for net_name, result in results.items():
            if not result.success or len(result.cells) < 3:
                continue

            smooth_points = smoother.smooth(result.cells, c_space_grid)

            reduction = smoother.path_length_reduction(result.cells, smooth_points)
            min_angle = smoother.min_segment_angle(smooth_points)
            is_valid = smoother.validate_smoothed_path(smooth_points, c_space_grid)

            if is_valid:
                total_reduction += reduction
                smoothed_count += 1
                if reduction >= 20.0:
                    console.print(
                        f"  ✓ {net_name}: {reduction:.1f}% reduction, min angle {min_angle:.1f}°"
                    )
            else:
                validation_failures += 1

        if smoothed_count > 0:
            avg_reduction = total_reduction / smoothed_count
            console.print(
                f"  ✓ Smoothed {smoothed_count} paths (avg {avg_reduction:.1f}% reduction)"
            )
        if validation_failures > 0:
            console.print(f"  ⚠ {validation_failures} paths failed validation (kept original)")

    # 5. Export Traces (Standard Grid Export)
    console.print("\n[bold cyan]Step 5:[/] Exporting traces to KiCad...")
    try:
        items_added = write_traces_to_pcb(
            template_pcb=working_pcb_path,
            output_pcb=args.output,
            routing_results=results,
            cell_size=args.cell_size,
            origin=board.origin,
            clear_existing=False,
        )
        console.print(f"  ✓ Wrote {items_added} items to {args.output}")
    except Exception as e:
        console.print(f"[red]Error exporting traces: {e}[/]")
        sys.exit(1)

    console.print("\n[bold green]Success![/]")


if __name__ == "__main__":
    main()
