"""
Full-field comparison instrument — compares the FDM temperature field against
an Elmer FEM field projected onto the FDM grid, producing a per-cell Delta-T map
and device T_j spot-checks with spatial disagreement attribution.

Same-objective discipline (R5): both solves use the same device power map,
ambient temperature, and board geometry — differing only in solver family
(FDM vs FEM), mesh (structured 2-D vs unstructured 3-D), and physical boundary
treatments (the independence axes).

Requirements: R3 (full-field Delta-T map), R4 (device T_j spot-checks), R5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig


# ---------------------------------------------------------------------------
# Spatial attribution regions
# ---------------------------------------------------------------------------


class AttributionRegion(Enum):
    """Regions for spatial attribution of disagreements."""

    DEVICE_FOOTPRINT = "device"
    NEAR_HEATSINK = "near_heatsink"
    FAR_FIELD = "far_field"
    COPPER_PLANE = "copper_plane"
    FR4_ONLY = "fr4_only"


# ---------------------------------------------------------------------------
# Comparison result
# ---------------------------------------------------------------------------


@dataclass
class ComparisonResult:
    """Result of comparing FDM and Elmer temperature fields.

    Attributes:
        is_clean: ``True`` when all per-cell deltas are within tolerance and
            all device T_j spot-checks agree.
        delta_map: Per-cell |T_FDM - T_Elmer| array ``(H, W)`` or ``None``.
        per_device_deltas: ``{ref: delta_C}`` for each device footprint-averaged
            T_j disagreement.
        attribution: Dict of ``AttributionRegion`` -> cell count with
            disagreement exceeding tolerance.
        max_delta_C: The largest per-cell |Delta-T| in the entire field.
        tolerance_C: The pre-registered per-cell agreement tolerance (deg-C).
        error_message: Only populated when the comparison cannot be performed.
    """

    is_clean: bool
    delta_map: np.ndarray | None = None
    per_device_deltas: dict[str, float] = field(default_factory=dict)
    attribution: dict[str, int] = field(default_factory=dict)
    max_delta_C: float = 0.0
    tolerance_C: float = 0.0
    error_message: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_fields(
    fdm_field: np.ndarray,
    elmer_field: np.ndarray,
    fdm_config: ThermalFDMConfig,
    devices: dict[str, tuple[float, float]] | None = None,
    copper_grid: np.ndarray | None = None,
    *,
    tolerance_C: float = 5.0,
) -> ComparisonResult:
    """Compare the FDM 2-D temperature field against the Elmer 3-D field
    projected onto the FDM grid.

    Produces:

    - Per-cell ``|Delta-T|`` map (``(H, W)`` array).
    - Per-device T_j spot-checks (area-averaged over the footprint).
    - Spatial disagreement attribution: which regions (device, near-heatsink,
      far-field, copper-plane) account for cells exceeding the tolerance.

    Args:
        fdm_field: ``(H, W)`` temperature field from ``solve_thermal_fdm``.
        elmer_field: ``(H, W)`` temperature field from Elmer, projected onto
            the FDM grid.
        fdm_config: Grid geometry (cell_size_mm, origin_mm, shape).
        devices: ``{ref: (x_mm, y_mm)}`` device centroids (optional).
        copper_grid: ``(H, W)`` copper fraction grid for attribution (optional).
        tolerance_C: Per-cell |Delta-T| threshold for CLEAN/VIOLATIONS.

    Returns:
        ``ComparisonResult`` with ``is_clean``, ``delta_map``, device deltas,
        and spatial attribution.
    """
    if fdm_field.shape != elmer_field.shape:
        return ComparisonResult(
            is_clean=False,
            error_message=(
                f"Field shape mismatch: FDM {fdm_field.shape} vs "
                f"Elmer {elmer_field.shape}"
            ),
        )

    H, W_val = fdm_field.shape
    delta = np.abs(fdm_field - elmer_field)
    max_delta = float(np.max(delta))
    exceeds = delta > tolerance_C
    n_exceeds = int(np.sum(exceeds))

    # --- Device T_j spot-checks (R4) ---
    per_device_deltas: dict[str, float] = {}
    cs = fdm_config.cell_size_mm
    ox, oy = fdm_config.origin_mm

    if devices:
        for dev_name, (dx_mm, dy_mm) in devices.items():
            dev_delta = _area_average(delta, dx_mm, dy_mm, cs, ox, oy)
            if dev_delta is not None:
                per_device_deltas[dev_name] = dev_delta

    # --- Spatial attribution (R3) ---
    attribution: dict[str, int] = {}

    if n_exceeds > 0:
        # Compute per-region counts for cells exceeding tolerance
        attribution = _attribute_disagreements(
            delta_map=delta,
            exceeds_mask=exceeds,
            fdm_config=fdm_config,
            devices=devices or {},
            copper_grid=copper_grid,
        )

    is_clean = n_exceeds == 0

    return ComparisonResult(
        is_clean=is_clean,
        delta_map=delta,
        per_device_deltas=per_device_deltas,
        attribution=attribution,
        max_delta_C=max_delta,
        tolerance_C=tolerance_C,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _area_average(
    field: np.ndarray,
    cx_mm: float,
    cy_mm: float,
    cell_size_mm: float,
    ox: float,
    oy: float,
    fp_mm: tuple[float, float] = (5.0, 5.0),
) -> float | None:
    """Area-average a scalar field over a rectangular footprint.

    Mirrors ``_area_average_temperature`` from ``tj_cross_check.py``.
    """
    half_w = fp_mm[0] / 2.0
    half_h = fp_mm[1] / 2.0

    col_min = int(np.floor((cx_mm - half_w - ox) / cell_size_mm))
    col_max = int(np.ceil((cx_mm + half_w - ox) / cell_size_mm))
    row_min = int(np.floor((cy_mm - half_h - oy) / cell_size_mm))
    row_max = int(np.ceil((cy_mm + half_h - oy) / cell_size_mm))

    H_val, W_val = field.shape
    col_min = max(0, col_min)
    col_max = min(W_val, col_max)
    row_min = max(0, row_min)
    row_max = min(H_val, row_max)

    if col_max <= col_min or row_max <= row_min:
        return None

    patch = field[row_min:row_max, col_min:col_max]
    return float(np.mean(patch))


def _attribute_disagreements(
    delta_map: np.ndarray,  # noqa: ARG001
    exceeds_mask: np.ndarray,
    fdm_config: ThermalFDMConfig,
    devices: dict[str, tuple[float, float]],
    copper_grid: np.ndarray | None = None,
) -> dict[str, int]:
    """Classify cells that exceed the tolerance by spatial region.

    Regions:
    - ``device``: within a device footprint.
    - ``near_heatsink``: within board_span/4 of the heatsink edge.
    - ``far_field``: away from both devices and the heatsink edge.
    - ``copper_plane``: in cells with copper fraction > 0.2.
    - ``fr4_only``: in cells with copper fraction <= 0.2.

    A cell that falls into multiple regions is assigned to the most
    specific (device > near_heatsink > copper_plane > far_field > fr4_only).
    """
    H_val = fdm_config.height_cells
    W_b = fdm_config.width_cells
    cs = fdm_config.cell_size_mm
    ox, oy = fdm_config.origin_mm
    hs = fdm_config.heatsink_edge.upper().strip()

    board_span_mm = max(H_val * cs, W_b * cs)
    near_threshold = board_span_mm / 4.0

    result: dict[str, int] = {
        "device": 0,
        "near_heatsink": 0,
        "far_field": 0,
        "copper_plane": 0,
        "fr4_only": 0,
    }

    # Precompute per-cell masks
    row_idx = np.arange(H_val, dtype=np.float64).reshape(-1, 1)
    col_idx = np.arange(W_b, dtype=np.float64).reshape(1, -1)
    cx_grid_mm = ox + (col_idx + 0.5) * cs  # (1, W)
    cy_grid_mm = oy + (row_idx + 0.5) * cs  # (H, 1)

    # Device footprint masks
    device_mask = np.zeros((H_val, W_b), dtype=bool)
    if devices:
        half_f = 2.5
        for (dx, dy) in devices.values():
            dev_cells = (
                (np.abs(cx_grid_mm - dx) <= half_f)
                & (np.abs(cy_grid_mm - dy) <= half_f)
            )
            device_mask |= dev_cells

    # Heatsink distance
    if hs == "TOP":
        hs_dist = np.abs(oy + H_val * cs - cy_grid_mm)
    elif hs == "BOTTOM":
        hs_dist = np.abs(cy_grid_mm - oy)
    elif hs == "LEFT":
        hs_dist = np.abs(cx_grid_mm - ox)
    elif hs == "RIGHT":
        hs_dist = np.abs(ox + W_b * cs - cx_grid_mm)
    else:
        hs_dist = np.full((H_val, W_b), np.inf)

    near_hs_mask = (hs_dist <= near_threshold) & (~device_mask)

    # Copper mask
    if copper_grid is not None:
        copper_mask = np.asarray(copper_grid, dtype=np.float64) > 0.2
    else:
        copper_mask = np.zeros((H_val, W_b), dtype=bool)

    # Iterate exceeding cells
    exc_rows, exc_cols = np.where(exceeds_mask)
    for r, c in zip(exc_rows, exc_cols):
        if device_mask[r, c]:
            result["device"] += 1
        elif near_hs_mask[r, c]:
            result["near_heatsink"] += 1
        elif copper_mask[r, c]:
            result["copper_plane"] += 1
        else:
            result["far_field"] += 1

        if not copper_mask[r, c]:
            result["fr4_only"] += 1

    # Remove zero entries for cleanliness
    return {k: v for k, v in result.items() if v > 0}
