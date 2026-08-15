"""
Geometric validation for placement results.

This module provides pure-Python/JAX geometric validation that doesn't depend
on external tools like kiutils. It checks:
- Component overlaps
- Boundary violations (components outside board)
- Clearance violations (HV-LV separation, etc.)
- Zone violations (components in wrong zones)
- Keepout violations (components in keepout regions)

Wave 4 Phase 4: the per-check DECISION compute (overlap severity
classification, boundary edge math, HV-LV clearance classification, keepout
intersection, mounting-hole distance) moved to the Rust kernel
``temper_drc_rs.geometric_validate`` (packages/temper-drc-rs/src/validation.rs).
Design boundaries, argued in-source (see the Rust module and
``packages/temper-drc-rs/VERIFICATION.md``):

- Every geometric primitive stays single-source-of-truth in temper-geometry:
  the pairwise signed box distances (``compute_pairwise_distances``), the
  rotated AABB half-sizes (``get_rotated_bounds``) and the boundary
  predicate (``compute_boundary_violation``) are computed HERE (all already
  Rust) and passed into the kernel — no reimplementation.
- The zone check's predicate (``point_in_zone``) was already Rust; the
  remaining zone logic is Board contract lookup (``get_zone`` /
  ``get_zone_for_point`` — out-of-scope harness/contract) plus message
  building, so ``_check_zones`` stays Python.
- Messages are built here from the Rust-returned numeric fields (the
  rtd_safety precedent): ``str(float)`` formatting (shortest-repr with a
  ``.0`` suffix and exponent thresholds) is a Python library semantic that
  Rust's ``Display`` does not reproduce (``10.0`` vs ``10``). The
  differential compares the full issues INCLUDING messages, so any mutation
  in the numeric decisions is still caught (messages derive from them).
- Location midpoints are computed here from the float32 positions array
  with the same numpy expressions the oracle used (float32 arithmetic).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, TypeAlias

import numpy as np

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.geometry.constraints import (
    compute_boundary_violation,
    point_in_zone,
)
from temper_placer.geometry import (
    compute_pairwise_distances,
)
from temper_placer.geometry.transform import get_rotated_bounds
from temper_placer.validation.base import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    Validator,
)

_RS = None


def _rs() -> Any:
    global _RS
    if _RS is None:
        import temper_drc_rs  # type: ignore[import-untyped]

        _RS = temper_drc_rs
    return _RS


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
        issues: list[ValidationIssue] = []
        metrics: dict = {}

        # Extract component data
        positions = state.positions
        positions.shape[0]

        # Get rotation one-hot vectors (use argmax for discrete)
        rotation_indices = np.argmax(state.rotation_logits, axis=-1)
        rotations = np.eye(4)[rotation_indices]  # (N, 4) one-hot

        # Get component dimensions
        bounds = netlist.get_bounds_array()  # (N, 2)
        widths = bounds[:, 0]
        heights = bounds[:, 1]

        # 1-3, 5: overlap / boundary / clearance / keepout+mounting-hole
        # checks — one kernel call (Rust decision compute over the
        # temper-geometry primitives), then per-kind wrapping below.
        findings, kmetrics = self._run_geometric_kernel(
            positions, rotations, widths, heights, netlist, board
        )
        overlap_issues, overlap_count, total_overlap = self._wrap_overlaps(
            findings, positions, netlist
        )
        issues.extend(overlap_issues)
        metrics["overlap_count"] = overlap_count
        metrics["total_overlap_area"] = float(total_overlap)

        boundary_issues = self._wrap_boundaries(findings, positions, netlist)
        issues.extend(boundary_issues)
        metrics["boundary_violations"] = int(kmetrics["boundary_violations"])

        clearance_issues, clearance_count = self._wrap_clearances(
            findings, positions, netlist
        )
        issues.extend(clearance_issues)
        metrics["clearance_violations"] = clearance_count

        # 4. Check zone violations (stays Python — see module docstring)
        zone_issues, zone_count = self._check_zones(positions, netlist, board)
        issues.extend(zone_issues)
        metrics["zone_violations"] = zone_count

        keepout_issues = self._wrap_keepouts(findings, positions, netlist)
        issues.extend(keepout_issues)
        metrics["keepout_violations"] = int(kmetrics["keepout_violations"])

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

    # ------------------------------------------------------------------
    # Rust-backed decision kernel (temper_drc_rs.geometric_validate)
    #
    # All geometric primitives (pairwise distances, rotated half-sizes,
    # boundary predicate) are computed here via the existing
    # temper-geometry Rust kernels and passed in; the kernel returns
    # structured findings (in the oracle's exact issue order) + metrics.
    # ------------------------------------------------------------------

    def _run_geometric_kernel(
        self,
        positions: Array,
        rotations: Array,
        widths: Array,
        heights: Array,
        netlist: Netlist,
        board: Board,
    ) -> tuple[list[dict], dict]:
        n = positions.shape[0]

        # Pairwise signed box distances — one call, shared by the overlap
        # and clearance checks (the oracle computed the matrix twice).
        rects = np.column_stack([positions, widths[:, None], heights[:, None]])
        rects_flat = rects.ravel().tolist()
        distances = np.array(compute_pairwise_distances(rects_flat)).reshape(n, n)

        # Rotated half-sizes + boundary predicate (temper-geometry, Rust).
        half_widths: list[float] = []
        half_heights: list[float] = []
        boundary: list[tuple[float, float, float, float]] = []
        board_x_min, board_y_min = board.origin
        board_x_max = board_x_min + board.width
        board_y_max = board_y_min + board.height
        for i in range(n):
            rot_one_hot = rotations[i]
            rot_idx = (
                int(np.argmax(rot_one_hot))
                if isinstance(rot_one_hot, np.ndarray) and rot_one_hot.ndim == 1
                else 0
            )
            angle_rad = {0: 0.0, 1: np.pi / 2, 2: np.pi, 3: 3 * np.pi / 2}[rot_idx]
            xmi, ymi, xma, yma = get_rotated_bounds(
                float(positions[i, 0]),
                float(positions[i, 1]),
                float(widths[i]),
                float(heights[i]),
                angle_rad,
            )
            rw, rh = xma - xmi, yma - ymi
            half_w, half_h = rw / 2, rh / 2
            half_widths.append(half_w)
            half_heights.append(half_h)

            pos = positions[i]
            bv = compute_boundary_violation(
                position_x=float(pos[0]),
                position_y=float(pos[1]),
                component_half_width=float(half_w),
                component_half_height=float(half_h),
                board_x_min=board_x_min,
                board_y_min=board_y_min,
                board_x_max=board_x_max,
                board_y_max=board_y_max,
            )
            boundary.append((bv.left, bv.right, bv.bottom, bv.top))

        net_classes = [c.net_class for c in netlist.components]
        keepouts = [tuple(float(v) for v in k) for k in board.keepout_regions]
        mounting_holes = [
            (float(h.position[0]), float(h.position[1]), float(h.keepout_radius))
            for h in board.mounting_holes
        ]

        findings, metrics = _rs().geometric_validate(
            positions=[(float(positions[i, 0]), float(positions[i, 1])) for i in range(n)],
            half_widths=half_widths,
            half_heights=half_heights,
            net_classes=net_classes,
            boundary=boundary,
            keepouts=keepouts,
            mounting_holes=mounting_holes,
            distances=distances.ravel().tolist(),
            overlap_threshold=float(self.overlap_threshold),
            min_clearance=float(self.min_clearance),
            hv_lv_clearance=float(self.hv_lv_clearance),
        )
        return findings, metrics

    def _wrap_overlaps(
        self,
        findings: list[dict],
        positions: Array,
        netlist: Netlist,
    ) -> tuple[list[GeometricViolation], int, float]:
        issues = []
        total_overlap = 0.0
        overlap_count = 0
        for f in findings:
            if f["kind"] != "overlap":
                continue
            i, j = f["i"], f["j"]
            comp_i = netlist.components[i]
            comp_j = netlist.components[j]
            overlap_amount = float(f["overlap_amount"])
            dist = float(f["dist"])
            total_overlap += overlap_amount
            overlap_count += 1
            issues.append(
                GeometricViolation(
                    severity=ValidationSeverity[f["severity"]],
                    code=f["code"],
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

    def _wrap_boundaries(
        self,
        findings: list[dict],
        positions: Array,
        netlist: Netlist,
    ) -> list[GeometricViolation]:
        issues = []
        for f in findings:
            if f["kind"] != "boundary":
                continue
            i = f["i"]
            comp = netlist.components[i]
            pos = positions[i]
            edges = [(e[0], float(e[1])) for e in f["edges"]]
            max_violation = float(f["max_violation"])
            edge_names = ", ".join(e[0] for e in edges)
            issues.append(
                GeometricViolation(
                    severity=ValidationSeverity[f["severity"]],
                    code=f["code"],
                    message=f"Component {comp.ref} extends {max_violation:.2f}mm outside board ({edge_names})",
                    component_refs=[comp.ref],
                    location=(float(pos[0]), float(pos[1])),
                    details={
                        "violations": edges,
                        "max_violation_mm": max_violation,
                    },
                    violation_type=ViolationType.BOUNDARY,
                    overlap_amount=max_violation,
                )
            )
        return issues

    def _wrap_clearances(
        self,
        findings: list[dict],
        positions: Array,
        netlist: Netlist,
    ) -> tuple[list[GeometricViolation], int]:
        issues = []
        violation_count = 0
        for f in findings:
            if f["kind"] != "clearance":
                continue
            i, j = f["i"], f["j"]
            comp_i = netlist.components[i]
            comp_j = netlist.components[j]
            dist = float(f["dist"])
            required_clearance = float(f["required_clearance"])
            shortage = float(f["shortage"])
            is_hv_lv_pair = bool(f["is_hv_lv"])
            violation_count += 1

            if is_hv_lv_pair:
                severity = ValidationSeverity.CRITICAL
                code = "GEO_HV_LV_CLEARANCE"
                msg = f"HV-LV clearance violation: {comp_i.ref} ({comp_i.net_class}) and {comp_j.ref} ({comp_j.net_class}) are {dist:.2f}mm apart (need {required_clearance}mm)"
            else:
                severity = (
                    ValidationSeverity.WARNING if dist > 0 else ValidationSeverity.ERROR
                )
                code = "GEO_CLEARANCE"
                msg = f"Clearance warning: {comp_i.ref} and {comp_j.ref} are {dist:.2f}mm apart (recommend {required_clearance}mm)"

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
    ) -> tuple[list[GeometricViolation], int]:
        """Check for components in wrong zones.

        Stays Python: the geometric predicate (``point_in_zone``) is already
        Rust (temper-geometry); the remaining logic is Board contract lookup
        (``get_zone`` / ``get_zone_for_point``) plus message building.
        """
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

            # Use shared predicate to check zone membership
            zone_x_min, zone_y_min, zone_x_max, zone_y_max = required_zone.bounds
            in_zone = point_in_zone(x, y, zone_x_min, zone_y_min, zone_x_max, zone_y_max)

            if not in_zone:
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

    def _wrap_keepouts(
        self,
        findings: list[dict],
        positions: Array,
        netlist: Netlist,
    ) -> list[GeometricViolation]:
        issues = []
        for f in findings:
            kind = f["kind"]
            if kind not in ("keepout", "mounting_hole"):
                continue
            i = f["i"]
            pos = positions[i]
            x, y = float(pos[0]), float(pos[1])
            comp = netlist.components[i]

            if kind == "keepout":
                keepout = tuple(float(v) for v in f["keepout_bounds"])
                issues.append(
                    GeometricViolation(
                        severity=ValidationSeverity.ERROR,
                        code=f["code"],
                        message=f"Component {comp.ref} overlaps with keepout region",
                        component_refs=[comp.ref],
                        location=(x, y),
                        details={
                            "keepout_bounds": keepout,
                        },
                        violation_type=ViolationType.KEEPOUT,
                    )
                )
            else:  # mounting_hole
                hx, hy = (float(v) for v in f["hole_position"])
                dist_to_hole = float(f["distance_to_hole"])
                min_dist = float(f["min_dist"])
                shortage = float(f["shortage"])
                issues.append(
                    GeometricViolation(
                        severity=ValidationSeverity.ERROR,
                        code=f["code"],
                        message=f"Component {comp.ref} is {shortage:.2f}mm too close to mounting hole at ({hx}, {hy})",
                        component_refs=[comp.ref],
                        location=(x, y),
                        details={
                            "hole_position": (hx, hy),
                            "distance_to_hole": dist_to_hole,
                            "required_distance": min_dist,
                        },
                        violation_type=ViolationType.MOUNTING_HOLE,
                        required_clearance=float(min_dist),
                        actual_distance=dist_to_hole,
                    )
                )
        return issues


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
