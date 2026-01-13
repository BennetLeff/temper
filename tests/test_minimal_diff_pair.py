#!/usr/bin/env python3.11
"""Minimal test: Just run diff pair routing and check for gaps."""

import sys
from pathlib import Path

sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.routing.diff_pair_router import DiffPairRouter


def test_diff_pair_fix():
    """Test that diff pair routing produces continuous paths."""

    print("Testing differential pair path continuity fix...\n")

    # Create a simple test case
    router = DiffPairRouter(
        grid_size=(400, 400, 2),  # 100mm / 0.25mm = 400 cells
        cell_size_mm=0.25,
        target_separation_mm=0.25,
        max_divergence_mm=2.0,
    )

    # Simple start and goal (10mm apart, straight line)
    start_pins = ((10.0, 50.0), (10.25, 50.0))  # P and N at start
    goal_pins = ((20.0, 50.0), (20.25, 50.0))  # P and N at goal

    print(f"Start: P={start_pins[0]}, N={start_pins[1]}")
    print(f"Goal:  P={goal_pins[0]}, N={goal_pins[1]}")
    print()

    # Route
    result = router.route_pair(start_pins, goal_pins, obstacles=set())

    if result is None:
        print("❌ FAIL: Routing failed")
        return False

    print(f"✅ Routing succeeded!")
    print(f"   P trace: {len(result.pos_cells)} cells")
    print(f"   N trace: {len(result.neg_cells)} cells")
    print(f"   Coupling: {result.coupling_ratio:.1%}")
    print(f"   Skew: {result.max_skew_mm:.3f}mm")
    print()

    # Check path continuity
    def check_gaps(cells, name):
        """Check for gaps in path."""
        gaps = []
        print(f"\n{name} trace cells (first 10 and last 10):")
        for i in range(min(10, len(cells))):
            print(f"  Cell {i}: {cells[i]}")
        if len(cells) > 20:
            print("  ...")
            for i in range(max(10, len(cells) - 10), len(cells)):
                print(f"  Cell {i}: {cells[i]}")

        for i in range(len(cells) - 1):
            x1, y1, l1 = cells[i]
            x2, y2, l2 = cells[i + 1]

            if l1 == l2:  # Same layer
                manhattan = abs(x2 - x1) + abs(y2 - y1)
                if manhattan > 1:
                    gaps.append((i, cells[i], cells[i + 1], manhattan))

        return gaps

    pos_gaps = check_gaps(result.pos_cells, "P")
    neg_gaps = check_gaps(result.neg_cells, "N")

    if pos_gaps:
        print(f"❌ FAIL: P trace has {len(pos_gaps)} gaps:")
        for idx, c1, c2, dist in pos_gaps[:3]:
            print(f"    Cell {idx}: {c1} → {c2}, distance={dist}")
        return False
    else:
        print(f"✅ PASS: P trace is continuous ({len(result.pos_cells)} cells)")

    if neg_gaps:
        print(f"❌ FAIL: N trace has {len(neg_gaps)} gaps:")
        for idx, c1, c2, dist in neg_gaps[:3]:
            print(f"    Cell {idx}: {c1} → {c2}, distance={dist}")
        return False
    else:
        print(f"✅ PASS: N trace is continuous ({len(result.neg_cells)} cells)")

    # Check endpoints
    if result.pos_cells[0][:2] != (40, 200):  # 10.0mm / 0.25mm = 40
        print(f"❌ FAIL: P path doesn't start at correct position")
        print(f"    Expected: (40, 200), Got: {result.pos_cells[0]}")
        return False

    if result.pos_cells[-1][:2] != (80, 200):  # 20.0mm / 0.25mm = 80
        print(f"❌ FAIL: P path doesn't end at correct position")
        print(f"    Expected: (80, 200), Got: {result.pos_cells[-1]}")
        return False

    print(f"✅ PASS: P path has correct start/end positions")

    return True


if __name__ == "__main__":
    success = test_diff_pair_fix()
    print("\n" + "=" * 60)
    if success:
        print("✅ DIFFERENTIAL PAIR FIX VALIDATED!")
        print("\nThe backward path fix works correctly.")
        print("Paths are continuous with no gaps.")
        sys.exit(0)
    else:
        print("❌ TEST FAILED")
        print("\nThe fix may not be working correctly.")
        sys.exit(1)
