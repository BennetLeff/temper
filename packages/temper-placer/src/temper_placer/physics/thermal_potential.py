"""
Thermal potential field construction for power-device anchoring.

Constructs a continuous scalar potential phi(x, y) over the board surface
before gradient-based placement begins.  Power devices are then greedily
anchored at field minima.  This moves thermal awareness from Phase 3
(epoch 3000) to Phase 0 --- before any optimizer iteration.

Five field components superpose at each grid cell:
    phi(x, y) = w_edge * phi_edge(x, y)
              + w_copper * phi_copper(x, y)
              + w_coupling * phi_coupling(x, y)
              + w_exclusion * phi_exclusion(x, y)
              + w_convection * phi_convection(x, y)

Arrays are numpy float64 throughout, for compatibility with the existing
gradient-based pipeline.

**Wave 4 Phase 4 (physics-gated migration).**  Every field kernel, the
grid builder, the greedy two-pass anchor search and the uniqueness
enforcement now delegate to ``temper_thermal`` (Rust,
``packages/temper-thermal/src/thermal_potential.rs``).  The public API,
the duck-typed copper-zone extraction, the ``logging`` behaviour and the
safety gates are unchanged, and parity is pinned bit-exactly by
``tests/physics/test_thermal_potential_rust_differential.py`` against the
verbatim pre-migration oracle.  The weighted superposition itself stays
in numpy so its broadcasting semantics (including the deliberate
``phi_copper`` 50x50 shape constraint) remain numpy's own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import temper_thermal as _tt

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

logger = logging.getLogger(__name__)

# Edge names, resolved to the integer codes the Rust kernels take.  The
# `.upper().strip()` normalisation stays on this side so CPython's exact
# Unicode case-folding and whitespace semantics are never reimplemented.
_EDGE_CODES: dict[str, int] = {"TOP": 0, "BOTTOM": 1, "LEFT": 2, "RIGHT": 3}
_UNKNOWN_EDGE_CODE = 4


def _edge_code(edge: str) -> int:
    return _EDGE_CODES.get(edge.upper().strip(), _UNKNOWN_EDGE_CODE)


def _f64_bytes(array: Array) -> bytes:
    return np.ascontiguousarray(array, dtype=np.float64).tobytes()


def _as_grid(raw: bytes, shape) -> Array:
    return np.frombuffer(raw, dtype=np.float64).reshape(shape).copy()


def _zone_bounds(copper_zones: list | None) -> list[tuple[float, float, float, float]]:
    """Duck-typed copper-zone extraction, verbatim from the reference.

    A zone contributes its ``.bounds`` when it has one, else the bounding
    box of a truthy ``.polygon``; anything else is skipped.  The *count*
    of the original list still matters (a non-empty list of unusable
    zones does NOT take the uniform branch), so callers pass both.
    """
    out: list[tuple[float, float, float, float]] = []
    if not copper_zones:
        return out
    for zone in copper_zones:
        if hasattr(zone, "bounds"):
            zx0, zy0, zx1, zy1 = zone.bounds
        elif hasattr(zone, "polygon") and zone.polygon:
            # approximate polygon by bounding box
            xs = [p[0] for p in zone.polygon]
            ys = [p[1] for p in zone.polygon]
            zx0, zy0, zx1, zy1 = min(xs), min(ys), max(xs), max(ys)
        else:
            continue
        out.append((float(zx0), float(zy0), float(zx1), float(zy1)))
    return out


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ThermalPotentialConfig:
    """Configuration for the thermal potential field components.

    Each weight defaults to 1.0; set to 0.0 to disable a component.
    """

    edge_weight: float = 1.0
    copper_weight: float = 1.0
    coupling_weight: float = 1.0
    exclusion_weight: float = 1.0
    convection_weight: float = 1.0

    # Decay length for edge-proximity exponential (mm)
    edge_decay_length_mm: float = 10.0

    # Exclusion radius around anchored power devices (mm)
    thermal_exclusion_radius_mm: float = 10.0
    # Exclusion barrier height (large constant to create a pseudo-hard wall)
    exclusion_barrier_height: float = 1e6
    # Steepness of the sigmoid exclusion barrier
    exclusion_steepness: float = 20.0

    # Grid resolution (N x N) for the discretized potential field
    grid_resolution: int = 50


def _config_tuple(config: ThermalPotentialConfig) -> tuple[float, ...]:
    """The nine scalars the Rust kernels read, in boundary order."""
    return (
        config.edge_weight,
        config.copper_weight,
        config.coupling_weight,
        config.exclusion_weight,
        config.convection_weight,
        config.edge_decay_length_mm,
        config.thermal_exclusion_radius_mm,
        config.exclusion_barrier_height,
        config.exclusion_steepness,
    )


# ---------------------------------------------------------------------------
# Field component functions
# Each returns a scalar potential array of shape (grid_resolution, grid_resolution)
# ---------------------------------------------------------------------------


def _validate_edge(edge: str, _board_bounds: tuple[float, float, float, float]) -> None:
    """Validate that the edge name is known. Logs warning on unknown edge."""
    valid = {"TOP", "BOTTOM", "LEFT", "RIGHT"}
    if edge.upper() not in valid:
        logger.warning(
            "Unknown heatsink edge '%s' --- valid edges: %s. phi_edge will default to zero.",
            edge,
            sorted(valid),
        )


def phi_edge(
    x_grid: Array,
    y_grid: Array,
    board_bounds: tuple[float, float, float, float],
    edge: str,
    decay_length_mm: float = 10.0,
) -> Array:
    """Distance-weighted potential from the declared heatsink edge.

    phi_edge(x, y) = 1 - exp(-d_edge(x, y) / lambda)
    where lambda = decay_length_mm, d_edge is distance to the edge.

    This yields phi_edge = 0 at the edge (minimum = best thermal position)
    and phi_edge -> 1 far from the edge (maximum = worst position).
    """
    _validate_edge(edge, board_bounds)
    raw = _tt.thermal_potential_phi_edge_py(
        _f64_bytes(x_grid),
        _f64_bytes(y_grid),
        *board_bounds,
        _edge_code(edge),
        decay_length_mm,
    )
    return _as_grid(raw, np.shape(x_grid))


def phi_copper(
    x_grid: Array,
    y_grid: Array,
    board_bounds: tuple[float, float, float, float],
    _layer_stackup: Array | None = None,
    copper_zones: list | None = None,
) -> Array:
    """Effective thermal conductivity of the FR4 + Cu stackup.

    Without copper zone definitions, returns a uniform conductivity field.
    With zones, lower potential in high-copper-fill regions where heat
    spreading is better.
    """
    del x_grid, y_grid  # uniform when no zone data
    zone_count = 0 if copper_zones is None else len(copper_zones)
    rows, cols, raw = _tt.thermal_potential_phi_copper_py(
        *board_bounds, zone_count, _zone_bounds(copper_zones)
    )
    return _as_grid(raw, (rows, cols))


def phi_coupling(
    x_grid: Array,
    y_grid: Array,
    device_positions: list[tuple[float, float]],
    device_powers: list[float],
    sigma_factor: float = 50.0,
) -> Array:
    """Superpose Gaussian kernels from each power device.

    phi_coupling(x, y) = sum_j P_j * exp(-||(x,y) - pos_j||^2 / (2 * sigma_j^2))
    where sigma_j = sqrt(P_j) * sigma_factor

    If no device positions are provided, returns a zero field.
    """
    pairs = [
        ((float(pos[0]), float(pos[1])), float(power))
        for pos, power in zip(device_positions, device_powers)
    ]
    raw = _tt.thermal_potential_phi_coupling_py(
        _f64_bytes(x_grid), _f64_bytes(y_grid), pairs, sigma_factor
    )
    return _as_grid(raw, np.shape(x_grid))


def phi_exclusion(
    x_grid: Array,
    y_grid: Array,
    anchor_positions: list[tuple[float, float]],
    radius_mm: float = 10.0,
    barrier_height: float = 1e6,
    steepness: float = 20.0,
) -> Array:
    """Sigmoid barrier around each anchored device.

    Not a true hard wall --- uses a steep sigmoid to keep the field
    differentiable.  At the anchor centroid the potential is ~barrier_height,
    decaying to ~0 at radius_mm.
    """
    raw = _tt.thermal_potential_phi_exclusion_py(
        _f64_bytes(x_grid),
        _f64_bytes(y_grid),
        [(float(ax), float(ay)) for ax, ay in anchor_positions],
        radius_mm,
        barrier_height,
        steepness,
    )
    return _as_grid(raw, np.shape(x_grid))


def phi_convection(
    x_grid: Array,
    y_grid: Array,
    airflow_vector: tuple[float, float] | None = None,
) -> Array:
    """Linear gradient in the dominant airflow direction.

    If airflow_vector is None, returns a zero field (uniform ambient).
    """
    if airflow_vector is None:
        airflow = None
    else:
        magnitude, direction_deg = airflow_vector
        airflow = (float(magnitude), float(direction_deg))
    raw = _tt.thermal_potential_phi_convection_py(
        _f64_bytes(x_grid), _f64_bytes(y_grid), airflow
    )
    return _as_grid(raw, np.shape(x_grid))


# ---------------------------------------------------------------------------
# Superposition
# ---------------------------------------------------------------------------


def superpose_fields(
    x_grid: Array,
    y_grid: Array,
    board_bounds: tuple[float, float, float, float],
    edge: str,
    config: ThermalPotentialConfig,
    device_positions: list[tuple[float, float]] | None = None,
    device_powers: list[float] | None = None,
    anchor_positions: list[tuple[float, float]] | None = None,
    copper_zones: list | None = None,
    airflow_vector: tuple[float, float] | None = None,
) -> Array:
    """Weighted superposition of all active field components.

    Returns a scalar potential array of shape (grid_resolution, grid_resolution).
    Lower potential = better thermal position.

    The accumulation stays in numpy on purpose: `phi_copper` returns a
    fixed 50x50 array when copper zones are supplied, and numpy's own
    broadcasting is what decides whether that composes with the potential
    grid (a `ValueError` when it does not).  Every component it sums is a
    Rust kernel.
    """
    total = np.zeros_like(x_grid)

    if config.edge_weight > 0:
        total = total + config.edge_weight * phi_edge(
            x_grid, y_grid, board_bounds, edge, config.edge_decay_length_mm
        )

    if config.copper_weight > 0:
        total = total + config.copper_weight * phi_copper(
            x_grid, y_grid, board_bounds, copper_zones=copper_zones
        )

    if config.coupling_weight > 0 and device_positions and device_powers:
        total = total + config.coupling_weight * phi_coupling(
            x_grid, y_grid, device_positions, device_powers
        )

    if config.exclusion_weight > 0 and anchor_positions:
        total = total + config.exclusion_weight * phi_exclusion(
            x_grid,
            y_grid,
            anchor_positions,
            radius_mm=config.thermal_exclusion_radius_mm,
            barrier_height=config.exclusion_barrier_height,
            steepness=config.exclusion_steepness,
        )

    if config.convection_weight > 0 and airflow_vector is not None:
        total = total + config.convection_weight * phi_convection(x_grid, y_grid, airflow_vector)

    return total


# ---------------------------------------------------------------------------
# Grid utilities
# ---------------------------------------------------------------------------


def build_potential_grid(
    board_bounds: tuple[float, float, float, float],
    resolution: int,
) -> tuple[Array, Array]:
    """Build (x_grid, y_grid) mesh arrays for the potential field.

    Returns two (resolution, resolution) arrays.
    """
    x_bytes, y_bytes = _tt.thermal_potential_build_grid_py(*board_bounds, resolution)
    shape = (resolution, resolution)
    return _as_grid(x_bytes, shape), _as_grid(y_bytes, shape)


# ---------------------------------------------------------------------------
# Greedy Anchor Assignment (U2)
# ---------------------------------------------------------------------------


def assign_thermal_anchors(
    board_bounds: tuple[float, float, float, float],
    edge: str,
    power_devices: list[tuple[str, float]],  # (ref, power_W)
    zones: dict[str, tuple[float, float, float, float]] | None = None,
    keepouts: list[tuple[float, float, float, float]] | None = None,
    config: ThermalPotentialConfig | None = None,
    copper_zones: list | None = None,
    airflow_vector: tuple[float, float] | None = None,
    min_separation_mm: float = 2.0,
) -> dict[str, tuple[float, float]]:
    """Greedy two-pass anchor assignment for power devices.

    Args:
        board_bounds: (x_min, y_min, x_max, y_max) in mm.
        edge: Heatsink edge name ("TOP", "BOTTOM", "LEFT", "RIGHT").
        power_devices: Sorted list of (component_ref, power_dissipation_W).
            Caller is responsible for sorting (descending power, alphabetical tie-break).
        zones: Optional per-component zone bounds dict (ref -> bounds).
        keepouts: Optional list of keepout regions (x_min, y_min, x_max, y_max).
        config: Potential field configuration.
        copper_zones: Optional copper zone definitions for phi_copper.
        airflow_vector: Optional (magnitude_m_s, direction_deg) for phi_convection.

    Returns:
        Dict mapping component_ref -> (x, y) anchor position in mm.
    """
    if not power_devices:
        return {}

    if config is None:
        config = ThermalPotentialConfig()

    if keepouts is None:
        keepouts = []

    resolution = config.grid_resolution
    if resolution < 0:
        # np.linspace rejects a negative sample count with a ValueError;
        # raise it from the same place the reference did rather than
        # letting the pyo3 boundary report a different exception class.
        build_potential_grid(board_bounds, resolution)

    devices = [
        (
            ref,
            float(power),
            None if (zones is None or ref not in zones) else tuple(zones[ref]),
        )
        for ref, power in power_devices
    ]

    anchors, skipped, clamped = _tt.thermal_potential_assign_anchors_py(
        *board_bounds,
        _edge_code(edge),
        resolution,
        devices,
        [tuple(k) for k in keepouts],
        _config_tuple(config),
        0 if copper_zones is None else len(copper_zones),
        _zone_bounds(copper_zones),
        None
        if airflow_vector is None
        else (float(airflow_vector[0]), float(airflow_vector[1])),
        min_separation_mm,
    )

    for ref in skipped:
        logger.warning("No valid anchor position found for '%s' --- skipping device", ref)

    for ref, ax, ay, cx, cy, dist in clamped:
        logger.warning(
            "Clamped anchor for '%s': phi_min=(%.2f, %.2f) -> clamped=(%.2f, %.2f) "
            "(delta=%.2f mm)",
            ref,
            ax,
            ay,
            cx,
            cy,
            dist,
        )

    return {ref: (x, y) for ref, x, y in anchors}


def _enforce_unique_positions(
    anchors: dict[str, tuple[float, float]],
    board_bounds: tuple[float, float, float, float],
    tolerance_mm: float = 0.1,
    offset_mm: float = 0.5,
) -> None:
    """Ensure no two anchors share the same position within tolerance_mm.

    For every violating pair (i < j) the later anchor is moved to the
    first x-position on its row -- stepping +offset_mm outward, then
    -offset_mm inward, never beyond the board bounds -- that is at least
    tolerance_mm from *every* other anchor, and the pair scan restarts
    after each move.  This replaces the old single right-offset clamped
    at x_max, which could land the nudged anchor exactly on another
    anchor already at x_max (issue #928) and never re-checked a pair the
    nudge had newly collided with a third anchor.  Mutates anchors
    in-place.

    The arithmetic is delegated bit-exactly to the Rust kernel
    ``temper_thermal.thermal_potential_enforce_unique_py`` (the pinned
    pure-Python oracle in ``tests/physics/_thermal_potential_py_oracle.py``
    mirrors the same algorithm; the differential suite keeps them
    bit-identical).
    """
    updated = _tt.thermal_potential_enforce_unique_py(
        [(ref, float(x), float(y)) for ref, (x, y) in anchors.items()],
        *board_bounds,
        tolerance_mm,
        offset_mm,
    )
    for ref, x, y in updated:
        anchors[ref] = (x, y)
# ---------------------------------------------------------------------------
# Safety Gates (U5)
# ---------------------------------------------------------------------------


class ThermalAnchoringSafetyError(Exception):
    """Raised when a safety gate check fails during thermal anchoring."""


def validate_heatsink_edge(
    board_bounds: tuple[float, float, float, float],
    edge_name: str,
    copper_zones: list | None = None,
    _board_side: str = "F.Cu",
) -> None:
    """Validate that the identified heatsink edge is a real board edge.

    Three safety-gate checks (HARD ABORTS on failure):

    1. Edge proximity: edge_name must map to a real board boundary.
    2. Copper density: adjacent zone must have non-zero copper pour density
       (checked only when copper_zones is provided). Raises on failure
       because insufficient copper for heat spreading = thermal runaway risk.
    3. Correct side: edge must be on the correct board side (TOP/BOTTOM for F.Cu,
       LEFT/RIGHT are valid for any side). No hard gate for this in current
       design --- all edges are valid for anchoring.

    Raises ThermalAnchoringSafetyError on any failure.
    """
    x_min, y_min, x_max, y_max = board_bounds

    if x_min >= x_max or y_min >= y_max:
        raise ThermalAnchoringSafetyError(
            f"Invalid board bounds: ({x_min}, {y_min}, {x_max}, {y_max}) "
            f"--- board dimensions must be positive"
        )

    valid_edges = {"TOP", "BOTTOM", "LEFT", "RIGHT"}
    edge_upper = edge_name.upper().strip()

    # Check 1: Edge name validity
    if edge_upper not in valid_edges:
        raise ThermalAnchoringSafetyError(
            f"Heatsink edge '{edge_name}' is not a valid edge. "
            f"Expected one of: {sorted(valid_edges)}"
        )

    # Check 2: Copper density in adjacent zone (HARD ABORT when data available)
    if copper_zones:
        # Verify at least one copper zone touches the declared edge
        found = False
        for zone in copper_zones:
            if hasattr(zone, "bounds"):
                zx0, zy0, zx1, zy1 = zone.bounds
                if (
                    edge_upper == "TOP"
                    and zy1 >= y_max - 5.0
                    or edge_upper == "BOTTOM"
                    and zy0 <= y_min + 5.0
                    or edge_upper == "LEFT"
                    and zx0 <= x_min + 5.0
                    or edge_upper == "RIGHT"
                    and zx1 >= x_max - 5.0
                ):
                    found = True
                    break
        if not found:
            raise ThermalAnchoringSafetyError(
                f"Copper density safety gate FAILED: No copper zone found adjacent "
                f"to declared heatsink edge '{edge_name}'. "
                f"Insufficient copper for heat spreading --- placement is thermally unsafe."
            )

    # Check 3: Correct board side (TOP/BOTTOM edges are valid for F.Cu, all edges valid)
    # The TOP/BOTTOM edges correspond to heatsink mounting on the component side.
    # No hard gate for this in current design --- all edges are valid for anchoring.


def validate_tj_safety(
    device_ref: str,
    power_w: float,
    Rjc: float | None,
    rated_tj_max: float | None,
    edge_distance_mm: float,
    ambient_C: float = 60.0,
) -> None:
    """Validate that predicted junction temperature does not exceed rated maximum.

    Uses the lumped-parameter model from physics/thermal.py.

    Raises ThermalAnchoringSafetyError if Tj > rated_tj_max.
    """
    if rated_tj_max is None:
        logger.warning("No rated Tj_max for '%s' --- skipping Tj safety check.", device_ref)
        return

    if Rjc is None:
        logger.warning(
            "No Rjc value for '%s' --- using IKW40N120H3 datasheet default "
            "0.31 K/W (supersedes the flat 0.6 TO-247 stand-in).",
            device_ref,
        )
        Rjc = 0.31

    from temper_placer.physics.thermal import estimate_junction_temp

    Tj = estimate_junction_temp(
        power_W=power_w,
        edge_distance_mm=edge_distance_mm,
        ambient_C=ambient_C,
        Rjc=Rjc,
    )

    if Tj > rated_tj_max:
        raise ThermalAnchoringSafetyError(
            f"Junction temperature violation for '{device_ref}': "
            f"predicted Tj={Tj:.1f}°C exceeds rated Tj_max={rated_tj_max:.1f}°C "
            f"(margin={rated_tj_max - Tj:.1f}°C). "
            f"Power={power_w:.1f}W, edge_distance={edge_distance_mm:.1f}mm, "
            f"Rjc={Rjc:.2f} K/W. Pipeline aborted --- placement is thermally unsafe."
        )


def validate_stackup_for_anchoring(
    n_layers: int,
) -> ThermalPotentialConfig:
    """Validate stackup suitability for thermal anchoring.

    If < 4 layers, disables phi_copper with a logged warning and returns
    a config with copper_weight=0. Does NOT abort --- proceeds with
    phi_base + phi_coupling only.

    Returns a ThermalPotentialConfig with adjusted copper_weight.
    """
    if n_layers < 4:
        logger.warning(
            "Copper density thermal field disabled --- requires >=4-layer stackup "
            "for meaningful thermal plane modeling. Proceeding with phi_base + "
            "phi_coupling only. (Got %d layers)",
            n_layers,
        )
        return ThermalPotentialConfig(copper_weight=0.0)
    return ThermalPotentialConfig()
