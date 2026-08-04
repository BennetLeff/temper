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

Wave 4 Phase 4: the grid arithmetic delegates to the Rust kernel
``temper_thermal.build_h_field_py`` (temper-thermal, ``heat_removal.rs``).
The dict-contract validation (missing ``DeviceThermalConfig`` raises the
original ``ValueError``s) stays here.  Bit-identical parity against the
pre-migration implementation is pinned by
``tests/physics/test_heat_removal_rust_differential.py``; the R1e
structural proof is in ``packages/temper-thermal/VERIFICATION.md``.

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
import temper_thermal as _tt

if TYPE_CHECKING:
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.physics.tj_cross_check import DeviceThermalConfig

# ---------------------------------------------------------------------------
# Background natural convection coefficient
# ---------------------------------------------------------------------------

H_CONV_BACKGROUND = 10.0  # W/(m²·K)
# source: natural convection coefficient for a vertical PCB in still
# air, per standard engineering heat transfer handbooks (typical range
# 5--25 W/(m²·K)).  The midpoint is conservative and dominates only
# over bare board cells — sink-footprint cells are governed by the
# much larger device-specific conductance g_dev.

# ---------------------------------------------------------------------------
# Footprint size (must match _build_heat_source_field in thermal_fdm.py)
# ---------------------------------------------------------------------------

_DEVICE_FOOTPRINT_MM = 5.0
# source: matches the 5×5 mm device footprint used by
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

    # --- Contract validation (unchanged from the pre-migration
    # implementation): a device without a DeviceThermalConfig raises the
    # original ValueError, in the original branch order (aggregate when
    # device_thermal is empty, per-device otherwise).  The Rust kernel
    # receives only validated devices, in dict iteration order. ---
    if not devices:
        xs: list[float] = []
        ys: list[float] = []
        r_cs: list[float] = []
        r_sa: list[float] = []
    else:
        if not device_thermal:
            missing = [d for d in devices if d not in device_thermal]
            if missing:
                raise ValueError(
                    f"{len(missing)} device(s) have no DeviceThermalConfig: "
                    f"{', '.join(sorted(missing))}. "
                    f"Provide a DeviceThermalConfig with R_θCS + R_θSA "
                    f"and 'because' citations."
                )
        for dev_name in devices:
            if dev_name not in device_thermal:
                raise ValueError(
                    f"Device '{dev_name}' has no DeviceThermalConfig — "
                    f"cannot compute through-plane sink. "
                    f"Provide a DeviceThermalConfig with R_θCS + R_θSA "
                    f"and 'because' citations, or remove the device."
                )
        xs = [devices[k][0] for k in devices]
        ys = [devices[k][1] for k in devices]
        r_cs = [device_thermal[k].R_theta_cs for k in devices]
        r_sa = [device_thermal[k].R_theta_sa for k in devices]

    raw = _tt.build_h_field_py(cs, ox, oy, h, w, xs, ys, r_cs, r_sa)
    return np.frombuffer(raw, dtype=np.float64).reshape((h, w)).copy()
