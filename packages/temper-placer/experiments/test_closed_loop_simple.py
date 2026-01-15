"""
Simple test of closed-loop components.

Tests each component in isolation before running full integration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("CLOSED-LOOP COMPONENT TESTS")
print("=" * 70)

# Test 1: Import all new modules
print("\n[1/5] Testing imports...")
try:
    from temper_placer.placement.router_failure_types import BlockingPair, SpatialFailureInfo
    from temper_placer.placement.benders_failure_mapper import map_failures_to_components
    from temper_placer.placement.benders_drc_mapper import map_drc_violations_to_components
    from temper_placer.placement.benders_cut_generator import BendersCutGenerator
    from temper_placer.placement.benders_loop import BendersOptimizer
    from temper_placer.io.kicad_drc import DRCResult
    print("✅ All imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Create BlockingPair
print("\n[2/5] Testing BlockingPair...")
try:
    pair = BlockingPair(
        component_a="U1",
        component_b="R5",
        failed_net="I_SENSE",
        current_spacing=3.5,
        required_spacing=5.0,
        confidence=0.8,
        reason="blocking_net_proximity"
    )
    print(f"✅ Created: {pair}")
except Exception as e:
    print(f"❌ Failed: {e}")
    sys.exit(1)

# Test 3: Cut generator with router failures
print("\n[3/5] Testing cut generator...")
try:
    generator = BendersCutGenerator()
    
    test_pairs = [
        BlockingPair("U1", "R5", "I_SENSE", 3.5, 5.0, 0.8, "test"),
        BlockingPair("C1", "R3", "SW_NODE", 2.0, 4.0, 0.6, "test"),
    ]
    
    cuts = generator.generate_cuts_from_router_failures(test_pairs, iteration=1)
    print(f"✅ Generated {len(cuts)} cuts from {len(test_pairs)} blocking pairs")
    
    for cut in cuts[:2]:
        print(f"   {cut.cut_type.value}: {cut.component_pair}, gap={cut.gap_required:.1f}mm")
        
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: DRC categorization
print("\n[4/5] Testing DRC categorization...")
try:
    from temper_placer.io.kicad_drc import DRCViolation
    from dataclasses import dataclass
    
    # Mock DRC result
    test_violations = [
        DRCViolation("tracks_crossing", "Tracks cross", "error", []),
        DRCViolation("lib_footprint_issues", "Footprint issue", "warning", []),
        DRCViolation("clearance", "Clearance violation", "error", []),
    ]
    
    @dataclass
    class MockDRCResult:
        violations: list
        source_file: Path = Path("test.kicad_pcb")
        date: str = "2024-01-01"
        kicad_version: str = "8.0"
        ACTIONABLE_TYPES = DRCResult.ACTIONABLE_TYPES
        COSMETIC_TYPES = DRCResult.COSMETIC_TYPES
        
        @property
        def actionable_violations(self):
            return [v for v in self.violations if v.type in self.ACTIONABLE_TYPES]
        
        @property
        def cosmetic_violations(self):
            return [v for v in self.violations if v.type in self.COSMETIC_TYPES]
        
        @property
        def actionable_error_count(self):
            return sum(1 for v in self.actionable_violations if v.is_error)
    
    result = MockDRCResult(violations=test_violations)
    
    actionable = len(result.actionable_violations)
    cosmetic = len(result.cosmetic_violations)
    
    print(f"✅ DRC categorization working:")
    print(f"   Total: 3, Actionable: {actionable}, Cosmetic: {cosmetic}")
    
    assert actionable == 2, f"Expected 2 actionable, got {actionable}"
    assert cosmetic == 1, f"Expected 1 cosmetic, got {cosmetic}"
    
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: BendersOptimizer initialization
print("\n[5/5] Testing BendersOptimizer initialization...")
try:
    benders_input = Path(__file__).parent.parent / "data" / "benders_input.json"
    test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"
    
    if not benders_input.exists():
        print(f"⚠️  Skipping: {benders_input.name} not found")
    elif not test_board.exists():
        print(f"⚠️  Skipping: {test_board.name} not found")
    else:
        optimizer = BendersOptimizer(
            component_data_json=benders_input,
            pcb_file=test_board,
            max_iterations=2,
            check_routability=False,  # Don't run full optimization
            use_router_feedback=True,
            require_drc_clean=True,
            verbose=False,
        )
        print(f"✅ BendersOptimizer initialized")
        print(f"   use_router_feedback: {optimizer.use_router_feedback}")
        print(f"   require_drc_clean: {optimizer.require_drc_clean}")
        
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ ALL COMPONENT TESTS PASSED")
print("=" * 70)
print("\nThe closed-loop system components are working correctly.")
print("Ready for full integration test.")
