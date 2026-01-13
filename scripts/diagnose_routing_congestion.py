#!/usr/bin/env python3
"""
Diagnostic test: Simulate actual pipeline routing to find where congestion builds up.

This test routes nets in order, measuring:
1. How much of the grid is blocked before/after each net
2. How many iterations each net takes
3. Which nets fail and why
"""

import sys

sys.path.insert(0, "packages/temper-placer/src")

import numpy as np
import time
from pathlib import Path
from dataclasses import replace

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.config_loader import load_constraints
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid, ClearanceGridStage
from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages import ApplyPlacementsStage


def analyze_grid_blockage(grid: ClearanceGrid, layer: int = 0) -> dict:
    """Analyze how much of a grid layer is blocked."""
    trace_grid = grid._trace_net_ids[layer]
    pad_grid = grid._pad_net_ids[layer]

    total_cells = grid.rows * grid.cols
    trace_blocked = np.count_nonzero(trace_grid)
    pad_blocked = np.count_nonzero(pad_grid)
    combined = (trace_grid != 0) | (pad_grid != 0)
    combined_blocked = np.count_nonzero(combined)

    return {
        "total_cells": total_cells,
        "pad_blocked": pad_blocked,
        "trace_blocked": trace_blocked,
        "combined_blocked": combined_blocked,
        "free_pct": 100.0 * (total_cells - combined_blocked) / total_cells,
    }


def simulate_routing():
    """Simulate routing in pipeline order to see where congestion builds."""

    print("=" * 70)
    print("ROUTING SIMULATION - TRACKING CONGESTION BUILDUP")
    print("=" * 70)

    # Load config and board
    config = load_constraints(Path("configs/temper_deterministic_config.yaml"))
    result = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
    metadata = extract_kicad_metadata(Path("pcb/temper.kicad_pcb"))

    # Setup state
    initial_state = BoardState(netlist=result.netlist, board=result.board)
    state = ApplyPlacementsStage().run(initial_state)

    # Convert pad sizes
    pad_sizes = {}
    for key, ps in metadata.pad_sizes.items():

        class PadInfo:
            def __init__(self, p):
                self.size = type("S", (), {"X": p.width, "Y": p.height})()

        pad_sizes[key] = PadInfo(ps)

    # Get net class clearances
    net_class_clearances = {}
    config_rules = getattr(config, "net_class_rules", {})
    for name, rules in config_rules.items():
        c = getattr(rules, "clearance_mm", None) or (
            rules.get("clearance_mm", 0.2) if isinstance(rules, dict) else 0.2
        )
        net_class_clearances[name] = c

    max_clearance = max(net_class_clearances.values()) + 0.3 if net_class_clearances else 2.5

    # Create grid with max clearance (current behavior)
    stage = ClearanceGridStage(
        cell_size_mm=0.25,
        layer_count=4,
        max_clearance_mm=max_clearance,
        net_class_clearances=net_class_clearances,
        pad_sizes=pad_sizes,
    )
    state = stage.run(state)
    grid = state.grid

    print(f"\nInitial grid: {grid.rows}x{grid.cols} cells")
    print(f"max_clearance_mm: {max_clearance}mm")

    for layer in [0, 3]:  # F.Cu and B.Cu
        stats = analyze_grid_blockage(grid, layer)
        print(
            f"  Layer {layer}: {stats['free_pct']:.1f}% free (pads: {stats['pad_blocked']}, traces: {stats['trace_blocked']})"
        )

    # Get net order (simplified - route in order from config)
    net_classes = getattr(config, "net_classes", {})

    # Group nets by priority
    hv_nets = [n for n, c in net_classes.items() if c == "HighVoltage"]
    power_nets = [n for n, c in net_classes.items() if c in ("Power", "PowerTrace")]
    signal_nets = [n for n, c in net_classes.items() if c in ("Signal", "FinePitch")]

    # Route order: HV first, then power, then signals
    net_order = hv_nets + power_nets + signal_nets

    print(f"\nRouting {len(net_order)} nets:")
    print(f"  HV: {hv_nets}")
    print(f"  Power: {power_nets}")
    print(f"  Signal: {signal_nets[:5]}...")

    # Build component lookup
    comp_by_ref = {c.ref: c for c in state.netlist.components}
    net_by_name = {n.name: n for n in state.netlist.nets}

    # Route each net and track congestion
    print("\n" + "=" * 70)
    print("ROUTING PROGRESS")
    print("=" * 70)

    total_iterations = 0
    failed_nets = []

    for net_name in net_order:
        if net_name not in net_by_name:
            continue

        net = net_by_name[net_name]
        net_class = net_classes.get(net_name, "Signal")
        clearance = net_class_clearances.get(net_class, 0.2)

        # Find pins
        pin_positions = []
        for comp_ref, pin_name in net.pins:
            if comp_ref not in comp_by_ref:
                continue
            comp = comp_by_ref[comp_ref]
            pin = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
            if not pin:
                continue
            pos = comp.initial_position or (0, 0)
            pin_positions.append((pos[0] + pin.position[0], pos[1] + pin.position[1]))

        if len(pin_positions) < 2:
            continue

        # Get current free space
        stats_before = analyze_grid_blockage(grid, 0)

        # Route the net
        pathfinder = MultiLayerAStar(
            grid=grid,
            net_name=net_name,
            trace_width=0.2,
            allowed_layers=[0, 3],
            use_adaptive_budget=False,
            max_iterations=50000,  # Cap for this test
        )

        start_time = time.time()

        # Route between first two pins (simplified MST)
        path_result = pathfinder.find_path(
            pin_positions[0], pin_positions[1], start_layer=0, end_layer=-1
        )

        elapsed = time.time() - start_time
        iterations = pathfinder.last_iterations
        total_iterations += iterations

        # Calculate distance
        dist_mm = abs(pin_positions[1][0] - pin_positions[0][0]) + abs(
            pin_positions[1][1] - pin_positions[0][1]
        )

        if path_result:
            # Block the route on the grid (simplified - block straight line)
            # In reality, would block actual path segments
            for seg in path_result.segments:
                grid.block_trace(
                    [(seg.start[0], seg.start[1]), (seg.end[0], seg.end[1])],
                    width_mm=0.2,
                    clearance_mm=clearance,
                    layer=seg.layer,
                    net_name=net_name,
                )

            stats_after = analyze_grid_blockage(grid, 0)
            delta_free = stats_before["free_pct"] - stats_after["free_pct"]

            status = "OK" if iterations < 1000 else "SLOW" if iterations < 10000 else "VERY_SLOW"
            print(
                f"  {net_name:15s} [{net_class:12s}] {status:9s} {iterations:6d} iters ({elapsed:.2f}s) dist={dist_mm:.0f}mm free={stats_after['free_pct']:.1f}% (-{delta_free:.1f}%)"
            )
        else:
            failed_nets.append((net_name, net_class, iterations, dist_mm))
            print(
                f"  {net_name:15s} [{net_class:12s}] FAILED    {iterations:6d} iters ({elapsed:.2f}s) dist={dist_mm:.0f}mm"
            )

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    final_stats = analyze_grid_blockage(grid, 0)
    print(f"\nFinal grid Layer 0: {final_stats['free_pct']:.1f}% free")
    print(f"  Pads blocked: {final_stats['pad_blocked']:,}")
    print(f"  Traces blocked: {final_stats['trace_blocked']:,}")
    print(f"\nTotal iterations: {total_iterations:,}")
    print(f"Failed nets: {len(failed_nets)}")

    if failed_nets:
        print("\nFailed nets:")
        for name, nc, iters, dist in failed_nets:
            print(f"  {name} ({nc}): {iters} iterations for {dist:.0f}mm")


if __name__ == "__main__":
    simulate_routing()
