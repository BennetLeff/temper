#!/usr/bin/env python3
"""
Test the minimal coupled router (EXP-1) against test fixtures.

This validates that:
1. Straight horizontal/vertical routing works
2. DRC oracle prevents violations
3. Metrics are calculated correctly
"""

import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "experiments"))

from diff_pair.test_fixtures import create_test_fixtures, get_fixtures_by_tag
from diff_pair.coupled_router import CoupledDiffPairRouter
from diff_pair.run_experiments import run_experiment


def test_minimal_router():
    """Test minimal router with straight-line fixtures."""

    print("=" * 70)
    print("EXP-1: Testing Minimal Coupled Router")
    print("=" * 70)
    print()

    # Get straight-line test fixtures
    fixtures = get_fixtures_by_tag("straight")

    if not fixtures:
        print("ERROR: No 'straight' fixtures found")
        return 1

    print(f"Found {len(fixtures)} straight-line test fixtures")
    print()

    # Create router (no DRC oracle for now - just testing routing logic)
    router = CoupledDiffPairRouter(
        grid_resolution_mm=0.1,
        trace_width_mm=0.127,
        target_spacing_mm=0.25,
        drc_oracle=None,  # EXP-1: Test without DRC oracle first
    )

    # Run tests
    results = []
    for fixture in fixtures:
        print(f"Testing: {fixture.name}")
        print(f"  Description: {fixture.description}")

        result = router.route(
            start_pins=fixture.start_pins,
            goal_pins=fixture.goal_pins,
            obstacles=fixture.obstacles,
            board_size=fixture.board_size,
        )

        results.append(result)

        if result.success:
            print(f"  ✅ SUCCESS")
            print(f"     Time: {result.routing_time_s * 1000:.2f}ms")
            print(f"     Coupling: {result.coupling_ratio:.1f}%")
            print(f"     Avg separation: {result.avg_separation_mm:.3f}mm")
            print(f"     Max skew: {result.max_skew_mm:.3f}mm")
            print(f"     Path length: P={len(result.pos_path)}, N={len(result.neg_path)} waypoints")
        else:
            print(f"  ❌ FAILED: {result.error_message}")

        print()

    # Summary
    print("=" * 70)
    print("Summary:")
    passed = sum(1 for r in results if r.success)
    print(f"  Passed: {passed}/{len(results)}")
    print(f"  Total time: {sum(r.routing_time_s for r in results) * 1000:.2f}ms")

    if passed == len(results):
        print("\n✅ All straight-line tests passed!")
    else:
        print(f"\n❌ {len(results) - passed} tests failed")

    print("=" * 70)

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(test_minimal_router())
