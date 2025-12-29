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
    parser.add_argument("--cell-size", type=float, default=0.5, help="Grid cell size in mm")
    parser.add_argument("--layers", type=int, default=2, help="Number of routing layers")
    
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
    assignments = assign_layers(netlist) # Use default constraints from layer_assignment.py
    console.print(f"  ✓ Determined routing order for {len(net_order)} nets")
    console.print(f"  ✓ Inferred strategies for {len(routing_ctx.strategies)} nets")

    # 4. Routing
    console.print("\n[bold cyan]Step 4:[/] Running Maze Router...")
    router = MazeRouter.from_board(
        board,
        cell_size_mm=args.cell_size,
        num_layers=args.layers,
    )
    
    console.print("  Blocking component areas...")
    router.block_components(netlist.components, positions)
    
    console.print("  Routing all nets (A*)...")
    start_time = time.time()
    
    # UPDATED: Sequential routing with dynamic cost maps from bridge
    results = {}
    for net_name in net_order:
        # Get pin positions
        pin_positions = []
        net = netlist.get_net(net_name)
        for comp_ref, pin_name in net.pins:
            comp_idx = netlist.get_component_index(comp_ref)
            comp = netlist.get_component(comp_ref)
            pin = comp.get_pin(pin_name)
            if pin:
                pin_pos = pin.absolute_position(
                    tuple(positions[comp_idx]), 
                    math.radians((comp.initial_rotation or 0) * 90.0)
                )
                pin_positions.append(pin_pos)
        
        if len(pin_positions) < 2:
            continue
            
        # Get semantic cost map
        cost_map = get_cost_map_for_net(
            grid_size=router.grid_size,
            cell_size_mm=router.cell_size,
            context=routing_ctx,
            net_id=net_name
        )
        
        # Determine assignment (fallback to default if missing)
        assignment = assignments.get(net_name)
        if not assignment:
             from temper_placer.routing.layer_assignment import LayerAssignment, Layer
             assignment = LayerAssignment(net_name, Layer.L4_BOT, {Layer.L4_BOT}, False, "Default")

        # Route with cost map
        result = router.route_net(net_name, pin_positions, assignment, cost_map=cost_map)
        results[net_name] = result
        
    elapsed = time.time() - start_time
    
    completion = compute_completion_rate(results)
    console.print(f"  ✓ Routing complete in {elapsed:.2f}s")
    console.print(f"  ✓ Completion rate: {completion:.2%}")

    # 5. Export Traces
    console.print("\n[bold cyan]Step 5:[/] Exporting traces to KiCad...")
    try:
        items_added = write_traces_to_pcb(
            template_pcb=args.input_pcb,
            output_pcb=args.output,
            routing_results=results,
            cell_size=args.cell_size,
            origin=board.origin,
            clear_existing=True
        )
        console.print(f"  ✓ Wrote {items_added} items to {args.output}")
    except Exception as e:
        console.print(f"[red]Error exporting traces: {e}[/]")
        sys.exit(1)

    console.print("\n[bold green]Success![/]")

if __name__ == "__main__":
    main()
