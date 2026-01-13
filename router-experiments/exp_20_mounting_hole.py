"""
EXP-20: Mounting Hole Avoidance Test

Verifies that the router correctly avoids mounting holes when
board.mounting_holes are blocked via block_board_features().

Scenario:
- Simple point-to-point route (straight line optimal: 40mm)
- Central mounting hole (5mm keepout radius) blocks the direct path
- Expected: Router detours around the hole (path length > 40mm)
- Without fix: Router ignores mounting hole and routes through it

Issue: temper-7gww.3
"""

from temper_placer.core.board import Board, LayerStackup, MountingHole
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.routing.layer_assignment import Layer, LayerAssignment
from temper_placer.routing.maze_router import MazeRouter
import numpy as np


def main():
    print("\n" + "=" * 60)
    print("EXP-20: Mounting Hole Avoidance Test")
    print("=" * 60)

    # Board setup: 100mm x 100mm, 2-layer
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    board.layer_stackup = LayerStackup.default_2layer()

    # Add mounting hole in the CENTER of the optimal path
    # Path is from (30, 50) to (70, 50) -> straight line at y=50
    # Mounting hole at (50, 50) with 5mm keepout radius
    board.mounting_holes = [
        MountingHole(
            position=(50.0, 50.0),
            diameter=3.2,  # M3 mounting hole
            keepout_radius=5.0,  # 5mm clearance
        )
    ]

    # Create simple 2-pin net
    components = [
        Component(
            ref="J_START",
            footprint="PinHeader_1x01",
            bounds=(2.54, 2.54),
            initial_position=(30.0, 50.0),
            initial_side=0,
            pins=[Pin(name="1", number="1", position=(0, 0))],
        ),
        Component(
            ref="J_END",
            footprint="PinHeader_1x01",
            bounds=(2.54, 2.54),
            initial_position=(70.0, 50.0),
            initial_side=0,
            pins=[Pin(name="1", number="1", position=(0, 0))],
        ),
    ]

    # Get positions from components
    positions = np.array([c.initial_position for c in components])

    nets = [
        Net(name="SIGNAL", pins=[("J_START", "1"), ("J_END", "1")]),
    ]

    netlist = Netlist(components=components, nets=nets)

    # Initialize router
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2, soft_blocking=False)

    # CRITICAL: Block board features (mounting holes)
    print("\n1. Blocking board features (mounting holes)...")
    router.block_board_features(board)

    # Block component pads
    router.block_pads(components, positions, netlist, margin=1.0)

    # Layer assignment
    assignments = {
        "SIGNAL": LayerAssignment(
            net="SIGNAL",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
            vias_required=False,
            reason="Standard signal",
        ),
    }

    # Route the net
    print("2. Routing SIGNAL net...")
    results = router.rrr_route_all_nets(
        netlist=netlist,
        positions=positions,
        net_order=["SIGNAL"],
        assignments=assignments,
        max_iterations=3,
    )

    # Analyze results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    result = results["SIGNAL"]
    straight_line_distance = 40.0  # (70 - 30)mm

    print(f"\nSIGNAL:")
    print(f"  Success: {result.success}")
    print(f"  Path Length: {result.length:.1f}mm")
    print(f"  Straight Line Distance: {straight_line_distance:.1f}mm")
    print(f"  Via Count: {result.via_count}")

    if result.success:
        detour_amount = result.length - straight_line_distance

        if detour_amount > 10.0:  # Significant detour (>10mm)
            print(f"\n✓ PASS: Router detoured around mounting hole")
            print(f"  Detour: +{detour_amount:.1f}mm ({detour_amount/straight_line_distance*100:.1f}% longer)")
            print("  Mounting hole avoidance is working!")
        elif result.via_count > 0:
            print(f"\n✓ PASS: Router used layer change to avoid mounting hole")
            print(f"  Via count: {result.via_count}")
            print("  Mounting hole blocked surface routing!")
        else:
            print(f"\n✗ FAIL: Path is suspiciously short ({result.length:.1f}mm)")
            print(f"  Detour: only +{detour_amount:.1f}mm")
            print("  Router may have routed THROUGH the mounting hole!")
    else:
        print(f"\n✗ FAIL: Routing failed - {result.failure_reason}")
        print("  Router should have found a detour path.")

    # Visual check: count blocked cells in mounting hole area
    hole_x, hole_y = 50.0, 50.0
    hole_radius = 5.0
    gx, gy = router._world_to_grid(hole_x, hole_y)
    radius_cells = int(np.ceil(hole_radius / router.cell_size))

    blocked_count = 0
    for dx in range(-radius_cells, radius_cells + 1):
        for dy in range(-radius_cells, radius_cells + 1):
            nx, ny = gx + dx, gy + dy
            if 0 <= nx < router.grid_size[0] and 0 <= ny < router.grid_size[1]:
                if router.occupancy[nx, ny, 0] == -1:
                    blocked_count += 1

    expected_blocked = int(np.pi * radius_cells**2)
    print(f"\nMounting Hole Grid Blocking:")
    print(f"  Blocked cells: {blocked_count}")
    print(f"  Expected (approx): {expected_blocked}")

    if blocked_count > 0:
        print("  ✓ Mounting hole was correctly blocked in routing grid")
    else:
        print("  ✗ Mounting hole was NOT blocked - block_board_features() failed!")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
