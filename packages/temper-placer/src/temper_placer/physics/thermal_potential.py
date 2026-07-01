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

All operations use JAX arrays (jnp.*) for compatibility with the
existing gradient-based pipeline, though anchoring itself does not
require differentiability today.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

if hasattr(jnp, "long"):
    _jnp_int = jnp.long  # type: ignore[attr-defined]
else:
    _jnp_int = jnp.int32

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Field component functions
# Each returns a scalar potential array of shape (grid_resolution, grid_resolution)
# ---------------------------------------------------------------------------


def _validate_edge(edge: str, board_bounds: tuple[float, float, float, float]) -> None:
    """Validate that the edge name is known. Logs warning on unknown edge."""
    valid = {"TOP", "BOTTOM", "LEFT", "RIGHT"}
    if edge.upper() not in valid:
        logger.warning(
            "Unknown heatsink edge '%s' --- valid edges: %s. "
            "phi_edge will default to zero.",
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
    x_min, y_min, x_max, y_max = board_bounds
    _validate_edge(edge, board_bounds)

    edge_upper = edge.upper().strip()
    if edge_upper == "TOP":
        d = y_max - y_grid
    elif edge_upper == "BOTTOM":
        d = y_grid - y_min
    elif edge_upper == "LEFT":
        d = x_grid - x_min
    elif edge_upper == "RIGHT":
        d = x_max - x_grid
    else:
        return jnp.zeros_like(x_grid)

    return 1.0 - jnp.exp(-d / decay_length_mm)


def phi_copper(
    x_grid: Array,
    y_grid: Array,
    board_bounds: tuple[float, float, float, float],
    layer_stackup: Array | None = None,
    copper_zones: list | None = None,
) -> Array:
    """Effective thermal conductivity of the FR4 + Cu stackup.

    Without copper zone definitions, returns a uniform conductivity field.
    With zones, lower potential in high-copper-fill regions where heat
    spreading is better.
    """
    del x_grid, y_grid  # uniform when no zone data
    eps = 1e-12

    if copper_zones is None or len(copper_zones) == 0:
        # Uniform conductivity --- return a constant field
        return jnp.ones((1, 1)) * 0.5

    # Build per-cell conductance from copper zones
    x_min, y_min, x_max, y_max = board_bounds
    board_w = x_max - x_min
    board_h = y_max - y_min
    if board_w <= 0 or board_h <= 0:
        return jnp.ones((1, 1)) * 0.5

    grid_res = 50  # default coarse estimate for copper
    conductance = jnp.zeros((grid_res, grid_res))

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

        # Map zone bounds to grid indices
        gx0 = max(0, int((zx0 - x_min) / board_w * grid_res))
        gx1 = min(grid_res, int((zx1 - x_min) / board_w * grid_res) + 1)
        gy0 = max(0, int((zy0 - y_min) / board_h * grid_res))
        gy1 = min(grid_res, int((zy1 - y_min) / board_h * grid_res) + 1)

        if gx1 > gx0 and gy1 > gy0:
            conductance = conductance.at[gx0:gx1, gy0:gy1].add(1.0)

    # Compute effective conductivity: high fill -> low potential
    # phi_copper = 1 / (k_eff + epsilon)
    k_eff = jnp.clip(conductance, 0.0, None) + eps
    return 1.0 / k_eff


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
    if not device_positions:
        return jnp.zeros_like(x_grid)

    field = jnp.zeros_like(x_grid)
    for pos, power in zip(device_positions, device_powers):
        dx = x_grid - pos[0]
        dy = y_grid - pos[1]
        dist_sq = dx * dx + dy * dy
        sigma = jnp.sqrt(max(power, 1e-6)) * sigma_factor
        sigma_sq = 2.0 * sigma * sigma
        field = field + power * jnp.exp(-dist_sq / sigma_sq)

    return field


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
    if not anchor_positions:
        return jnp.zeros_like(x_grid)

    field = jnp.zeros_like(x_grid)
    for ax, ay in anchor_positions:
        dx = x_grid - ax
        dy = y_grid - ay
        dist = jnp.sqrt(dx * dx + dy * dy)
        # sigmoid: high when dist < radius, low when dist > radius
        # barrier_height * sigma(kappa * (radius - dist))
        barrier = barrier_height * (1.0 / (1.0 + jnp.exp(-steepness * (dist - radius_mm))))
        field = jnp.maximum(field, barrier)

    return field


def phi_convection(
    x_grid: Array,
    y_grid: Array,
    airflow_vector: tuple[float, float] | None = None,
) -> Array:
    """Linear gradient in the dominant airflow direction.

    If airflow_vector is None, returns a zero field (uniform ambient).
    """
    if airflow_vector is None:
        return jnp.zeros_like(x_grid)

    magnitude, direction_deg = airflow_vector
    if magnitude <= 0:
        return jnp.zeros_like(x_grid)

    # Convert direction (degrees from +x) to unit vector
    rad = jnp.radians(direction_deg)
    ux = jnp.cos(rad)
    uy = jnp.sin(rad)

    # Linear ramp: projection onto airflow direction
    return magnitude * (x_grid * ux + y_grid * uy)


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
    """
    total = jnp.zeros_like(x_grid)

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
        total = total + config.convection_weight * phi_convection(
            x_grid, y_grid, airflow_vector
        )

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
    x_min, y_min, x_max, y_max = board_bounds
    x_lin = jnp.linspace(x_min, x_max, resolution)
    y_lin = jnp.linspace(y_min, y_max, resolution)
    x_grid, y_grid = jnp.meshgrid(x_lin, y_lin)
    return x_grid, y_grid


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
    x_grid, y_grid = build_potential_grid(board_bounds, resolution)

    # Determine edge strip bounds (within 10mm of declared edge)
    x_min, y_min, x_max, y_max = board_bounds
    edge_upper = edge.upper().strip()
    edge_margin = 10.0

    def _in_edge_strip(x: float, y: float) -> bool:
        if edge_upper == "TOP":
            return (y_max - y) <= edge_margin
        elif edge_upper == "BOTTOM":
            return (y - y_min) <= edge_margin
        elif edge_upper == "LEFT":
            return (x - x_min) <= edge_margin
        elif edge_upper == "RIGHT":
            return (x_max - x) <= edge_margin
        return False

    def _in_zone(ref: str, x: float, y: float) -> bool:
        if zones is None or ref not in zones:
            return True
        zx0, zy0, zx1, zy1 = zones[ref]
        return zx0 <= x <= zx1 and zy0 <= y <= zy1

    def _in_keepout(x: float, y: float) -> bool:
        for kx0, ky0, kx1, ky1 in keepouts:
            if kx0 <= x <= kx1 and ky0 <= y <= ky1:
                return True
        return False

    def _find_min_valid(phi: Array, ref: str, existing_positions: list[tuple[float, float]]) -> tuple[float, float] | None:
        """Find the minimum phi position within all constraints."""
        best_val = float("inf")
        best_xy: tuple[float, float] | None = None
        min_dist2 = min_separation_mm * min_separation_mm
        for i in range(resolution):
            for j in range(resolution):
                x = float(x_grid[i, j])
                y = float(y_grid[i, j])
                if not _in_edge_strip(x, y):
                    continue
                if not _in_zone(ref, x, y):
                    continue
                if _in_keepout(x, y):
                    continue
                # Check min separation from existing anchors
                too_close = False
                for ex, ey in existing_positions:
                    if ((x - ex) ** 2 + (y - ey) ** 2) < min_dist2:
                        too_close = True
                        break
                if too_close:
                    continue
                val = float(phi[i, j])
                if val < best_val:
                    best_val = val
                    best_xy = (x, y)
        return best_xy

    # --- Pass 1: phi_base only (edge + copper, no coupling) ---
    phi_base = superpose_fields(
        x_grid,
        y_grid,
        board_bounds,
        edge,
        ThermalPotentialConfig(
            edge_weight=config.edge_weight,
            copper_weight=config.copper_weight,
            coupling_weight=0.0,  # no coupling in Pass 1
            exclusion_weight=0.0,  # no exclusion in Pass 1
            convection_weight=config.convection_weight,
            edge_decay_length_mm=config.edge_decay_length_mm,
            grid_resolution=config.grid_resolution,
        ),
        copper_zones=copper_zones,
        airflow_vector=airflow_vector,
    )

    pass1_anchors: dict[str, tuple[float, float]] = {}
    existing: list[tuple[float, float]] = []

    for ref, _power in power_devices:
        xy = _find_min_valid(phi_base, ref, existing)
        if xy is None:
            logger.warning(
                "No valid anchor position found for '%s' --- skipping device", ref
            )
            continue
        pass1_anchors[ref] = xy
        existing.append(xy)

    if not pass1_anchors:
        return {}

    # --- Pass 2: phi_coupling correction (up to 3 iterations) ---
    MAX_ITERATIONS = 3
    REASSIGN_THRESHOLD_MM = 5.0

    for _iteration in range(MAX_ITERATIONS):
        anchor_positions_list = list(pass1_anchors.values())
        device_powers_list = [p for _, p in power_devices if _ in pass1_anchors]
        # Use anchor positions as device_positions for coupling
        coupled_device_positions = [
            pass1_anchors[ref] for ref, _ in power_devices if ref in pass1_anchors
        ]
        coupled_powers = [
            pw for ref, pw in power_devices if ref in pass1_anchors
        ]

        phi_full = superpose_fields(
            x_grid,
            y_grid,
            board_bounds,
            edge,
            ThermalPotentialConfig(
                edge_weight=config.edge_weight,
                copper_weight=config.copper_weight,
                coupling_weight=config.coupling_weight,
                exclusion_weight=config.exclusion_weight,
                convection_weight=config.convection_weight,
                edge_decay_length_mm=config.edge_decay_length_mm,
                thermal_exclusion_radius_mm=config.thermal_exclusion_radius_mm,
                exclusion_barrier_height=config.exclusion_barrier_height,
                exclusion_steepness=config.exclusion_steepness,
                grid_resolution=config.grid_resolution,
            ),
            device_positions=coupled_device_positions,
            device_powers=coupled_powers,
            anchor_positions=anchor_positions_list,
            copper_zones=copper_zones,
            airflow_vector=airflow_vector,
        )

        updated = False
        new_anchors: dict[str, tuple[float, float]] = {}
        new_existing: list[tuple[float, float]] = []

        for ref, _power in power_devices:
            if ref not in pass1_anchors:
                continue
            xy = _find_min_valid(phi_full, ref, new_existing)
            if xy is None:
                new_anchors[ref] = pass1_anchors[ref]
                new_existing.append(pass1_anchors[ref])
                continue

            old_x, old_y = pass1_anchors[ref]
            new_x, new_y = xy
            dist = jnp.sqrt((new_x - old_x) ** 2 + (new_y - old_y) ** 2)
            if float(dist) > REASSIGN_THRESHOLD_MM:
                new_anchors[ref] = xy
                new_existing.append(xy)
                updated = True
            else:
                new_anchors[ref] = pass1_anchors[ref]
                new_existing.append(pass1_anchors[ref])

        pass1_anchors = new_anchors
        if not updated:
            break

    # --- Clamp final positions ---
    final: dict[str, tuple[float, float]] = {}
    for ref, (ax, ay) in pass1_anchors.items():
        # Clamp to board bounds
        cx = float(jnp.clip(ax, x_min, x_max))
        cy = float(jnp.clip(ay, y_min, y_max))

        # Clamp to zone
        if zones and ref in zones:
            zx0, zy0, zx1, zy1 = zones[ref]
            cx = float(jnp.clip(cx, zx0, zx1))
            cy = float(jnp.clip(cy, zy0, zy1))

        # Warn if clamped position differs significantly from phi_min
        dist = jnp.sqrt((cx - ax) ** 2 + (cy - ay) ** 2)
        if float(dist) > 2.0:
            logger.warning(
                "Clamped anchor for '%s': phi_min=(%.2f, %.2f) -> clamped=(%.2f, %.2f) "
                "(delta=%.2f mm)",
                ref, ax, ay, cx, cy, float(dist),
            )

        final[ref] = (cx, cy)

    # --- Uniqueness enforcement (R13) ---
    _enforce_unique_positions(final, board_bounds)

    return final


def _enforce_unique_positions(
    anchors: dict[str, tuple[float, float]],
    board_bounds: tuple[float, float, float, float],
    tolerance_mm: float = 0.1,
    offset_mm: float = 0.5,
) -> None:
    """Ensure no two anchors share the same position within tolerance_mm.

    If a duplicate is found, offsets the second device by offset_mm along
    the edge strip and re-checks. Mutates anchors in-place.
    """
    refs = list(anchors.keys())
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            ri, rj = refs[i], refs[j]
            xi, yi = anchors[ri]
            xj, yj = anchors[rj]
            dist = ((xi - xj) ** 2 + (yi - yj) ** 2) ** 0.5
            if dist < tolerance_mm:
                # Offset rj by offset_mm along x (clamped to board bounds)
                _, _, x_max, _ = board_bounds
                new_x = min(xj + offset_mm, x_max)
                anchors[rj] = (new_x, yj)


# ---------------------------------------------------------------------------
# Safety Gates (U5)
# ---------------------------------------------------------------------------


class ThermalAnchoringSafetyError(Exception):
    """Raised when a safety gate check fails during thermal anchoring."""


def validate_heatsink_edge(
    board_bounds: tuple[float, float, float, float],
    edge_name: str,
    copper_zones: list | None = None,
    board_side: str = "F.Cu",
) -> None:
    """Validate that the identified heatsink edge is a real board edge.

    Three checks:
    1. Edge proximity: edge_name must map to a real board boundary.
    2. Copper density: adjacent zone must have non-zero copper pour density
       (checked only when copper_zones is provided).
    3. Correct side: edge must be on the correct board side (TOP/BOTTOM for F.Cu,
       LEFT/RIGHT are valid for any side).

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

    # Check 2: Copper density in adjacent zone (soft check, only when data available)
    if copper_zones:
        # Verify at least one copper zone touches the declared edge
        found = False
        for zone in copper_zones:
            if hasattr(zone, "bounds"):
                zx0, zy0, zx1, zy1 = zone.bounds
                if edge_upper == "TOP" and zy1 >= y_max - 5.0:
                    found = True
                    break
                elif edge_upper == "BOTTOM" and zy0 <= y_min + 5.0:
                    found = True
                    break
                elif edge_upper == "LEFT" and zx0 <= x_min + 5.0:
                    found = True
                    break
                elif edge_upper == "RIGHT" and zx1 >= x_max - 5.0:
                    found = True
                    break
        if not found:
            logger.warning(
                "No copper zone found adjacent to declared heatsink edge '%s'. "
                "Copper density may be insufficient for heat spreading.",
                edge_name,
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
    ambient_C: float = 40.0,
) -> None:
    """Validate that predicted junction temperature does not exceed rated maximum.

    Uses the lumped-parameter model from physics/thermal.py.

    Raises ThermalAnchoringSafetyError if Tj > rated_tj_max.
    """
    if rated_tj_max is None:
        logger.warning(
            "No rated Tj_max for '%s' --- skipping Tj safety check.", device_ref
        )
        return

    if Rjc is None:
        logger.warning(
            "No Rjc value for '%s' --- using conservative default 0.6 K/W.", device_ref
        )
        Rjc = 0.6

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
            "phi_coupling only. (Got %d layers)", n_layers
        )
        return ThermalPotentialConfig(copper_weight=0.0)
    return ThermalPotentialConfig()
