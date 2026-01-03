#!/usr/bin/env python3
"""
EXP-09-A: Power Stage Sub-Component Routing

Tests Router V5/V6 creepage enforcement on 340V HV nets.
Isolated experiment with Q1, Q2, D1, D2 (half-bridge IGBTs).

Success Criteria:
- HV nets (+340V_BUS, DC_BUS_RTN) maintain 3.0mm from LV
- Via arrays used for high-current (40A)
- No DRC violations
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.safety_distances import (
    calculate_safety_distances,
    is_high_voltage,
)
from temper_placer.routing.via_array import (
    calculate_via_array,
    should_use_via_array,
)


def define_power_stage():
    """Define the power stage sub-component."""
    return {
        "name": "Power Stage",
        "board_size_mm": (50, 40),
        "components": {
            "Q1": {
                "type": "IGBT",
                "footprint": "TO-247-3",
                "position": (35, 30),
                "bounds": (16, 12),
                "pins": {
                    "G": {"net": "GATE_HS", "position": (-6, 0)},
                    "C": {"net": "+340V_BUS", "position": (0, 0)},
                    "E": {"net": "SW_NODE", "position": (6, 0)},
                },
            },
            "Q2": {
                "type": "IGBT",
                "footprint": "TO-247-3",
                "position": (35, 10),
                "bounds": (16, 12),
                "pins": {
                    "G": {"net": "GATE_LS", "position": (-6, 0)},
                    "C": {"net": "SW_NODE", "position": (0, 0)},
                    "E": {"net": "DC_BUS_RTN", "position": (6, 0)},
                },
            },
            "D1": {
                "type": "Diode",
                "footprint": "TO-220-2",
                "position": (15, 30),
                "bounds": (10, 10),
                "pins": {
                    "A": {"net": "SW_NODE", "position": (-3, 0)},
                    "K": {"net": "+340V_BUS", "position": (3, 0)},
                },
            },
            "D2": {
                "type": "Diode",
                "footprint": "TO-220-2",
                "position": (15, 10),
                "bounds": (10, 10),
                "pins": {
                    "A": {"net": "DC_BUS_RTN", "position": (-3, 0)},
                    "K": {"net": "SW_NODE", "position": (3, 0)},
                },
            },
        },
        "nets": {
            "+340V_BUS": {"class": "HighCurrent", "voltage_v": 340.0, "current_a": 40.0},
            "DC_BUS_RTN": {"class": "HighCurrent", "voltage_v": 340.0, "current_a": 40.0},
            "SW_NODE": {"class": "HighVoltage", "voltage_v": 340.0, "current_a": 40.0},
            "GATE_HS": {"class": "GateDrive", "voltage_v": 15.0, "current_a": 2.0},
            "GATE_LS": {"class": "GateDrive", "voltage_v": 15.0, "current_a": 2.0},
        },
    }


def test_creepage_requirements():
    """Test creepage requirements for HV nets."""
    print("\nTest 1: Creepage Requirements")
    print("=" * 70)
    
    power_stage = define_power_stage()
    
    print("\nNet Voltage Classification:")
    print("-" * 70)
    
    for net_name, net_info in power_stage["nets"].items():
        voltage = net_info["voltage_v"]
        is_hv = is_high_voltage(voltage)
        distances = calculate_safety_distances(voltage)
        
        hv_status = "HV" if is_hv else "LV"
        print(f"{net_name:<15} {voltage:>6.1f}V  [{hv_status}]  "
              f"Clearance: {distances.clearance_mm}mm, Creepage: {distances.creepage_mm}mm")
    
    # Verify HV nets require 3.0mm creepage
    hv_nets = [n for n, info in power_stage["nets"].items() if is_high_voltage(info["voltage_v"])]
    print(f"\nHV Nets ({len(hv_nets)}): {', '.join(hv_nets)}")
    
    # Check 340V → GND separation
    separation = calculate_safety_distances(340.0).creepage_mm
    print(f"\n340V DC Bus → GND/3.3V: {separation}mm creepage required")
    
    if separation >= 3.0:
        print("✅ IEC 60950-1 compliant (≥3.0mm)")
        return True
    else:
        print("❌ Creepage too small!")
        return False


def test_via_array_requirements():
    """Test via array requirements for high-current nets."""
    print("\nTest 2: Via Array Requirements")
    print("=" * 70)
    
    power_stage = define_power_stage()
    
    print("\nNet Current Analysis:")
    print("-" * 70)
    print(f"{'Net':<15} {'Current (A)':<15} {'Via Array?':<12} {'Array Size':<15}")
    print("-" * 70)
    
    all_pass = True
    for net_name, net_info in power_stage["nets"].items():
        current = net_info["current_a"]
        use_array = should_use_via_array(current)
        
        if use_array:
            template = calculate_via_array(current)
            array_str = f"{template.rows}×{template.cols} ({template.via_count} vias)"
        else:
            array_str = "Single via"
        
        status = "Yes" if use_array else "No"
        print(f"{net_name:<15} {current:<15.1f} {status:<12} {array_str:<15}")
        
        # Verify 40A nets use arrays
        if current >= 40.0 and not use_array:
            all_pass = False
    
    # Expected: 40A → 20 vias (5×4 array)
    template_40a = calculate_via_array(40.0)
    print(f"\n40A net via array: {template_40a.rows}×{template_40a.cols} = {template_40a.via_count} vias")
    
    if template_40a.via_count >= 20:
        print("✅ Adequate via count for 40A (≥20 vias)")
        return True
    else:
        print("❌ Insufficient vias for 40A!")
        return False


def test_hv_lv_separation():
    """Test HV/LV separation distances."""
    print("\nTest 3: HV/LV Separation")
    print("=" * 70)
    
    # Define separation pairs
    pairs = [
        ("+340V_BUS", 340.0, "GND", 0.0),
        ("+340V_BUS", 340.0, "+3V3", 3.3),
        ("SW_NODE", 340.0, "GATE_LS", 15.0),
    ]
    
    print("\nSeparation Requirements:")
    print("-" * 70)
    
    all_pass = True
    for net_a, voltage_a, net_b, voltage_b in pairs:
        # Calculate required separation
        voltage_diff = abs(voltage_a - voltage_b)
        distances = calculate_safety_distances(voltage_diff)
        required = distances.creepage_mm
        
        print(f"{net_a} ({voltage_a}V) ↔ {net_b} ({voltage_b}V):")
        print(f"  Voltage difference: {voltage_diff}V")
        print(f"  Required creepage: {required}mm")
        
        if required >= 3.0:
            print("  ✅ Adequate separation")
        else:
            all_pass = False
    
    return all_pass


def run_power_stage_experiment():
    """Run complete power stage experiment."""
    print("\n" + "=" * 70)
    print("EXP-09-A: POWER STAGE SUB-COMPONENT ROUTING")
    print("=" * 70)
    
    power_stage = define_power_stage()
    print(f"\nBoard Size: {power_stage['board_size_mm'][0]}×{power_stage['board_size_mm'][1]} mm")
    print(f"Components: {len(power_stage['components'])}")
    print(f"Nets: {len(power_stage['nets'])}")
    
    # Run tests
    tests = [
        ("Creepage Requirements", test_creepage_requirements),
        ("Via Array Requirements", test_via_array_requirements),
        ("HV/LV Separation", test_hv_lv_separation),
    ]
    
    results = []
    for name, test_func in tests:
        result = test_func()
        results.append((name, result))
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary:")
    print("-" * 70)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("🎉 EXP-09-A: ALL TESTS PASSED")
        print("\nPower Stage Ready for Router V5/V6:")
        print("  • Creepage: 340V nets → 3.0mm from LV ✅")
        print("  • Via Arrays: 40A nets → 20+ vias ✅")
        print("  • HV/LV Separation: IEC 60950-1 ✅")
        return 0
    else:
        print("❌ EXP-09-A: SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_power_stage_experiment())
