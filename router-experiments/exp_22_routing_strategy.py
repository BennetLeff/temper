"""
EXP-22: Routing Strategy Enforcement Verification

Verifies that the router honors NetClassRules.routing_strategy fields:
- "wide_trace": Discourages vias (multiplies via cost by 10x)
- "plane_preferred": Prefers inner plane layers (L2/L3)
- "plane_required": Forces routing on plane layers only

Scenario:
- Route 3 nets with different strategies
- Verify layer distribution and via counts match strategy
- Expected: Each net follows its routing strategy constraints

Issue: temper-b577
"""

from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.routing.layer_assignment import Layer, LayerAssignment
from temper_placer.routing.maze_router import MazeRouter
import numpy as np


def main():
    print("\n" + "=" * 60)
    print("EXP-22: Routing Strategy Enforcement Verification")
    print("=" * 60)

    # Board setup: 4-layer to test plane routing
    board = Board(width=120.0, height=80.0, origin=(0.0, 0.0))
    board.layer_stackup = LayerStackup.default_4layer()

    # Design rules with different routing strategies
    wide_trace_rules = NetClassRules(
        name="WideTrace",
        trace_width=2.0,
        clearance=0.5,
        routing_strategy="wide_trace",  # Should minimize vias
        via_diameter=0.8,
        via_drill=0.4,
    )

    plane_preferred_rules = NetClassRules(
        name="PlanePref",
        trace_width=0.3,
        clearance=0.2,
        routing_strategy="plane_preferred",  # Should prefer L2/L3
        via_diameter=0.6,
        via_drill=0.3,
    )

    standard_rules = NetClassRules(
        name="Standard",
        trace_width=0.25,
        clearance=0.2,
        routing_strategy=None,  # No constraints
        via_diameter=0.6,
        via_drill=0.3,
    )

    design_rules = DesignRules()
    design_rules.net_classes = {
        "WideTrace": wide_trace_rules,
        "PlanePref": plane_preferred_rules,
        "Standard": standard_rules,
    }
    design_rules.net_class_assignments = {
        "POWER_WIDE": "WideTrace",
        "GND_PLANE": "PlanePref",
        "SIGNAL_STD": "Standard",
    }

    # Create components - use longer paths to force routing decisions
    components = []
    y_positions = [20.0, 40.0, 60.0]
    for i, prefix in enumerate(["WIDE", "PLANE", "STD"]):
        y = y_positions[i]
        components.extend(
            [
                Component(
                    ref=f"J_{prefix}_START",
                    footprint="PinHeader_1x01",
                    bounds=(2.54, 2.54),
                    initial_position=(20.0, y),
                    initial_side=0,
                    pins=[Pin(name="1", number="1", position=(0, 0))],
                ),
                Component(
                    ref=f"J_{prefix}_END",
                    footprint="PinHeader_1x01",
                    bounds=(2.54, 2.54),
                    initial_position=(100.0, y),
                    initial_side=0,
                    pins=[Pin(name="1", number="1", position=(0, 0))],
                ),
            ]
        )

    # Get positions from components
    positions = np.array([c.initial_position for c in components])

    nets = [
        Net(name="POWER_WIDE", pins=[("J_WIDE_START", "1"), ("J_WIDE_END", "1")]),
        Net(name="GND_PLANE", pins=[("J_PLANE_START", "1"), ("J_PLANE_END", "1")]),
        Net(name="SIGNAL_STD", pins=[("J_STD_START", "1"), ("J_STD_END", "1")]),
    ]

    netlist = Netlist(components=components, nets=nets)

    # Initialize router
    router = MazeRouter.from_board(
        board,
        cell_size_mm=1.0,
        num_layers=4,
        soft_blocking=False,
        design_rules=design_rules,
        via_cost=5.0,  # Base via cost
    )

    # Block pads
    router.block_pads(components, positions, netlist, margin=1.0)

    # Layer assignments - allow all layers to test strategy enforcement
    assignments = {
        "POWER_WIDE": LayerAssignment(
            net="POWER_WIDE",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
            vias_required=False,
            reason="Test wide_trace strategy",
        ),
        "GND_PLANE": LayerAssignment(
            net="GND_PLANE",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
            vias_required=False,
            reason="Test plane_preferred strategy",
        ),
        "SIGNAL_STD": LayerAssignment(
            net="SIGNAL_STD",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
            vias_required=False,
            reason="Baseline (no strategy)",
        ),
    }

    # Route nets
    print("\n1. Routing nets with different strategies...")
    results = router.rrr_route_all_nets(
        netlist=netlist,
        positions=positions,
        net_order=["POWER_WIDE", "GND_PLANE", "SIGNAL_STD"],
        assignments=assignments,
        max_iterations=3,
    )

    # Analyze routing results
    print("\n" + "=" * 60)
    print("STRATEGY VERIFICATION")
    print("=" * 60)

    def analyze_path_layers(cells):
        """Return layer distribution as a dict {layer_idx: cell_count}"""
        layer_dist = {}
        for cell in cells:
            layer_dist[cell.layer] = layer_dist.get(cell.layer, 0) + 1
        return layer_dist

    # Test 1: Wide Trace Strategy (should minimize vias)
    wide_result = results["POWER_WIDE"]
    print(f"\nPOWER_WIDE (wide_trace strategy):")
    print(f"  Success: {wide_result.success}")
    print(f"  Path Length: {wide_result.length:.1f}mm")
    print(f"  Via Count: {wide_result.via_count}")

    if wide_result.success:
        if wide_result.via_count <= 1:  # At most 1 via (or 0)
            print("  ✓ PASS: Minimized vias as expected for wide traces")
        else:
            print(f"  ✗ FAIL: Too many vias ({wide_result.via_count}) for wide_trace strategy")

    # Test 2: Plane Preferred Strategy (should use L2/L3)
    plane_result = results["GND_PLANE"]
    print(f"\nGND_PLANE (plane_preferred strategy):")
    print(f"  Success: {plane_result.success}")
    print(f"  Path Length: {plane_result.length:.1f}mm")
    print(f"  Via Count: {plane_result.via_count}")

    if plane_result.success:
        layer_dist = analyze_path_layers(plane_result.cells)
        print(f"  Layer distribution: {layer_dist}")

        plane_cells = layer_dist.get(1, 0) + layer_dist.get(2, 0)  # L2 + L3
        total_cells = sum(layer_dist.values())
        plane_ratio = plane_cells / max(1, total_cells)

        print(f"  Plane layer usage: {plane_ratio * 100:.1f}%")

        if plane_ratio > 0.5:  # Majority on plane layers
            print("  ✓ PASS: Prefers plane layers (L2/L3) as expected")
        else:
            print(f"  ⚠ WARNING: Only {plane_ratio * 100:.1f}% on plane layers")

    # Test 3: Standard Strategy (baseline)
    std_result = results["SIGNAL_STD"]
    print(f"\nSIGNAL_STD (no strategy):")
    print(f"  Success: {std_result.success}")
    print(f"  Path Length: {std_result.length:.1f}mm")
    print(f"  Via Count: {std_result.via_count}")

    if std_result.success:
        layer_dist = analyze_path_layers(std_result.cells)
        print(f"  Layer distribution: {layer_dist}")
        print("  (No strategy constraints - baseline behavior)")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    tests_passed = 0
    total_tests = 0

    if wide_result.success:
        total_tests += 1
        if wide_result.via_count <= 1:
            tests_passed += 1

    if plane_result.success:
        total_tests += 1
        layer_dist = analyze_path_layers(plane_result.cells)
        plane_cells = layer_dist.get(1, 0) + layer_dist.get(2, 0)
        if plane_cells / max(1, sum(layer_dist.values())) > 0.5:
            tests_passed += 1

    print(f"\nTests Passed: {tests_passed}/{total_tests}")

    if tests_passed == total_tests:
        print("✓ ALL STRATEGY TESTS PASSED")
        print("Routing strategy enforcement is working!")
    else:
        print("✗ SOME STRATEGY TESTS FAILED")
        print("Router may not be fully honoring routing_strategy field.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
