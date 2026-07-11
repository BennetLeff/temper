"""
Per-cell vertical sink field builder (issue #141).

Builds the ``h_field`` (W/(K·mm²)) for the thermal FDM solver from
per-device heatsink thermal resistances.  The sink models the
through-plane heat-removal path (junction→case→sink→ambient) that the
2-D in-plane FDM does not capture — without it all device heat is forced
to conduct in-plane to a single Dirichlet edge, over-predicting T_j by
hundreds of degrees.

Source of truth: ``DeviceThermalConfig`` from ``tj_cross_check.py`` (U11)
provides R_θCS and R_θSA — the ONE canonical repository of per-device
thermal resistances.  This module REUSES that config, not a second copy.

Public API
----------
.. code-block:: python

    from temper_placer.physics.heat_removal import (
        build_h_field,
        H_CONV_BACKGROUND,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.physics.tj_cross_check import DeviceThermalConfig

# ---------------------------------------------------------------------------
# Background natural convection coefficient
# ---------------------------------------------------------------------------

H_CONV_BACKGROUND = 10.0  # W/(m²·K)
# because: natural convection coefficient for a vertical PCB in still
# air, per standard engineering heat transfer handbooks (typical range
# 5--25 W/(m²·K)).  The midpoint is conservative and dominates only
# over bare board cells — sink-footprint cells are governed by the
# much larger device-specific conductance g_dev.

# ---------------------------------------------------------------------------
# Footprint size (must match _build_heat_source_field in thermal_fdm.py)
# ---------------------------------------------------------------------------

_DEVICE_FOOTPRINT_MM = 5.0
# because: matches the 5×5 mm device footprint used by
# _build_heat_source_field and _area_average_temperature in
# thermal_fdm.py and tj_cross_check.py — consistent cell counting
# across heat source, sink, and area-average routines.


def build_h_field(
    config: ThermalFDMConfig,
    devices: dict[str, tuple[float, float]],
    device_thermal: dict[str, DeviceThermalConfig],
) -> np.ndarray:
    """Build per-cell vertical conductance field ``(H, W)`` in ``W/(K·mm²)``.

    Composed of:
    1. **Strong sink** over each power device's footprint: per-cell
       vertical conductance ``h = g_dev / N`` where
       ``g_dev = 1 / (R_θCS + R_θSA)`` [W/K] is the total device
       vertical conductance and ``N`` is the number of footprint cells.
       When ``R_θCS + R_θSA == 0`` (board-heatsinked), the sink is
       skipped for that device (no additional vertical path needed —
       the FDM Dirichlet edge models the clamped sink directly).
    2. **Weak background** natural convection everywhere else:
       ``h_conv = H_CONV_BACKGROUND / 1e6`` [W/(mm²·K)], converted
       from W/(m²·K).

    The resulting ``h_field`` has the SAME units as the FDM diagonal
    entries (W/(K·mm²)), so ``diag += h_cell`` is dimensionally
    consistent.

    Args:
        config: FDM grid geometry (cell_size_mm, origin_mm, shape).
        devices: ``{ref: (x_mm, y_mm)}`` device centroids.
        device_thermal: ``{ref: DeviceThermalConfig}`` per-device
            datasheet R_θ with ``because`` citations (U11 source of truth).

    Returns:
        ``(height_cells, width_cells)`` float64 array in ``W/(K·mm²)``.

    Raises:
        ValueError: If a device in *devices* has no thermal config.
    """
    h = config.height_cells
    w = config.width_cells
    cs = config.cell_size_mm  # mm
    ox, oy = config.origin_mm

    # --- Background convection (weak, uniform) ---
    cell_area_m2 = (cs * 1e-3) ** 2  # m²
    h_bg = H_CONV_BACKGROUND * cell_area_m2 / (cs * cs)  # W/(m²·K) → W/(K·mm²)
    # because: h [W/(m²·K)] × cell_area_m2 [m²] / cell_area_mm2 [mm²]
    # = 10 W/(m²·K) × (cs·1e-3)² m² / cs² mm²
    # = 10 × 1e-6 [W/K/mm²] = 1e-5 W/(K·mm²)

    h_field = np.full((h, w), h_bg, dtype=np.float64)

    if not devices:
        return h_field

    if not device_thermal:
        missing = [d for d in devices if d not in device_thermal]
        if missing:
            raise ValueError(
                f"{len(missing)} device(s) have no DeviceThermalConfig: "
                f"{', '.join(sorted(missing))}. "
                f"Provide a DeviceThermalConfig with R_θCS + R_θSA "
                f"and 'because' citations."
            )
        return h_field

    # --- Device footprint sinks ---
    half_f = _DEVICE_FOOTPRINT_MM / 2.0

    for dev_name, (dx_mm, dy_mm) in devices.items():
        if dev_name not in device_thermal:
            raise ValueError(
                f"Device '{dev_name}' has no DeviceThermalConfig — "
                f"cannot compute through-plane sink. "
                f"Provide a DeviceThermalConfig with R_θCS + R_θSA "
                f"and 'because' citations, or remove the device."
            )

        dev_th = device_thermal[dev_name]
        R_vert = dev_th.R_theta_cs + dev_th.R_theta_sa

        if R_vert <= 0.0:
            # Board-heatsinked: R_θCS + R_θSA = 0 → the FDM Dirichlet
            # edge already models the clamped sink directly.
            # No additional sink needed for this device.
            continue

        g_dev = 1.0 / R_vert  # W/K — total device vertical conductance

        # Device footprint bounding box in grid coordinates
        col_min = max(0, int(np.floor((dx_mm - half_f - ox) / cs)))
        col_max = min(w, int(np.ceil((dx_mm + half_f - ox) / cs)))
        row_min = max(0, int(np.floor((dy_mm - half_f - oy) / cs)))
        row_max = min(h, int(np.ceil((dy_mm + half_f - oy) / cs)))

        n_cells = max(1, (row_max - row_min) * (col_max - col_min))
        h_cell = g_dev / (n_cells * cs * cs)  # W/K / mm² = W/(K·mm²)
        # because: g_dev [W/K] divided by total footprint area [mm²]
        # gives per-area vertical conductance matching the FDM diagonal
        # coefficient units (W/(K·mm²)).

        h_field[row_min:row_max, col_min:col_max] += h_cell

    return h_field
