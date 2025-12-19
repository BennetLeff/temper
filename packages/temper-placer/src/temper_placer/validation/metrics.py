"""
Placement quality metrics computation.

This module computes quality metrics for a placement without determining
pass/fail status. Useful for:
- Comparing different placements
- Tracking optimization progress
- Reporting final placement quality
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.geometry.overlap import (
    compute_pairwise_distances,
)
from temper_placer.geometry.transform import get_rotated_bounds


@dataclass
class PlacementMetrics:
    """
    Quality metrics for a placement.

    All distances/areas are in mm or mm².
    """

    # Overlap metrics
    overlap_count: int = 0  # Number of overlapping component pairs
    total_overlap_area: float = 0.0  # Sum of overlap amounts (mm)
    worst_overlap: float = 0.0  # Largest single overlap (mm)

    # Boundary metrics
    boundary_violations: int = 0  # Components outside board
    total_boundary_violation: float = 0.0  # Sum of violation amounts (mm)

    # Clearance metrics
    clearance_violations: int = 0  # Pairs too close together
    hv_lv_violations: int = 0  # HV-LV pairs violating 10mm clearance
    min_hv_lv_clearance: float = float("inf")  # Minimum HV-LV distance

    # Zone metrics
    zone_violations: int = 0  # Components in wrong zones

    # Keepout metrics
    keepout_violations: int = 0  # Components in keepout regions

    # Wirelength metrics
    total_wirelength: float = 0.0  # Half-perimeter wirelength (mm)
    max_net_length: float = 0.0  # Longest net (mm)
    avg_net_length: float = 0.0  # Average net length (mm)

    # Congestion metrics
    max_congestion: float = 0.0  # Maximum local congestion score
    avg_congestion: float = 0.0  # Average congestion

    # Distribution metrics
    utilization: float = 0.0  # Component area / board area
    spread_score: float = 0.0  # How spread out components are (higher = more spread)
    center_of_mass: tuple = (0.0, 0.0)  # Center of mass of all components

    # Timing
    computation_time_ms: float = 0.0

    def summary(self) -> str:
        """Get a human-readable summary of key metrics."""
        lines = [
            "=== Placement Metrics ===",
            f"Overlaps: {self.overlap_count} ({self.total_overlap_area:.2f}mm² total)",
            f"Boundary violations: {self.boundary_violations}",
            f"Clearance violations: {self.clearance_violations} (HV-LV: {self.hv_lv_violations})",
            f"Zone violations: {self.zone_violations}",
            f"Keepout violations: {self.keepout_violations}",
            f"Wirelength: {self.total_wirelength:.1f}mm (avg: {self.avg_net_length:.1f}mm)",
            f"Utilization: {self.utilization * 100:.1f}%",
            f"Computed in {self.computation_time_ms:.1f}ms",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "overlap_count": self.overlap_count,
            "total_overlap_area": self.total_overlap_area,
            "worst_overlap": self.worst_overlap,
            "boundary_violations": self.boundary_violations,
            "total_boundary_violation": self.total_boundary_violation,
            "clearance_violations": self.clearance_violations,
            "hv_lv_violations": self.hv_lv_violations,
            "min_hv_lv_clearance": self.min_hv_lv_clearance
            if self.min_hv_lv_clearance != float("inf")
            else None,
            "zone_violations": self.zone_violations,
            "keepout_violations": self.keepout_violations,
            "total_wirelength": self.total_wirelength,
            "max_net_length": self.max_net_length,
            "avg_net_length": self.avg_net_length,
            "max_congestion": self.max_congestion,
            "avg_congestion": self.avg_congestion,
            "utilization": self.utilization,
            "spread_score": self.spread_score,
            "center_of_mass": self.center_of_mass,
            "computation_time_ms": self.computation_time_ms,
        }

    @property
    def is_valid(self) -> bool:
        """Check if placement has no critical violations."""
        return (
            self.overlap_count == 0
            and self.boundary_violations == 0
            and self.hv_lv_violations == 0
            and self.keepout_violations == 0
        )


def compute_metrics(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    hv_lv_clearance: float = 10.0,
) -> PlacementMetrics:
    """
    Compute comprehensive placement quality metrics.

    Args:
        state: Current placement state.
        netlist: Component netlist.
        board: Board definition.
        hv_lv_clearance: Required HV-LV clearance in mm.

    Returns:
        PlacementMetrics with all computed values.
    """
    start_time = time.time()
    metrics = PlacementMetrics()

    # Extract component data
    positions = state.positions
    n_components = positions.shape[0]

    # Get rotation one-hot vectors
    rotation_indices = jnp.argmax(state.rotation_logits, axis=-1)
    rotations = jnp.eye(4)[rotation_indices]

    # Get component dimensions
    bounds = netlist.get_bounds_array()
    widths = bounds[:, 0]
    heights = bounds[:, 1]

    # Compute pairwise distances once
    distances = compute_pairwise_distances(positions, rotations, widths, heights)

    # === Overlap metrics ===
    _compute_overlap_metrics(metrics, distances, n_components)

    # === Boundary metrics ===
    _compute_boundary_metrics(metrics, positions, rotations, widths, heights, board)

    # === Clearance metrics ===
    _compute_clearance_metrics(metrics, distances, netlist, hv_lv_clearance)

    # === Zone metrics ===
    _compute_zone_metrics(metrics, positions, netlist, board)

    # === Keepout metrics ===
    _compute_keepout_metrics(metrics, positions, rotations, widths, heights, board)

    # === Wirelength metrics ===
    _compute_wirelength_metrics(metrics, positions, rotation_indices, netlist)

    # === Distribution metrics ===
    _compute_distribution_metrics(metrics, positions, widths, heights, board)

    metrics.computation_time_ms = (time.time() - start_time) * 1000
    return metrics


def _compute_overlap_metrics(metrics: PlacementMetrics, distances: Array, n: int) -> None:
    """Compute overlap-related metrics."""
    overlap_count = 0
    total_overlap = 0.0
    worst_overlap = 0.0

    for i in range(n):
        for j in range(i + 1, n):
            dist = float(distances[i, j])
            if dist < 0:
                overlap_amount = -dist
                overlap_count += 1
                total_overlap += overlap_amount
                worst_overlap = max(worst_overlap, overlap_amount)

    metrics.overlap_count = overlap_count
    metrics.total_overlap_area = total_overlap
    metrics.worst_overlap = worst_overlap


def _compute_boundary_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
    board: Board,
) -> None:
    """Compute boundary violation metrics."""
    ox, oy = board.origin
    board_min = jnp.array([ox, oy])
    board_max = jnp.array([ox + board.width, oy + board.height])

    n = positions.shape[0]
    violation_count = 0
    total_violation = 0.0

    for i in range(n):
        rot = rotations[i]
        rw, rh = get_rotated_bounds(float(widths[i]), float(heights[i]), rot)
        half_w, half_h = rw / 2, rh / 2

        pos = positions[i]

        # Check violations
        violations = [
            max(0, float(board_min[0] - (pos[0] - half_w))),  # left
            max(0, float((pos[0] + half_w) - board_max[0])),  # right
            max(0, float(board_min[1] - (pos[1] - half_h))),  # bottom
            max(0, float((pos[1] + half_h) - board_max[1])),  # top
        ]

        max_violation = max(violations)
        if max_violation > 0:
            violation_count += 1
            total_violation += max_violation

    metrics.boundary_violations = violation_count
    metrics.total_boundary_violation = total_violation


def _compute_clearance_metrics(
    metrics: PlacementMetrics,
    distances: Array,
    netlist: Netlist,
    hv_lv_clearance: float,
) -> None:
    """Compute clearance violation metrics."""
    n = len(netlist.components)
    clearance_violations = 0
    hv_lv_violations = 0
    min_hv_lv = float("inf")

    min_clearance = 0.2  # Default minimum clearance

    for i in range(n):
        for j in range(i + 1, n):
            comp_i = netlist.components[i]
            comp_j = netlist.components[j]
            dist = float(distances[i, j])

            is_hv_lv = (
                comp_i.net_class == "HighVoltage" and comp_j.net_class != "HighVoltage"
            ) or (comp_j.net_class == "HighVoltage" and comp_i.net_class != "HighVoltage")

            if is_hv_lv:
                min_hv_lv = min(min_hv_lv, dist)
                if dist < hv_lv_clearance:
                    hv_lv_violations += 1
                    clearance_violations += 1
            elif dist < min_clearance:
                clearance_violations += 1

    metrics.clearance_violations = clearance_violations
    metrics.hv_lv_violations = hv_lv_violations
    metrics.min_hv_lv_clearance = min_hv_lv


def _compute_zone_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    netlist: Netlist,
    board: Board,
) -> None:
    """Compute zone violation metrics."""
    zone_violations = 0

    for i, comp in enumerate(netlist.components):
        if comp.zone is None:
            continue

        x, y = float(positions[i, 0]), float(positions[i, 1])

        try:
            required_zone = board.get_zone(comp.zone)
            if not required_zone.contains_point(x, y):
                zone_violations += 1
        except KeyError:
            # Zone not defined - count as violation
            zone_violations += 1

    metrics.zone_violations = zone_violations


def _compute_keepout_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
    board: Board,
) -> None:
    """Compute keepout violation metrics."""
    n = positions.shape[0]
    keepout_violations = 0

    for i in range(n):
        pos = positions[i]
        x, y = float(pos[0]), float(pos[1])

        rot = rotations[i]
        rw, rh = get_rotated_bounds(float(widths[i]), float(heights[i]), rot)
        half_w, half_h = rw / 2, rh / 2

        comp_min_x = x - half_w
        comp_max_x = x + half_w
        comp_min_y = y - half_h
        comp_max_y = y + half_h

        # Check rectangular keepouts
        for kx_min, ky_min, kx_max, ky_max in board.keepout_regions:
            if (
                comp_max_x > kx_min
                and comp_min_x < kx_max
                and comp_max_y > ky_min
                and comp_min_y < ky_max
            ):
                keepout_violations += 1
                break  # Only count once per component
        else:
            # Also check mounting holes
            for hole in board.mounting_holes:
                hx, hy = hole.position
                dist_to_hole = ((x - hx) ** 2 + (y - hy) ** 2) ** 0.5
                min_dist = max(half_w, half_h) + hole.keepout_radius
                if dist_to_hole < min_dist:
                    keepout_violations += 1
                    break

    metrics.keepout_violations = keepout_violations


def _compute_wirelength_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    rotation_indices: Array,
    netlist: Netlist,
) -> None:
    """Compute wirelength metrics using half-perimeter wirelength (HPWL)."""
    total_wirelength = 0.0
    max_net_length = 0.0
    net_lengths = []

    # Rotation angles for each index (0, 90, 180, 270 degrees)
    rotation_angles = [0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2]

    for net in netlist.nets:
        if len(net.pins) < 2:
            continue

        # Collect all pin positions for this net
        pin_positions = []

        for comp_ref, pin_name in net.pins:
            try:
                comp_idx = netlist.get_component_index(comp_ref)
                comp = netlist.get_component(comp_ref)
                pin = comp.get_pin(pin_name)

                if pin is None:
                    continue

                # Get component position and rotation
                comp_pos = positions[comp_idx]
                rot_idx = int(rotation_indices[comp_idx])
                angle = rotation_angles[rot_idx]

                # Compute absolute pin position
                abs_pos = pin.absolute_position(
                    (float(comp_pos[0]), float(comp_pos[1])),
                    angle,
                )
                pin_positions.append(abs_pos)
            except (KeyError, IndexError):
                continue

        if len(pin_positions) < 2:
            continue

        # Compute HPWL for this net
        xs = [p[0] for p in pin_positions]
        ys = [p[1] for p in pin_positions]

        hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))

        # Apply net weight
        weighted_hpwl = hpwl * net.weight

        total_wirelength += weighted_hpwl
        max_net_length = max(max_net_length, hpwl)
        net_lengths.append(hpwl)

    metrics.total_wirelength = total_wirelength
    metrics.max_net_length = max_net_length
    metrics.avg_net_length = sum(net_lengths) / len(net_lengths) if net_lengths else 0.0


def _compute_distribution_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    widths: Array,
    heights: Array,
    board: Board,
) -> None:
    """Compute placement distribution metrics."""
    n = positions.shape[0]

    # Utilization
    total_component_area = float(jnp.sum(widths * heights))
    board_area = board.width * board.height
    metrics.utilization = total_component_area / board_area

    # Center of mass
    com_x = float(jnp.mean(positions[:, 0]))
    com_y = float(jnp.mean(positions[:, 1]))
    metrics.center_of_mass = (com_x, com_y)

    # Spread score: average distance from center of mass
    distances_from_com = jnp.sqrt((positions[:, 0] - com_x) ** 2 + (positions[:, 1] - com_y) ** 2)
    metrics.spread_score = float(jnp.mean(distances_from_com))
