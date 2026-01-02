#!/usr/bin/env python3
"""
EXP-16-H: High-Current Power Bus with Hierarchical Routing

Direct test of hierarchical routing on EXP-16 scenario.
Bypasses rrr_route_all_nets and calls route_net_hierarchical directly.
"""

import sys
from pathlib import Path
import jax.numpy as jnp

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.netlist import Component, Pin
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.core.design_rules import NetClassRules
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

def test_hierarchical_exp16():
    print("="*70)
    print("EXP-16-H: Hierarchical Routing Test")
    print("="*70)
    
    # Load constraints
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)
    
    # Configure Via4x4 override
    dr.net_overrides["PWR_20A"] = NetClassRules(
        name="HighPower",
        trace_width=2.0,
        clearance=0.5,
        via_template="Via4x4"
    )
    
    # Define Components
    u1_pins = [Pin(name="OUT", number="1", net="PWR_20A", position=(0.0, 0.0))]
    u2_pins = [Pin(name="IN", number="1", net="PWR_20A", position=(0.0, 0.0))]
    
    components = [
        Component(ref="U1_SRC", footprint="TerminalBlock", bounds=(10.0, 10.0), 
                  initial_position=(20.0, 50.0), initial_side=0, pins=u1_pins),
        Component(ref="U2_LOAD", footprint="DPAK", bounds=(10.0, 10.0), 
                  initial_position=(80.0, 50.0), initial_side=1, pins=u2_pins),
    ]
    
    pos_arr = jnp.array([c.initial_position for c in components])
    
    # Router Setup
    print("\nInitializing Router...")
    router = MazeRouter(
        grid_size=(500, 500),
        cell_size_mm=0.2,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    print("Blocking pads...")
    # Block pads manually (simple version)
    for comp in components:
        cx, cy = comp.initial_position
        # Convert to grid coordinates
        gx = int(cx / router.cell_size)
        gy = int(cy / router.cell_size)
        # Block 10mm x 10mm region
        cells = int(10.0 / router.cell_size)
        for dx in range(-cells//2, cells//2):
            for dy in range(-cells//2, cells//2):
                nx, ny = gx + dx, gy + dy
                if 0 <= nx < router.grid_size[0] and 0 <= ny < router.grid_size[1]:
                    for layer in range(router.num_layers):
                        router.occupancy[nx, ny, layer] = -1
    
    # Layer assignment
    assignment = LayerAssignment(
        net="PWR_20A",
        primary_layer=Layer.L1_TOP,
        allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
        vias_required=True
    )
    
    # Pin positions in world coordinates
    pin_positions_world = [(20.0, 50.0), (80.0, 50.0)]
    pin_sides = [0, 1]  # Top, Bottom
    
    # Route using HIERARCHICAL routing
    print("\n" + "-"*70)
    print("🔬 TEST: Routing PWR_20A using HIERARCHICAL routing...")
    print("-"*70)
    
    result = router.route_net_hierarchical(
        net_name="PWR_20A",
        pin_positions=pin_positions_world,
        assignment=assignment,
        pin_sides=pin_sides,
        trace_width_mm=2.0,
        clearance_mm=0.5
    )
    
    # Results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    if result and result.success:
        print(f"✅ PWR_20A: SUCCESS")
        print(f"   Path: {len(result.cells)} cells")
        print(f"   Length: {result.length:.1f}mm")
        print(f"   Via Count: {result.via_count}")
        print(f"   Explicit Vias: {len(result.explicit_vias)}")
        
        if len(result.explicit_vias) >= 16:
            print("   🎉 Via array correctly generated (16 vias for 4x4)!")
        else:
            print(f"   ⚠️  Expected 16 vias, got {len(result.explicit_vias)}")
        
        return True
    else:
        reason = result.failure_reason if result else "No result returned"
        print(f"❌ PWR_20A: FAILED")
        print(f"   Reason: {reason}")
        return False

if __name__ == "__main__":
    success = test_hierarchical_exp16()
    sys.exit(0 if success else 1)
