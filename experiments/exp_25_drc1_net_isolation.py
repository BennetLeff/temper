#!/usr/bin/env python3
"""
EXP-25: DRC-1 Net Isolation Experiment

Purpose: Verify that the maze router correctly implements net isolation,
preventing shorts between different nets.

Background:
- DRC-1 requires tracking per-cell net ownership
- When routing Net A, cells owned by Net B must be blocked (infinite cost)
- This prevents electrical shorts between different nets

Test Case:
- Two nets that MUST cross (no alternative path)
- Expected: Second net should FAIL to route
- This proves the isolation is working

Results:
- Before fix: Net B routes through Net A's cells (short!)
- After fix: Net B fails to route (isolation working)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter


def test_net_isolation_crossing_nets():
    """
    Test that two nets that MUST cross cannot create a short.

    Setup:
    - 10x10 grid, 1 layer (forces collision)
    - Net A: Horizontal at y=5 from x=1 to x=8
    - Net B: Vertical at x=5 from y=1 to y=8
    - They MUST cross at cell (5, 5)

    Expected:
    - Net A routes successfully
    - Net B FAILS (no path without crossing Net A)
    """
    print("=" * 60)
    print("EXP-25: DRC-1 Net Isolation Test")
    print("=" * 60)

    router = MazeRouter(
        grid_size=(10, 10),
        cell_size_mm=1.0,
        num_layers=1,
        soft_blocking=True,  # RRR mode - but isolation should still block foreign nets
    )

    # Define pin positions
    pins_a = [(1.0, 5.0), (8.0, 5.0)]  # Horizontal
    pins_b = [(5.0, 1.0), (5.0, 8.0)]  # Vertical - must cross at (5, 5)

    print(f"\nGrid: 10x10, 1 layer")
    print(f"Net A pins: {pins_a} (horizontal)")
    print(f"Net B pins: {pins_b} (vertical - MUST cross at (5,5))")

    # Route Net A first
    print("\n--- Routing Net A ---")
    path_a = router.route_net_rrr("NET_A", pins_a, None)

    if not path_a.success:
        print(f"FAIL: Net A failed to route: {path_a.failure_reason}")
        return False

    print(f"SUCCESS: Net A routed with {len(path_a.cells)} cells")

    # Verify cell ownership
    crossing_cell = (5, 5, 0)
    owner = router.cell_owner.get(crossing_cell)
    print(f"Cell ownership at {crossing_cell}: {owner}")

    if owner != "NET_A":
        print(f"FAIL: Expected NET_A to own cell {crossing_cell}, got {owner}")
        return False

    # Route Net B - should FAIL due to isolation
    print("\n--- Routing Net B (should FAIL - isolation) ---")
    path_b = router.route_net_rrr("NET_B", pins_b, None)

    if path_b.success:
        print("FAIL: Net B routed successfully (SHORT CREATED!)")
        print(f"  Path B cells: {[(c.x, c.y) for c in path_b.cells]}")

        # Check for actual short
        cells_a = set((c.x, c.y) for c in path_a.cells)
        cells_b = set((c.x, c.y) for c in path_b.cells)
        intersection = cells_a & cells_b

        if intersection:
            print(f"  ELECTRIC SHORT at cells: {intersection}")
        else:
            print(f"  Note: Path went around, not through intersection")
        return False

    print(f"SUCCESS: Net B failed to route (isolation working!)")
    print(f"  Failure reason: {path_b.failure_reason}")

    # Additional verification: check that crossing cell is still owned by NET_A
    final_owner = router.cell_owner.get(crossing_cell)
    print(f"\nFinal ownership at {crossing_cell}: {final_owner}")

    return True


def test_net_isolation_with_alternate_path():
    """
    Test that nets CAN route if there's an alternate path around.

    Setup:
    - 15x15 grid, 1 layer
    - Net A: Horizontal at y=7 from x=2 to x=12
    - Net B: Vertical at x=7 from y=2 to y=12
    - With a wider grid, Net B can route AROUND Net A

    Expected:
    - Net A routes successfully
    - Net B finds alternate path (goes around the edges)
    """
    print("\n" + "=" * 60)
    print("EXP-25b: DRC-1 with Alternate Path")
    print("=" * 60)

    router = MazeRouter(grid_size=(15, 15), cell_size_mm=1.0, num_layers=1, soft_blocking=True)

    pins_a = [(2.0, 7.0), (12.0, 7.0)]  # Horizontal through middle
    pins_b = [(7.0, 2.0), (7.0, 12.0)]  # Vertical - can go around

    print(f"\nGrid: 15x15, 1 layer (wider, allows alternate path)")
    print(f"Net A pins: {pins_a}")
    print(f"Net B pins: {pins_b}")

    # Route Net A
    print("\n--- Routing Net A ---")
    path_a = router.route_net_rrr("NET_A", pins_a, None)

    if not path_a.success:
        print(f"FAIL: Net A failed: {path_a.failure_reason}")
        return False

    print(f"SUCCESS: Net A routed with {len(path_a.cells)} cells")

    # Route Net B - should find alternate path
    print("\n--- Routing Net B (should find alternate path) ---")
    path_b = router.route_net_rrr("NET_B", pins_b, None)

    if not path_b.success:
        print(f"FAIL: Net B failed (unexpected with wide grid): {path_b.failure_reason}")
        return False

    print(f"SUCCESS: Net B routed with {len(path_b.cells)} cells")

    # Verify no short
    cells_a = set((c.x, c.y) for c in path_a.cells)
    cells_b = set((c.x, c.y) for c in path_b.cells)
    intersection = cells_a & cells_b

    if intersection:
        print(f"FAIL: Short created at {intersection}")
        return False

    print(f"VERIFIED: No intersection between nets")
    print(f"  Net A path: {sorted(cells_a)}")
    print(f"  Net B path: {sorted(cells_b)}")

    return True


def main():
    """Run all DRC-1 experiments."""
    print("\n" + "#" * 60)
    print("# EXP-25: DRC-1 Net Isolation Experiment")
    print("#" * 60)

    results = []

    # Test 1: Crossing nets (should fail)
    results.append(("Crossing Nets (no alternate path)", test_net_isolation_crossing_nets()))

    # Test 2: Alternate path (should succeed)
    results.append(("Alternate Path Available", test_net_isolation_with_alternate_path()))

    # Summary
    print("\n" + "=" * 60)
    print("EXPERIMENT SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("ALL TESTS PASSED - DRC-1 Net Isolation is working correctly!")
        return 0
    else:
        print("SOME TESTS FAILED - DRC-1 needs fix")
        return 1


if __name__ == "__main__":
    sys.exit(main())
