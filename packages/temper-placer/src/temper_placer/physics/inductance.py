"""
Parasitic inductance estimation for PCB current loops.

The scalar arithmetic runs in the ``temper-thermal`` Rust kernels
(``estimate_loop_inductance_py`` / ``estimate_gate_inductance_py``,
Wave 4 Phase A #4); this module keeps the public API and the physical
model documentation.
"""

from __future__ import annotations

import temper_thermal as _tt


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

    The arithmetic runs in the ``temper-thermal`` Rust kernel
    (``estimate_loop_inductance_py``, Wave 4 Phase A #4), which mirrors
    this function's exact f64 operation order bit-for-bit (pinned by the
    differential suite ``tests/physics/test_inductance_rust_differential.py``).
    """
    return _tt.estimate_loop_inductance_py(
        loop_area_mm2,
        perimeter_mm,
        layer_separation_mm,
        routing_factor,
    )


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

    The arithmetic runs in the ``temper-thermal`` Rust kernel
    (``estimate_gate_inductance_py``, Wave 4 Phase A #4), which mirrors
    this function's exact f64 operation order bit-for-bit (pinned by the
    differential suite ``tests/physics/test_inductance_rust_differential.py``).
    """
    # Assuming tight coupling (back-to-back or over ground plane)
    return _tt.estimate_gate_inductance_py(source_to_gate_dist_mm, return_dist_mm)
