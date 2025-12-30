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

console = Console()

def main():
    parser = argparse.ArgumentParser(description="Internal Maze Router")
    parser.add_argument("input_pcb", type=Path, help="Input placed .kicad_pcb file")
    parser.add_argument("-o", "--output", type=Path, help="Output routed .kicad_pcb file")
    parser.add_argument("-c", "--config", type=Path, help="PCL constraints file")
    parser.add_argument("--cell-size", type=float, default=1.0, help="Grid cell size in mm")
    parser.add_argument("--layers", type=int, default=2, help="Number of routing layers")
    parser.add_argument("--rrr-iters", type=int, default=5, help="Number of RRR iterations")
    parser.add_argument("--via-cost", type=float, default=50.0, help="Via penalty (default 50.0, higher = fewer vias)")
    parser.add_argument("--region-size", type=int, default=0, help="Enable region-based routing with this min region size (0=disabled)")
    parser.add_argument("--soft-blocking", action="store_true", help="Enable negotiated congestion (allow routing through occupied cells)")
    parser.add_argument("--history-increment", type=float, default=1.0, help="History cost increment per conflict (default 1.0, use 2.0 for aggressive)")
    parser.add_argument("--exclude-power-nets", action="store_true", help="Exclude power nets (GND, VCC, etc.) from routing")
    
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

    # 2. Handle Constraints/Loops
    loops = LoopCollection()
    if args.config:
        console.print("\n[bold cyan]Step 2:[/] Loading constraints...")
        try:
            constraints = load_constraints(args.config)
            # Use board from constraints if possible for geometry
            # board = create_board_from_constraints(constraints)
            
            # Map PCL critical loops to LoopCollection
            for i, p_loop in enumerate(constraints.critical_loops):
                # Placeholder: Loop objects need net indices, but we'll use order_nets' default behavior
                pass
            
            console.print(f"  ✓ Loaded constraints from {args.config}")
        except Exception as e:
            console.print(f"[yellow]Warning loading constraints: {e}[/]")

    # 3. Routing Order and Layer Assignment
    console.print("\n[bold cyan]Step 3:[/] Pre-routing analysis...")
    
    # NEW: Build Hypergraph for Physics-Aware Strategy Inference
    from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
    from temper_placer.routing.bridge.api import get_routing_context, get_cost_map_for_net
    
    hg = netlist_to_hypergraph(netlist)
    routing_ctx = get_routing_context(hg, positions, board, netlist)
    
    net_order = order_nets(netlist, loops)
    
    if args.exclude_power_nets:
        power_keywords = ["GND", "VCC", "VDD", "VSS", "+", "3V3", "5V", "12V"]
        original_count = len(net_order)
        net_order = [name for name in net_order if not any(k in name.upper() for k in power_keywords)]
        console.print(f"  [yellow]Excluded {original_count - len(net_order)} power nets[/]")

    assignments = assign_layers(netlist) # Use default constraints from layer_assignment.py
    console.print(f"  ✓ Determined routing order for {len(net_order)} nets")
    console.print(f"  ✓ Inferred strategies for {len(routing_ctx.strategies)} nets")

    # 4. Routing
    console.print("\n[bold cyan]Step 4:[/] Running Maze Router (RRR)...")
    
    if args.region_size > 0:
        # Region-based routing with quadtree decomposition
        from temper_placer.routing.region_router import RoutingQuadTree
        console.print(f"  Using region-based routing (min_region_size={args.region_size})")
        tree = RoutingQuadTree(grid_size=(int(board.width / args.cell_size), int(board.height / args.cell_size)), min_region_size=args.region_size, halo=3)
        console.print(f"  Quadtree: {tree.leaf_count()} regions")
    
    router = MazeRouter.from_board(
        board,
        cell_size_mm=args.cell_size,
        num_layers=args.layers,
        via_cost=args.via_cost,
        soft_blocking=args.soft_blocking,
    )
    console.print(f"  Via cost: {args.via_cost}")
    if args.soft_blocking:
        console.print(f"  [bold green]Soft blocking enabled[/] (negotiated congestion)")
    console.print(f"  History increment: {args.history_increment}")
    
    # Pre-compute cost maps for RRR
    cost_maps = {}
    for net_name in net_order:
        cm = get_cost_map_for_net(
            grid_size=router.grid_size,
            cell_size_mm=router.cell_size,
            context=routing_ctx,
            net_id=net_name
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
            console.print(f"  ({loc['world_x']:.1f}, {loc['world_y']:.1f}, L{loc['layer']+1}): {', '.join(loc['nets'])}")
        if len(conflict_locs) > 10:
            console.print(f"  ... and {len(conflict_locs)-10} more")

    # 5. Export Traces
    console.print("\n[bold cyan]Step 5:[/] Exporting traces to KiCad...")
    try:
        items_added = write_traces_to_pcb(
            template_pcb=args.input_pcb,
            output_pcb=args.output,
            routing_results=results,
            cell_size=args.cell_size,
            origin=board.origin,
            clear_existing=False
        )
        console.print(f"  ✓ Wrote {items_added} items to {args.output}")
    except Exception as e:
        console.print(f"[red]Error exporting traces: {e}[/]")
        sys.exit(1)

    console.print("\n[bold green]Success![/]")

if __name__ == "__main__":
    main()
