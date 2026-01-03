#!/usr/bin/env python3
"""
EXP-25: DRC-1 Net Isolation Experiment

Purpose: Verify that the maze router correctly implements net isolation,
preventing shorts between different nets.

Test Case:
- Two nets that MUST cross (no alternative path)
- Expected: Second net should FAIL to route

Results:
- Before fix: Net B routes through Net A's cells (short!)
- After fix: Net B fails to route (isolation working)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter


def test_net_isolation_crossing_nets():
    """Test that two nets that MUST cross cannot create a short."""
    print("=" * 60)
    print("EXP-25: DRC-1 Net Isolation Test")
    print("=" * 60)

    router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, num_layers=1, soft_blocking=True)

    pins_a = [(1.0, 5.0), (8.0, 5.0)]
    pins_b = [(5.0, 1.0), (5.0, 8.0)]

    print(f"\nGrid: 10x10, 1 layer")
    print(f"Net A: horizontal at y=5")
    print(f"Net B: vertical at x=5 (MUST cross at (5,5))")

    print("\n--- Routing Net A ---")
    path_a = router.route_net_rrr("NET_A", pins_a, None)

    if not path_a.success:
        print(f"FAIL: Net A failed: {path_a.failure_reason}")
        return False

    print(f"SUCCESS: Net A routed ({len(path_a.cells)} cells)")

    owner = router.cell_owner.get((5, 5, 0))
    print(f"Cell (5,5) owned by: {owner}")

    print("\n--- Routing Net B (should FAIL) ---")
    path_b = router.route_net_rrr("NET_B", pins_b, None)

    if path_b.success:
        print("FAIL: Net B routed (SHORT!)")
        return False

    print(f"SUCCESS: Net B failed (isolation working)")
    print(f"  Reason: {path_b.failure_reason}")
    return True


def main():
    print("\n" + "#" * 60)
    print("# EXP-25: DRC-1 Net Isolation")
    print("#" * 60)

    passed = test_net_isolation_crossing_nets()

    print("\n" + "=" * 60)
    if passed:
        print("PASSED - DRC-1 Net Isolation working!")
        return 0
    else:
        print("FAILED - DRC-1 needs fix")
        return 1


if __name__ == "__main__":
    sys.exit(main())
