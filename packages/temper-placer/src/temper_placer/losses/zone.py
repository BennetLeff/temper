"""
Zone membership loss function.

This module enforces zone placement constraints, ensuring components are placed
within their designated zones on the PCB.

Zones separate the board into regions with specific electrical properties:
- HV_ZONE: High-voltage components (rectifier, IGBTs)
- LV_ZONE: Low-voltage control circuitry
- MCU_ZONE: Microcontroller and digital logic
- INTERFACE_ZONE: Connectors and user interface
"""

from __future__ import annotations

from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Zone
from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
)


def compute_zone_distance(
    position: Array,
    zone_bounds: Array,
) -> Array:
    """
    Compute signed distance from position to zone boundary.

    Negative = inside zone, Positive = outside zone.

    Args:
        position: (2,) position [x, y] in mm.
        zone_bounds: [x_min, y_min, x_max, y_max] zone bounds.

    Returns:
        Signed distance (negative inside, positive outside).
    """
    x, y = position[0], position[1]
    x_min, y_min, x_max, y_max = zone_bounds

    # Distance to each edge (positive = outside)
    dx_left = x_min - x
    dx_right = x - x_max
    dy_bottom = y_min - y
    dy_top = y - y_max

    # Maximum distance to any edge (positive if outside)
    dx = jnp.maximum(dx_left, dx_right)
    dy = jnp.maximum(dy_bottom, dy_top)

    # If both positive, we're in a corner - use Euclidean distance
    # If one positive and one negative, use the positive one
    # If both negative, use the maximum (least negative = closest to edge)
    outside_x = dx > 0
    outside_y = dy > 0

    # Corner case: outside both edges
    # Add small epsilon inside sqrt to prevent NaN gradients at exactly 0
    corner_dist = jnp.sqrt(jnp.maximum(0.0, dx) ** 2 + jnp.maximum(0.0, dy) ** 2 + 1e-8)

    # Edge case: outside one edge only
    edge_dist = jnp.maximum(dx, dy)

    # Inside case: maximum of negative distances
    inside_dist = jnp.maximum(dx, dy)

    # Select appropriate distance
    return jnp.where(
        outside_x & outside_y,
        corner_dist,
        jnp.where(outside_x | outside_y, edge_dist, inside_dist),
    )


def compute_zone_membership_penalty(
    positions: Array,
    context: LossContext,
    zone_assignments: dict[str, str] | None = None,
) -> Array:
    """
    Compute zone membership violation penalty.

    Penalizes components that are outside their designated zones.

    Args:
        positions: (N, 2) component center positions.
        context: LossContext with board zones.
        zone_assignments: Optional dict mapping component_ref -> zone_name.
            If None, builds from component.zone fields in netlist.

    Returns:
        Total zone violation penalty (scalar).
    """
    if not context.board.zones:
        return jnp.array(0.0)

    # Build zone assignments from component.zone if not provided
    if zone_assignments is None:
        zone_assignments = {}
        # 1. Check components themselves for explicit zone assignments
        for comp in context.netlist.components:
            if comp.zone:
                zone_assignments[comp.ref] = comp.zone

        # 2. Check board zones for mandatory component lists
        for zone in context.board.zones:
            for comp_ref in zone.components:
                zone_assignments[comp_ref] = zone.name

    if not zone_assignments:
        return jnp.array(0.0)

    # Build zone lookup
    zone_lookup: dict[str, Zone] = {z.name: z for z in context.board.zones}

    total_penalty = jnp.array(0.0)

    for comp_ref, zone_name in zone_assignments.items():
        if zone_name not in zone_lookup:
            continue

        try:
            comp_idx = context.get_component_index(comp_ref)
        except KeyError:
            continue

        zone = zone_lookup[zone_name]
        position = positions[comp_idx]
        zone_bounds = jnp.array(zone.bounds, dtype=jnp.float32)

        # Compute signed distance (positive = outside)
        distance = compute_zone_distance(position, zone_bounds)

        # Quadratic penalty for being outside zone
        penalty = jnp.maximum(0.0, distance) ** 2
        total_penalty = total_penalty + penalty

    return total_penalty


@dataclass
class ZoneMembershipLoss(LossFunction):
    """
    Loss function penalizing components outside their designated zones.

    Each component can be assigned to a zone, and this loss penalizes
    components that are placed outside their assigned zone boundary.

    The penalty is quadratic in the distance outside the zone:
    penalty = max(0, distance_outside)²

    Attributes:
        zone_assignments: Dict mapping component_ref -> zone_name.
            If None, uses zone.components from board definition.
    """

    zone_assignments: dict[str, str] | None = None

    @property
    def name(self) -> str:
        return "zone_membership"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute zone membership loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with board zones.

        Returns:
            LossResult with total zone violation penalty.
        """
        penalty = compute_zone_membership_penalty(positions, context, self.zone_assignments)
        return LossResult(value=penalty)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Zone enforcement is strongest early, then relaxes.

        This curriculum ensures components settle into their zones before
        wirelength optimization pulls them together. Without this, wirelength
        gradients can dominate zone gradients, causing components to cluster
        outside their designated zones.

        Args:
            epoch: Current epoch number.
            total_epochs: Total number of epochs.

        Returns:
            Weight multiplier (3.0 early, 1.0 later).
        """
        progress = epoch / jnp.maximum(total_epochs, 1)
        # Start at 3x weight for first 30% of training, then decay to 1x
        result = jnp.where(progress < 0.3, 3.0, 1.0)
        return result  # type: ignore


def create_temper_zone_assignments() -> dict[str, str]:
    """
    Create default zone assignments for Temper board.

    Returns:
        Dict mapping component_ref -> zone_name.
    """
    return {
        # High-voltage zone: IGBTs, rectifier, HV capacitors
        "Q1": "HV_ZONE",
        "Q2": "HV_ZONE",
        "D1": "HV_ZONE",  # Rectifier diode
        "D2": "HV_ZONE",
        "D3": "HV_ZONE",
        "D4": "HV_ZONE",
        "C_HV1": "HV_ZONE",  # HV filter capacitors
        "C_HV2": "HV_ZONE",
        # Low-voltage zone: Gate drivers, isolated supplies
        "U_DRV1": "LV_ZONE",  # High-side gate driver
        "U_DRV2": "LV_ZONE",  # Low-side gate driver
        "U_ISO1": "LV_ZONE",  # Isolated DC-DC for gate drive
        "U_ISO2": "LV_ZONE",
        # MCU zone: Microcontroller and support
        "U_MCU": "MCU_ZONE",
        "U_REG": "MCU_ZONE",  # LDO regulator
        "Y1": "MCU_ZONE",  # Crystal
        # Interface zone: Connectors
        "J_AC": "INTERFACE_ZONE",  # AC input connector
        "J_COIL": "INTERFACE_ZONE",  # Coil output connector
        "J_UI": "INTERFACE_ZONE",  # User interface connector
    }
