"""
Geometric validation for placement results.

This module provides pure-Python/JAX geometric validation that doesn't depend
on external tools like kiutils. It checks:
- Component overlaps
- Boundary violations (components outside board)
- Clearance violations (HV-LV separation, etc.)
- Zone violations (components in wrong zones)
- Keepout violations (components in keepout regions)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.geometry.overlap import (
    compute_pairwise_distances,
    count_overlaps,
)
from temper_placer.geometry.transform import get_rotated_bounds
from temper_placer.validation.base import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    Validator,
)


class ViolationType(Enum):
    """Types of geometric violations."""

    OVERLAP = auto()  # Components overlap each other
    BOUNDARY = auto()  # Component outside board boundary
    CLEARANCE = auto()  # Insufficient clearance between components
    ZONE = auto()  # Component in wrong zone
    KEEPOUT = auto()  # Component in keepout region
    MOUNTING_HOLE = auto()  # Component too close to mounting hole


@dataclass
class GeometricViolation(ValidationIssue):
    """
    A geometric violation with additional spatial data.

    Extends ValidationIssue with violation-specific information.
    """

    violation_type: ViolationType = ViolationType.OVERLAP
    overlap_amount: float = 0.0  # For overlaps: penetration depth in mm
    required_clearance: float = 0.0  # For clearance: required distance
    actual_distance: float = 0.0  # For clearance: measured distance


class GeometricValidator(Validator):
    """
    Validates placement geometry without external tools.

    Checks:
    - Component-component overlaps
    - Board boundary violations
    - HV-LV clearance requirements (10mm for Temper)
    - Zone assignments
    - Keepout and mounting hole violations
    """

    def __init__(
        self,
        min_clearance: float = 0.2,  # Default minimum clearance in mm
        hv_lv_clearance: float = 10.0,  # HV-LV isolation clearance
        overlap_threshold: float = 0.01,  # Ignore overlaps smaller than this
    ):
        """
        Initialize the geometric validator.

        Args:
            min_clearance: Default minimum clearance between components (mm).
            hv_lv_clearance: Required clearance between HV and LV components (mm).
            overlap_threshold: Overlaps smaller than this are ignored (mm).
        """
        self.min_clearance = min_clearance
        self.hv_lv_clearance = hv_lv_clearance
        self.overlap_threshold = overlap_threshold

    @property
    def name(self) -> str:
        return "GeometricValidator"

    def validate(
        self,
        state: PlacementState,
        netlist: Netlist,
        board: Board,
    ) -> ValidationResult:
        """
        Run geometric validation on a placement.

        Args:
            state: Current placement state.
            netlist: Component netlist.
            board: Board definition.

        Returns:
            ValidationResult with any violations found.
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []
        metrics: dict = {}

        # Extract component data
        positions = state.positions
        n_components = positions.shape[0]

        # Get rotation one-hot vectors (use argmax for discrete)
        rotation_indices = jnp.argmax(state.rotation_logits, axis=-1)
        rotations = jnp.eye(4)[rotation_indices]  # (N, 4) one-hot

        # Get component dimensions
        bounds = netlist.get_bounds_array()  # (N, 2)
        widths = bounds[:, 0]
        heights = bounds[:, 1]

        # 1. Check overlaps
        overlap_issues, overlap_count, total_overlap = self._check_overlaps(
            positions, rotations, widths, heights, netlist
        )
        issues.extend(overlap_issues)
        metrics["overlap_count"] = overlap_count
        metrics["total_overlap_area"] = float(total_overlap)

        # 2. Check boundary violations
        boundary_issues, boundary_count = self._check_boundaries(
            positions, rotations, widths, heights, netlist, board
        )
        issues.extend(boundary_issues)
        metrics["boundary_violations"] = boundary_count

        # 3. Check clearance violations (HV-LV)
        clearance_issues, clearance_count = self._check_clearances(
            positions, rotations, widths, heights, netlist
        )
        issues.extend(clearance_issues)
        metrics["clearance_violations"] = clearance_count

        # 4. Check zone violations
        zone_issues, zone_count = self._check_zones(positions, netlist, board)
        issues.extend(zone_issues)
        metrics["zone_violations"] = zone_count

        # 5. Check keepout violations
        keepout_issues, keepout_count = self._check_keepouts(
            positions, rotations, widths, heights, netlist, board
        )
        issues.extend(keepout_issues)
        metrics["keepout_violations"] = keepout_count

        # Determine overall validity
        error_count = sum(
            1
            for i in issues
            if i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
        )
        valid = error_count == 0

        elapsed_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            valid=valid,
            issues=issues,
            metrics=metrics,
            elapsed_ms=elapsed_ms,
            validator_name=self.name,
        )

    def _check_overlaps(
        self,
        positions: Array,
        rotations: Array,
        widths: Array,
        heights: Array,
        netlist: Netlist,
    ) -> Tuple[List[GeometricViolation], int, float]:
        """Check for component overlaps."""
        issues = []

        # Compute pairwise distances
        distances = compute_pairwise_distances(positions, rotations, widths, heights)

        # Find overlapping pairs (negative distance)
        n = positions.shape[0]
        total_overlap = 0.0
        overlap_count = 0

        for i in range(n):
            for j in range(i + 1, n):
                dist = float(distances[i, j])
                if dist < -self.overlap_threshold:
                    overlap_amount = -dist
                    total_overlap += overlap_amount
                    overlap_count += 1

                    comp_i = netlist.components[i]
                    comp_j = netlist.components[j]

                    # Determine severity based on overlap amount
                    if overlap_amount > 5.0:
                        severity = ValidationSeverity.CRITICAL
                    elif overlap_amount > 1.0:
                        severity = ValidationSeverity.ERROR
                    else:
                        severity = ValidationSeverity.WARNING

                    issues.append(
                        GeometricViolation(
                            severity=severity,
                            code="GEO_OVERLAP",
                            message=f"Components {comp_i.ref} and {comp_j.ref} overlap by {overlap_amount:.2f}mm",
                            component_refs=[comp_i.ref, comp_j.ref],
                            location=(
                                float((positions[i, 0] + positions[j, 0]) / 2),
                                float((positions[i, 1] + positions[j, 1]) / 2),
                            ),
                            details={
                                "overlap_mm": overlap_amount,
                                "distance": dist,
                            },
                            violation_type=ViolationType.OVERLAP,
                            overlap_amount=overlap_amount,
                        )
                    )

        return issues, overlap_count, total_overlap

    def _check_boundaries(
        self,
        positions: Array,
        rotations: Array,
        widths: Array,
        heights: Array,
        netlist: Netlist,
        board: Board,
    ) -> Tuple[List[GeometricViolation], int]:
        """Check for components outside board boundaries."""
        issues = []
        violation_count = 0

        # Board bounds
        ox, oy = board.origin
        board_min = jnp.array([ox, oy])
        board_max = jnp.array([ox + board.width, oy + board.height])

        n = positions.shape[0]

        for i in range(n):
            # Get rotated component bounds
            rot_one_hot = rotations[i]
            rw, rh = get_rotated_bounds(float(widths[i]), float(heights[i]), rot_one_hot)
            half_w, half_h = rw / 2, rh / 2

            pos = positions[i]
            comp = netlist.components[i]

            # Check each edge
            violations = []

            # Left edge
            left_violation = float(board_min[0] - (pos[0] - half_w))
            if left_violation > 0:
                violations.append(("left", left_violation))

            # Right edge
            right_violation = float((pos[0] + half_w) - board_max[0])
            if right_violation > 0:
                violations.append(("right", right_violation))

            # Bottom edge
            bottom_violation = float(board_min[1] - (pos[1] - half_h))
            if bottom_violation > 0:
                violations.append(("bottom", bottom_violation))

            # Top edge
            top_violation = float((pos[1] + half_h) - board_max[1])
            if top_violation > 0:
                violations.append(("top", top_violation))

            if violations:
                violation_count += 1
                max_violation = max(v[1] for v in violations)
                edges = ", ".join(v[0] for v in violations)

                severity = (
                    ValidationSeverity.CRITICAL
                    if max_violation > 10.0
                    else ValidationSeverity.ERROR
                )

                issues.append(
                    GeometricViolation(
                        severity=severity,
                        code="GEO_BOUNDARY",
                        message=f"Component {comp.ref} extends {max_violation:.2f}mm outside board ({edges})",
                        component_refs=[comp.ref],
                        location=(float(pos[0]), float(pos[1])),
                        details={
                            "violations": violations,
                            "max_violation_mm": max_violation,
                        },
                        violation_type=ViolationType.BOUNDARY,
                        overlap_amount=max_violation,
                    )
                )

        return issues, violation_count

    def _check_clearances(
        self,
        positions: Array,
        rotations: Array,
        widths: Array,
        heights: Array,
        netlist: Netlist,
    ) -> Tuple[List[GeometricViolation], int]:
        """Check for HV-LV clearance violations."""
        issues = []
        violation_count = 0

        # Compute pairwise distances
        distances = compute_pairwise_distances(positions, rotations, widths, heights)

        n = positions.shape[0]

        for i in range(n):
            for j in range(i + 1, n):
                comp_i = netlist.components[i]
                comp_j = netlist.components[j]

                # Check if HV-LV pair
                is_hv_lv_pair = (
                    comp_i.net_class == "HighVoltage" and comp_j.net_class != "HighVoltage"
                ) or (comp_j.net_class == "HighVoltage" and comp_i.net_class != "HighVoltage")

                if is_hv_lv_pair:
                    required_clearance = self.hv_lv_clearance
                else:
                    required_clearance = self.min_clearance

                dist = float(distances[i, j])

                if dist < required_clearance:
                    # Clearance violation
                    shortage = required_clearance - dist

                    if is_hv_lv_pair:
                        # HV-LV violations are critical
                        severity = ValidationSeverity.CRITICAL
                        code = "GEO_HV_LV_CLEARANCE"
                        msg = f"HV-LV clearance violation: {comp_i.ref} ({comp_i.net_class}) and {comp_j.ref} ({comp_j.net_class}) are {dist:.2f}mm apart (need {required_clearance}mm)"
                    else:
                        severity = (
                            ValidationSeverity.WARNING if dist > 0 else ValidationSeverity.ERROR
                        )
                        code = "GEO_CLEARANCE"
                        msg = f"Clearance warning: {comp_i.ref} and {comp_j.ref} are {dist:.2f}mm apart (recommend {required_clearance}mm)"

                    violation_count += 1
                    issues.append(
                        GeometricViolation(
                            severity=severity,
                            code=code,
                            message=msg,
                            component_refs=[comp_i.ref, comp_j.ref],
                            location=(
                                float((positions[i, 0] + positions[j, 0]) / 2),
                                float((positions[i, 1] + positions[j, 1]) / 2),
                            ),
                            details={
                                "actual_distance_mm": dist,
                                "required_clearance_mm": required_clearance,
                                "shortage_mm": shortage,
                                "is_hv_lv": is_hv_lv_pair,
                            },
                            violation_type=ViolationType.CLEARANCE,
                            required_clearance=required_clearance,
                            actual_distance=dist,
                        )
                    )

        return issues, violation_count

    def _check_zones(
        self,
        positions: Array,
        netlist: Netlist,
        board: Board,
    ) -> Tuple[List[GeometricViolation], int]:
        """Check for components in wrong zones."""
        issues = []
        violation_count = 0

        n = positions.shape[0]

        for i in range(n):
            comp = netlist.components[i]
            pos = positions[i]
            x, y = float(pos[0]), float(pos[1])

            # Skip if component has no zone requirement
            if comp.zone is None:
                continue

            # Check if component is in its assigned zone
            try:
                required_zone = board.get_zone(comp.zone)
            except KeyError:
                # Zone doesn't exist in board definition
                issues.append(
                    GeometricViolation(
                        severity=ValidationSeverity.WARNING,
                        code="GEO_ZONE_UNDEFINED",
                        message=f"Component {comp.ref} requires zone '{comp.zone}' which is not defined",
                        component_refs=[comp.ref],
                        location=(x, y),
                        details={"required_zone": comp.zone},
                        violation_type=ViolationType.ZONE,
                    )
                )
                continue

            if not required_zone.contains_point(x, y):
                violation_count += 1

                # Find actual zone if any
                actual_zone = board.get_zone_for_point(x, y)
                actual_zone_name = actual_zone.name if actual_zone else "outside all zones"

                issues.append(
                    GeometricViolation(
                        severity=ValidationSeverity.ERROR,
                        code="GEO_ZONE_VIOLATION",
                        message=f"Component {comp.ref} should be in zone '{comp.zone}' but is in '{actual_zone_name}'",
                        component_refs=[comp.ref],
                        location=(x, y),
                        details={
                            "required_zone": comp.zone,
                            "actual_zone": actual_zone_name,
                        },
                        violation_type=ViolationType.ZONE,
                    )
                )

        return issues, violation_count

    def _check_keepouts(
        self,
        positions: Array,
        rotations: Array,
        widths: Array,
        heights: Array,
        netlist: Netlist,
        board: Board,
    ) -> Tuple[List[GeometricViolation], int]:
        """Check for components in keepout regions or too close to mounting holes."""
        issues = []
        violation_count = 0

        n = positions.shape[0]

        for i in range(n):
            pos = positions[i]
            x, y = float(pos[0]), float(pos[1])
            comp = netlist.components[i]

            # Get rotated bounds
            rot_one_hot = rotations[i]
            rw, rh = get_rotated_bounds(float(widths[i]), float(heights[i]), rot_one_hot)
            half_w, half_h = rw / 2, rh / 2

            # Component bounding box
            comp_min_x = x - half_w
            comp_max_x = x + half_w
            comp_min_y = y - half_h
            comp_max_y = y + half_h

            # Check rectangular keepouts
            for keepout in board.keepout_regions:
                kx_min, ky_min, kx_max, ky_max = keepout

                # Check for intersection
                if (
                    comp_max_x > kx_min
                    and comp_min_x < kx_max
                    and comp_max_y > ky_min
                    and comp_min_y < ky_max
                ):
                    violation_count += 1
                    issues.append(
                        GeometricViolation(
                            severity=ValidationSeverity.ERROR,
                            code="GEO_KEEPOUT",
                            message=f"Component {comp.ref} overlaps with keepout region",
                            component_refs=[comp.ref],
                            location=(x, y),
                            details={
                                "keepout_bounds": keepout,
                            },
                            violation_type=ViolationType.KEEPOUT,
                        )
                    )

            # Check mounting holes
            for hole in board.mounting_holes:
                hx, hy = hole.position

                # Distance from component center to hole center
                dist_to_hole = ((x - hx) ** 2 + (y - hy) ** 2) ** 0.5

                # Minimum distance considering component size and keepout radius
                min_dist = max(half_w, half_h) + hole.keepout_radius

                if dist_to_hole < min_dist:
                    violation_count += 1
                    shortage = min_dist - dist_to_hole
                    issues.append(
                        GeometricViolation(
                            severity=ValidationSeverity.ERROR,
                            code="GEO_MOUNTING_HOLE",
                            message=f"Component {comp.ref} is {shortage:.2f}mm too close to mounting hole at ({hx}, {hy})",
                            component_refs=[comp.ref],
                            location=(x, y),
                            details={
                                "hole_position": (hx, hy),
                                "distance_to_hole": dist_to_hole,
                                "required_distance": min_dist,
                            },
                            violation_type=ViolationType.MOUNTING_HOLE,
                            required_clearance=min_dist,
                            actual_distance=dist_to_hole,
                        )
                    )

        return issues, violation_count


def validate_placement(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    hv_lv_clearance: float = 10.0,
) -> ValidationResult:
    """
    Convenience function to run geometric validation.

    Args:
        state: Current placement state.
        netlist: Component netlist.
        board: Board definition.
        hv_lv_clearance: Required HV-LV clearance in mm.

    Returns:
        ValidationResult with any violations found.
    """
    validator = GeometricValidator(hv_lv_clearance=hv_lv_clearance)
    return validator.validate(state, netlist, board)
