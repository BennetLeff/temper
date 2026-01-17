"""
Parasitic inductance estimation for PCB current loops.
"""

from __future__ import annotations

import math
import numpy as np


def estimate_loop_inductance(
    loop_area_mm2: float,
    perimeter_mm: float,
    layer_separation_mm: float = 0.4,
    routing_factor: float = 1.2,
) -> float:
    """
    Estimate parasitic loop inductance from area and perimeter.

    Model: L ≈ μ₀ * Area / h
    Combined with a perimeter-based term for non-ideal ground planes.

    Args:
        loop_area_mm2: Geometric area of the loop in mm².
        perimeter_mm: Perimeter of the loop in mm.
        layer_separation_mm: Distance between signal and ground plane (mm).
        routing_factor: Multiplier for non-ideal trace routing (>1.0).

    Returns:
        Estimated inductance in nH.
    """
    MU_0 = 4 * math.pi * 1e-7  # H/m (Permeability of free space)

    # 1. Area-based term (Planar loop above ground plane)
    # L_area = μ₀ * Area / h
    area_m2 = loop_area_mm2 * 1e-6
    h_m = layer_separation_mm * 1e-3
    L_area_H = (MU_0 * area_m2 / h_m) if h_m > 0 else 0
    L_area_nH = L_area_H * 1e9

    # 2. Self-inductance of conductor (simplified)
    # L_self ≈ 0.2 nH/mm for typical PCB traces
    L_self_nH = perimeter_mm * 0.2

    # 3. Combined Model with Calibration
    # For small loops (gate drive), the self-inductance and return path dominate.
    # For large loops, the area-based term dominates.
    L_total_nH = (L_area_nH * 0.5 + L_self_nH) * routing_factor

    return float(L_total_nH)


def estimate_gate_inductance(
    source_to_gate_dist_mm: float,
    return_dist_mm: float,
) -> float:
    """
    Specific estimator for gate drive loops.
    
    Args:
        source_to_gate_dist_mm: Distance from driver output to gate.
        return_dist_mm: Distance from source back to driver ground.
        
    Returns:
        Estimated inductance in nH.
    """
    # Assuming tight coupling (back-to-back or over ground plane)
    perimeter = source_to_gate_dist_mm + return_dist_mm + 5.0 # +5mm for internal
    # Rough rule of thumb: 0.8 nH/mm for PCB loops over ground plane
    return perimeter * 0.8