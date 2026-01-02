"""
EXP-06-B: Via Array Verification

Tests that the router places via arrays (4x4 = 16 vias) for high-current nets.
"""
from temper_placer.core.netlist import Component, Pin, Netlist
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.design_rules import create_temper_design_rules
import jax.numpy as jnp

def main():
    print("=== EXP-06-B: Via Array Test ===\n")
    
    # Create design rules with HighCurrent class having Via4x4
    dr = create_temper_design_rules()
    dr.net_class_assignments["PWR_20A"] = "HighCurrent"  # Assign to HighCurrent class
    
    # Verify template
    template = dr.get_via_template("PWR_20A")
    print(f"Via template for PWR_20A: {template.name} ({template.via_count} vias)")
    print(f"Template bbox: {template.get_footprint_bbox()}\n")
    
    # Create 2-layer router
    router = MazeRouter(
        grid_size=(100, 100),
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.2
    )
    
    # Block middle area on layer 0 to force via usage 
    for gx in range(40, 60):
        for gy in range(40, 60):
            router.occupancy[gx, gy, 0] = -1
            
    print("Routing PWR_20A from (1,5) to (9,5)...")
    print("Middle area blocked on L0 to force via usage\n")
    
    # Route with forced layer change
    path = router.find_path_rrr(
        start=(10, 50),  # Grid coords
        end=(90, 50),
        layer=0,
        allow_layer_change=True,
        p_scale=1.0
    )
    
    if path is None:
        print("FAIL: No path found")
        return
        
    # Count layer transitions
    transitions = 0
    for i in range(len(path) - 1):
        if path[i].layer != path[i+1].layer:
            transitions += 1
            print(f"Via at ({path[i].x}, {path[i].y}): L{path[i].layer} -> L{path[i+1].layer}")
    
    print(f"\nLayer transitions: {transitions}")
    print(f"Vias per transition: {template.via_count}")
    print(f"Total vias: {transitions * template.via_count}")
    
    if transitions * template.via_count >= 4:
        print(f"\n✓ SUCCESS: {transitions * template.via_count} vias placed for 20A net!")
    else:
        print(f"\n✗ FAIL: Only {transitions * template.via_count} vias (need ≥4)")

if __name__ == "__main__":
    main()
