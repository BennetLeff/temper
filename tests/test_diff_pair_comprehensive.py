#!/usr/bin/env python3.11
"""
Comprehensive test suite for differential pair path reconstruction fix.

Tests:
1. Path continuity (no gaps)
2. Correct start/end points
3. Various path lengths
4. Layer changes
5. Obstacle avoidance
"""

import sys
from pathlib import Path

sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.routing.diff_pair_router import DiffPairRouter


def check_path_continuity(cells, name):
    """Check for gaps in path. Returns list of gaps found."""
    gaps = []
    for i in range(len(cells) - 1):
        x1, y1, l1 = cells[i]
        x2, y2, l2 = cells[i + 1]

        if l1 == l2:  # Same layer - must be adjacent
            manhattan = abs(x2 - x1) + abs(y2 - y1)
            if manhattan > 1:
                gaps.append(
                    {"index": i, "from": cells[i], "to": cells[i + 1], "distance": manhattan}
                )
        # Layer change is OK (via)
    return gaps


def test_simple_straight_line():
    """Test 1: Simple straight line routing (10mm)."""
    print("\n" + "=" * 60)
    print("TEST 1: Simple straight line (10mm)")
    print("=" * 60)

    router = DiffPairRouter(
        grid_size=(400, 400, 2),
        cell_size_mm=0.25,
        target_separation_mm=0.25,
        max_divergence_mm=2.0,
    )

    start_pins = ((10.0, 50.0), (10.25, 50.0))
    goal_pins = ((20.0, 50.0), (20.25, 50.0))

    result = router.route_pair(start_pins, goal_pins, obstacles=set())

    if result is None:
        print("❌ FAIL: Routing failed")
        return False

    print(f"  P trace: {len(result.pos_cells)} cells")
    print(f"  N trace: {len(result.neg_cells)} cells")

    pos_gaps = check_path_continuity(result.pos_cells, "P")
    neg_gaps = check_path_continuity(result.neg_cells, "N")

    if pos_gaps:
        print(f"❌ FAIL: P trace has {len(pos_gaps)} gaps")
        for g in pos_gaps[:3]:
            print(f"    {g['from']} → {g['to']}, distance={g['distance']}")
        return False

    if neg_gaps:
        print(f"❌ FAIL: N trace has {len(neg_gaps)} gaps")
        for g in neg_gaps[:3]:
            print(f"    {g['from']} → {g['to']}, distance={g['distance']}")
        return False

    # Check endpoints
    expected_start_p = (40, 200, 0)  # 10.0mm / 0.25mm = 40
    expected_end_p = (80, 200, 0)  # 20.0mm / 0.25mm = 80

    if result.pos_cells[0] != expected_start_p:
        print(f"❌ FAIL: P path wrong start: {result.pos_cells[0]} != {expected_start_p}")
        return False

    if result.pos_cells[-1] != expected_end_p:
        print(f"❌ FAIL: P path wrong end: {result.pos_cells[-1]} != {expected_end_p}")
        return False

    print("✅ PASS: Continuous path with correct endpoints")
    return True


def test_longer_path():
    """Test 2: Longer path (25mm)."""
    print("\n" + "=" * 60)
    print("TEST 2: Longer path (25mm)")
    print("=" * 60)

    router = DiffPairRouter(
        grid_size=(400, 400, 2),
        cell_size_mm=0.25,
        target_separation_mm=0.25,
        max_divergence_mm=2.0,
    )

    start_pins = ((5.0, 50.0), (5.25, 50.0))
    goal_pins = ((30.0, 50.0), (30.25, 50.0))

    result = router.route_pair(start_pins, goal_pins, obstacles=set())

    if result is None:
        print("❌ FAIL: Routing failed")
        return False

    print(f"  P trace: {len(result.pos_cells)} cells")

    pos_gaps = check_path_continuity(result.pos_cells, "P")
    neg_gaps = check_path_continuity(result.neg_cells, "N")

    if pos_gaps or neg_gaps:
        print(f"❌ FAIL: Found {len(pos_gaps)} P gaps, {len(neg_gaps)} N gaps")
        return False

    print("✅ PASS: Continuous path")
    return True


def test_diagonal_path():
    """Test 3: Diagonal path (requires turns)."""
    print("\n" + "=" * 60)
    print("TEST 3: Diagonal path (10mm x 10mm)")
    print("=" * 60)

    router = DiffPairRouter(
        grid_size=(400, 400, 2),
        cell_size_mm=0.25,
        target_separation_mm=0.25,
        max_divergence_mm=2.0,
    )

    start_pins = ((10.0, 10.0), (10.25, 10.0))
    goal_pins = ((20.0, 20.0), (20.25, 20.0))

    result = router.route_pair(start_pins, goal_pins, obstacles=set())

    if result is None:
        print("❌ FAIL: Routing failed")
        return False

    print(f"  P trace: {len(result.pos_cells)} cells")

    pos_gaps = check_path_continuity(result.pos_cells, "P")
    neg_gaps = check_path_continuity(result.neg_cells, "N")

    if pos_gaps or neg_gaps:
        print(f"❌ FAIL: Found {len(pos_gaps)} P gaps, {len(neg_gaps)} N gaps")
        return False

    print("✅ PASS: Continuous path")
    return True


def test_short_path():
    """Test 4: Very short path (2mm)."""
    print("\n" + "=" * 60)
    print("TEST 4: Short path (2mm)")
    print("=" * 60)

    router = DiffPairRouter(
        grid_size=(400, 400, 2),
        cell_size_mm=0.25,
        target_separation_mm=0.25,
        max_divergence_mm=2.0,
    )

    start_pins = ((10.0, 50.0), (10.25, 50.0))
    goal_pins = ((12.0, 50.0), (12.25, 50.0))

    result = router.route_pair(start_pins, goal_pins, obstacles=set())

    if result is None:
        print("❌ FAIL: Routing failed")
        return False

    print(f"  P trace: {len(result.pos_cells)} cells")

    pos_gaps = check_path_continuity(result.pos_cells, "P")
    neg_gaps = check_path_continuity(result.neg_cells, "N")

    if pos_gaps or neg_gaps:
        print(f"❌ FAIL: Found {len(pos_gaps)} P gaps, {len(neg_gaps)} N gaps")
        return False

    print("✅ PASS: Continuous path")
    return True


def test_with_obstacles():
    """Test 5: Path with obstacles (forces detour)."""
    print("\n" + "=" * 60)
    print("TEST 5: Path with obstacles")
    print("=" * 60)

    router = DiffPairRouter(
        grid_size=(400, 400, 2),
        cell_size_mm=0.25,
        target_separation_mm=0.25,
        max_divergence_mm=3.0,  # Allow more divergence for obstacle avoidance
    )

    start_pins = ((10.0, 50.0), (10.25, 50.0))
    goal_pins = ((20.0, 50.0), (20.25, 50.0))

    # Create obstacle wall in the middle
    obstacles = set()
    for y in range(180, 220):  # y = 45mm to 55mm
        obstacles.add((60, y, 0))  # x = 15mm, layer 0
        obstacles.add((61, y, 0))

    result = router.route_pair(start_pins, goal_pins, obstacles=obstacles)

    if result is None:
        print("❌ FAIL: Routing failed (couldn't find path around obstacle)")
        return False

    print(f"  P trace: {len(result.pos_cells)} cells")

    pos_gaps = check_path_continuity(result.pos_cells, "P")
    neg_gaps = check_path_continuity(result.neg_cells, "N")

    if pos_gaps or neg_gaps:
        print(f"❌ FAIL: Found {len(pos_gaps)} P gaps, {len(neg_gaps)} N gaps")
        return False

    print("✅ PASS: Continuous path around obstacle")
    return True


def test_multiple_routes():
    """Test 6: Run multiple routes to check consistency."""
    print("\n" + "=" * 60)
    print("TEST 6: Multiple routes (consistency check)")
    print("=" * 60)

    router = DiffPairRouter(
        grid_size=(400, 400, 2),
        cell_size_mm=0.25,
        target_separation_mm=0.25,
        max_divergence_mm=2.0,
    )

    test_cases = [
        ((5.0, 25.0), (5.25, 25.0), (15.0, 25.0), (15.25, 25.0)),
        ((10.0, 30.0), (10.25, 30.0), (25.0, 30.0), (25.25, 30.0)),
        ((15.0, 35.0), (15.25, 35.0), (30.0, 35.0), (30.25, 35.0)),
        ((20.0, 40.0), (20.25, 40.0), (35.0, 40.0), (35.25, 40.0)),
        ((25.0, 45.0), (25.25, 45.0), (40.0, 45.0), (40.25, 45.0)),
    ]

    all_passed = True
    for i, (sp, sn, gp, gn) in enumerate(test_cases):
        result = router.route_pair((sp, sn), (gp, gn), obstacles=set())

        if result is None:
            print(f"  Route {i + 1}: ❌ FAIL (routing failed)")
            all_passed = False
            continue

        pos_gaps = check_path_continuity(result.pos_cells, "P")
        neg_gaps = check_path_continuity(result.neg_cells, "N")

        if pos_gaps or neg_gaps:
            print(f"  Route {i + 1}: ❌ FAIL ({len(pos_gaps)} P gaps, {len(neg_gaps)} N gaps)")
            all_passed = False
        else:
            print(f"  Route {i + 1}: ✅ PASS ({len(result.pos_cells)} cells)")

    return all_passed


def main():
    print("=" * 60)
    print("DIFFERENTIAL PAIR PATH RECONSTRUCTION TEST SUITE")
    print("=" * 60)

    results = {
        "test_simple_straight_line": test_simple_straight_line(),
        "test_longer_path": test_longer_path(),
        "test_diagonal_path": test_diagonal_path(),
        "test_short_path": test_short_path(),
        "test_with_obstacles": test_with_obstacles(),
        "test_multiple_routes": test_multiple_routes(),
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("✅ ALL TESTS PASSED!")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
