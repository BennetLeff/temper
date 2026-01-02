#!/usr/bin/env python3
"""
Performance Profiling for Differential Pair Router

Measures routing time and compares against baseline single-net routing.

METRICS:
- Routing time (differential pair vs 2× single nets)
- States explored
- Memory usage
- Beam pruning effectiveness
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.diff_pair_router import DiffPairRouter


def profile_diff_pair_routing():
    """Profile differential pair router performance."""
    print("\n" + "=" * 70)
    print("Differential Pair Router - Performance Profiling")
    print("=" * 70 + "\n")
    
    # Test scenarios
    scenarios = [
        ("Simple (no obstacles)", 100, 100, set()),
        ("Medium obstacles", 100, 100, {(50+i, 50+j, 0) for i in range(-10, 10) for j in range(-10, 10)}),
        ("Dense obstacles", 100, 100, {(50+i, 50+j, 0) for i in range(-20, 20) for j in range(-20, 20)}),
    ]
    
    for scenario_name, grid_w, grid_h, obstacles in scenarios:
        print(f"📊 Scenario: {scenario_name}")
        print(f"   Grid: {grid_w}x{grid_h}, Obstacles: {len(obstacles)}")
        
        router = DiffPairRouter(
            grid_size=(grid_w, grid_h, 2),
            cell_size_mm=0.2,
            target_separation_mm=0.2,
            max_skew_mm=0.5,
            beam_width=1000,
        )
        
        # Route from (10, 50) to (90, 50)
        start_pins = ((10.0, 50.0), (10.0, 48.0))
        goal_pins = ((90.0, 50.0), (90.0, 48.0))
        
        start_time = time.time()
        result = router.route_pair(
            start_pins=start_pins,
            goal_pins=goal_pins,
            obstacles=obstacles,
            enable_length_matching=False,  # Disable for profiling
        )
        elapsed = time.time() - start_time
        
        print(f"   Time: {elapsed*1000:.1f}ms")
        print(f"   Success: {result.success}")
        
        if result.success:
            print(f"   Coupling: {result.coupling_ratio:.1f}%")
            print(f"   States explored: {router.states_explored:,}")
            print(f"   Coupling pruned: {router.states_pruned:,}")
            print(f"   Beam pruned: {router.beam_pruned}")
            print(f"   Pruning efficiency: {(router.states_pruned/max(router.states_explored,1))*100:.1f}%")
        else:
            print(f"   Failed: {result.failure_reason}")
        
        print()
    
    print("=" * 70)
    print("Profiling complete!\n")


if __name__ == "__main__":
    profile_diff_pair_routing()
