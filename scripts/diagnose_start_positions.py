#!/usr/bin/env python3
"""
Diagnostic test: Why do some nets fail with only 1 iteration?

Hypothesis: The start/end positions are blocked by the 6.3mm clearance
from neighboring pads, so A* can't even begin.
"""

import sys

sys.path.insert(0, "packages/temper-placer/src")

import numpy as np
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.config_loader import load_constraints
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid, ClearanceGridStage
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages import ApplyPlacementsStage


def check_start_positions():
    """Check if start positions are blocked."""

    print("=" * 70)
    print("CHECKING START/END POSITION AVAILABILITY")
    print("=" * 70)

    # Setup
    config = load_constraints(Path("configs/temper_deterministic_config.yaml"))
    result = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
    metadata = extract_kicad_metadata(Path("pcb/temper.kicad_pcb"))

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

    max_clearance = max(net_class_clearances.values()) + 0.3

    # Create grids with different clearances
    grids = {}
    for clearance_mm in [6.3, 2.0, 0.5, 0.2]:
        stage = ClearanceGridStage(
            cell_size_mm=0.25,
            layer_count=4,
            max_clearance_mm=clearance_mm,
            net_class_clearances=net_class_clearances,
            pad_sizes=pad_sizes,
        )
        grids[clearance_mm] = stage.run(state).grid

    # Test nets that failed with 1 iteration
    test_nets = ["SW_NODE", "+15V", "VCC_BOOT", "PWM_H", "PWM_L", "SPI_MISO", "GATE_H", "GATE_L"]
    net_classes = getattr(config, "net_classes", {})

    comp_by_ref = {c.ref: c for c in state.netlist.components}
    net_by_name = {n.name: n for n in state.netlist.nets}

    print(f"\nChecking {len(test_nets)} nets that failed with 1 iteration:")
    print(
        f"{'Net':<15} {'Class':<12} {'Start Pos':<20} {'6.3mm':<8} {'2.0mm':<8} {'0.5mm':<8} {'0.2mm':<8}"
    )
    print("-" * 90)

    for net_name in test_nets:
        if net_name not in net_by_name:
            continue

        net = net_by_name[net_name]
        net_class = net_classes.get(net_name, "Signal")

        # Find first pin position
        for comp_ref, pin_name in net.pins:
            if comp_ref not in comp_by_ref:
                continue
            comp = comp_by_ref[comp_ref]
            pin = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
            if not pin:
                continue
            pos = comp.initial_position or (0, 0)
            pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])

            # Check availability in each grid
            results = []
            for clearance_mm in [6.3, 2.0, 0.5, 0.2]:
                grid = grids[clearance_mm]
                # Check all 8 neighbors + center
                available_count = 0
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        test_x = pin_pos[0] + dx * 0.25
                        test_y = pin_pos[1] + dy * 0.25
                        if grid.is_available(test_x, test_y, layer=0, net_name=net_name):
                            available_count += 1
                results.append(f"{available_count}/9")

            print(
                f"{net_name:<15} {net_class:<12} ({pin_pos[0]:.1f}, {pin_pos[1]:.1f}){'':<5} {results[0]:<8} {results[1]:<8} {results[2]:<8} {results[3]:<8}"
            )
            break  # Only check first pin

    # Show what's blocking a specific net
    print("\n" + "=" * 70)
    print("DETAILED ANALYSIS: PWM_H")
    print("=" * 70)

    net = net_by_name.get("PWM_H")
    if net:
        for comp_ref, pin_name in net.pins:
            if comp_ref not in comp_by_ref:
                continue
            comp = comp_by_ref[comp_ref]
            pin = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
            if not pin:
                continue
            pos = comp.initial_position or (0, 0)
            pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])

            print(f"\nPin position: ({pin_pos[0]:.3f}, {pin_pos[1]:.3f})")
            print(f"Component: {comp_ref} ({comp.name})")

            grid = grids[6.3]

            # Check 5x5 area around pin
            print("\nGrid availability (5x5 area, 0.25mm cells):")
            print("  0=blocked, 1=free")
            print("      ", end="")
            for dx in range(-2, 3):
                x = pin_pos[0] + dx * 0.25
                print(f"{x:7.2f}", end="")
            print()

            for dy in range(-2, 3):
                y = pin_pos[1] + dy * 0.25
                print(f"{y:6.2f} ", end="")
                for dx in range(-2, 3):
                    x = pin_pos[0] + dx * 0.25
                    available = grid.is_available(x, y, layer=0, net_name="PWM_H")
                    print(f"{'  1    ' if available else '  0    '}", end="")
                print()

            # Check what net is blocking each cell
            print("\nBlocking net IDs:")
            print("      ", end="")
            for dx in range(-2, 3):
                x = pin_pos[0] + dx * 0.25
                print(f"{x:7.2f}", end="")
            print()

            for dy in range(-2, 3):
                y = pin_pos[1] + dy * 0.25
                print(f"{y:6.2f} ", end="")
                for dx in range(-2, 3):
                    x = pin_pos[0] + dx * 0.25
                    row, col = grid._mm_to_cell(x, y)
                    if 0 <= row < grid.rows and 0 <= col < grid.cols:
                        pad_id = grid._pad_net_ids[0][row, col]
                        trace_id = grid._trace_net_ids[0][row, col]
                        net_id = pad_id if pad_id != 0 else trace_id
                        if net_id > 0:
                            blocking_net = grid._id_to_net.get(net_id, "?")
                            print(f"{blocking_net[:6]:>7}", end="")
                        else:
                            print(f"{'free':>7}", end="")
                    else:
                        print(f"{'OOB':>7}", end="")
                print()

            break


if __name__ == "__main__":
    check_start_positions()
