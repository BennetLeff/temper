"""
EXP-07-C: Plane Connection Routing Test

Verifies that PlaneConnectionRouter correctly routes high-current nets:
1. Connects component pads to copper planes
2. Places via arrays (Via4x4) at component pads
3. No traced routing (length = 0mm)
4. Validates via positions centered on pads

This tests the CORE functionality of professional high-current routing.
"""

import sys
import tempfile
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, ViaTemplate
from temper_placer.io.config_loader import load_constraints, Zone
from temper_placer.routing.plane_connection import PlaneConnectionRouter
from temper_placer.routing.unified_router import UnifiedRouter, RoutingConfig


def test_plane_connection_basic():
    """Test 1: Basic plane connection with 2 pins"""
    print("\n" + "="*80)
    print("TEST 1: Basic Plane Connection (2-pin net, 20A)")
    print("="*80)
    
    # Setup: 100x100mm board with 2 connectors
    # AC_L net (20A) connects J1.1 to J2.1
    # Zone: AC_PLANE on F.Cu covering full board
    
    board = Board(width=100.0, height=100.0, num_layers=2)
    
    # Design rules with Via4x4 template
    design_rules = DesignRules()
    via_template = ViaTemplate(
        name="Via4x4",
        rows=4,
        cols=4,
        pitch_mm=1.0,
        via_diameter_mm=0.6,
        via_drill_mm=0.3,
    )
    design_rules.via_templates["Via4x4"] = via_template
    design_rules.net_class_assignments["AC_L"] = "HighCurrent"
    
    # Zone for AC_PLANE
    zone = Zone(
        name="AC_PLANE",
        net_classes=["HighCurrent"],
        layer="F.Cu",
        bounds=[0, 0, 100, 100],
    )
    zones = [zone]
    
    # Pin positions (J1 at left, J2 at right)
    pin_positions = [
        (10.0, 50.0),  # J1.1
        (90.0, 50.0),  # J2.1
    ]
    
    # Route using PlaneConnectionRouter
    plane_router = PlaneConnectionRouter(design_rules, cell_size_mm=0.1)
    connections = plane_router.route_net_to_plane("AC_L", pin_positions, zones)
    
    # Verify results
    print(f"Routing result: {len(connections)} connections")
    
    all_success = all(c.success for c in connections)
    if not all_success:
        failures = [c for c in connections if not c.success]
        print(f"❌ FAIL: {len(failures)} connections failed")
        for c in failures:
            print(f"   - Pin at ({c.pin_position[0]:.1f}, {c.pin_position[1]:.1f}): {c.failure_reason}")
        return False
    
    print(f"✅ All connections successful")
    
    # Check via count (should be 16 vias per pin for Via4x4)
    expected_vias_per_pin = 16
    for i, conn in enumerate(connections):
        actual_vias = len(conn.via_positions)
        print(f"   Pin {i+1} at ({conn.pin_position[0]:.1f}, {conn.pin_position[1]:.1f}): {actual_vias} vias")
        
        if actual_vias != expected_vias_per_pin:
            print(f"❌ FAIL: Expected {expected_vias_per_pin} vias, got {actual_vias}")
            return False
    
    # Check via positions (should be centered on pin)
    print(f"\n   Verifying via array centering:")
    for i, conn in enumerate(connections):
        center_x = sum(x for x, y in conn.via_positions) / len(conn.via_positions)
        center_y = sum(y for x, y in conn.via_positions) / len(conn.via_positions)
        
        offset_x = abs(center_x - conn.pin_position[0])
        offset_y = abs(center_y - conn.pin_position[1])
        
        print(f"   Pin {i+1} center offset: ({offset_x:.3f}, {offset_y:.3f}) mm")
        
        if offset_x > 0.5 or offset_y > 0.5:
            print(f"❌ FAIL: Via array not centered (offset > 0.5mm)")
            return False
    
    print(f"✅ PASS: Basic plane connection working")
    print(f"   ✓ {len(connections)} pins connected")
    print(f"   ✓ {expected_vias_per_pin} vias per pin (Via4x4)")
    print(f"   ✓ Via arrays centered on pads")
    return True


def test_unified_router_integration():
    """Test 2: Plane connection via UnifiedRouter"""
    print("\n" + "="*80)
    print("TEST 2: UnifiedRouter Plane Connection Integration")
    print("="*80)
    
    # Create config with high-current net
    config = {
        "board": {"width_mm": 100.0, "height_mm": 100.0},
        "net_classes": {"AC_L": "HighCurrent"},
        "net_class_rules": {
            "HighCurrent": {
                "trace_width_mm": 3.0,
                "clearance_mm": 1.0,
                "max_current_rating": 20.0,
                "routing_strategy": "plane_required",
                "via_template": "Via4x4",
            }
        },
        "zones": [
            {
                "name": "AC_PLANE",
                "net_classes": ["HighCurrent"],
                "layer": "F.Cu",
                "bounds": [0, 0, 100, 100],
            }
        ],
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        config_path = Path(f.name)
    
    try:
        constraints = load_constraints(config_path)
        config_path.unlink()
    except Exception as e:
        config_path.unlink()
        print(f"❌ FAIL: Config loading failed: {e}")
        return False
    
    # Create board and router
    board = Board(width=100.0, height=100.0, num_layers=2)
    
    # Build design rules from constraints
    design_rules = DesignRules()
    via_template = ViaTemplate(
        name="Via4x4",
        rows=4,
        cols=4,
        pitch_mm=1.0,
        via_diameter_mm=0.6,
        via_drill_mm=0.3,
    )
    design_rules.via_templates["Via4x4"] = via_template
    design_rules.net_class_assignments["AC_L"] = "HighCurrent"
    
    router = UnifiedRouter(board, RoutingConfig(), design_rules)
    
    # Pin positions
    pin_positions = [
        (20.0, 50.0),
        (80.0, 50.0),
    ]
    
    # Create dummy assignment (not used for plane connections)
    from temper_placer.routing.layer_assignment import LayerAssignment, Layer
    assignment = LayerAssignment(
        primary_layer=Layer.L1_TOP,
        allowed_layers=[Layer.L1_TOP],
    )
    
    # Route with zones parameter
    result = router.route_net("AC_L", pin_positions, assignment, zones=constraints.zones)
    
    # Verify results
    print(f"Routing method: {result.method}")
    print(f"Success: {result.success}")
    print(f"Via count: {result.via_count}")
    print(f"Length: {result.length:.3f} mm")
    
    if not result.success:
        print(f"❌ FAIL: Routing failed: {result.failure_reason}")
        return False
    
    if result.method != "plane_connection":
        print(f"❌ FAIL: Expected method='plane_connection', got '{result.method}'")
        return False
    
    if result.via_count != 32:  # 2 pins × 16 vias
        print(f"❌ FAIL: Expected 32 vias (2 pins × 16), got {result.via_count}")
        return False
    
    if result.length != 0.0:
        print(f"❌ FAIL: Expected length=0.0 (no traced routing), got {result.length:.3f}")
        return False
    
    print(f"✅ PASS: UnifiedRouter plane connection working")
    print(f"   ✓ Method: plane_connection")
    print(f"   ✓ Via count: 32 (2 pins × 16 vias)")
    print(f"   ✓ Length: 0.0mm (no traced routing)")
    return True


def run_all_tests():
    """Run all plane connection tests"""
    print("\n" + "█"*80)
    print("EXP-07-C: Plane Connection Routing Test")
    print("█"*80)
    print("\nPurpose: Verify PlaneConnectionRouter routes high-current nets correctly")
    
    results = []
    
    # Run tests
    results.append(("Test 1: Basic plane connection", test_plane_connection_basic()))
    results.append(("Test 2: UnifiedRouter integration", test_unified_router_integration()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nResults: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Plane connection routing verified!")
        print("\nKey Validations:")
        print("  ✓ PlaneConnectionRouter connects pads to planes")
        print("  ✓ Via4x4 arrays placed at component pads (16 vias per pin)")
        print("  ✓ Via arrays centered on pads (offset < 0.5mm)")
        print("  ✓ No traced routing (length = 0mm)")
        print("  ✓ UnifiedRouter dispatches to plane_connection method")
        return True
    else:
        print("\n❌ SOME TESTS FAILED - Review implementation")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
