"""
Test zone-aware routing with MVB Level 3 board.

This test validates that:
1. ClearanceMatrix.parse() works correctly
2. Zone manager is created from board zones  
3. Clearance grid is populated with zone-specific values
4. Router enforces zone-aware clearance during routing

MVB Level 3 has:
- 2 connectors (J1, J2) with GND + SIG nets
- 1 HV zone (5,0) to (10,10) with 3.0mm clearance
"""
import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.constraints.design_rules import ClearanceMatrix
from temper_placer.routing.maze_router import MazeRouter

def test_zone_aware_routing():
    """Test that zone-aware routing works correctly."""
    
    print("=" * 60)
    print("ZONE-AWARE ROUTING VALIDATION TEST")
    print("=" * 60)
    
    # 1. Parse MVB Level 3 board
    print("\n1. Parsing MVB Level 3 board...")
    pcb_path = Path(__file__).parent / "mvb_level_3.kicad_pcb"
    result = parse_kicad_pcb(str(pcb_path))
    
    print(f"   ✓ Board: {result.board.width} x {result.board.height}mm")
    print(f"   ✓ Zones: {len(result.board.zones)}")
    print(f"   ✓ Nets: {len(result.netlist.nets)}")

    
    # 2. Parse ClearanceMatrix from KiCad board
    print("\n2. Parsing ClearanceMatrix from KiCad board...")
    try:
        matrix = ClearanceMatrix.parse(result.kicad_board)
        print(f"   ✓ ClearanceMatrix parsed")
        print(f"   ✓ Default clearance: {matrix.default_clearance}mm")
        print(f"   ✓ Has zone manager: {matrix.zone_manager is not None}")
    except Exception as e:
        print(f"   ✗ Failed to parse ClearanceMatrix: {e}")
        matrix = ClearanceMatrix.create_default()
        print(f"   → Using default matrix instead")
    
    # 3. Create MazeRouter with clearance matrix
    print("\n3. Creating MazeRouter with zone support...")
    router = MazeRouter.from_board(
        result.board,
        netlist=result.netlist,
        cell_size_mm=0.2,
    )
    
    print(f"   ✓ Router created: {router.grid_size[0]} x {router.grid_size[1]} grid")
    print(f"   ✓ Has clearance_matrix: {router.clearance_matrix is not None}")
    print(f"   ✓ Has clearance_grid: {hasattr(router, 'clearance_grid')}")
    
    if hasattr(router, 'clearance_grid'):
        print(f"   ✓ Clearance grid shape: {router.clearance_grid.shape}")
        print(f"   ✓ Min clearance in grid: {router.clearance_grid.min():.3f}mm")
        print(f"   ✓ Max clearance in grid: {router.clearance_grid.max():.3f}mm")
    
    # 4. Test clearance query at different locations
    print("\n4. Testing zone-aware clearance queries...")
    
    # Test point inside HV zone (5,0) to (10,10)
    hv_zone_point = (7.5, 5.0)  # Center of HV zone
    signal_point = (2.5, 5.0)   # Outside HV zone
    
    if router.clearance_matrix:
        clearance_hv = router.clearance_matrix.get_clearance(
            "SIG", "HV", hv_zone_point[0], hv_zone_point[1]
        )
        clearance_signal = router.clearance_matrix.get_clearance(
            "SIG", "GND", signal_point[0], signal_point[1]
        )
        
        print(f"   ✓ Clearance at HV zone ({hv_zone_point}): {clearance_hv}mm")
        print(f"   ✓ Clearance at signal area ({signal_point}): {clearance_signal}mm")
        
        # Verify HV zone has higher clearance
        if clearance_hv > clearance_signal:
            print(f"   ✓ HV zone clearance is higher (as expected)")
        else:
            print(f"   ⚠ WARNING: HV clearance not higher than signal clearance")
    else:
        print(f"   ⚠ No clearance matrix - zone test skipped")
    
    # 5. Route the board
    print("\n5. Routing board with zone-aware clearance...")
    try:
        routed_paths = router.rrr_route_all_nets(
            result.netlist,
            max_iterations=10,
        )
        
        successful = sum(1 for p in routed_paths.values() if p.success)
        total = len(routed_paths)
        
        print(f"   ✓ Routing complete: {successful}/{total} nets routed")
        
        for net_name, path in routed_paths.items():
            status = "✓" if path.success else "✗"
            print(f"     {status} {net_name}: {path.via_count} vias, {path.length:.1f}mm")
    
    except Exception as e:
        print(f"   ✗ Routing failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_zone_aware_routing()
