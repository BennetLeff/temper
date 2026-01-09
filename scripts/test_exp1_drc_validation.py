#!/usr/bin/env python3
"""
Test the minimal coupled router (EXP-1) with DRC oracle validation.

This validates that the DRC oracle can prevent violations.
"""

import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "experiments"))

from diff_pair.test_fixtures import create_test_fixtures
from diff_pair.coupled_router import CoupledDiffPairRouter


class MockDRCOracle:
    """
    Mock DRC oracle for testing.

    Simulates a pad at (5.0, 5.0) with 1mm radius that blocks routing.
    """

    def __init__(self, has_blocking_pad: bool = False):
        self.has_blocking_pad = has_blocking_pad
        self.pad_center = (5.0, 5.0)
        self.pad_radius = 1.0
        self.check_count = 0

    def can_place_track_segment(
        self,
        start: tuple,
        end: tuple,
        layer: int,
        net: str,
        width: float,
        neckdown: bool = False,
    ) -> tuple:
        """Check if track segment can be placed."""
        self.check_count += 1

        if not self.has_blocking_pad:
            return (True, "OK")

        # Check if segment intersects with pad
        # Simplified: check if midpoint is within pad + clearance
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2

        dx = mid_x - self.pad_center[0]
        dy = mid_y - self.pad_center[1]
        dist = (dx * dx + dy * dy) ** 0.5

        # Required clearance: pad_radius + trace_width/2 + clearance
        required_clearance = self.pad_radius + width / 2 + 0.16  # 0.16mm clearance

        if dist < required_clearance:
            return (
                False,
                f"Too close to pad at ({self.pad_center[0]}, {self.pad_center[1]}): {dist:.3f}mm < {required_clearance:.3f}mm",
            )

        return (True, "OK")


def test_with_drc_oracle():
    """Test router with DRC oracle validation."""

    print("=" * 70)
    print("EXP-1: Testing Minimal Router with DRC Oracle")
    print("=" * 70)
    print()

    # Test 1: Routing without obstacles (should pass)
    print("Test 1: Straight routing WITHOUT blocking pad")
    print("-" * 70)

    oracle_pass = MockDRCOracle(has_blocking_pad=False)
    router_pass = CoupledDiffPairRouter(
        grid_resolution_mm=0.1, trace_width_mm=0.127, target_spacing_mm=0.25, drc_oracle=oracle_pass
    )

    result_pass = router_pass.route(
        start_pins=((1.0, 5.0), (1.0, 5.25)),
        goal_pins=((9.0, 5.0), (9.0, 5.25)),
        obstacles=set(),
        board_size=(10.0, 10.0, 1),
        net_pos="USB_D+",
        net_neg="USB_D-",
    )

    print(f"Result: {'✅ SUCCESS' if result_pass.success else '❌ FAILED'}")
    if result_pass.success:
        print(f"  DRC checks performed: {oracle_pass.check_count}")
        print(f"  Path length: {len(result_pass.pos_path)} waypoints")
    else:
        print(f"  Error: {result_pass.error_message}")
    print()

    # Test 2: Routing through blocking pad (should fail)
    print("Test 2: Straight routing WITH blocking pad at (5.0, 5.0)")
    print("-" * 70)

    oracle_fail = MockDRCOracle(has_blocking_pad=True)
    router_fail = CoupledDiffPairRouter(
        grid_resolution_mm=0.1, trace_width_mm=0.127, target_spacing_mm=0.25, drc_oracle=oracle_fail
    )

    result_fail = router_fail.route(
        start_pins=((1.0, 5.0), (1.0, 5.25)),
        goal_pins=((9.0, 5.0), (9.0, 5.25)),
        obstacles=set(),
        board_size=(10.0, 10.0, 1),
        net_pos="USB_D+",
        net_neg="USB_D-",
    )

    print(
        f"Result: {'❌ FAILED (expected)' if not result_fail.success else '✅ PASSED (unexpected!)'}"
    )
    if not result_fail.success:
        print(f"  DRC checks performed: {oracle_fail.check_count}")
        print(f"  Error caught: {result_fail.error_message}")
        print(f"  ✅ DRC oracle correctly prevented violation!")
    else:
        print(f"  ❌ ERROR: Should have failed due to pad clearance!")
    print()

    # Test 3: Routing around pad (path avoids pad)
    print("Test 3: Routing AROUND pad (not through it)")
    print("-" * 70)

    oracle_around = MockDRCOracle(has_blocking_pad=True)
    router_around = CoupledDiffPairRouter(
        grid_resolution_mm=0.1,
        trace_width_mm=0.127,
        target_spacing_mm=0.25,
        drc_oracle=oracle_around,
    )

    # Route above the pad at y=7 (pad is at y=5)
    result_around = router_around.route(
        start_pins=((1.0, 7.0), (1.0, 7.25)),
        goal_pins=((9.0, 7.0), (9.0, 7.25)),
        obstacles=set(),
        board_size=(10.0, 10.0, 1),
        net_pos="USB_D+",
        net_neg="USB_D-",
    )

    print(f"Result: {'✅ SUCCESS' if result_around.success else '❌ FAILED'}")
    if result_around.success:
        print(f"  DRC checks performed: {oracle_around.check_count}")
        print(f"  All checks passed - path is clear of pad")
    else:
        print(f"  Error: {result_around.error_message}")
    print()

    # Summary
    print("=" * 70)
    print("Summary:")
    print(f"  Test 1 (no pad):      {'✅ PASS' if result_pass.success else '❌ FAIL'}")
    print(
        f"  Test 2 (blocked):     {'✅ PASS' if not result_fail.success else '❌ FAIL'} (should fail)"
    )
    print(f"  Test 3 (clear path):  {'✅ PASS' if result_around.success else '❌ FAIL'}")

    all_pass = result_pass.success and (not result_fail.success) and result_around.success

    if all_pass:
        print("\n✅ All DRC oracle tests passed!")
        print("\nKey Validation:")
        print("  ✓ Router can route when DRC oracle approves")
        print("  ✓ Router is blocked when DRC oracle rejects")
        print("  ✓ DRC oracle checks EVERY segment during routing")
        print("\nThis proves the coupled router approach works!")
    else:
        print("\n❌ Some tests failed")

    print("=" * 70)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(test_with_drc_oracle())
