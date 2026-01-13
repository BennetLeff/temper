#!/usr/bin/env python3
"""
Test EXP-3: A* Obstacle Avoidance

Tests the coupled router's A* pathfinding with obstacle avoidance.
"""

import sys
import os

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../packages/temper-placer"))

from experiments.diff_pair.coupled_router import CoupledDiffPairRouter
from experiments.diff_pair.test_fixtures import get_fixture_by_name, get_fixtures_by_tag


def test_single_obstacle():
    """Test routing around a single circular obstacle."""
    print("=" * 70)
    print("EXP-3: Test 1 - Single Obstacle Avoidance")
    print("=" * 70)
    print()

    fixture = get_fixture_by_name("obstacle_single_pad")
    if not fixture:
        print("❌ Could not find obstacle test fixture!")
        return False

    print(f"Test: {fixture.name}")
    print(f"Description: {fixture.description}")
    print(f"Obstacles: {len(fixture.obstacles)} grid cells")
    print()

    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
        max_divergence_mm=1.0,  # Allow 1mm divergence for obstacle avoidance
    )

    # Route with A*
    result = router.route_with_astar(
        start_pins=fixture.start_pins,
        goal_pins=fixture.goal_pins,
        obstacles=fixture.obstacles,
        board_size=fixture.board_size,
    )

    if result.success:
        print("✅ SUCCESS")
        print(f"   Time: {result.routing_time_s * 1000:.2f}ms")
        print(f"   Coupling: {result.coupling_ratio:.1f}%")
        print(f"   Avg separation: {result.avg_separation_mm:.3f}mm")
        print(f"   Max skew: {result.max_skew_mm:.3f}mm")
        print(f"   Path length: P={len(result.pos_path)}, N={len(result.neg_path)} waypoints")
        print()

        # Check if path avoids obstacle (center at 5.0, 5.0)
        obstacle_center = (5.0, 5.0)
        min_dist_to_obstacle = float("inf")
        for wp in result.pos_path + result.neg_path:
            dist = ((wp[0] - obstacle_center[0]) ** 2 + (wp[1] - obstacle_center[1]) ** 2) ** 0.5
            min_dist_to_obstacle = min(min_dist_to_obstacle, dist)

        print(f"   Closest approach to obstacle: {min_dist_to_obstacle:.3f}mm")
        if min_dist_to_obstacle > 1.0:  # Should stay >1mm away (pad radius)
            print("   ✅ Path successfully avoids obstacle")
        else:
            print("   ⚠️  Path comes very close to obstacle")

        return True
    else:
        print(f"❌ FAILED: {result.error_message}")
        return False


def test_narrow_corridor():
    """Test routing through a narrow corridor."""
    print()
    print("-" * 70)
    print("EXP-3: Test 2 - Narrow Corridor")
    print("-" * 70)
    print()

    fixture = get_fixture_by_name("narrow_corridor")
    if not fixture:
        print("❌ Could not find corridor test fixture!")
        return False

    print(f"Test: {fixture.name}")
    print(f"Description: {fixture.description}")
    print(f"Obstacles: {len(fixture.obstacles)} grid cells")
    print()

    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
        max_divergence_mm=0.5,  # Tight corridor requires good coupling
    )

    result = router.route_with_astar(
        start_pins=fixture.start_pins,
        goal_pins=fixture.goal_pins,
        obstacles=fixture.obstacles,
        board_size=fixture.board_size,
    )

    if result.success:
        print("✅ SUCCESS")
        print(f"   Time: {result.routing_time_s * 1000:.2f}ms")
        print(f"   Coupling: {result.coupling_ratio:.1f}%")
        print(f"   Avg separation: {result.avg_separation_mm:.3f}mm")
        print(f"   Max skew: {result.max_skew_mm:.3f}mm")
        print()

        # Corridor should maintain good coupling
        if result.coupling_ratio > 70:
            print("   ✅ Good coupling maintained through corridor")
        else:
            print(f"   ⚠️  Coupling dropped to {result.coupling_ratio:.1f}%")

        return True
    else:
        print(f"❌ FAILED: {result.error_message}")
        return False


def test_straight_path_with_astar():
    """Regression: A* should work for straight paths too."""
    print()
    print("-" * 70)
    print("EXP-3: Test 3 - Regression (straight path with A*)")
    print("-" * 70)
    print()

    fixture = get_fixture_by_name("straight_horizontal")

    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
    )

    result = router.route_with_astar(
        start_pins=fixture.start_pins,
        goal_pins=fixture.goal_pins,
        obstacles=fixture.obstacles,
        board_size=fixture.board_size,
    )

    if result.success:
        print("✅ A* works for straight paths")
        print(f"   Time: {result.routing_time_s * 1000:.2f}ms")
        print(f"   Coupling: {result.coupling_ratio:.1f}%")
        return True
    else:
        print(f"❌ A* failed on straight path: {result.error_message}")
        return False


def main():
    print()

    tests = [
        ("Single obstacle", test_single_obstacle),
        ("Narrow corridor", test_narrow_corridor),
        ("Straight path (regression)", test_straight_path_with_astar),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"❌ Exception in {name}: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    print()
    print("=" * 70)
    print("Summary:")
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name:30s} {status}")
    print()

    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("✅ All EXP-3 A* tests passed!")
    else:
        print("❌ Some EXP-3 tests failed")
        sys.exit(1)

    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
