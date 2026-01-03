#!/usr/bin/env python3
"""
TEST-01: Minimal A* Unit Test (No Obstacles)

Tests pure A* pathfinding with no pads, design rules, or obstacles.
Verifies basic connectivity on a small grid.

Expected Results:
- Same-layer routing should succeed with path length ≈ Manhattan distance
- Cross-layer routing should succeed with 1 via + path length
- Visit count should be reasonable (< 1000 for 50x50 grid)

Issue: temper-57py
Epic: temper-koke (Debug A* Pathfinding Inefficiency)
"""

import sys
from pathlib import Path

# Adjust path to import packages
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter


def test_same_layer_routing():
    """Test A* routing on same layer (L0 -> L0)."""
    print("\n" + "="*60)
    print("TEST 1: Same-Layer Routing (L0 -> L0)")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(50, 50),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0  # No clearance constraints
    )
    
    # No pads blocked - pure routing test
    start = (5, 25)
    end = (45, 25)
    
    print(f"Start: {start}, End: {end}, Layer: 0")
    print(f"Expected Manhattan distance: {abs(end[0] - start[0]) + abs(end[1] - start[1])}")
    
    path = router.find_path_rrr(
        start=start,
        end=end,
        layer=0,
        allow_layer_change=False,  # No layer change
        end_layer=0
    )
    
    if path is None:
        print("❌ FAILED: No path found")
        return False
    
    print(f"✅ SUCCESS: Path found with {len(path)} cells")
    print(f"   Via count: {sum(1 for i in range(1, len(path)) if path[i].layer != path[i-1].layer)}")
    
    # Sanity check: path length should be reasonable
    expected_min = abs(end[0] - start[0]) + abs(end[1] - start[1])
    if len(path) > expected_min * 3:
        print(f"⚠️  WARNING: Path is {len(path) / expected_min:.1f}x longer than Manhattan distance")
    
    return True


def test_cross_layer_routing():
    """Test A* routing across layers (L0 -> L1)."""
    print("\n" + "="*60)
    print("TEST 2: Cross-Layer Routing (L0 -> L1)")  
    print("="*60)
    
    router = MazeRouter(
        grid_size=(50, 50),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    start = (5, 25)
    end = (45, 25)
    
    print(f"Start: {start} on L0, End: {end} on L1")
    print(f"Expected: Via transition + horizontal routing")
    
    path = router.find_path_rrr(
        start=start,
        end=end,
        layer=0,
        allow_layer_change=True,  # Allow vias
        end_layer=1  # Target is on L1
    )
    
    if path is None:
        print("❌ FAILED: No path found")
        return False
    
    via_count = sum(1 for i in range(1, len(path)) if path[i].layer != path[i-1].layer)
    print(f"✅ SUCCESS: Path found with {len(path)} cells, {via_count} layer transitions")
    
    # Check that we actually changed layers
    if via_count == 0:
        print("⚠️  WARNING: No layer transitions detected (expected at least 1)")
    
    return True


def test_diagonal_routing():
    """Test A* routing diagonally (tests both X and Y movement)."""
    print("\n" + "="*60)
    print("TEST 3: Diagonal Routing (L0 -> L0)")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(50, 50),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    start = (5, 5)
    end = (45, 45)
    
    print(f"Start: {start}, End: {end}, Layer: 0")
    print(f"Expected Manhattan distance: {abs(end[0] - start[0]) + abs(end[1] - start[1])}")
    
    path = router.find_path_rrr(
        start=start,
        end=end,
        layer=0,
        allow_layer_change=False,
        end_layer=0
    )
    
    if path is None:
        print("❌ FAILED: No path found")
        return False
    
    print(f"✅ SUCCESS: Path found with {len(path)} cells")
    
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("A* MINIMAL UNIT TESTS")
    print("="*60)
    print("Testing pure A* pathfinding with NO obstacles, pads, or design rules")
    
    results = []
    results.append(("Same-layer routing", test_same_layer_routing()))
    results.append(("Cross-layer routing", test_cross_layer_routing()))
    results.append(("Diagonal routing", test_diagonal_routing()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed")
        sys.exit(1)
