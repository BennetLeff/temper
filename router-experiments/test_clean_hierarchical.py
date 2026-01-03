#!/usr/bin/env python3
"""
Clean Hierarchical Routing Test

Tests hierarchical routing WITHOUT manual pad blocking to isolate heuristic behavior.
"""

import sys
from pathlib import Path
import jax.numpy as jnp

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

def test_clean_hierarchical():
    print("="*70)
    print("CLEAN HIERARCHICAL ROUTING TEST (No Pad Blocking)")
    print("="*70)
    
    # Simple router - no design rules, no pad blocking
    router = MazeRouter(
        grid_size=(500, 500),
        cell_size_mm=0.2,
        num_layers=2,
        min_clearance=0.0
    )
    
    # Layer assignment
    assignment = LayerAssignment(
        net="TEST_NET",
        primary_layer=Layer.L1_TOP,
        allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
        vias_required=True
    )
    
    # Pin positions - simple cross-layer route
    pin_positions_world = [(20.0, 50.0), (80.0, 50.0)]
    pin_sides = [0, 1]  # Top, Bottom
    
    print("\n" + "-"*70)
    print("🔬 TEST: Hierarchical routing on CLEAN grid (no obstacles)")
    print("-"*70)
    
    result = router.route_net_hierarchical(
        net_name="TEST_NET",
        pin_positions=pin_positions_world,
        assignment=assignment,
        pin_sides=pin_sides
    )
    
    # Results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    if result and result.success:
        print(f"✅ SUCCESS: {len(result.cells)} cells, {result.via_count} vias")
        return True
    else:
        print(f"❌ FAILED")
        return False

if __name__ == "__main__":
    success = test_clean_hierarchical()
    sys.exit(0 if success else 1)
