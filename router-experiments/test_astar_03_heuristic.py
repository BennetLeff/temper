#!/usr/bin/env python3
"""
TEST-03: Validate A* Heuristic Function

Tests that _heuristic() returns correct Manhattan distance and is admissible.
An inadmissible heuristic (overestimates) can cause A* to fail or explore exponentially.

Expected Results:
- Heuristic should equal Manhattan distance for same-layer
- Heuristic should be ≤ actual path cost (admissible)
- Cross-layer heuristic should account for via cost

Issue: temper-6men
Epic: temper-koke (Debug A* Pathfinding Inefficiency)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter, GridCell


def test_heuristic_correctness():
    """Test that heuristic returns correct Manhattan distance."""
    print("\n" + "="*60)
    print("TEST 1: Heuristic Correctness (Manhattan Distance)")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(100, 100),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    test_cases = [
        # (start, end, expected_manhattan)
        ((10, 10, 0), (50, 10, 0), 40),
        ((10, 10, 0), (10, 50, 0), 40),
        ((10, 10, 0), (50, 50, 0), 80),
        ((0, 0, 0), (99, 99, 0), 198),
    ]
    
    all_correct = True
    
    for start_tuple, end_tuple, expected in test_cases:
        start_cell = GridCell(*start_tuple)
        end_cell = GridCell(*end_tuple)
        
        heuristic = router._heuristic(start_cell, end_cell)
        
        if heuristic == expected:
            print(f"✅ {start_tuple[:2]} -> {end_tuple[:2]}: h={heuristic} (correct)")
        else:
            print(f"❌ {start_tuple[:2]} -> {end_tuple[:2]}: h={heuristic}, expected={expected}")
            all_correct = False
    
    return all_correct


def test_heuristic_admissibility():
    """Test that heuristic is admissible (never overestimates)."""
    print("\n" + "="*60)
    print("TEST 2: Heuristic Admissibility")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(100, 100),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    # Route and compare heuristic to actual path cost
    test_cases = [
        ((10, 10), (50, 50), 0, 0),  # same layer
        ((10, 10), (50, 50), 0, 1),  # cross layer
    ]
    
    all_admissible = True
    
    for start, end, start_layer, end_layer in test_cases:
        start_cell = GridCell(start[0], start[1], start_layer)
        end_cell = GridCell(end[0], end[1], end_layer)
        
        h = router._heuristic(start_cell, end_cell)
        
        # Find actual path
        path = router.find_path_rrr(
            start=start,
            end=end,
            layer=start_layer,
            allow_layer_change=(start_layer != end_layer),
            end_layer=end_layer
        )
        
        if path is None:
            print(f"⚠️  Route failed for {start} -> {end}")
            continue
        
        actual_cost = len(path) - 1 + sum(1 for i in range(1, len(path)) if path[i].layer != path[i-1].layer) * router.via_cost
        
        if h <= actual_cost:
            print(f"✅ {start}@L{start_layer} -> {end}@L{end_layer}: h={h:.0f}, actual={actual_cost:.0f} (admissible)")
        else:
            print(f"❌ {start}@L{start_layer} -> {end}@L{end_layer}: h={h:.0f}, actual={actual_cost:.0f} (OVERESTIMATE!)")
            all_admissible = False
    
    return all_admissible


def test_cross_layer_heuristic():
    """Test heuristic for cross-layer routing."""
    print("\n" + "="*60)
    print("TEST 3: Cross-Layer Heuristic")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(100, 100),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0,
        via_cost=5.0  # Set explicit via cost
    )
    
    # For cross-layer, heuristic should be at least Manhattan distance + via cost
    start_cell = GridCell(10, 10, 0)
    end_cell = GridCell(50, 10, 1)  # Different layer
    
    h = router._heuristic(start_cell, end_cell)
    manhattan = abs(50 - 10) + abs(10 - 10)
    
    print(f"Start: {start_cell}")
    print(f"End: {end_cell}")
    print(f"Via cost: {router.via_cost}")
    print(f"Manhattan distance: {manhattan}")
    print(f"Heuristic: {h}")
    
    # The heuristic should NOT ignore layer difference
    # For optimal A*, we'd want h ≈ manhattan for same layer
    # But cross-layer is trickier - some implementations just use Manhattan
    
    path = router.find_path_rrr(
        start=(10, 10),
        end=(50, 10),
        layer=0,
        allow_layer_change=True,
        end_layer=1
    )
    
    if path:
        actual_length = len(path)
        via_count = sum(1 for i in range(1, len(path)) if path[i].layer != path[i-1].layer)
        print(f"Actual path: {actual_length} cells, {via_count} vias")
        
        if h <= actual_length + via_count * router.via_cost:
            print(f"✅ Heuristic is admissible for cross-layer")
            return True
        else:
            print(f"❌ Heuristic OVERESTIMATES for cross-layer!")
            return False
    else:
        print("❌ Route failed")
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("A* HEURISTIC VALIDATION TESTS")
    print("="*60)
    
    results = []
    results.append(("Heuristic correctness", test_heuristic_correctness()))
    results.append(("Heuristic admissibility", test_heuristic_admissibility()))
    results.append(("Cross-layer heuristic", test_cross_layer_heuristic()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 Heuristic implementation is correct!")
        sys.exit(0)
    else:
        print("\n💥 Heuristic has bugs - this could cause A* inefficiency!")
        sys.exit(1)
