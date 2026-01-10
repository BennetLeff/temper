#!/usr/bin/env python3
"""Comprehensive router profiling to identify optimization opportunities."""

import cProfile
import pstats
import io
import time
import sys
from pathlib import Path

def main():
    sys.path.insert(0, str(Path(__file__).parent / "packages/temper-placer/src"))

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.routing.maze_router import MazeRouter
    from temper_placer.routing.net_ordering import order_nets
    from temper_placer.routing.layer_assignment import assign_layers
    from temper_placer.core.loop import LoopCollection
    import jax.numpy as jnp
    import numpy as np

    input_pcb = Path("/Users/bennet/Desktop/temper/pcb/temper_placed.kicad_pcb")
    cell_size = 0.2
    num_layers = 2

    print("=== Comprehensive Router Profiling ===")
    print(f"Input: {input_pcb}")
    print(f"Grid: {cell_size}mm, {num_layers} layers")

    # Parse PCB
    t0 = time.perf_counter()
    parse_result = parse_kicad_pcb(input_pcb)
    netlist = parse_result.netlist
    board = parse_result.board
    print(f"\n[1] Parse: {(time.perf_counter() - t0)*1000:.1f}ms")

    positions_list = [comp.initial_position for comp in netlist.components]
    positions = jnp.array(positions_list)

    # Net order
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    power_keywords = ["GND", "VCC", "VDD", "VSS", "+", "3V3", "5V", "12V"]
    net_order = [n for n in net_order if not any(k in n.upper() for k in power_keywords)]
    print(f"Nets to route: {len(net_order)}")

    assignments = assign_layers(netlist)

    # Create router
    t0 = time.perf_counter()
    router = MazeRouter.from_board(
        board,
        cell_size_mm=cell_size,
        num_layers=num_layers,
        via_cost=50.0,
        soft_blocking=False,
    )
    print(f"\n[2] Router init: {(time.perf_counter() - t0)*1000:.1f}ms")
    print(f"Grid size: {router.grid_size} = {router.grid_size[0] * router.grid_size[1] * num_layers:,} cells")

    # Block components
    t0 = time.perf_counter()
    router.block_components(netlist.components, positions, margin=0.5)
    print(f"\n[3] block_components: {(time.perf_counter() - t0)*1000:.1f}ms")

    # Block pads
    t0 = time.perf_counter()
    router.block_pads(netlist.components, positions, netlist, trace_width=0.2, clearance=0.2)
    print(f"[4] block_pads: {(time.perf_counter() - t0)*1000:.1f}ms")

    # Profile RRR routing
    print("\n=== Profiling RRR Routing ===")

    t_route_start = time.perf_counter()
    results = router.rrr_route_all_nets(
        netlist,
        positions,
        net_order,
        assignments,
        max_iterations=3,
        history_increment=1.0,
    )
    route_time = time.perf_counter() - t_route_start

    print(f"\n=== Routing Complete: {route_time*1000:.1f}ms ===")
    successful = sum(1 for r in results.values() if r.success)
    print(f"Routed: {successful}/{len(results)} nets")

    # Custom timing analysis
    print("\n" + "="*60)
    print("ROUTER INTERNAL PROFILING")
    print("="*60)
    print(f"Total Time: {router.stats.total_time_ms:.1f}ms")
    print(f"  - Cost Prep: {router.stats.profile.prepare_costs_ms:.1f}ms")
    print(f"  - Rip-up: {router.stats.profile.rip_up_ms:.1f}ms")
    print(f"  - A* Total: {router.stats.profile.astar_total_ms:.1f}ms")
    print(f"    - Numba: {router.stats.profile.numba_time_ms:.1f}ms ({router.stats.profile.numba_calls} calls, {router.stats.profile.numba_time_ms/max(1,router.stats.profile.numba_calls):.2f}ms/call)")
    print(f"    - Python: {router.stats.profile.python_time_ms:.1f}ms ({router.stats.profile.python_calls} calls)")
    print(f"  - Dist Map: {router.stats.profile.dist_map_ms:.1f}ms ({router.stats.profile.dist_map_calls} computes, {router.stats.profile.dist_map_cache_hits} cache hits)")
    print(f"  - Conflict Analysis: {router.stats.profile.analyze_conflicts_ms:.1f}ms")


if __name__ == "__main__":
    main()
