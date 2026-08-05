"""
Copper coverage grid builder for thermal FDM solver (issue #137).

Derives per-cell copper fraction [0, 1] from the board's actual
layer stackup: plane layers contribute solid coverage (minus keepouts),
signal layers contribute trace coverage (0 at placement time), weighted
by copper_weight (oz).  This replaces the former ``copper_grid=None``
path that silently defaulted to pure-FR4 (k_eff ~ 4.8e-4 W/K), yielding
~189,000 deg-C at the IGBTs and a false-KILL verdict.

Wave 4 Phase 4: the mask arithmetic (board area, keepout rects,
mounting-hole circles) and the per-trace ``np.minimum(1.0, grid +
cell_cov)`` accumulation delegate to the Rust kernels
``temper_thermal.copper_masks_py`` / ``copper_trace_accumulate_py``
(temper-thermal, ``copper_coverage.rs``).  The polygon rasterisation
boundary (``temper_geometry``), the trace-object introspection
(``_trace_layer_match``), the weighted-sum / fraction / clip numpy
lines, and ``check_thermal_plausibility`` stay Python.  Bit-identical
parity against the pre-migration implementation is pinned by
``tests/physics/test_copper_coverage_phase4_rust_differential.py``
(and the Wave 3 rasterise differential); the R1e structural proof is
in ``packages/temper-thermal/VERIFICATION.md``.

Public API
----------
.. code-block:: python

    from temper_placer.physics.copper_coverage import (
        copper_coverage_grid,
        check_thermal_plausibility,
        SANITY_CEILING_C,
    )

    grid = copper_coverage_grid(board, fdm_config)
    result = solve_thermal_fdm(config=fdm_config, ..., copper_grid=grid)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import temper_geometry as _tg
import temper_thermal as _tt

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig


def copper_coverage_grid(
    board: Board,
    fdm_config: ThermalFDMConfig,
    traces: list | None = None,
) -> np.ndarray:
    """Build per-cell effective copper fraction grid aligned to the FDM grid.

    Coverage model (physically defensible, derived from stackup):

    - **Plane layers** (``layer_type == "plane"``): solid copper pour over
      the board area (inside ``outline_polygon`` if present, else the
      width x height rectangle) **minus** ``keepouts`` and mounting-hole
      keepout zones.  Planes are real pours -- they dominate in-plane heat
      spreading.

    - **Signal layers** (``layer_type in {"signal", "mixed"}``): rasterised
      trace coverage if *traces* are supplied (pattern from
      ``_trace_to_cell_coverage`` in ``thermal_fdm.py``).  At placement
      time (no traces) signal layers contribute ~0.

    - **Combination**: per-cell effective fraction is the weighted mean of
      layer coverages by ``copper_weight`` (oz), normalised so the result
      is in [0, 1].  A cell over two 1 oz solid planes reads ~0.4; a cell
      inside a keepout reads low/zero.

    For the standard Temper 4-layer stackup at placement time (no traces):
    (In1.Cu 1oz + In2.Cu 1oz) / (2+1+1+1) oz = 0.40.

    At routing time with *traces*, the per-layer trace coverage is
    rasterised here so that the consumer need only pass ``copper_grid=``
    (not also ``traces=``) to ``solve_thermal_fdm``, avoiding
    double-counting.

    Args:
        board: ``Board`` with ``.layer_stackup``, ``.keepouts``
            (list of ``(x_min, y_min, x_max, y_max)`` rects),
            ``.mounting_holes``, and optionally ``.outline_polygon``.
        fdm_config: ``ThermalFDMConfig`` with ``cell_size_mm``,
            ``origin_mm``, ``height_cells``, ``width_cells``.
        traces: Optional routed trace segments (placement-time: ``None``).
            When provided, trace copper is rasterised per layer and
            accumulated into the coverage fraction.

    Returns:
        ``(height_cells, width_cells)`` float64 array in [0, 1].
    """
    from temper_placer.physics.thermal_fdm import _trace_to_cell_coverage

    h = fdm_config.height_cells
    w = fdm_config.width_cells
    ox, oy = fdm_config.origin_mm
    cs = fdm_config.cell_size_mm

    stackup = board.layer_stackup
    if stackup is None or len(stackup.layers) == 0:
        return np.zeros((h, w), dtype=np.float64)

    # --- Board area / keepout / active-area masks (Rust kernel) ---
    if board.has_polygon_outline and board.outline_polygon:
        polygon_mask = _rasterise_polygon_mask(board.outline_polygon, h, w, ox, oy, cs)
        has_polygon = True
        pm_bytes = polygon_mask.tobytes()
        board_w = board.width  # unused by the kernel in polygon mode
        board_h = board.height
    else:
        has_polygon = False
        pm_bytes = None
        board_w = board.width
        board_h = board.height

    keep_flat = [v for k in board.keepouts for v in k]
    hole_flat = [v for mh in board.mounting_holes for v in (mh.position[0], mh.position[1], mh.keepout_radius)]

    ib, ko, act = _tt.copper_masks_py(
        h, w, ox, oy, cs, board_w, board_h, has_polygon, pm_bytes, keep_flat, hole_flat
    )
    active_area = np.frombuffer(act, dtype=np.bool_).reshape((h, w))

    # --- Accumulate per-layer weighted coverage ---
    total_copper_weight = sum(ly.copper_weight for ly in stackup.layers)
    if total_copper_weight <= 0.0:
        return np.zeros((h, w), dtype=np.float64)

    weighted_sum = np.zeros((h, w), dtype=np.float64)

    for layer in stackup.layers:
        cw = layer.copper_weight
        if cw <= 0.0:
            continue

        if layer.layer_type == "plane":
            # Solid coverage wherever inside the board and not in a keepout
            weighted_sum += active_area.astype(np.float64) * cw

        elif layer.layer_type in ("signal", "mixed"):
            if traces is not None and layer.is_routable:
                # Rasterise only traces assigned to this layer
                layer_traces = [t for t in traces if _trace_layer_match(t, layer.name)]
                if layer_traces:
                    trace_grid = np.zeros((h, w), dtype=np.float64)
                    for t in layer_traces:
                        if hasattr(t, "start") and hasattr(t, "end"):
                            sx, sy = float(t.start[0]), float(t.start[1])
                            ex, ey = float(t.end[0]), float(t.end[1])
                            tw = getattr(t, "width", 0.5)
                        elif isinstance(t, (list, tuple)) and len(t) >= 4:
                            sx, sy, ex, ey = (float(t[0]), float(t[1]), float(t[2]), float(t[3]))
                            tw = float(t[4]) if len(t) >= 5 else 0.5
                        else:
                            continue
                        cell_cov = _trace_to_cell_coverage(
                            (sx, sy),
                            (ex, ey),
                            tw,
                            (ox, oy),
                            cs,
                            h,
                            w,
                        )
                        # np.minimum(1.0, trace_grid + cell_cov) with the
                        # reference's NaN propagation — Rust kernel.
                        raw = _tt.copper_trace_accumulate_py(trace_grid.tobytes(), cell_cov.tobytes())
                        trace_grid = np.frombuffer(raw, dtype=np.float64).reshape((h, w)).copy()
                    # Clip to active area
                    trace_grid *= active_area.astype(np.float64)
                    weighted_sum += trace_grid * cw

    fraction = weighted_sum / total_copper_weight
    return np.clip(fraction, 0.0, 1.0)


def _trace_layer_match(trace, layer_name: str) -> bool:
    """Check if a trace segment is on the given KiCad layer."""
    if hasattr(trace, "layer"):
        return str(trace.layer) == layer_name
    # Tuple format: (x1, y1, x2, y2, width, layer, ...)
    if isinstance(trace, (list, tuple)) and len(trace) >= 6:
        return str(trace[5]) == layer_name
    return False


def _rasterise_polygon_mask(
    polygon: list[tuple[float, float]],
    height_cells: int,
    width_cells: int,
    ox: float,
    oy: float,
    cs: float,
) -> np.ndarray:
    """Rasterise a polygon outline to a boolean grid mask.

    Uses the ray-casting (even-odd rule) algorithm: a cell centre is
    inside the polygon if a horizontal ray to +infinity crosses an odd
    number of polygon edges.  Computed in the ``temper_geometry`` Rust
    crate (``packages/temper-geometry/src/copper_coverage.rs``) with
    the exact f64 arithmetic order of the former pure-Python loop.

    Returns a ``(height_cells, width_cells)`` bool array.
    """
    raw = _tg.rasterise_polygon_mask(
        [v for pt in polygon for v in pt], height_cells, width_cells, ox, oy, cs
    )
    return np.frombuffer(raw, dtype=np.bool_).reshape((height_cells, width_cells))


# ---------------------------------------------------------------------------
# Defensive ceiling for thermal field plausibility (the durable gate from
# issue #137).  A properly heatsunk 4-layer PCB with solid inner copper
# planes should never approach these temperatures at the rated ~30 W total
# dissipation; reaching this ceiling means the conductivity field is
# effectively pure-FR4 (or otherwise garbage input).
# ---------------------------------------------------------------------------

SANITY_CEILING_C = 400.0
# source: at < 30 W dissipation on a 100x150 mm board with 2x1oz inner
# copper planes, peak IGBT T_j should stay well below 200 deg-C (typical
# TO-247 T_j_max = 150 deg-C, worst-case with bad heatsinking ~250 deg-C).
# 400 deg-C provides a safety factor > 2x above worst-case physics -- if
# the solver produces temperatures above this, the conductivity field is
# not physically representative and the result MUST be rejected to prevent
# a garbage-driven keep/kill verdict (#137).
#
# Note: this ceiling is deliberately DEFENSIVE -- it exists to catch the
# pure-FR4 (k_eff ~ 4.8e-4 W/K -> ~189,000 deg-C) garbage, not to
# substitute for proper validation.  A solver producing 405 deg-C in a
# legitimate high-power scenario would also trip this; that result should
# be investigated rather than silently accepted.


def check_thermal_plausibility(
    field: np.ndarray | None,
    ambient_C: float = 40.0,  # noqa: ARG001
    ceiling_C: float = SANITY_CEILING_C,
) -> tuple[bool, str]:
    """Check if a thermal field is physically plausible.

    Args:
        field: Temperature field ``(height_cells, width_cells)`` or None.
        ambient_C: Ambient temperature for comparison. Part of this function's
            keyword API (``battery_run.py`` passes it by name) — **do not
            re-prefix with an underscore**; a ruff ARG001 autofix did, and the
            call raised ``TypeError``. Currently **accepted and ignored**: the
            plausibility test only checks against ``ceiling_C``, so a field
            below ambient is not flagged. Scoped as a follow-up. See
            ``docs/evidence/2026-07-26-api-signature-drift-gate.md``.
        ceiling_C: Maximum plausible temperature.

    Returns:
        ``(plausible, reason)`` -- ``True`` if the field passes the check.
    """
    if field is None:
        return False, "field is None"

    peak = float(np.max(field))
    if peak > ceiling_C:
        return False, (
            f"peak temperature {peak:.1f} C exceeds sanity ceiling "
            f"{ceiling_C} C -- conductivity field may be degenerate (e.g. "
            f"pure-FR4, no copper planes; see issue #137)"
        )

    return True, f"peak {peak:.1f} C (ceiling {ceiling_C} C)"
