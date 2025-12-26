"""
Physics-based inductance estimation for PCB loops.

This module provides tools to estimate parasitic inductance from 
geometric loop areas, critical for EMI and switching noise analysis.
"""

from __future__ import annotations

import math

def estimate_loop_inductance(
    loop_area_mm2: float,
    layer_separation_mm: float = 0.4,
    routing_factor: float = 1.3,
) -> float:
    """
    Estimate loop inductance from area for a planar loop above a ground plane.

    Physics:
    L ≈ μ₀ × Area / h
    
    Where:
    - μ₀ = 4π × 10⁻⁷ H/m (permeability of free space)
    - Area = loop area in m²
    - h = height above ground plane (layer separation) in m

    This formula is a first-order approximation for small h relative to loop diameter.
    
    Args:
        loop_area_mm2: Geometric loop area in mm².
        layer_separation_mm: Signal-to-return layer distance in mm (default 0.4 for 4-layer 1.6mm PCB).
        routing_factor: Multiplier for non-ideal routing (>1.0). Accounts for vias and non-uniformity.

    Returns:
        Estimated inductance in nH.
    """
    MU_0 = 4 * math.pi * 1e-7  # H/m

    # Convert to SI units (meters)
    area_m2 = loop_area_mm2 * 1e-6
    h_m = layer_separation_mm * 1e-3

    # Calculate Inductance in Henries
    # L = μ₀ * Area / h
    L_H = MU_0 * area_m2 / h_m
    
    # Convert to nanoHenries
    L_nH = L_H * 1e9

    # Apply empirical routing factor
    return L_nH * routing_factor


def estimate_partial_inductance(
    length_mm: float,
    width_mm: float,
    thickness_mm: float = 0.035,
) -> float:
    """
    Estimate the partial self-inductance of a rectangular trace.
    
    Formula (Rosa):
    L = 0.2 × l × [ln(2l / (w + t)) + 0.5 + 0.2235 × (w + t) / l]
    
    Args:
        length_mm: Trace length in mm.
        width_mm: Trace width in mm.
        thickness_mm: Copper thickness in mm (default 35um = 1oz).
        
    Returns:
        Inductance in nH.
    """
    l = length_mm
    w = width_mm
    t = thickness_mm
    
    if l <= 0:
        return 0.0
        
    # L_nH = 0.2 * l * (log(2*l / (w+t)) + 0.5)
    # (Simplified version of Rosa's formula)
    return 0.2 * l * (math.log(2 * l / (w + t)) + 0.5)
