#!/usr/bin/env python3
"""
Router Benchmarking Infrastructure.

This script runs the internal router on a set of benchmark boards and
collects performance metrics (completion rate, wirelength, runtime).
"""

import argparse
import json
import time
import math
from pathlib import Path
from dataclasses import asdict

import jax.numpy as jnp

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.unified_router import UnifiedRouter, RoutingStrategy, RoutingConfig
from temper_placer.routing.layer_assignment import assign_layers, Layer
from temper_placer.routing.strategy import order_nets
from temper_placer.core.netlist import Netlist
from temper_placer.routing.bridge.api import get_routing_context, get_cost_map_for_net
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph

from temper_placer.core.state import PlacementState

def benchmark_single_board(
    pcb_path: Path,
    strategy: RoutingStrategy = RoutingStrategy.AUTO,
    cell_size: float = 0.5,
    use_physics: bool = True
) -> dict:
    """Run benchmark on a single board."""
    print(f"Benchmarking {pcb_path.name}...")
    start_total = time.time()
    
    # 1. Load Board
    parse_result = parse_kicad_pcb(pcb_path)
    board = parse_result.board
    netlist = parse_result.netlist
    state = PlacementState.from_netlist_and_board(netlist, board)
    
    # Extract positions
    positions = state.positions
    
    # 2. Setup Router
    config = RoutingConfig(
        strategy=strategy,
        maze_cell_size=cell_size,
        enable_via=True
    )
    
    # Physics Bridge
    hypergraph = None
    if use_physics:
        try:
            hypergraph = netlist_to_hypergraph(netlist)
        except Exception as e:
            print(f"  Warning: Failed to build hypergraph: {e}")
            
    router = UnifiedRouter(board, config=config, hypergraph=hypergraph)
    
    # 3. Pre-routing Analysis
    # Default loops to empty if not available in input
    loops = [] 
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist)
    
    # 4. Run Routing
    start_route = time.time()
    results = router.route_all_nets(netlist, positions, net_order, assignments)
    route_time = time.time() - start_route
    
    # 5. Collect Metrics
    stats = router.get_statistics(results)
    
    # Add extra metrics
    stats["total_runtime"] = time.time() - start_total
    stats["routing_runtime"] = route_time
    stats["board_name"] = pcb_path.name
    stats["strategy"] = strategy.value
    stats["physics_enabled"] = use_physics
    
    # Print summary
    print(f"  Completion: {stats['completion_rate']:.1%}")
    print(f"  Nets: {stats['successful']}/{stats['total_nets']}")
    print(f"  Time: {route_time:.2f}s")
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Benchmark Internal Router")
    parser.add_argument("inputs", nargs="+", type=Path, help="Input .kicad_pcb files")
    parser.add_argument("--output", "-o", type=Path, default="benchmark_results.json", help="Output JSON file")
    parser.add_argument("--strategy", type=str, default="auto", choices=["maze", "push_shove", "auto"], help="Routing strategy")
    parser.add_argument("--no-physics", action="store_true", help="Disable physics-aware bridge")
    parser.add_argument("--cell-size", type=float, default=0.5, help="Grid cell size in mm")
    
    args = parser.parse_args()
    
    strat_map = {
        "maze": RoutingStrategy.MAZE_ONLY,
        "push_shove": RoutingStrategy.PUSH_SHOVE_ONLY,
        "auto": RoutingStrategy.AUTO
    }
    strategy = strat_map[args.strategy]
    
    all_results = []
    
    for pcb_path in args.inputs:
        if not pcb_path.exists():
            print(f"Error: File not found: {pcb_path}")
            continue
            
        try:
            metrics = benchmark_single_board(
                pcb_path, 
                strategy=strategy, 
                cell_size=args.cell_size,
                use_physics=not args.no_physics
            )
            all_results.append(metrics)
        except Exception as e:
            print(f"Failed to benchmark {pcb_path.name}: {e}")
            import traceback
            traceback.print_exc()
            
    # Save results
    with open(args.output, "w") as f:
        json.dump(all_results, f, indent=2)
        
    print(f"\nSaved results to {args.output}")

if __name__ == "__main__":
    main()
