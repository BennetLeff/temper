"""
EXP-08-A: Threshold Precision Test

Tests exact current values at decision boundaries (5.0A and 10.0A) to verify:
1. No off-by-one errors
2. Floating point comparison correctness
3. Strategy selection precision

This is CRITICAL - threshold bugs cause silent routing failures.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.current_capacity_strategy import (
    CurrentCapacityStrategy,
    select_current_capacity_strategy,
)
from temper_placer.core.design_rules import DesignRules
from temper_placer.io.config_loader import NetClassRule


def create_net_class(name: str, current: float, has_zone: bool = False):
    """Create test net class with specific current rating"""
    net_class = NetClassRule(
        name=name,
        trace_width_mm=0.5,
        clearance_mm=0.2,
        max_current_rating=current,
        routing_strategy="standard" if current < 10.0 else "plane_required",
    )
    
    design_rules = DesignRules()
    design_rules.net_classes[name] = net_class
    design_rules.net_class_assignments[f"NET_{name}"] = name
    
    # Mock zone if has_zone=True
    zones = []
    if has_zone:
        from dataclasses import dataclass
        @dataclass
        class MockZone:
            name: str
            net_classes: list[str]
        zones = [MockZone(name="TEST_ZONE", net_classes=[name])]
    
    return design_rules, zones


def test_5a_threshold():
    """Test 5A threshold (STANDARD_MAZE → WIDE_TRACE_WITH_VIA_ARRAY)"""
    print("\n" + "="*80)
    print("TEST 1: 5A Threshold (Standard → Via Arrays)")
    print("="*80)
    
    test_cases = [
        (4.999, CurrentCapacityStrategy.STANDARD_MAZE, "Just below 5A"),
        (5.000, CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY, "Exactly 5A"),
        (5.001, CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY, "Just above 5A"),
    ]
    
    all_pass = True
    for current, expected_strategy, description in test_cases:
        design_rules, zones = create_net_class(f"TEST_{current}", current, has_zone=False)
        
        actual_strategy = select_current_capacity_strategy(
            f"NET_TEST_{current}",
            design_rules,
            zones
        )
        
        status = "✅" if actual_strategy == expected_strategy else "❌"
        print(f"{status} {current:.3f}A: {actual_strategy.name} ({description})")
        
        if actual_strategy != expected_strategy:
            print(f"   Expected: {expected_strategy.name}")
            print(f"   Got: {actual_strategy.name}")
            all_pass = False
    
    return all_pass


def test_10a_threshold():
    """Test 10A threshold (WIDE_TRACE → PLANE_VIA_ONLY)"""
    print("\n" + "="*80)
    print("TEST 2: 10A Threshold (Via Arrays → Plane Connection)")
    print("="*80)
    
    test_cases = [
        (9.999, False, CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY, "Just below 10A, no zone"),
        (10.000, True, CurrentCapacityStrategy.PLANE_VIA_ONLY, "Exactly 10A, with zone"),
        (10.001, True, CurrentCapacityStrategy.PLANE_VIA_ONLY, "Just above 10A, with zone"),
    ]
    
    all_pass = True
    for current, has_zone, expected_strategy, description in test_cases:
        design_rules, zones = create_net_class(f"TEST_{current}", current, has_zone=has_zone)
        
        actual_strategy = select_current_capacity_strategy(
            f"NET_TEST_{current}",
            design_rules,
            zones
        )
        
        status = "✅" if actual_strategy == expected_strategy else "❌"
        print(f"{status} {current:.3f}A (zone={has_zone}): {actual_strategy.name} ({description})")
        
        if actual_strategy != expected_strategy:
            print(f"   Expected: {expected_strategy.name}")
            print(f"   Got: {actual_strategy.name}")
            all_pass = False
    
    return all_pass


def test_zone_influence():
    """Test how zone assignment affects strategy at medium currents (5-10A)"""
    print("\n" + "="*80)
    print("TEST 3: Zone Influence on Medium Current (5-10A)")
    print("="*80)
    
    test_cases = [
        (7.0, False, CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY, "7A without zone"),
        (7.0, True, CurrentCapacityStrategy.PLANE_VIA_ONLY, "7A with zone (thermal preferred)"),
    ]
    
    all_pass = True
    for current, has_zone, expected_strategy, description in test_cases:
        design_rules, zones = create_net_class(f"TEST_{current}_{has_zone}", current, has_zone=has_zone)
        
        actual_strategy = select_current_capacity_strategy(
            f"NET_TEST_{current}_{has_zone}",
            design_rules,
            zones
        )
        
        status = "✅" if actual_strategy == expected_strategy else "❌"
        print(f"{status} {current:.1f}A (zone={has_zone}): {actual_strategy.name}")
        print(f"   {description}")
        
        if actual_strategy != expected_strategy:
            print(f"   Expected: {expected_strategy.name}")
            print(f"   Got: {actual_strategy.name}")
            all_pass = False
    
    return all_pass


def test_floating_point_edge_cases():
    """Test floating point edge cases"""
    print("\n" + "="*80)
    print("TEST 4: Floating Point Edge Cases")
    print("="*80)
    
    test_cases = [
        (4.9999999, CurrentCapacityStrategy.STANDARD_MAZE, "4.9999999A (FP precision)"),
        (5.0000001, CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY, "5.0000001A (FP precision)"),
        (9.9999999, CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY, "9.9999999A (FP precision)"),
    ]
    
    all_pass = True
    for current, expected_strategy, description in test_cases:
        design_rules, zones = create_net_class(f"TEST_FP_{current}", current, has_zone=False)
        
        actual_strategy = select_current_capacity_strategy(
            f"NET_TEST_FP_{current}",
            design_rules,
            zones
        )
        
        status = "✅" if actual_strategy == expected_strategy else "❌"
        print(f"{status} {current:.7f}A: {actual_strategy.name}")
        print(f"   {description}")
        
        if actual_strategy != expected_strategy:
            print(f"   Expected: {expected_strategy.name}")
            print(f"   Got: {actual_strategy.name}")
            all_pass = False
    
    return all_pass


def run_all_tests():
    """Run all threshold precision tests"""
    print("\n" + "█"*80)
    print("EXP-08-A: Threshold Precision Test")
    print("█"*80)
    print("\nPurpose: Verify exact threshold behavior and floating point correctness")
    print("Critical: Off-by-one errors cause silent routing failures\n")
    
    results = []
    
    # Run tests
    results.append(("Test 1: 5A threshold", test_5a_threshold()))
    results.append(("Test 2: 10A threshold", test_10a_threshold()))
    results.append(("Test 3: Zone influence", test_zone_influence()))
    results.append(("Test 4: Floating point edge cases", test_floating_point_edge_cases()))
    
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
        print("\n🎉 ALL TESTS PASSED - Threshold logic precise!")
        print("\nKey Validations:")
        print("  ✓ 5A threshold exact (no off-by-one)")
        print("  ✓ 10A threshold exact (no off-by-one)")
        print("  ✓ Zone assignment affects strategy correctly")
        print("  ✓ Floating point comparisons correct")
        print("\n⚠️  CRITICAL: No threshold bugs detected")
        return True
    else:
        print("\n❌ THRESHOLD BUGS DETECTED - CRITICAL FIX REQUIRED")
        print("   These bugs cause silent routing failures!")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
