#!/usr/bin/env python3
"""
Test EXP-2: 45° Corner Support

Tests the coupled router's ability to route L-shaped paths with corners.
"""

import sys
import os

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../packages/temper-placer"))

from experiments.diff_pair.coupled_router import CoupledDiffPairRouter
from experiments.diff_pair.test_fixtures import get_fixture_by_name


def test_corner_routing():
    """Test L-shaped routing with corner waypoints."""
    print("=" * 70)
    print("EXP-2: Testing Corner Routing with Waypoints")
    print("=" * 70)
    print()

    # Get the corner test fixture
    fixture = get_fixture_by_name("single_corner_45deg")
    if not fixture:
        print("❌ Could not find corner test fixture!")
        return False

    print(f"Test: {fixture.name}")
    print(f"Description: {fixture.description}")
    print(f"Start: P={fixture.start_pins[0]}, N={fixture.start_pins[1]}")
    print(f"Goal:  P={fixture.goal_pins[0]}, N={fixture.goal_pins[1]}")
    print()

    # Create router (no DRC oracle for basic test)
    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
    )

    # Calculate corner waypoints
    waypoints = router.calculate_corner_waypoints(fixture.start_pins, fixture.goal_pins)

    if waypoints:
        print(f"Generated {len(waypoints)} waypoint(s):")
        for i, (pos_wp, neg_wp) in enumerate(waypoints):
            print(f"  WP{i + 1}: P={pos_wp}, N={neg_wp}")
        print()
    else:
        print("No waypoints needed (straight path)")
        print()

    # Route with waypoints
    result = router.route(
        start_pins=fixture.start_pins,
        goal_pins=fixture.goal_pins,
        obstacles=fixture.obstacles,
        board_size=fixture.board_size,
        waypoints=waypoints,
    )

    # Print results
    if result.success:
        print("✅ SUCCESS")
        print(f"   Time: {result.routing_time_s * 1000:.2f}ms")
        print(f"   Coupling: {result.coupling_ratio:.1f}%")
        print(f"   Avg separation: {result.avg_separation_mm:.3f}mm")
        print(f"   Max skew: {result.max_skew_mm:.3f}mm")
        print(f"   Path length: P={len(result.pos_path)}, N={len(result.neg_path)} waypoints")
        print()

        # Validate corner geometry
        if len(result.pos_path) > 2:
            print("Corner analysis:")
            # Find the corner point (where direction changes)
            for i in range(1, len(result.pos_path) - 1):
                prev = result.pos_path[i - 1]
                curr = result.pos_path[i]
                next_ = result.pos_path[i + 1]

                # Check if direction changes
                dx1 = curr[0] - prev[0]
                dy1 = curr[1] - prev[1]
                dx2 = next_[0] - curr[0]
                dy2 = next_[1] - curr[1]

                # Normalize
                len1 = (dx1**2 + dy1**2) ** 0.5
                len2 = (dx2**2 + dy2**2) ** 0.5

                if len1 > 0 and len2 > 0:
                    dx1 /= len1
                    dy1 /= len1
                    dx2 /= len2
                    dy2 /= len2

                    # Check if directions are different
                    if abs(dx1 - dx2) > 0.1 or abs(dy1 - dy2) > 0.1:
                        print(f"  Corner found at waypoint {i}: {curr}")
                        print(
                            f"  Direction change: ({dx1:.2f}, {dy1:.2f}) -> ({dx2:.2f}, {dy2:.2f})"
                        )
                        break

        return True
    else:
        print(f"❌ FAILED")
        print(f"   Error: {result.error_message}")
        return False


def test_straight_paths_still_work():
    """Verify that straight paths still work without waypoints."""
    print()
    print("-" * 70)
    print("Regression test: Straight paths without waypoints")
    print("-" * 70)
    print()

    fixture = get_fixture_by_name("straight_horizontal")

    router = CoupledDiffPairRouter(
        grid_resolution_mm=fixture.grid_resolution_mm,
        trace_width_mm=fixture.trace_width_mm,
        target_spacing_mm=fixture.spacing_mm,
    )

    # Route without waypoints (EXP-1 behavior)
    result = router.route(
        start_pins=fixture.start_pins,
        goal_pins=fixture.goal_pins,
        obstacles=fixture.obstacles,
        board_size=fixture.board_size,
        waypoints=None,
    )

    if result.success:
        print("✅ Straight routing still works")
        return True
    else:
        print(f"❌ Regression: {result.error_message}")
        return False


def main():
    print()

    # Test 1: Corner routing
    test1_passed = test_corner_routing()

    # Test 2: Regression test
    test2_passed = test_straight_paths_still_work()

    print()
    print("=" * 70)
    print("Summary:")
    print(f"  Corner routing:     {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"  Straight routing:   {'✅ PASS' if test2_passed else '❌ FAIL'}")
    print()

    if test1_passed and test2_passed:
        print("✅ All EXP-2 tests passed!")
    else:
        print("❌ Some tests failed")
        sys.exit(1)

    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
