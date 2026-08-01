"""Full-field MFEM vs FDM comparison instrument.

U3 of the external-MFEM corroboration plan.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ComparisonResult:
    """Result of comparing an MFEM field against the FDM field."""

    delta_map: np.ndarray
    """Per-cell |T_mfem - T_fdm| (C)."""
    device_deltas: dict[str, float]
    """Per-device T_j deltas (C)."""
    max_delta_C: float
    """Maximum per-cell delta."""
    exceeds_tolerance: bool
    """True if any cell exceeds the comparison tolerance."""
    attribution: str
    """Human-readable description of where the models diverge."""


def compare_fields(  # noqa: ARG001
    fdm_field: np.ndarray,
    mfem_field: np.ndarray,
    tolerance_C: float = 5.0,
    *,
    devices: dict[str, tuple[int, int]] | None = None,
    cell_size_mm: float = 1.0,
    heatsink_edge: str = "TOP",
) -> ComparisonResult:
    """Compare MFEM and FDM temperature fields across the full board.

    Args:
        fdm_field: ``(H, W)`` FDM temperature field in C.
        mfem_field: ``(H, W)`` MFEM temperature field projected onto the FDM grid.
        tolerance_C: per-cell comparison tolerance.
        devices: ``{name: (row, col)}`` device positions on the grid, for spot-checks.
        cell_size_mm: cell size in mm.
        heatsink_edge: which edge is the heatsink (TOP/BOTTOM/LEFT/RIGHT).

    ``cell_size_mm`` is part of this function's keyword API —
    ``mfem_gate.py:94`` passes it by name. **Do not re-prefix it with an
    underscore.** A ruff ARG001 autofix did, and every gate invocation raised
    ``TypeError``; see ``docs/evidence/2026-07-26-api-signature-drift-gate.md``.

    KNOWN GAP, not closed here: the parameter is **accepted and ignored**. The
    comparison runs entirely in grid-index space, so a caller supplying a real
    cell size gets the same answer as one supplying the 1.0 default. Any future
    metric expressed in physical units (gradient per mm, spatial correlation
    length) must actually consume it. Scoped as a follow-up rather than folded
    into a signature repair.
    """
    del cell_size_mm  # inherited unused arg (baseline debt)
    H, W = fdm_field.shape
    if mfem_field.shape != (H, W):
        raise ValueError(f"MFEM field shape {mfem_field.shape} != FDM shape {(H, W)}")

    delta_map = np.abs(mfem_field - fdm_field)
    max_delta = float(np.max(delta_map))
    exceeds = max_delta > tolerance_C

    device_deltas: dict[str, float] = {}
    if devices:
        for name, (r, c) in devices.items():
            rr = max(0, min(H - 1, int(r)))
            cc = max(0, min(W - 1, int(c)))
            device_deltas[name] = float(delta_map[rr, cc])

    attribution = _attribute_disagreement(
        delta_map, fdm_field, mfem_field, tolerance_C, heatsink_edge
    )

    return ComparisonResult(
        delta_map=delta_map,
        device_deltas=device_deltas,
        max_delta_C=max_delta,
        exceeds_tolerance=exceeds,
        attribution=attribution,
    )


def project_mfem_to_fdm(
    mfem_result: MFEMResult,
    fdm_config: ThermalFDMConfig,
) -> np.ndarray:
    """Project an MFEM nodal solution onto the FDM grid.

    Uses scipy.interpolate.griddata (nearest-neighbor, deterministic).
    Falls back to a flat reshape when node coordinates are unavailable.
    """
    from scipy.interpolate import griddata

    H = fdm_config.height_cells
    W = fdm_config.width_cells
    cs = fdm_config.cell_size_mm
    ox, oy = fdm_config.origin_mm

    if mfem_result.node_coords is not None and len(mfem_result.node_coords) > 0:
        nc = mfem_result.node_coords
        t = mfem_result.temperature
        t = np.asarray(t).ravel()
        min_len = min(len(nc), len(t))
        nc, t = nc[:min_len], t[:min_len]

        xs = np.array([ox + cs * (c + 0.5) for c in range(W)])
        ys = np.array([oy + cs * (r + 0.5) for r in range(H)])
        grid_x, grid_y = np.meshgrid(xs, ys, indexing="xy")
        grid_pts = np.column_stack([grid_x.ravel(), grid_y.ravel()])

        src_pts = nc[:, :2]
        temps = griddata(src_pts, t, grid_pts, method="nearest", rescale=False)
        return temps.reshape(H, W)

    temp = np.asarray(mfem_result.temperature).ravel()
    if len(temp) == H * W:
        return temp.reshape(H, W)

    raise ValueError(
        f"cannot project MFEM field (size {len(temp)}) onto FDM grid ({H}x{W}={H * W})"
    )


def _attribute_disagreement(
    delta_map: np.ndarray,
    fdm_field: np.ndarray,
    mfem_field: np.ndarray,
    tolerance_C: float,
    heatsink_edge: str,
) -> str:
    """Classify where the two fields disagree."""
    H, W = delta_map.shape
    exceeds_mask = delta_map > tolerance_C
    if not exceeds_mask.any():
        return "fields agree within tolerance"

    near_heatsink = np.zeros_like(exceeds_mask, dtype=bool)
    if heatsink_edge.upper() == "TOP":
        near_heatsink[-2:, :] = True
    elif heatsink_edge.upper() == "BOTTOM":
        near_heatsink[:2, :] = True

    far_field = exceeds_mask & ~near_heatsink

    parts = []
    if (exceeds_mask & near_heatsink).any():
        parts.append("near-heatsink edge")
    if far_field.any():
        parts.append("far-field")

    if not parts:
        parts.append("isolated cells")

    mfem_hotter = float(np.sum(mfem_field[exceeds_mask] - fdm_field[exceeds_mask]))
    direction = "MFEM hotter" if mfem_hotter > 0 else "FDM hotter"

    return f"disagreement in {', '.join(parts)}; {direction}"
