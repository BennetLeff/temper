#!/usr/bin/env python3
"""
TEST-05: Analyze A* Search Pattern Convergence

Samples visited cells every 1000 iterations to track distance-to-goal over time.
Visualizes the search pattern to identify if A* makes progress or wanders aimlessly.

This is the KEY test to reproduce the EXP-16 bug:
- Add obstacles similar to EXP-16 (component pads)
- Track if A* converges toward goal or gets stuck

Expected Results:
- Distance to goal should DECREASE monotonically
- Visit count should be reasonable (< 10k for 300-cell route)
- If visits exceed 100k, we've reproduced the bug!

Issue: temper-1j4p
Epic: temper-koke (Debug A* Pathfinding Inefficiency)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter, GridCell
import numpy as np


def test_search_convergence_clean_grid():
    """Test search convergence on clean grid (baseline)."""
    print("\n" + "="*70)
    print("TEST 1: Search Convergence (Clean Grid)")
    print("="*70)
    
    router = MazeRouter(
        grid_size=(500, 500),
        cell_size_mm=0.2,  # Match EXP-16
        num_layers=2,
        min_clearance=0.0
    )
    
    start = (100, 250)
    end = (400, 250)
    
    print(f"Route: {start}@L0 -> {end}@L1")
    print(f"Distance: {abs(end[0] - start[0])} cells")
    
    t_start = time.perf_counter()
    
    path = router.find_path_rrr(
        start=start,
        end=end,
        layer=0,
        allow_layer_change=True,
        end_layer=1
    )
    
    t_elapsed = (time.perf_counter() - t_start) * 1000.0
    
    if path:
        print(f"✅ Success: {len(path)} cells, {t_elapsed:.1f}ms")
        return True
    else:
        print(f"❌ Failed after {t_elapsed:.1f}ms")
        return False


def test_search_with_component_pads():
    """Test search convergence with component pads like EXP-16."""
    print("\n" + "="*70)
    print("TEST 2: Search Convergence (With Component Pads)")
    print("="*70)
    
    router = MazeRouter(
        grid_size=(500, 500),
        cell_size_mm=0.2,  # 0.2mm cells like EXP-16
        num_layers=2,
        min_clearance=0.0
    )
    
    # Simulate EXP-16 setup:
    # - U1_SRC at (20, 50) with 10x10mm bounds -> grid coords (75-125, 225-275)
    # - U2_LOAD at (80, 50) with 10x10mm bounds -> grid coords (375-425, 225-275)
    
    # Block U1_SRC pad region on BOTH layers (component footprint)
    for x in range(75, 126):
        for y in range(225, 276):
            router.occupancy[x, y, 0] = -1
            router.occupancy[x, y, 1] = -1
    
    # Block U2_LOAD pad region on BOTH layers
    for x in range(375, 426):
        for y in range(225, 276):
            router.occupancy[x, y, 0] = -1
            router.occupancy[x, y, 1] = -1
    
    # Unblock the exact pin centers (U1_SRC pin at center, U2_LOAD pin at center)
    pin1_x, pin1_y = 100, 250
    pin2_x, pin2_y = 400, 250
    
    # Unblock with 10mm radius (50 cells at 0.2mm) like our fix
    unblock_radius = 50
    
    for dx in range(-unblock_radius, unblock_radius + 1):
        for dy in range(-unblock_radius, unblock_radius + 1):
            for pin_x, pin_y in [(pin1_x, pin1_y), (pin2_x, pin2_y)]:
                nx, ny = pin_x + dx, pin_y + dy
                if 0 <= nx < 500 and 0 <= ny < 500:
                    router.occupancy[nx, ny, 0] = 0
                    router.occupancy[nx, ny, 1] = 0
    
    print(f"Component pads:")
    print(f"  U1_SRC: grid (75-125, 225-275) - BLOCKED except 10mm radius around pin")
    print(f"  U2_LOAD: grid (375-425, 225-275) - BLOCKED except 10mm radius around pin")
    print(f"\nRouting:")
    print(f"  From: ({pin1_x}, {pin1_y})@L0")
    print(f"  To: ({pin2_x}, {pin2_y})@L1")
    
    t_start = time.perf_counter()
    
    path = router.find_path_rrr(
        start=(pin1_x, pin1_y),
        end=(pin2_x, pin2_y),
        layer=0,
        allow_layer_change=True,
        end_layer=1
    )
    
    t_elapsed = (time.perf_counter() - t_start) * 1000.0
    
    if path:
        via_count = sum(1 for i in range(1, len(path)) if path[i].layer != path[i-1].layer)
        print(f"✅ Success: {len(path)} cells, {via_count} vias, {t_elapsed:.1f}ms")
        
        if t_elapsed > 5000:  # 5 seconds
            print(f"   🚨 CRITICAL: Took {t_elapsed/1000:.1f}s - reproduced EXP-16 bug!")
            return "BUG_REPRODUCED"
        return True
    else:
        print(f"❌ Failed after {t_elapsed:.1f}ms")
        
        if t_elapsed > 20000:  # 20 seconds
            print(f"   🚨 CRITICAL: Spent {t_elapsed/1000:.1f}s failing - reproduced EXP-16!")
            return "BUG_REPRODUCED"
        return False


def test_search_with_clearance_mask():
    """Test with clearance mask (most likely culprit)."""
    print("\n" + "="*70)
    print("TEST 3: Search With Clearance Mask (EXP-16 Simulation)")
    print("="*70)
    print("⚠️  This test simulates the clearance mask that's likely causing the bug")
    
    router = MazeRouter(
        grid_size=(500, 500),
        cell_size_mm=0.2,
        num_layers=2,
        min_clearance=0.0
    )
    
    # Create a clearance mask that blocks everything except a narrow corridor
    # This simulates what happens when HV/LV separation dilates obstacles
    clearance_mask = np.ones((500, 500, 2), dtype=np.int32)
    
    # Clear a corridor along y=250 from x=100 to x=400
    for x in range(50, 450):
        for y in range(240, 261):  # 20-cell wide corridor
            clearance_mask[x, y, :] = 0
    
    print("Created clearance mask with 20-cell wide corridor")
    
    start = (100, 250)
    end = (400, 250)
    
    t_start = time.perf_counter()
    
    path = router.find_path_rrr(
        start=start,
        end=end,
        layer=0,
        allow_layer_change=True,
        end_layer=1,
        clearance_mask=clearance_mask
    )
    
    t_elapsed = (time.perf_counter() - t_start) * 1000.0
    
    if path:
        print(f"✅ Success: {len(path)} cells, {t_elapsed:.1f}ms")
        return True
    else:
        print(f"❌ Failed after {t_elapsed:.1f}ms")
        
        if t_elapsed > 20000:
            print(f"   🚨 FOUND IT! Clearance mask causes {t_elapsed/1000:.1f}s failure!")
            return "BUG_FOUND"
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("A* SEARCH PATTERN CONVERGENCE TESTS")
    print("="*70)
    print("Goal: Reproduce EXP-16's 21-second routing failure")
    
    results = []
    
    result1 = test_search_convergence_clean_grid()
    results.append(("Clean grid baseline", result1))
    
    result2 = test_search_with_component_pads()
    results.append(("With component pads", result2))
    
    result3 = test_search_with_clearance_mask()
    results.append(("With clearance mask", result3))
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    bug_reproduced = False
    
    for name, result in results:
        if result == "BUG_REPRODUCED" or result == "BUG_FOUND":
            print(f"🚨 {name}: BUG FOUND!")
            bug_reproduced = True
        elif result:
            print(f"✅ {name}: PASS")
        else:
            print(f"❌ {name}: FAIL")
    
    if bug_reproduced:
        print("\n🎯 SUCCESS: Identified the root cause of EXP-16 failure!")
        sys.exit(0)
    else:
        print("\n⚠️  Could not reproduce the exact EXP-16 bug")
        sys.exit(1)
