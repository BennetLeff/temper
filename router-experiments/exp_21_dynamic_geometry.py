"""
EXP-21: Dynamic Trace/Via Geometry Verification

Verifies that the router uses NetClassRules.trace_width and via_diameter
instead of hardcoded 0.2mm/0.8mm values.

Scenario:
- Route a HighCurrent net (3.0mm trace, 1.0mm via)
- Route a Signal net (0.2mm trace, 0.6mm via)
- Inspect registered Track/Via objects via DRCOracle
- Expected: HighCurrent tracks are 3.0mm wide, vias are 1.0mm diameter
- Without fix: All tracks would be hardcoded 0.2mm

Issue: temper-4539.3
"""

from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.routing.constraints import DRCOracle
from temper_placer.routing.layer_assignment import Layer, LayerAssignment
from temper_placer.routing.maze_router import MazeRouter
import numpy as np


def main():
    print("\n" + "=" * 60)
    print("EXP-21: Dynamic Trace/Via Geometry Verification")
    print("=" * 60)

    # Board setup
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    board.layer_stackup = LayerStackup.default_2layer()

    # Design rules with distinct trace widths
    high_current_rules = NetClassRules(
        name="HighCurrent",
        trace_width=3.0,  # Wide trace for high current
        clearance=1.0,
        via_diameter=1.0,
        via_drill=0.6,
    )

    signal_rules = NetClassRules(
        name="Signal",
        trace_width=0.2,  # Standard trace
        clearance=0.2,
        via_diameter=0.6,
        via_drill=0.3,
    )

    design_rules = DesignRules()
    design_rules.net_classes = {
        "HighCurrent": high_current_rules,
        "Signal": signal_rules,
    }
    design_rules.net_class_assignments = {
        "POWER": "HighCurrent",
        "SIGNAL": "Signal",
    }

    # Create components
    components = [
        Component(
            ref="J_PWR_1",
            footprint="PinHeader_1x01",
            bounds=(2.54, 2.54),
            initial_position=(20.0, 30.0),
            initial_side=0,
            pins=[Pin(name="1", number="1", position=(0, 0))],
        ),
        Component(
            ref="J_PWR_2",
            footprint="PinHeader_1x01",
            bounds=(2.54, 2.54),
            initial_position=(20.0, 70.0),
            initial_side=0,
            pins=[Pin(name="1", number="1", position=(0, 0))],
        ),
        Component(
            ref="J_SIG_1",
            footprint="PinHeader_1x01",
            bounds=(2.54, 2.54),
            initial_position=(60.0, 30.0),
            initial_side=0,
            pins=[Pin(name="1", number="1", position=(0, 0))],
        ),
        Component(
            ref="J_SIG_2",
            footprint="PinHeader_1x01",
            bounds=(2.54, 2.54),
            initial_position=(60.0, 70.0),
            initial_side=0,
            pins=[Pin(name="1", number="1", position=(0, 0))],
        ),
    ]

    # Get positions from components
    positions = np.array([c.initial_position for c in components])

    nets = [
        Net(name="POWER", pins=[("J_PWR_1", "1"), ("J_PWR_2", "1")]),
        Net(name="SIGNAL", pins=[("J_SIG_1", "1"), ("J_SIG_2", "1")]),
    ]

    netlist = Netlist(components=components, nets=nets)

    # Initialize DRC Oracle
    drc_oracle = DRCOracle(rules=design_rules)

    # Initialize router with DRC support
    router = MazeRouter.from_board(
        board,
        cell_size_mm=1.0,
        num_layers=2,
        soft_blocking=False,
        design_rules=design_rules,
        drc_oracle=drc_oracle,
        strict_mode=True,
    )

    # Block pads
    router.block_pads(components, positions, netlist, margin=2.0)

    # Layer assignments (force vias by starting on opposite layers)
    assignments = {
        "POWER": LayerAssignment(
            net="POWER",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
            vias_required=True,
            reason="Multi-layer power",
        ),
        "SIGNAL": LayerAssignment(
            net="SIGNAL",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
            vias_required=True,
            reason="Multi-layer signal",
        ),
    }

    # Route nets
    print("\n1. Routing nets...")
    results = router.rrr_route_all_nets(
        netlist=netlist,
        positions=positions,
        net_order=["POWER", "SIGNAL"],
        assignments=assignments,
        max_iterations=3,
    )

    # Analyze Track/Via geometry from DRCOracle
    print("\n" + "=" * 60)
    print("GEOMETRY VERIFICATION")
    print("=" * 60)

    # Get registered tracks and vias
    power_tracks = [t for t in drc_oracle.tracks if t.net == "POWER"]
    power_vias = [v for v in drc_oracle.vias if v.net == "POWER"]
    signal_tracks = [t for t in drc_oracle.tracks if t.net == "SIGNAL"]
    signal_vias = [v for v in drc_oracle.vias if v.net == "SIGNAL"]

    print(f"\nPOWER net (HighCurrent class):")
    print(f"  Tracks: {len(power_tracks)}")
    print(f"  Vias: {len(power_vias)}")

    if power_tracks:
        widths = [t.width for t in power_tracks]
        avg_width = sum(widths) / len(widths)
        print(f"  Track widths: {widths[:5]}{'...' if len(widths) > 5 else ''}")
        print(f"  Average width: {avg_width:.2f}mm (expected: 3.0mm)")

        # Check neckdown zones
        neckdown_tracks = [t for t in power_tracks if t.width < 3.0]
        if neckdown_tracks:
            print(f"  Neckdown tracks: {len(neckdown_tracks)} (width < 3.0mm)")

        if abs(avg_width - 3.0) < 0.5:
            print("  ✓ PASS: HighCurrent trace width is correct")
        else:
            print(f"  ✗ FAIL: Expected 3.0mm, got {avg_width:.2f}mm")

    if power_vias:
        via_diameters = [v.diameter for v in power_vias]
        avg_dia = sum(via_diameters) / len(via_diameters)
        print(f"  Via diameters: {via_diameters}")
        print(f"  Average diameter: {avg_dia:.2f}mm (expected: 1.0mm)")

        if abs(avg_dia - 1.0) < 0.1:
            print("  ✓ PASS: HighCurrent via diameter is correct")
        else:
            print(f"  ✗ FAIL: Expected 1.0mm, got {avg_dia:.2f}mm")

    print(f"\nSIGNAL net (Signal class):")
    print(f"  Tracks: {len(signal_tracks)}")
    print(f"  Vias: {len(signal_vias)}")

    if signal_tracks:
        widths = [t.width for t in signal_tracks]
        avg_width = sum(widths) / len(widths)
        print(f"  Track widths: {widths[:5]}{'...' if len(widths) > 5 else ''}")
        print(f"  Average width: {avg_width:.2f}mm (expected: 0.2mm)")

        if abs(avg_width - 0.2) < 0.05:
            print("  ✓ PASS: Signal trace width is correct")
        else:
            print(f"  ✗ FAIL: Expected 0.2mm, got {avg_width:.2f}mm")

    if signal_vias:
        via_diameters = [v.diameter for v in signal_vias]
        avg_dia = sum(via_diameters) / len(via_diameters)
        print(f"  Via diameters: {via_diameters}")
        print(f"  Average diameter: {avg_dia:.2f}mm (expected: 0.6mm)")

        if abs(avg_dia - 0.6) < 0.1:
            print("  ✓ PASS: Signal via diameter is correct")
        else:
            print(f"  ✗ FAIL: Expected 0.6mm, got {avg_dia:.2f}mm")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_pass = True
    if power_tracks and abs(sum(t.width for t in power_tracks) / len(power_tracks) - 3.0) >= 0.5:
        all_pass = False
    if signal_tracks and abs(sum(t.width for t in signal_tracks) / len(signal_tracks) - 0.2) >= 0.05:
        all_pass = False

    if all_pass:
        print("\n✓ ALL TESTS PASSED")
        print("Dynamic trace/via geometry is working correctly!")
    else:
        print("\n✗ SOME TESTS FAILED")
        print("Router may still be using hardcoded geometry.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
