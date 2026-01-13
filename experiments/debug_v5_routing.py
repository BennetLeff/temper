"""
Debug script to trace +5V routing through the sequential routing stage.
"""

import sys
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

from temper_placer.core.netlist import Netlist
from temper_placer.io.kicad_parser import KiCadParser
from temper_placer.deterministic.stages.layer_assignment import LayerAssignmentStage
from temper_placer.core.state import BoardState
from dataclasses import replace
import yaml


def main():
    print("=" * 70)
    print("Debug +5V Routing")
    print("=" * 70)
    print()

    # Load config
    with open("configs/temper_deterministic_config.yaml") as f:
        config = yaml.safe_load(f)

    net_classes = config.get("net_classes", {})

    # Load netlist
    parser = KiCadParser()
    board = parser.parse("pcb/temper.kicad_pcb")
    netlist = board.netlist

    # Find +5V net
    v5_net = None
    for net in netlist.nets:
        if net.name == "+5V":
            v5_net = net
            break

    if not v5_net:
        print("ERROR: +5V net not found")
        return 1

    print(f"Found +5V net:")
    print(f"  Name: {v5_net.name}")
    print(f"  Net class (from parser): {v5_net.net_class}")
    print(f"  Net class (from config): {net_classes.get('+5V', 'N/A')}")
    print(f"  Pins: {len(v5_net.pins)}")
    print()

    # Check layer assignment
    stage = LayerAssignmentStage(net_classes=net_classes)

    # Create minimal state
    state = BoardState(netlist=netlist)
    state_with_assignments = stage.run(state)

    # Find +5V assignment
    v5_assignment = None
    if state_with_assignments.layer_assignments:
        for assignment in state_with_assignments.layer_assignments:
            if assignment.net_name == "+5V":
                v5_assignment = assignment
                break

    if v5_assignment:
        print(f"Layer assignment for +5V:")
        print(f"  Layer: {v5_assignment.layer}")
        print(f"  Is plane: {v5_assignment.is_plane}")
        print(f"  Allow layer change: {v5_assignment.allow_layer_change}")
    else:
        print("ERROR: No layer assignment for +5V")
        return 1

    print()
    print("=" * 70)
    print("Expected Behavior:")
    print("=" * 70)
    print("  ✓ Net class: PowerTrace")
    print("  ✓ Layer: 0 (F.Cu)")
    print("  ✓ Is plane: False")
    print("  ✓ Should route via MST with A* pathfinding")
    print("  ✓ Should NOT create plane vias")
    print()

    if v5_assignment.is_plane:
        print("✗ PROBLEM: +5V is marked as plane net - will skip MST routing!")
        return 1
    else:
        print("✓ CORRECT: +5V is NOT a plane net - will go through MST routing")

    # Check pin positions
    print()
    print(f"+5V pin locations ({len(v5_net.pins)} pins):")
    comp_by_ref = {comp.ref: comp for comp in netlist.components}
    for i, (comp_ref, pin_name) in enumerate(v5_net.pins):
        if comp_ref in comp_by_ref:
            comp = comp_by_ref[comp_ref]
            pin = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
            if pin and comp.initial_position:
                pos = comp.initial_position
                pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                print(f"  {i + 1}. {comp_ref}.{pin_name}: {pin_pos}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
