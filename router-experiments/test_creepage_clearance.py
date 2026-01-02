#!/usr/bin/env python3
"""
Creepage/Clearance Verification Test

Tests that safety distance calculation correctly enforces HV/LV isolation
per IEC 60950-1 standards.

This is a VALIDATION test, not a full router integration test.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.safety_distances import (
    calculate_safety_distances,
    get_hv_lv_separation,
    is_high_voltage,
)


def test_voltage_classification():
    """Test that voltage classification is correct."""
    print("Test 1: Voltage Classification")
    print("-" * 60)
    
    tests = [
        (3.3, False, "3.3V logic should be LV"),
        (12.0, False, "12V should be LV"),
        (60.0, True, "60V is threshold for HV"),
        (340.0, True, "340V DC bus should be HV"),
    ]
    
    passed = 0
    for voltage, expected_hv, description in tests:
        result = is_high_voltage(voltage)
        status = "✅" if result == expected_hv else "❌"
        print(f"{status} {description}: {voltage}V → {'HV' if result else 'LV'}")
        if result == expected_hv:
            passed += 1
    
    print(f"Passed: {passed}/{len(tests)}\n")
    return passed == len(tests)


def test_temper_voltages():
    """Test safety distances for actual Temper PCB voltages."""
    print("Test 2: Temper PCB Voltage Safety Distances")
    print("-" * 60)
    
    # Temper PCB voltages
    voltages = {
        "3.3V Logic": 3.3,
        "15V Analog": 15.0,
        "340V DC Bus": 340.0,
    }
    
    # Expected distances (from IEC 60950-1)
    expected = {
        "3.3V Logic": (0.2, 0.4),    # <50V
        "15V Analog": (0.2, 0.4),     # <50V
        "340V DC Bus": (2.5, 3.0),    # 300-600V
    }
    
    passed = 0
    for name, voltage in voltages.items():
        distances = calculate_safety_distances(voltage)
        exp_clearance, exp_creepage = expected[name]
        
        clearance_ok = distances.clearance_mm == exp_clearance
        creepage_ok = distances.creepage_mm == exp_creepage
        
        if clearance_ok and creepage_ok:
            print(f"✅ {name}: clearance={distances.clearance_mm}mm, creepage={distances.creepage_mm}mm")
            passed += 1
        else:
            print(f"❌ {name}: Expected ({exp_clearance}, {exp_creepage}), got ({distances.clearance_mm}, {distances.creepage_mm})")
    
    print(f"Passed: {passed}/{len(voltages)}\n")
    return passed == len(voltages)


def test_hv_lv_separation():
    """Test HV-LV separation requirements."""
    print("Test 3: HV-LV Separation")
    print("-" * 60)
    
    test_cases = [
        # (HV voltage, LV voltage, expected separation, description)
        (340.0, 3.3, 3.0, "340V DC Bus ↔ 3.3V Logic"),
        (15.0, 3.3, 0.4, "15V Analog ↔ 3.3V Logic"),
        (340.0, 15.0, 3.0, "340V DC Bus ↔ 15V Analog"),
    ]
    
    passed = 0
    for hv_v, lv_v, expected_mm, description in test_cases:
        separation = get_hv_lv_separation(hv_v, lv_v)
        
        if abs(separation - expected_mm) < 0.01:  # Float tolerance
            print(f"✅ {description}: {separation}mm (expected {expected_mm}mm)")
            passed += 1
        else:
            print(f"❌ {description}: {separation}mm (expected {expected_mm}mm)")
    
    print(f"Passed: {passed}/{len(test_cases)}\n")
    return passed == len(test_cases)


def test_iec_compliance():
    """Test that values match IEC 60950-1 standard."""
    print("Test 4: IEC 60950-1 Compliance")
    print("-" * 60)
    
    # Test key voltage thresholds from IEC standard
    test_voltages = [
        # (voltage, expected_clearance, expected_creepage)
        (49, 0.2, 0.4),      # Below 50V threshold
        (149, 1.0, 2.0),     # 50-150V range
        (299, 2.0, 2.5),     # 150-300V range
        (599, 2.5, 3.0),     # 300-600V range
    ]
    
    passed = 0
    for voltage, exp_clearance, exp_creepage in test_voltages:
        distances = calculate_safety_distances(voltage)
        
        clearance_ok = abs(distances.clearance_mm - exp_clearance) < 0.01
        creepage_ok = abs(distances.creepage_mm - exp_creepage) < 0.01
        
        if clearance_ok and creepage_ok:
            print(f"✅ {voltage}V: {distances.clearance_mm}mm / {distances.creepage_mm}mm")
            passed += 1
        else:
            print(f"❌ {voltage}V: Expected {exp_clearance}/{exp_creepage}, got {distances.clearance_mm}/{distances.creepage_mm}")
    
    print(f"Passed: {passed}/{len(test_voltages)}\n")
    return passed == len(test_voltages)


def run_all_tests():
    """Run all creepage/clearance tests."""
    print("\n" + "=" * 60)
    print("Creepage/Clearance Verification Test Suite")
    print("IEC 60950-1 / UL 60950-1 Compliance")
    print("=" * 60 + "\n")
    
    tests = [
        test_voltage_classification,
        test_temper_voltages,
        test_hv_lv_separation,
        test_iec_compliance,
    ]
    
    results = [test() for test in tests]
    
    print("=" * 60)
    total_passed = sum(results)
    total_tests = len(results)
    
    if all(results):
        print(f"🎉 ALL TESTS PASSED ({total_passed}/{total_tests})")
        print("\n✅ Safety distance calculations are IEC 60950-1 compliant")
        print("✅ Temper PCB: 340V DC Bus requires 3.0mm creepage from 3.3V")
        print("=" * 60)
        return 0
    else:
        print(f"❌ SOME TESTS FAILED ({total_passed}/{total_tests})")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
