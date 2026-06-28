"""
Safety Distance Calculation for HV/LV Isolation

Implements IEC 60950-1 and UL 60950-1 creepage and clearance requirements
for high-voltage PCB routing.

Definitions:
- Clearance: Shortest distance through air between conductors
- Creepage: Shortest distance along PCB surface between conductors

Critical for safety certification and preventing arc-over/tracking.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class SafetyDistances:
    """
    Required safety distances for a given voltage.
    
    Attributes:
        clearance_mm: Minimum air-path distance
        creepage_mm: Minimum surface-path distance
        voltage_v: Voltage rating these distances apply to
    """
    clearance_mm: float
    creepage_mm: float
    voltage_v: float


def calculate_safety_distances(
    voltage_v: float,
    pollution_degree: int = 2,
    material_group: str = "IIIa",
    overvoltage_category: int = 2,
) -> SafetyDistances:
    """
    Calculate required creepage and clearance per IEC 60950-1.
    
    Based on Table 2K (clearance) and Table 2N (creepage) from IEC 60950-1.
    Conservative values for PCB routing.
    
    Args:
        voltage_v: Working voltage (AC RMS or DC)
        pollution_degree: 1 (clean), 2 (normal), 3 (conductive)
        material_group: PCB material (IIIa for standard FR-4)
        overvoltage_category: I-IV (transient protection level)
        
    Returns:
        SafetyDistances with required clearance and creepage
        
    Notes:
        - Values are for basic insulation
        - Multiply by 2 for reinforced insulation
        - Temper (340V DC bus): clearance=2.5mm, creepage=3.0mm
    """
    # IEC 60950-1 Table 2K: Clearance (simplified, pollution degree 2)
    # Conservative values for PCB routing
    clearance_table = [
        (50, 0.2),      # <50V: 0.2mm
        (150, 1.0),     # 50-150V: 1.0mm
        (300, 2.0),     # 150-300V: 2.0mm
        (600, 2.5),     # 300-600V: 2.5mm
        (1000, 4.0),    # 600-1000V: 4.0mm
        (float('inf'), 5.0),  # >1000V: 5.0mm + calculate
    ]
    
    # IEC 60950-1 Table 2N: Creepage (Material Group IIIa, pollution degree 2)
    # CTI (Comparative Tracking Index) 175-399 for FR-4
    creepage_table = [
        (50, 0.4),      # <50V: 0.4mm
        (150, 2.0),     # 50-150V: 2.0mm
        (300, 2.5),     # 150-300V: 2.5mm
        (600, 3.0),     # 300-600V: 3.0mm
        (1000, 5.0),    # 600-1000V: 5.0mm
        (float('inf'), 8.0),  # >1000V: 8.0mm + calculate
    ]
    
    # Lookup clearance
    clearance_mm = 0.2
    for voltage_limit, distance in clearance_table:
        if voltage_v <= voltage_limit:
            clearance_mm = distance
            break
    
    # Lookup creepage
    creepage_mm = 0.4
    for voltage_limit, distance in creepage_table:
        if voltage_v <= voltage_limit:
            creepage_mm = distance
            break
    
    # Apply factors for overvoltage category and pollution degree
    # For OV category III (industrial), add 25%
    if overvoltage_category >= 3:
        clearance_mm *= 1.25
        creepage_mm *= 1.25
    
    # For pollution degree 3, double creepage
    if pollution_degree >= 3:
        creepage_mm *= 2.0
    
    return SafetyDistances(
        clearance_mm=clearance_mm,
        creepage_mm=creepage_mm,
        voltage_v=voltage_v,
    )


def get_hv_lv_separation(hv_voltage_v: float, lv_voltage_v: float) -> float:
    """
    Calculate required separation between HV and LV nets.
    
    Uses the more conservative of clearance and creepage for PCB routing.
    Routers should maintain this distance between net classes.
    
    Args:
        hv_voltage_v: High voltage net (e.g., 340V DC bus)
        lv_voltage_v: Low voltage net (e.g., 3.3V logic)
        
    Returns:
        Required separation in mm (uses creepage, more conservative)
    """
    # Calculate voltage difference
    voltage_diff = abs(hv_voltage_v - lv_voltage_v)
    
    # Get safety distances for the voltage difference
    distances = calculate_safety_distances(voltage_diff)
    
    # Use creepage (more conservative for PCB surfaces)
    return distances.creepage_mm


def is_high_voltage(voltage_v: float, threshold_v: float = 60.0) -> bool:
    """
    Determine if voltage requires special HV handling.
    
    IEC 60950-1 defines >60V as requiring safety distances.
    
    Args:
        voltage_v: Voltage to check
        threshold_v: HV threshold (default 60V per IEC standard)
        
    Returns:
        True if voltage exceeds HV threshold
    """
    return abs(voltage_v) >= threshold_v


# Example usage and validation
if __name__ == "__main__":
    print("Safety Distance Calculator (IEC 60950-1)")
    print("=" * 60)
    
    # Test cases for common Temper voltages
    test_voltages = [
        ("3.3V Logic", 3.3),
        ("15V Analog", 15.0),
        ("340V DC Bus", 340.0),
        ("400V Bulk Cap", 400.0),
    ]
    
    for name, voltage in test_voltages:
        distances = calculate_safety_distances(voltage)
        is_hv = is_high_voltage(voltage)
        
        print(f"\n{name} ({voltage}V):")
        print(f"  HV Classification: {'Yes' if is_hv else 'No'}")
        print(f"  Clearance: {distances.clearance_mm}mm")
        print(f"  Creepage: {distances.creepage_mm}mm")
    
    # Test HV-LV separation
    print(f"\n{'-' * 60}")
    print("HV-LV Separation Requirements:")
    print(f"{'-' * 60}")
    
    hv_lv_pairs = [
        ("340V DC Bus", "3.3V Logic", 340.0, 3.3),
        ("15V Analog", "3.3V Logic", 15.0, 3.3),
    ]
    
    for hv_name, lv_name, hv_v, lv_v in hv_lv_pairs:
        separation = get_hv_lv_separation(hv_v, lv_v)
        print(f"{hv_name} ↔ {lv_name}: {separation}mm")
    
    print(f"\n{'=' * 60}")
    print("✅ Safety distance calculations complete")
