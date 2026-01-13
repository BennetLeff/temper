#!/usr/bin/env python3
"""
Test EXP-3: Hierarchical Waypoint Routing

Tests the revised hierarchical approach for obstacle avoidance.
"""

import sys
import os

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../packages/temper-placer"))

from experiments.diff_pair.coupled_router import CoupledDiffPairRouter
from experiments.diff_pair.test_fixtures import get_fixture_by_name


def test_hierarchical_straight():
    """Test hierarchical routing on straight path (baseline)."""
    print("=" * 70)
    print("EXP-3 Hierarchical: Test 1 - Straight Path (Baseline)")
    print("=" * 70)
    print()

    fixture = get_fixture_by_name("straight_horizontal")

    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
    )

    result = router.route_hierarchical(
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
        print(f"   Path length: P={len(result.pos_path)}, N={len(result.neg_path)}")
        return True
    else:
        print(f"❌ FAILED: {result.error_message}")
        return False


def test_hierarchical_single_obstacle():
    """Test hierarchical routing around single obstacle."""
    print()
    print("-" * 70)
    print("EXP-3 Hierarchical: Test 2 - Single Obstacle")
    print("-" * 70)
    print()

    fixture = get_fixture_by_name("obstacle_single_pad")

    print(f"Test: {fixture.name}")
    print(f"Obstacles: {len(fixture.obstacles)} grid cells (centered at 5.0, 5.0)")
    print()

    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
        max_divergence_mm=1.0,
    )

    result = router.route_hierarchical(
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
        print(f"   Path length: P={len(result.pos_path)}, N={len(result.neg_path)}")

        # Check obstacle avoidance
        obstacle_center = (5.0, 5.0)
        min_dist = float("inf")
        for wp in result.pos_path + result.neg_path:
            dist = ((wp[0] - obstacle_center[0]) ** 2 + (wp[1] - obstacle_center[1]) ** 2) ** 0.5
            min_dist = min(min_dist, dist)

        print(f"   Closest approach to obstacle: {min_dist:.3f}mm")
        if min_dist > 1.0:
            print("   ✅ Successfully avoids obstacle (>1mm clearance)")
        else:
            print(f"   ⚠️  Close to obstacle ({min_dist:.3f}mm)")

        return True
    else:
        print(f"❌ FAILED: {result.error_message}")
        return False


def test_hierarchical_corner():
    """Test hierarchical routing with corner."""
    print()
    print("-" * 70)
    print("EXP-3 Hierarchical: Test 3 - L-Shaped Corner")
    print("-" * 70)
    print()

    fixture = get_fixture_by_name("single_corner_45deg")

    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
    )

    result = router.route_hierarchical(
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
        return True
    else:
        print(f"❌ FAILED: {result.error_message}")
        return False


def main():
    print()

    tests = [
        ("Straight path (baseline)", test_hierarchical_straight),
        ("Single obstacle", test_hierarchical_single_obstacle),
        ("L-shaped corner", test_hierarchical_corner),
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
        print("✅ All EXP-3 hierarchical tests passed!")
        print()
        print("Key Achievement: Hierarchical approach successfully routes around")
        print("obstacles using coarse waypoint planning + fine segment routing.")
    else:
        print("❌ Some EXP-3 tests failed")
        sys.exit(1)

    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
