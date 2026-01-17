"""
Physics-based EMI Radiated Emissions prediction for PCB loops.

This module provides tools to estimate the radiated electric field strength
from switching loops, critical for FCC/CE compliance validation.
"""

from __future__ import annotations

import math

def predict_radiated_emissions(
    loop_area_mm2: float,
    current_peak_a: float,
    frequency_mhz: float,
    distance_m: float = 3.0,
) -> float:
    """
    Predict the radiated electric field strength from a small loop antenna.
    
    Formula (Differential Mode):
    E = (1.316e-14 * A * I * f^2) / d  [Volts/meter]
    
    Where:
    - A = Loop area in mm²
    - I = Peak current in Amps
    - f = Frequency in MHz
    - d = Measurement distance in meters
    
    Args:
        loop_area_mm2: Geometric loop area.
        current_peak_a: Peak switching current.
        frequency_mhz: Switching frequency or harmonic frequency.
        distance_m: Measurement distance (default 3m for FCC/CE).
        
    Returns:
        Radiated field strength in dBµV/m.
    """
    if loop_area_mm2 <= 0 or current_peak_a <= 0 or frequency_mhz <= 0:
        return 0.0
        
    # Calculate field in V/m
    e_v_per_m = (1.316e-14 * loop_area_mm2 * current_peak_a * (frequency_mhz**2)) / distance_m
    
    # Convert to µV/m
    e_uv_per_m = e_v_per_m * 1e6
    
    # Convert to dBµV/m
    if e_uv_per_m <= 0:
        return 0.0
        
    return 20 * math.log10(e_uv_per_m)


def check_emi_compliance(
    field_strength_dbuv: float,
    standard: str = "CISPR32_CLASS_B"
) -> bool:
    """
    Check if predicted emissions meet standard limits.
    
    CISPR 32 Class B (Residential) limits at 3m:
    - 30MHz to 230MHz: 40 dBµV/m
    - 230MHz to 1000MHz: 47 dBµV/m
    """
    # Simple lookup for 30-230MHz range
    limit = 40.0
    if standard == "CISPR32_CLASS_A":
        limit = 50.0
        
    return field_strength_dbuv <= limit
