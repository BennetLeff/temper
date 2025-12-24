#!/usr/bin/env python3
"""
Profile the maze router on temper.kicad_pcb.
"""
import sys
import time
from pathlib import Path

import jax.numpy as jnp

from temper_placer.core.loop import LoopCollection
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.layer_assignment import assign_layers
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.net_ordering import order_nets


def main():
    # Find project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent

    # Find PCB file
    if len(sys.argv) > 1:
        pcb_path = Path(sys.argv[1])
    else:
        pcb_path = project_root / "pcb/temper.kicad_pcb"

    if not pcb_path.exists():
        print(f"Error: {pcb_path} not found")
        sys.exit(1)

    print(f"Parsing {pcb_path}...")
    start_parse = time.perf_counter()
    parse_result = parse_kicad_pcb(pcb_path)
    print(f"Parse time: {(time.perf_counter() - start_parse)*1000:.2f}ms")

    netlist = parse_result.netlist
    board = parse_result.board

    # Extract component positions
    positions = jnp.array([
        (c.initial_position[0], c.initial_position[1])
        for c in netlist.components
    ])

    print(f"Components: {netlist.n_components}")
    print(f"Nets: {netlist.n_nets}")
    print(f"Board size: {board.width:.1f}x{board.height:.1f}mm")

    # Topological steps
    print("Running topological analysis...")
    loops = LoopCollection([])
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist)

    # Initialize Router
    cell_size = 0.5
    print(f"Initializing MazeRouter (cell_size={cell_size}mm)...")
    router = MazeRouter.from_board(board, cell_size_mm=cell_size, num_layers=4)

    print("Blocking components...")
    router.block_components(netlist.components, positions, margin=0.1, layer_specific=True)

    print("Routing nets...")
    router.route_all_nets(netlist, positions, net_order, assignments)

    stats = router.stats
    print("\n--- Routing Statistics ---")
    print(f"Total Routing Time: {stats.total_time_ms:.2f} ms")
    print(f"NetsRouted: {stats.nets_routed}/{len(net_order)} ({stats.nets_routed/len(net_order)*100:.1f}%)")
    print(f"Avg Time/Net: {stats.avg_time_per_net_ms:.2f} ms")
    print(f"Max Time/Net: {stats.max_time_per_net_ms:.2f} ms")
    print(f"Total A* Iterations: {stats.total_astar_iterations}")
    print(f"Avg A* Iterations/Path: {stats.avg_iterations_per_path:.1f}")

if __name__ == "__main__":
    main()
