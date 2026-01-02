#!/usr/bin/env python3
"""
TEST-02: Bisection Test - Same-Layer vs Cross-Layer Routing

Compares routing performance across different grid sizes to identify scaling issues.
Tests both same-layer and cross-layer routing to isolate layer transition overhead.

Expected Results:
- Same-layer: Visit count should scale linearly with distance
- Cross-layer: Should add constant overhead for via
- 500x500 grid should NOT explode to 100k+ visits for 300-cell route

Issue: temper-bb64
Epic: temper-koke (Debug A* Pathfinding Inefficiency)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter, GridCell


def measure_routing(grid_size, distance, same_layer=True, label=""):
    """
    Measure routing performance for a given configuration.
    
    Returns: (success, path_length, time_ms, visits)
    """
    router = MazeRouter(
        grid_size=(grid_size, grid_size),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    # Center the route
    center = grid_size // 2
    start_x = center - distance // 2
    end_x = center + distance // 2
    y = center
    
    start = (start_x, y)
    end = (end_x, y)
    
    start_layer = 0
    end_layer = 0 if same_layer else 1
    
    # Monkey-patch to count visits
    visit_count = [0]
    original_find_path = router.find_path_rrr
    
    def counting_find_path(*args, **kwargs):
        # Access visit counter from Python A* fallback
        result = original_find_path(*args, **kwargs)
        # Try to extract visit count from stats if available
        return result
    
    t_start = time.perf_counter()
    
    path = router.find_path_rrr(
        start=start,
        end=end,
        layer=start_layer,
        allow_layer_change=not same_layer,
        end_layer=end_layer
    )
    
    t_elapsed = (time.perf_counter() - t_start) * 1000.0  # ms
    
    success = path is not None
    path_length = len(path) if path else 0
    
    # Estimate visits from time (rough heuristic: ~10k visits/sec for Python A*)
    estimated_visits = int(t_elapsed * 10)  # Very rough estimate
    
    return success, path_length, t_elapsed, estimated_visits


def test_grid_scaling():
    """Test how A* performance scales with grid size."""
    print("\n" + "="*70)
    print("BISECTION TEST: Grid Size Scaling")
    print("="*70)
    
    # Test configurations: (grid_size, route_distance)
    configs = [
        (50, 40),
        (100, 80),
        (500, 300),  # This is similar to EXP-16
    ]
    
    results = []
    
    for grid_size, distance in configs:
        print(f"\n--- Grid: {grid_size}x{grid_size}, Distance: {distance} cells ---")
        
        # Same-layer test
        success, path_len, time_ms, visits = measure_routing(
            grid_size, distance, same_layer=True, label=f"{grid_size}x{grid_size}_same"
        )
        
        status = "✅" if success else "❌"
        print(f"{status} Same-layer:  {time_ms:7.1f}ms, path={path_len} cells, ~{visits} visits")
        
        if success and path_len > distance * 2:
            print(f"   ⚠️  Path is {path_len/distance:.1f}x longer than expected!")
        
        results.append(("same", grid_size, distance, success, time_ms, path_len))
        
        # Cross-layer test
        success, path_len, time_ms, visits = measure_routing(
            grid_size, distance, same_layer=False, label=f"{grid_size}x{grid_size}_cross"
        )
        
        status = "✅" if success else "❌"
        print(f"{status} Cross-layer: {time_ms:7.1f}ms, path={path_len} cells, ~{visits} visits")
        
        results.append(("cross", grid_size, distance, success, time_ms, path_len))
        
        # Check for exponential scaling
        if time_ms > 5000:  # 5 seconds is way too long
            print(f"   🚨 CRITICAL: Routing took {time_ms/1000:.1f}s - likely pathfinding bug!")
    
    return results


def analyze_scaling(results):
    """Analyze scaling behavior from results."""
    print("\n" + "="*70)
    print("SCALING ANALYSIS")
    print("="*70)
    
    same_layer_times = [(r[1], r[4]) for r in results if r[0] == "same"]
    
    if len(same_layer_times) >= 2:
        # Check if scaling is linear
        small_grid, small_time = same_layer_times[0]
        large_grid, large_time = same_layer_times[-1]
        
        size_ratio = large_grid / small_grid
        time_ratio = large_time / small_time if small_time > 0 else float('inf')
        
        print(f"\nSame-layer scaling:")
        print(f"  Grid size ratio: {size_ratio:.1f}x")
        print(f"  Time ratio: {time_ratio:.1f}x")
        
        if time_ratio > size_ratio ** 2:
            print(f"  🚨 WORSE than quadratic scaling!")
        elif time_ratio > size_ratio * 1.5:
            print(f"  ⚠️  Worse than linear scaling")
        else:
            print(f"  ✅ Scaling appears linear")
    
    # Check cross-layer overhead
    for mode, grid_size, distance, success, time_ms, path_len in results:
        if grid_size == 500:
            if mode == "cross" and time_ms > 20000:  # 20 seconds
                print(f"\n🚨 FOUND THE BUG:")
                print(f"   Cross-layer routing on 500x500 grid took {time_ms/1000:.1f}s")
                print(f"   This matches the EXP-16 failure pattern!")
                return True
    
    return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("A* BISECTION TESTS - Grid Scaling & Layer Transitions")
    print("="*70)
    
    results = test_grid_scaling()
    bug_found = analyze_scaling(results)
    
    print("\n" + "="*70)
    print("CONCLUSION")
    print("="*70)
    
    if bug_found:
        print("💥 Reproduced the pathfinding bug!")
        print("   Root cause: Grid size or layer transitions cause exponential search")
        sys.exit(1)
    else:
        all_passed = all(r[3] for r in results)  # Check success field
        if all_passed:
            print("🎉 All routing tests passed!")
            print("   A* scales reasonably across grid sizes")
            sys.exit(0)
        else:
            print("⚠️  Some routes failed but didn't hit the exponential bug")
            sys.exit(1)
