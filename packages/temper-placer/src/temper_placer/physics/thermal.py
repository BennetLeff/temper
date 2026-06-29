"""
Thermal junction temperature estimation for PCB components.
"""

from __future__ import annotations


def estimate_junction_temp(
    power_W: float,
    edge_distance_mm: float,
    copper_area_mm2: float = 0.0,
    ambient_C: float = 40.0,
    Rjc: float = 0.6,
    Rch: float = 0.25,
    Rha_base: float = 2.0,
) -> float:
    """
    Estimate component junction temperature from placement and environment.

    Model: Tj = Tamb + P * (Rjc + Rch + Rha)
    Rha depends on distance to board edge (heatsink mount) and copper area.

    Args:
        power_W: Power dissipation in Watts.
        edge_distance_mm: Distance to board edge in mm.
        copper_area_mm2: Area of connected copper pour in mm².
        ambient_C: Ambient temperature in °C.
        Rjc: Junction-to-case thermal resistance (K/W). Default 0.6 (TO-247).
        Rch: Case-to-heatsink thermal resistance (K/W). Default 0.25 (grease).
        Rha_base: Base heatsink-to-ambient resistance (K/W). Default 2.0.

    Returns:
        Estimated junction temperature in °C.
    """
    # 1. Edge Penalty
    # Effective Rha increases as component moves away from edge (mount point)
    # Heuristic: 0.2 K/W per mm beyond 5mm
    edge_penalty = max(0.0, edge_distance_mm - 5.0) * 0.2

    # 2. Copper Spreading Benefit
    # Larger copper pours help spread heat, reducing effective Rha
    # Heuristic: 0.1 K/W reduction per 1000mm², capped at 0.5 K/W
    copper_benefit = min(0.5, (copper_area_mm2 / 1000.0) * 0.1)

    # 3. Total Resistance
    R_total = Rjc + Rch + Rha_base + edge_penalty - copper_benefit

    # 4. Junction Temperature
    T_junction = ambient_C + (power_W * R_total)

    return float(T_junction)
