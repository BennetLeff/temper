#!/usr/bin/env python3
"""
Diagnostic test: Investigate why A* takes 50K+ iterations

Hypothesis: The ClearanceGrid uses max_clearance_mm (6.3mm) for ALL pads,
blocking most of the routing area even for low-voltage Signal nets.

This test will:
1. Create a ClearanceGrid like the pipeline does
2. Measure what percentage of the grid is blocked
3. Compare with a grid using correct per-net-class clearances
"""

import sys

sys.path.insert(0, "packages/temper-placer/src")

import numpy as np
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.config_loader import load_constraints
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid, ClearanceGridStage


def analyze_grid_blockage(grid: ClearanceGrid, layer: int = 0) -> dict:
    """Analyze how much of a grid layer is blocked."""
    trace_grid = grid._trace_net_ids[layer]
    pad_grid = grid._pad_net_ids[layer]

    total_cells = grid.rows * grid.cols

    # Count blocked cells (non-zero in either grid)
    trace_blocked = np.count_nonzero(trace_grid)
    pad_blocked = np.count_nonzero(pad_grid)

    # Combined blocked (either trace or pad blocked)
    combined = (trace_grid != 0) | (pad_grid != 0)
    combined_blocked = np.count_nonzero(combined)

    return {
        "total_cells": total_cells,
        "trace_blocked": trace_blocked,
        "pad_blocked": pad_blocked,
        "combined_blocked": combined_blocked,
        "trace_blocked_pct": 100.0 * trace_blocked / total_cells,
        "pad_blocked_pct": 100.0 * pad_blocked / total_cells,
        "combined_blocked_pct": 100.0 * combined_blocked / total_cells,
        "free_cells": total_cells - combined_blocked,
        "free_pct": 100.0 * (total_cells - combined_blocked) / total_cells,
    }


def test_clearance_grid_blockage():
    """Test the clearance grid blockage with different settings."""

    print("=" * 70)
    print("CLEARANCE GRID BLOCKAGE DIAGNOSTIC")
    print("=" * 70)

    # Load config
    config_path = Path("configs/temper_deterministic_config.yaml")
    config = load_constraints(config_path)

    # Load board
    board_path = Path("pcb/temper.kicad_pcb")
    result = parse_kicad_pcb(board_path)
    metadata = extract_kicad_metadata(board_path)

    # Get net class clearances
    net_class_clearances = {}
    config_rules = getattr(config, "net_class_rules", None)
    if config_rules:
        for name, rules in config_rules.items():
            if hasattr(rules, "clearance_mm"):
                net_class_clearances[name] = rules.clearance_mm
            elif isinstance(rules, dict):
                net_class_clearances[name] = rules.get("clearance_mm", 0.2)

    max_clearance = max(net_class_clearances.values()) + 0.3 if net_class_clearances else 2.5

    print(f"\nNet class clearances:")
    for name, clearance in sorted(net_class_clearances.items(), key=lambda x: -x[1]):
        print(f"  {name}: {clearance}mm")
    print(f"\nmax_clearance_mm used for ALL pads: {max_clearance}mm")

    # Create initial state
    from temper_placer.deterministic.state import BoardState

    initial_state = BoardState(
        netlist=result.netlist,
        board=result.board,
    )

    # Apply placements
    from temper_placer.deterministic.stages import ApplyPlacementsStage

    apply_stage = ApplyPlacementsStage()
    state = apply_stage.run(initial_state)

    # Convert pad sizes
    pad_sizes_for_stage = {}
    for key, pad_size in metadata.pad_sizes.items():

        class PadInfo:
            def __init__(self, pad_size_obj):
                self.size = type("Size", (), {"X": pad_size_obj.width, "Y": pad_size_obj.height})()
                self.number = pad_size_obj.pad_number

        pad_sizes_for_stage[key] = PadInfo(pad_size)

    # Test 1: Current behavior (max_clearance for all)
    print("\n" + "=" * 70)
    print("TEST 1: Current behavior (max_clearance_mm for ALL pads)")
    print("=" * 70)

    stage1 = ClearanceGridStage(
        cell_size_mm=0.25,
        layer_count=4,
        max_clearance_mm=max_clearance,  # 6.3mm for HighVoltage
        net_class_clearances=net_class_clearances,
        pad_sizes=pad_sizes_for_stage,
    )
    state1 = stage1.run(state)

    for layer in range(4):
        stats = analyze_grid_blockage(state1.grid, layer)
        print(f"\n  Layer {layer}:")
        print(
            f"    Grid size: {state1.grid.rows} x {state1.grid.cols} = {stats['total_cells']:,} cells"
        )
        print(f"    Pad blocked: {stats['pad_blocked']:,} ({stats['pad_blocked_pct']:.1f}%)")
        print(f"    Trace blocked: {stats['trace_blocked']:,} ({stats['trace_blocked_pct']:.1f}%)")
        print(
            f"    Combined blocked: {stats['combined_blocked']:,} ({stats['combined_blocked_pct']:.1f}%)"
        )
        print(f"    FREE for routing: {stats['free_cells']:,} ({stats['free_pct']:.1f}%)")

    # Test 2: Using Signal clearance (0.2mm) for all pads
    print("\n" + "=" * 70)
    print("TEST 2: Using Signal clearance (0.2mm) for all pads")
    print("=" * 70)

    stage2 = ClearanceGridStage(
        cell_size_mm=0.25,
        layer_count=4,
        max_clearance_mm=0.2,  # Signal clearance
        net_class_clearances=net_class_clearances,
        pad_sizes=pad_sizes_for_stage,
    )
    state2 = stage2.run(state)

    for layer in range(4):
        stats = analyze_grid_blockage(state2.grid, layer)
        print(f"\n  Layer {layer}:")
        print(
            f"    Grid size: {state2.grid.rows} x {state2.grid.cols} = {stats['total_cells']:,} cells"
        )
        print(f"    Pad blocked: {stats['pad_blocked']:,} ({stats['pad_blocked_pct']:.1f}%)")
        print(f"    Trace blocked: {stats['trace_blocked']:,} ({stats['trace_blocked_pct']:.1f}%)")
        print(
            f"    Combined blocked: {stats['combined_blocked']:,} ({stats['combined_blocked_pct']:.1f}%)"
        )
        print(f"    FREE for routing: {stats['free_cells']:,} ({stats['free_pct']:.1f}%)")

    # Test 3: Compare A* exploration on both grids
    print("\n" + "=" * 70)
    print("TEST 3: A* exploration comparison")
    print("=" * 70)

    # Pick a signal net that was slow (TEMP_SENSE, SPI_CS_TEMP, etc.)
    test_net = "SPI_CS_TEMP"

    # Find pin positions
    comp_by_ref = {c.ref: c for c in state.netlist.components}
    net = next((n for n in state.netlist.nets if n.name == test_net), None)

    if net:
        pin_positions = []
        for comp_ref, pin_name in net.pins:
            if comp_ref not in comp_by_ref:
                continue
            comp = comp_by_ref[comp_ref]
            pin = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
            if not pin:
                continue
            pos = comp.initial_position or (0, 0)
            pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
            pin_positions.append(pin_pos)

        if len(pin_positions) >= 2:
            start = pin_positions[0]
            end = pin_positions[1]

            print(f"\n  Net: {test_net}")
            print(f"  Start: {start}")
            print(f"  End: {end}")

            # Calculate manhattan distance
            dist_mm = abs(end[0] - start[0]) + abs(end[1] - start[1])
            dist_cells = dist_mm / 0.25
            print(f"  Manhattan distance: {dist_mm:.1f}mm ({dist_cells:.0f} cells)")

            # Test with conservative grid
            from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar

            print("\n  With max_clearance (6.3mm) grid:")
            ml_astar1 = MultiLayerAStar(
                grid=state1.grid,
                net_name=test_net,
                trace_width=0.2,
                allowed_layers=[0, 3],  # F.Cu and B.Cu
                use_adaptive_budget=False,  # Use simple iteration count
                max_iterations=100000,
            )

            import time

            t1_start = time.time()
            result1 = ml_astar1.find_path(start, end, start_layer=0, end_layer=-1)
            t1_elapsed = time.time() - t1_start

            if result1:
                print(f"    SUCCESS in {ml_astar1.last_iterations} iterations ({t1_elapsed:.2f}s)")
            else:
                print(
                    f"    FAILED after {ml_astar1.last_iterations} iterations ({t1_elapsed:.2f}s)"
                )
                print(f"    Iterations per cell: {ml_astar1.last_iterations / dist_cells:.1f}x")

            print("\n  With Signal clearance (0.2mm) grid:")
            ml_astar2 = MultiLayerAStar(
                grid=state2.grid,
                net_name=test_net,
                trace_width=0.2,
                allowed_layers=[0, 3],  # F.Cu and B.Cu
                use_adaptive_budget=False,
                max_iterations=100000,
            )

            t2_start = time.time()
            result2 = ml_astar2.find_path(start, end, start_layer=0, end_layer=-1)
            t2_elapsed = time.time() - t2_start

            if result2:
                print(f"    SUCCESS in {ml_astar2.last_iterations} iterations ({t2_elapsed:.2f}s)")
            else:
                print(
                    f"    FAILED after {ml_astar2.last_iterations} iterations ({t2_elapsed:.2f}s)"
                )
                print(f"    Iterations per cell: {ml_astar2.last_iterations / dist_cells:.1f}x")

            if result1 and result2:
                speedup = ml_astar1.last_iterations / ml_astar2.last_iterations
                print(f"\n  Speedup with correct clearance: {speedup:.1f}x")


if __name__ == "__main__":
    test_clearance_grid_blockage()
