"""
Physics-based metrics for PCB design validation.

This module implements measurement functions that ground placement quality
in physical properties (mm, mm², degrees, etc.) rather than abstract scores.

``measure_geometric`` and ``measure_thermal``'s arithmetic run in the
``temper-thermal`` Rust kernels (``measure_geometric_py`` /
``measure_thermal_edges_py``, Wave 4); this module keeps the public API,
resolves the pyclass fields the kernels read into primitive arrays (a
one-time attribute-read boundary, not compute), and delegates. Bit-parity
against the pre-migration implementation is pinned by
``tests/metrics/test_physics_rust_differential.py`` (oracle:
``tests/metrics/_physics_py_oracle.py``).

``measure_emi`` and ``measure_routability`` are deliberately NOT ported:

- ``measure_emi``'s shoelace-area formula calls ``np.dot`` twice. On this
  platform (and in general, per numpy's own docs) ``np.dot`` for 1-D float64
  arrays dispatches to the system BLAS (Accelerate on this machine) rather
  than a fixed-order reduction -- measured: elementwise-product-then-
  pairwise-sum disagrees with ``np.dot`` on ~63% of random loops even at
  n=4 vertices, so no independent Rust reduction can reproduce it
  bit-for-bit. This is the same shape of gap that keeps
  ``Netlist.compute_eigenvector_centrality`` (LAPACK ``?syevd``) and
  ``Board``'s KiCad-transform call site in Python -- see those modules'
  docstrings. The function's remaining scalar arithmetic
  (``estimate_loop_inductance``) already delegates to Rust.
- ``measure_routability`` is orchestration glue: it calls
  ``router_v6.congestion.analyze_congestion`` and
  ``validation.metrics.compute_metrics`` (each independently classified/
  already-migrated elsewhere) and combines their outputs with a single
  ``max(0.0, 100.0 * (1.0 - x))`` clamp -- not worth its own FFI crossing,
  the same call this repo already made for the 2-line ``kicad_transform``
  scalar formula (``packages/temper-geometry``'s
  ``VERIFICATION.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import temper_thermal as _tt

from temper_placer.physics.thermal import FIRMWARE_TRIP_TS_C, thermal_resistance_for

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.state import PlacementState


@dataclass
class GeometricMetrics:
    """Raw geometric violations."""

    overlap_count: int = 0
    overlap_area_mm2: float = 0.0
    zone_violation_count: int = 0
    zone_violation_max_mm: float = 0.0
    boundary_violation_count: int = 0
    min_hv_lv_clearance_mm: float = 1000.0


@dataclass
class EMIMetrics:
    """EMI-related metrics (loop areas)."""

    gate_loop_area_mm2: float = 0.0
    power_loop_area_mm2: float = 0.0
    total_loop_area_mm2: float = 0.0


@dataclass
class ThermalMetrics:
    """Thermal safety metrics."""

    max_junction_temp_c: float = 0.0
    thermal_margin_c: float = 0.0
    edge_distance_avg_mm: float = 0.0


@dataclass
class RoutabilityMetrics:
    """Routability and congestion metrics."""

    completion_pct: float = 0.0
    overflow_cells: int = 0
    max_congestion: float = 0.0
    total_wirelength_mm: float = 0.0


@dataclass
class PhysicsReport:
    """Comprehensive physical measurement report."""

    geometric: GeometricMetrics = field(default_factory=GeometricMetrics)
    emi: EMIMetrics = field(default_factory=EMIMetrics)
    thermal: ThermalMetrics = field(default_factory=ThermalMetrics)
    routability: RoutabilityMetrics = field(default_factory=RoutabilityMetrics)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        from dataclasses import asdict

        data = asdict(self)
        return self._convert_numpy(data)

    def _convert_numpy(self, obj: Any) -> Any:
        """Recursively convert numpy types to python types for JSON."""
        if isinstance(obj, dict):
            return {k: self._convert_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy(v) for v in obj]
        elif isinstance(obj, (np.float32, np.float64, np.float16)):
            return float(obj)
        elif isinstance(obj, (np.int32, np.int64, np.int16)):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj


def measure_geometric(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    min_separation: float = 0.5,
) -> GeometricMetrics:
    """
    Measure raw geometric violations.

    The arithmetic runs in the ``temper-thermal`` Rust kernel
    (``measure_geometric_py``, Wave 4), which mirrors this function's
    exact NEP-50 float32/float64 promotion and CPython/numpy operator
    semantics bit-for-bit (pinned by the differential suite
    ``tests/metrics/test_physics_rust_differential.py``). This wrapper
    only resolves the pyclass fields the kernel reads into primitive
    arrays -- a one-time attribute-read boundary, not compute.
    """
    positions = np.asarray(state.positions)
    n = len(netlist.components)

    zone_lookup = {z.name: tuple(float(v) for v in z.bounds) for z in board.zones}
    zone_bounds = [
        zone_lookup.get(c.zone) if (c.zone and c.zone in zone_lookup) else None
        for c in netlist.components
    ]
    is_hv = [c.net_class == "HighVoltage" for c in netlist.components]

    (
        overlap_count,
        overlap_area_mm2,
        zone_violation_count,
        zone_violation_max_mm,
        boundary_violation_count,
        min_hv_lv_clearance_mm,
    ) = _tt.measure_geometric_py(
        [float(positions[i, 0]) for i in range(n)],
        [float(positions[i, 1]) for i in range(n)],
        [float(c.bounds[0]) for c in netlist.components],
        [float(c.bounds[1]) for c in netlist.components],
        float(min_separation),
        zone_bounds,
        (float(board.origin[0]), float(board.origin[1])),
        float(board.width),
        float(board.height),
        is_hv,
    )

    return GeometricMetrics(
        overlap_count=overlap_count,
        overlap_area_mm2=overlap_area_mm2,
        zone_violation_count=zone_violation_count,
        zone_violation_max_mm=zone_violation_max_mm,
        boundary_violation_count=boundary_violation_count,
        min_hv_lv_clearance_mm=min_hv_lv_clearance_mm,
    )


def measure_emi(
    state: PlacementState,
    netlist: Netlist,
    loop_refs: list[list[str]] | None = None,
) -> EMIMetrics:
    """
    Estimate loop areas and inductances based on component placement.
    """
    if not loop_refs:
        return EMIMetrics()

    from temper_placer.physics.inductance import estimate_loop_inductance

    positions = np.array(state.positions)
    metrics = EMIMetrics()

    for i, loop in enumerate(loop_refs):
        if len(loop) < 2:
            continue

        # Get vertices
        vertices = []
        for ref in loop:
            try:
                idx = netlist.get_component_index(ref)
                vertices.append(positions[idx])
            except KeyError:
                continue

        if len(vertices) < 2:
            continue

        v = np.array(vertices)

        # 1. Compute Area (Shoelace)
        if len(v) >= 3:
            area = 0.5 * np.abs(
                np.dot(v[:, 0], np.roll(v[:, 1], 1)) - np.dot(v[:, 1], np.roll(v[:, 0], 1))
            )
        else:
            area = 0.0

        # 2. Compute Perimeter
        # Manhattan-ish routing factor (1.2x) assumed internally in physics module or applied here?
        # Let's compute raw perimeter and let estimator handle factors.
        diffs = np.diff(np.vstack([v, v[0]]), axis=0)
        perimeter = np.sum(np.sqrt(np.sum(diffs**2, axis=1)))

        # 3. Estimate Inductance (nH)
        inductance = estimate_loop_inductance(loop_area_mm2=area, perimeter_mm=perimeter)

        if i == 0:  # Convention: first loop is gate drive
            metrics.gate_loop_area_mm2 = inductance  # Note: field name remains for compatibility
        elif i == 1:  # Convention: second loop is power
            metrics.power_loop_area_mm2 = inductance

        metrics.total_loop_area_mm2 += inductance

    return metrics


def measure_routability(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
) -> RoutabilityMetrics:
    """
    Measure routability indicators (post-placement estimation).
    """
    import numpy as np

    from temper_placer.router_v6.congestion import analyze_congestion

    metrics = RoutabilityMetrics()

    # Run congestion analysis
    # Use JAX positions
    pos_jax = np.array(state.positions)
    res = analyze_congestion(netlist, board, positions=pos_jax)

    metrics.max_congestion = res.max_utilization
    metrics.overflow_cells = len(res.bottlenecks)

    # total_wirelength (HPWL) via the deterministic numpy metric core
    # (replaces the removed JAX LossContext path).
    from temper_placer.validation.metrics import compute_metrics

    metrics.total_wirelength_mm = compute_metrics(state, netlist, board).total_wirelength

    # completion_pct estimation
    # This is hard without a router, but we can use (1 - overflow_ratio)
    metrics.completion_pct = max(0.0, 100.0 * (1.0 - res.overflow_ratio()))

    return metrics


def measure_thermal(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    power_dissipation: dict[str, float] | None = None,
    ambient_temp_c: float = 60.0,
) -> ThermalMetrics:
    """
    Estimate junction temperatures based on placement and power dissipation.

    **Sensor-chain model (corrected 2026-08-15):** the thermal sensor
    measures heatsink temperature Ts, not junction temperature, and the
    chain is ``Tj = Tc + P·Rjc; Tc = Ts + P·Rch; Ts = Ta + P·Rha``.
    The edge-distance computation, the per-device Ts/Tc/Tj chain, the
    ``max_tj``/``max_ts`` folds, and ``edge_distance_avg_mm`` run in the
    ``temper-thermal`` Rust kernel (``measure_thermal_edges_py``, Wave 4)
    with PER-DEVICE resistances (``physics.thermal.thermal_resistance_for``
    — datasheet values for the IKW40N120H3 IGBTs, placeholders elsewhere).
    Mirrors this function's exact NEP-50 float32-narrowing arithmetic
    bit-for-bit (pinned by
    ``tests/metrics/test_physics_rust_differential.py``).

    ``thermal_margin_c`` is the margin of the hottest heatsink temperature
    against the 80 °C firmware over-temp trip — the first active
    protection layer, at the sensor (decision doc §6.1). The junction
    limits are 125 °C (design-for) / 175 °C (absolute survival) — see
    ``physics.thermal``'s constants. The previous 150 °C margin basis was
    the datasheet's storage temperature (Tstg), not a junction limit.
    """
    if not power_dissipation:
        return ThermalMetrics(ambient_temp_c, 0.0, 0.0)

    positions = np.asarray(state.positions)

    xs: list[float] = []
    ys: list[float] = []
    powers: list[float] = []
    rjcs: list[float] = []
    rchs: list[float] = []
    rhas: list[float] = []
    for ref, power in power_dissipation.items():
        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue
        xs.append(float(positions[idx, 0]))
        ys.append(float(positions[idx, 1]))
        powers.append(float(power))
        rjc, rch, rha = thermal_resistance_for(ref)
        rjcs.append(rjc)
        rchs.append(rch)
        rhas.append(rha)

    max_tj, max_ts, edge_distance_avg_mm = _tt.measure_thermal_edges_py(
        xs,
        ys,
        powers,
        rjcs,
        rchs,
        rhas,
        (float(board.origin[0]), float(board.origin[1])),
        float(board.width),
        float(board.height),
        float(ambient_temp_c),
    )

    metrics = ThermalMetrics()
    metrics.max_junction_temp_c = max_tj
    # Margin vs the 80 °C firmware heatsink trip, in sensor (Ts) space —
    # see the decision doc §6.1 ladder (75 warn / 80 firmware / 85 latch).
    metrics.thermal_margin_c = FIRMWARE_TRIP_TS_C - max_ts
    metrics.edge_distance_avg_mm = edge_distance_avg_mm

    return metrics
