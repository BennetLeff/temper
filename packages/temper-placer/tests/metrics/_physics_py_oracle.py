"""Pinned Python oracle for ``metrics/physics.py`` (Wave 4, physics/metrics
cluster).

DO NOT EDIT -- THESE ARE THE REFERENCE.
=======================================
``GeometricMetrics``, ``ThermalMetrics`` and the bodies of
``_oracle_measure_geometric`` / ``_oracle_measure_thermal`` below are a
**verbatim** ``git show`` extraction from commit
``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5`` (``origin/main``, 2026-08-03) of
``temper_placer/metrics/physics.py`` -- the module as committed *before* any
Rust kernel existed for it. Only the names carry an ``_oracle_`` /
``Oracle`` prefix and the docstrings are trimmed; no arithmetic, branch, or
operator was changed. ``test_methodology_conventions.py``-style verbatim
checks are not set up for this module (no prior precedent file existed to
diff against); the extraction is a direct ``git show <sha>:<path>`` copy-out,
kept in one block below for an easy side-by-side diff against
``git show 550cab2a3:packages/temper-placer/src/temper_placer/metrics/physics.py``.

Scope
-----
Only ``measure_geometric`` and ``measure_thermal`` are pinned here.
``measure_emi`` and ``measure_routability`` are **not** ported by this
migration -- see ``packages/temper-thermal/src/geometric_metrics.rs`` and
``packages/temper-thermal/src/thermal_edges.rs``'s module docs, and the
migration's evidence note, for why (BLAS non-determinism in ``np.dot`` for
``measure_emi``'s shoelace area; pure orchestration glue for
``measure_routability``).

Numpy/CPython traps this file is measured against (see the differential
suite, ``test_physics_rust_differential.py``, for the numbers):

- **B1/B7 -- `**` is libm `pow`, not `x*x`.** ``dist_x**2 + dist_y**2``
  (both zone-violation and HV/LV-clearance arms) is CPython/numpy `pow`,
  not multiplication -- measured to disagree with `x*x` on ~0.12% of random
  f64 inputs on this platform (see ``hostmath.rs``'s own measurement, and
  ``test_physics_rust_differential.py::TestBitExactnessCatalogPins``).
- **B5 -- CPython `max`/`min` keep the FIRST argument on ties/NaN.**
  ``max(0, zone.bounds[0] - (x - hw), (x + hw) - zone.bounds[2])`` puts the
  constant ``0`` first; ``max(dx, dy, 0.0)`` in the HV/LV clearance arm puts
  a *computed* value (``dx``) first -- the NaN-survives-if-first behaviour
  is therefore exercised differently in the two call sites, and both are
  pinned separately.
- **New class (recorded by this migration) -- NEP-50 mixed float32/float64
  promotion, WITHOUT narrowing.** ``state.positions`` is always constructed
  float32 (every factory in ``core/state.py`` hardcodes
  ``dtype=np.float32``); ``widths``/``heights`` are built from a Python list
  of ``Component.bounds`` floats, which is float64. Every arithmetic
  expression in ``measure_geometric`` that combines a position with a
  width/height-derived value has an ACTUAL float64 operand somewhere in the
  chain (the width/height side), so NEP-50 promotes to float64 (widening the
  f32 position value exactly) rather than narrowing -- unlike
  ``measure_thermal`` (see below), no precision is lost beyond the position
  array's own float32 storage. The *same-dtype* position-vs-position
  subtractions (``positions[i,0] - positions[j,0]``) DO stay float32 until
  they meet a width/height value, so the subtraction+abs happens in float32
  first, then widens.
- **New class (recorded by this migration) -- NEP-50 narrowing.**
  ``measure_thermal``'s edge-distance loop has NO float64 array anchor:
  ``board.origin``/``width``/``height`` are plain Python floats (weak
  scalars under NEP-50), and ``pos[0]``/``pos[1]`` are float32 (actual).
  A weak Python float meeting an actual float32 array value ADOPTS the
  array's dtype -- so ``pos[0] - origin[0]`` and (critically)
  ``origin[0] + width - pos[0]`` compute in float32 throughout, including
  the ``origin[0] + width`` sub-term, which is computed as a *full
  double-precision* Python float add first and only narrowed to float32
  at the point it meets ``pos[0]``. Measured: for 2000 random inputs, a
  naive whole-computation-in-float64 reimplementation of this line
  disagrees with the real narrowed computation on 2000/2000 samples (see
  the differential suite). ``np.mean(edge_dists)`` over the resulting list
  of float32 scalars is *also* a float32-dtype array reduction (numpy's
  pairwise-sum algorithm run in float32 arithmetic, not float64), only
  widened to a Python float by the final ``float(...)`` cast.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class OracleGeometricMetrics:
    """Verbatim ``GeometricMetrics`` (raw geometric violations)."""

    overlap_count: int = 0
    overlap_area_mm2: float = 0.0
    zone_violation_count: int = 0
    zone_violation_max_mm: float = 0.0
    boundary_violation_count: int = 0
    min_hv_lv_clearance_mm: float = 1000.0


@dataclass
class OracleThermalMetrics:
    """Reference ``ThermalMetrics`` (thermal safety metrics)."""

    max_junction_temp_c: float = 0.0
    thermal_margin_c: float = 0.0
    thermal_margin_touch_c: float = 0.0
    thermal_margin_component_c: float = 0.0
    edge_distance_avg_mm: float = 0.0


def _oracle_measure_geometric(
    state,
    netlist,
    board,
    min_separation: float = 0.5,
) -> OracleGeometricMetrics:
    """
    Measure raw geometric violations.

    Verbatim body of ``measure_geometric`` at the pinned commit (only the
    class name changed, ``GeometricMetrics`` -> ``OracleGeometricMetrics``).
    """
    positions = np.array(state.positions)
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])
    n = len(netlist.components)

    metrics = OracleGeometricMetrics()

    # 1. Overlaps
    for i in range(n):
        hw_i, hh_i = widths[i] / 2, heights[i] / 2
        for j in range(i + 1, n):
            hw_j, hh_j = widths[j] / 2, heights[j] / 2

            dx = abs(positions[i, 0] - positions[j, 0])
            dy = abs(positions[i, 1] - positions[j, 1])

            ox = (hw_i + hw_j + min_separation) - dx
            oy = (hh_i + hh_j + min_separation) - dy

            if ox > 0 and oy > 0:
                metrics.overlap_count += 1
                metrics.overlap_area_mm2 += ox * oy

    # 2. Zone Violations
    zone_map = {z.name: z for z in board.zones}
    for i, comp in enumerate(netlist.components):
        if comp.zone and comp.zone in zone_map:
            zone = zone_map[comp.zone]
            x, y = positions[i]
            hw, hh = widths[i] / 2, heights[i] / 2

            # Check if component bounds are fully within zone
            dist_x = max(0, zone.bounds[0] - (x - hw), (x + hw) - zone.bounds[2])
            dist_y = max(0, zone.bounds[1] - (y - hh), (y + hh) - zone.bounds[3])

            if dist_x > 0 or dist_y > 0:
                metrics.zone_violation_count += 1
                metrics.zone_violation_max_mm = max(
                    metrics.zone_violation_max_mm, np.sqrt(dist_x**2 + dist_y**2)
                )

    # 3. Boundary Violations
    for i in range(n):
        x, y = positions[i]
        hw, hh = widths[i] / 2, heights[i] / 2

        if (
            x - hw < board.origin[0]
            or x + hw > board.origin[0] + board.width
            or y - hh < board.origin[1]
            or y + hh > board.origin[1] + board.height
        ):
            metrics.boundary_violation_count += 1

    # 4. HV-LV Clearance (Creepage proxy)
    hv_indices = [i for i, c in enumerate(netlist.components) if c.net_class == "HighVoltage"]
    lv_indices = [i for i, c in enumerate(netlist.components) if c.net_class != "HighVoltage"]

    if hv_indices and lv_indices:
        for i in hv_indices:
            hw_i, hh_i = widths[i] / 2, heights[i] / 2
            for j in lv_indices:
                hw_j, hh_j = widths[j] / 2, heights[j] / 2

                dx = abs(positions[i, 0] - positions[j, 0]) - hw_i - hw_j
                dy = abs(positions[i, 1] - positions[j, 1]) - hh_i - hh_j

                dist = max(dx, dy, 0.0)
                if dx > 0 and dy > 0:
                    dist = np.sqrt(dx**2 + dy**2)

                metrics.min_hv_lv_clearance_mm = min(metrics.min_hv_lv_clearance_mm, dist)

    return metrics


def _oracle_measure_thermal(
    state,
    netlist,
    board,
    power_dissipation: dict[str, float] | None = None,
    ambient_temp_c: float = 60.0,
) -> OracleThermalMetrics:
    """
    Estimate junction temperatures based on placement and power dissipation.

    Reference body of ``measure_thermal`` after the 2026-08-15 thermal
    correction (per-footprint R resolution, firmware-trip/touch/component
    margins, 60 °C worst-case ambient).  ``estimate_junction_temp`` is
    imported from the real (already Rust-delegating, Wave 4 Phase A #3)
    module -- that sub-kernel's bit-parity is independently pinned by
    ``test_thermal_rust_differential.py`` and is not re-proven here.

    NOTE: this file is content-hash pinned in ``scripts/oracle_hashes.json``.
    This edit is the deliberate re-pin of the thermal-correction PR — the
    pre-correction oracle pinned the wrong analysis constants (flat
    0.6/0.25/1.0 K/W for every component, 150 °C margin, 40 °C ambient),
    which the safety audit found defective.  The corrected reference is
    proven bit-identical to the Rust kernel by
    ``tests/metrics/test_physics_rust_differential.py``.  See
    ``docs/evidence/2026-08-15-thermal-analysis-corrections.md``.
    """
    if not power_dissipation:
        return OracleThermalMetrics(ambient_temp_c, 0.0, 0.0, 0.0, 0.0)

    from temper_placer.physics.thermal import (
        COMPONENT_MAX_C,
        FIRMWARE_TRIP_C,
        TOUCH_TEMP_C,
        _DEFAULT_RCH,
        _DEFAULT_RHA,
        _DEFAULT_RJC,
        estimate_junction_temp,
        lookup_thermal_properties,
    )

    positions = np.array(state.positions)
    max_tj = ambient_temp_c
    edge_dists = []

    for ref, power in power_dissipation.items():
        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue

        pos = positions[idx]
        # Dist to closest edge
        dx = min(pos[0] - board.origin[0], board.origin[0] + board.width - pos[0])
        dy = min(pos[1] - board.origin[1], board.origin[1] + board.height - pos[1])
        dist = min(dx, dy)
        edge_dists.append(dist)

        # Per-footprint thermal properties (Rust table), falling back to
        # the legacy flat stackup for unmatched footprints.
        comp = netlist.components[idx]
        props = lookup_thermal_properties(comp.footprint)
        if props is None:
            rjc, rch, rha = _DEFAULT_RJC, _DEFAULT_RCH, _DEFAULT_RHA
        else:
            rjc, rch, rha, _source = props

        # Estimate Tj using the refined model (copper area 0.0 here —
        # no benefit claimed, conservative direction).
        tj = estimate_junction_temp(
            power_W=power,
            edge_distance_mm=dist,
            copper_area_mm2=0.0,
            ambient_C=ambient_temp_c,
            Rjc=rjc,
            Rch=rch,
            Rha_base=rha,
        )
        max_tj = max(max_tj, tj)

    metrics = OracleThermalMetrics()
    metrics.max_junction_temp_c = max_tj
    metrics.thermal_margin_c = FIRMWARE_TRIP_C - max_tj
    metrics.thermal_margin_touch_c = TOUCH_TEMP_C - max_tj
    metrics.thermal_margin_component_c = COMPONENT_MAX_C - max_tj
    metrics.edge_distance_avg_mm = float(np.mean(edge_dists)) if edge_dists else 0.0

    return metrics
