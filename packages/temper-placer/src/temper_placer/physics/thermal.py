"""
Thermal junction temperature estimation for PCB components.

The scalar arithmetic runs in the ``temper-thermal`` Rust kernel
(``estimate_junction_temp_py``, Wave 4 Phase A #3); this module keeps
the public API and the default thermal-resistance parameters.
"""

from __future__ import annotations

import temper_thermal as _tt


def estimate_junction_temp(
    power_W: float,
    edge_distance_mm: float,
    copper_area_mm2: float = 0.0,
    ambient_C: float = 40.0,
    Rjc: float = 0.6,
    Rch: float = 0.25,
    Rha_base: float = 1.0,
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
        Rha_base: Base heatsink-to-ambient resistance (K/W). Default 1.0.
            Wakefield 694-100 extrusion family, ~75mm length, natural convection,
            de-rated for temper induction-cooker enclosure (50 °C ambient, limited
            vertical chimney).

    The arithmetic runs in the ``temper-thermal`` Rust kernel
    (``estimate_junction_temp_py``, Wave 4 Phase A #3), which mirrors
    this function's exact f64 operation order bit-for-bit (pinned by the
    differential suite ``tests/physics/test_thermal_rust_differential.py``).

    Returns:
        Estimated junction temperature in °C.
    """
    return _tt.estimate_junction_temp_py(
        power_W,
        edge_distance_mm,
        copper_area_mm2,
        ambient_C,
        Rjc,
        Rch,
        Rha_base,
    )
