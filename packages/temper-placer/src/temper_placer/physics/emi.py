"""
Physics-based EMI Radiated Emissions prediction for PCB loops.

This module provides tools to estimate the radiated electric field strength
from switching loops, critical for FCC/CE compliance validation.

Wave 4 Phase 4: the arithmetic delegates to the Rust kernels in
`temper-thermal` (`temper_thermal.predict_radiated_emissions_py` /
`temper_thermal.check_emi_compliance_py`).  Bit-identical parity against
the pre-migration implementation is pinned by
`tests/physics/test_emi_rust_differential.py`; the R1e structural proof
is in `packages/temper-thermal/VERIFICATION.md`.
"""

from __future__ import annotations

import temper_thermal as _tt


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
    return _tt.predict_radiated_emissions_py(
        loop_area_mm2, current_peak_a, frequency_mhz, distance_m
    )


def check_emi_compliance(field_strength_dbuv: float, standard: str = "CISPR32_CLASS_B") -> bool:
    """
    Check if predicted emissions meet standard limits.

    CISPR 32 Class B (Residential) limits at 3m:
    - 30MHz to 230MHz: 40 dBµV/m
    - 230MHz to 1000MHz: 47 dBµV/m
    """
    return _tt.check_emi_compliance_py(field_strength_dbuv, standard)
