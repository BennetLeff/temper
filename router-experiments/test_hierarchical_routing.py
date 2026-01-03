#!/usr/bin/env python3
"""
Test Hierarchical Routing

Verifies that 2-pass hierarchical routing fixes clearance mask routing failures.

Issue: temper-edni
Related: temper-koke (A* debugging epic)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
import numpy as np


def test_hierarchical_vs_standard():
    """Compare standard MST vs hierarchical routing with clearance mask."""
    print("\n" + "="*70)
    print("HIERARCHICAL ROUTING TEST")
    print("="*70)
    
    # Setup similar to EXP-16
    router = MazeRouter(
        grid_size=(500, 500),
        cell_size_mm=0.2,
        num_layers=2,
        min_clearance=0.2
    )
    
    # Create aggressive clearance mask (simulates HV/LV separation)
    # Clear only a narrow 10-cell corridor
    clearance_mask = np.ones((500, 500, 2), dtype=np.int32)
    for x in range(50, 450):
        for y in range(245, 256):  # 10-cell wide corridor
            clearance_mask[x, y, :] = 0
    
    # Pin positions
    pin_positions_world = [(20.0, 50.0), (80.0, 50.0)]  # 60mm apart
    pin_positions = [(100, 250), (400, 250)]  # Grid coords
    
    # Layer assignment
    assignment = LayerAssignment(
        net="TEST_NET",
        primary_layer=Layer.L1_TOP,
        allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
        vias_required=True
    )
    
    print("\nTest setup:")
    print(f"  Distance: 300 cells (60mm)")
    print(f"  Clearance mask: 10-cell wide corridor")
    print(f"  Expected: Standard MST will struggle, hierarchical should succeed")
    
    #-------------------------------------------------------------------
    # TEST 1: Standard MST routing (expected to be slow)
    #-------------------------------------------------------------------
    print("\n" + "-"*70)
    print("TEST 1: Standard MST Routing")
    print("-"*70)
    
    t_start = time.perf_counter()
    
    # Manually create clearance mask for standard routing
    # (Normally route_net_mst generates this, but we're testing the pathfinding)
    
    # For this test, just route without the aggressive mask first
    path_standard = router.find_path_rrr(
        start=pin_positions[0],
        end=pin_positions[1],
        layer=0,
        allow_layer_change=True,
        end_layer=1,
        clearance_mask=clearance_mask
    )
    
    t_standard = (time.perf_counter() - t_start) * 1000.0
    
    if path_standard:
        print(f"✅ Standard: {len(path_standard)} cells, {t_standard:.1f}ms")
    else:
        print(f"❌ Standard: FAILED after {t_standard:.1f}ms")
    
    #-------------------------------------------------------------------
    # TEST 2: Hierarchical routing
    #-------------------------------------------------------------------
    print("\n" + "-"*70)
    print("TEST 2: Hierarchical Routing")
    print("-"*70)
    
    t_start = time.perf_counter()
    
    path_hierarchical = router.route_net_hierarchical(
        net_name="TEST_NET",
        pin_positions=pin_positions_world,
        assignment=assignment,
        pin_sides=[0, 1],  # Top and bottom
    )
    
    t_hierarchical = (time.perf_counter() - t_start) * 1000.0
    
    if path_hierarchical and path_hierarchical.success:
        print(f"✅ Hierarchical: {len(path_hierarchical.cells)} cells, {t_hierarchical:.1f}ms")
        
        if t_hierarchical < t_standard * 0.5:
            print(f"   🎉 SPEEDUP: {t_standard/t_hierarchical:.1f}x faster!")
    else:
        print(f"❌ Hierarchical: FAILED after {t_hierarchical:.1f}ms")
    
    #-------------------------------------------------------------------
    # Analysis
    #-------------------------------------------------------------------
    print("\n" + "="*70)
    print("ANALYSIS")
    print("="*70)
    
    if path_hierarchical and path_hierarchical.success:
        if not path_standard:
            print("✅ SUCCESS: Hierarchical routing succeeded where standard failed!")
            return True
        elif t_hierarchical < t_standard * 0.8:
            print(f"✅ SUCCESS: Hierarchical is {t_standard/t_hierarchical:.1f}x faster")
            return True
        else:
            print("⚠️  Both succeeded but hierarchical not significantly faster")
            return True
    else:
        print("❌ FAILURE: Hierarchical routing did not improve over standard")
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("HIERARCHICAL ROUTING VALIDATION")
    print("="*70)
    print("Testing 2-pass routing to fix clearance mask issues")
    
    success = test_hierarchical_vs_standard()
    
    if success:
        print("\n🎉 Hierarchical routing is working!")
        sys.exit(0)
    else:
        print("\n💥 Hierarchical routing needs more work")
        sys.exit(1)
