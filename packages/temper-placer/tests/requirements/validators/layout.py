"""
Layout Review Checklist validation functions.

These functions check if a PCB layout meets REQ-REV-02: Layout Review Checklist
requirements for board dimensions, layer stack, critical loops, and ground plane integrity.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum


class LayoutViolationType(Enum):
    """Types of layout violations."""

    BOARD_DIMENSIONS = "board_dimensions"
    LAYER_STACK = "layer_stack"
    CRITICAL_LOOP = "critical_loop"
    GROUND_PLANE = "ground_plane"
    CLEARANCE_CREEPAGE = "clearance_creepage"


@dataclass
class LayoutViolation:
    """A layout review checklist violation."""

    code: str
    message: str
    violation_type: LayoutViolationType
    location: Optional[Tuple[float, float]] = None
    severity: str = "error"  # error, warning, critical
    details: Optional[Dict[str, Any]] = None


@dataclass
class LayoutReviewResult:
    """Result of layout review checklist validation."""

    passed: bool
    violations: List[LayoutViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "critical")


@dataclass
class BoardSpecification:
    """Board specification for validation."""

    width: float = 100.0  # mm
    height: float = 150.0  # mm
    corner_radius: float = 3.0  # mm
    thickness: float = 1.6  # mm
    mounting_hole_diameter: float = 3.2  # mm
    mounting_hole_offset: float = 5.0  # mm from edge
    mounting_hole_keepout: float = 3.0  # mm radius


@dataclass
class LayerStackSpecification:
    """Layer stack specification for validation."""

    layer_count: int = 4
    outer_copper_weight: float = 2.0  # oz
    inner_copper_weight: float = 1.0  # oz
    controlled_impedance: bool = False


@dataclass
class CriticalLoopSpecification:
    """Critical loop area specifications."""

    dc_bus_max_area: float = 5.0  # cm²
    gate_drive_max_area: float = 2.0  # cm²
    buck_sw_max_area: float = 1.0  # cm²
    bootstrap_minimized: bool = True
    ct_burden_minimized: bool = True


@dataclass
class GroundPlaneSpecification:
    """Ground plane integrity specifications."""

    max_slot_length: float = 30.0  # mm
    via_stitching_spacing: float = 5.0  # mm
    star_ground_required: bool = True
    ground_separation_required: bool = True


@dataclass
class ClearanceSpecification:
    """Clearance and creepage specifications."""

    hv_lv_clearance: float = 6.0  # mm
    hv_lv_creepage: float = 8.0  # mm
    isolation_slots_required: bool = True


def check_board_dimensions(board, spec: BoardSpecification) -> LayoutReviewResult:
    """
    Check board outline and mechanical constraints.

    Args:
        board: Board object with dimensions and mounting holes
        spec: Board specification to validate against

    Returns:
        LayoutReviewResult with violations found
    """
    violations = []

    # Check board dimensions
    if hasattr(board, "width") and abs(board.width - spec.width) > 0.1:
        violations.append(
            LayoutViolation(
                code="BOARD-001",
                message=f"Board width {board.width}mm != specified {spec.width}mm",
                violation_type=LayoutViolationType.BOARD_DIMENSIONS,
                severity="error",
                details={"actual": board.width, "specified": spec.width},
            )
        )

    if hasattr(board, "height") and abs(board.height - spec.height) > 0.1:
        violations.append(
            LayoutViolation(
                code="BOARD-002",
                message=f"Board height {board.height}mm != specified {spec.height}mm",
                violation_type=LayoutViolationType.BOARD_DIMENSIONS,
                severity="error",
                details={"actual": board.height, "specified": spec.height},
            )
        )

    # Check corner radii (if available in board geometry)
    if hasattr(board, "corner_radius") and abs(board.corner_radius - spec.corner_radius) > 0.1:
        violations.append(
            LayoutViolation(
                code="BOARD-003",
                message=f"Corner radius {board.corner_radius}mm != specified {spec.corner_radius}mm",
                violation_type=LayoutViolationType.BOARD_DIMENSIONS,
                severity="warning",
                details={"actual": board.corner_radius, "specified": spec.corner_radius},
            )
        )

    # Check mounting holes
    if hasattr(board, "mounting_holes") and board.mounting_holes:
        for i, hole in enumerate(board.mounting_holes):
            # Check hole diameter
            if abs(hole.diameter - spec.mounting_hole_diameter) > 0.1:
                violations.append(
                    LayoutViolation(
                        code="BOARD-004",
                        message=f"Mounting hole {i} diameter {hole.diameter}mm != specified {spec.mounting_hole_diameter}mm",
                        violation_type=LayoutViolationType.BOARD_DIMENSIONS,
                        location=hole.position,
                        severity="error",
                        details={
                            "hole_index": i,
                            "actual": hole.diameter,
                            "specified": spec.mounting_hole_diameter,
                        },
                    )
                )

            # Check hole offset from edge (simplified check)
            expected_offset = spec.mounting_hole_offset
            if hasattr(hole, "position"):
                x, y = hole.position
                # Check if hole is approximately 5mm from edge
                if (
                    x < expected_offset - 1.0
                    or x > board.width - expected_offset + 1.0
                    or y < expected_offset - 1.0
                    or y > board.height - expected_offset + 1.0
                ):
                    violations.append(
                        LayoutViolation(
                            code="BOARD-005",
                            message=f"Mounting hole {i} not at correct offset from edge",
                            violation_type=LayoutViolationType.BOARD_DIMENSIONS,
                            location=hole.position,
                            severity="warning",
                            details={
                                "hole_index": i,
                                "position": hole.position,
                                "expected_offset": expected_offset,
                            },
                        )
                    )

            # Check keepout radius
            if (
                hasattr(hole, "keepout_radius")
                and abs(hole.keepout_radius - spec.mounting_hole_keepout) > 0.1
            ):
                violations.append(
                    LayoutViolation(
                        code="BOARD-006",
                        message=f"Mounting hole {i} keepout {hole.keepout_radius}mm != specified {spec.mounting_hole_keepout}mm",
                        violation_type=LayoutViolationType.BOARD_DIMENSIONS,
                        location=hole.position,
                        severity="warning",
                        details={
                            "hole_index": i,
                            "actual": hole.keepout_radius,
                            "specified": spec.mounting_hole_keepout,
                        },
                    )
                )

    # Check board thickness (if available)
    if hasattr(board, "thickness") and abs(board.thickness - spec.thickness) > 0.05:
        violations.append(
            LayoutViolation(
                code="BOARD-007",
                message=f"Board thickness {board.thickness}mm != specified {spec.thickness}mm",
                violation_type=LayoutViolationType.BOARD_DIMENSIONS,
                severity="error",
                details={"actual": board.thickness, "specified": spec.thickness},
            )
        )

    return LayoutReviewResult(
        passed=len([v for v in violations if v.severity == "error"]) == 0, violations=violations
    )


def check_layer_stack(board, spec: LayerStackSpecification) -> LayoutReviewResult:
    """
    Check layer stackup verification.

    Args:
        board: Board object with layer stack information
        spec: Layer stack specification to validate against

    Returns:
        LayoutReviewResult with violations found
    """
    violations = []

    # Check if board has layer stack information
    if not hasattr(board, "layer_stack"):
        violations.append(
            LayoutViolation(
                code="LAYER-001",
                message="Board layer stack information not available",
                violation_type=LayoutViolationType.LAYER_STACK,
                severity="error",
            )
        )
        return LayoutReviewResult(passed=False, violations=violations)

    layer_stack = board.layer_stack

    # Check layer count
    if len(layer_stack.layers) != spec.layer_count:
        violations.append(
            LayoutViolation(
                code="LAYER-002",
                message=f"Layer count {len(layer_stack.layers)} != specified {spec.layer_count}",
                violation_type=LayoutViolationType.LAYER_STACK,
                severity="error",
                details={"actual": len(layer_stack.layers), "specified": spec.layer_count},
            )
        )

    # Check copper weights for outer layers
    if len(layer_stack.layers) >= 2:
        top_layer = layer_stack.layers[0]
        if abs(top_layer.copper_weight - spec.outer_copper_weight) > 0.1:
            violations.append(
                LayoutViolation(
                    code="LAYER-003",
                    message=f"Top layer copper weight {top_layer.copper_weight}oz != specified {spec.outer_copper_weight}oz",
                    violation_type=LayoutViolationType.LAYER_STACK,
                    severity="error",
                    details={
                        "actual": top_layer.copper_weight,
                        "specified": spec.outer_copper_weight,
                    },
                )
            )

        bottom_layer = layer_stack.layers[-1]
        if abs(bottom_layer.copper_weight - spec.outer_copper_weight) > 0.1:
            violations.append(
                LayoutViolation(
                    code="LAYER-004",
                    message=f"Bottom layer copper weight {bottom_layer.copper_weight}oz != specified {spec.outer_copper_weight}oz",
                    violation_type=LayoutViolationType.LAYER_STACK,
                    severity="error",
                    details={
                        "actual": bottom_layer.copper_weight,
                        "specified": spec.outer_copper_weight,
                    },
                )
            )

    # Check copper weights for inner layers
    if len(layer_stack.layers) >= 4:
        for i, layer in enumerate(layer_stack.layers[1:-1], 1):
            if abs(layer.copper_weight - spec.inner_copper_weight) > 0.1:
                violations.append(
                    LayoutViolation(
                        code="LAYER-005",
                        message=f"Inner layer {i} copper weight {layer.copper_weight}oz != specified {spec.inner_copper_weight}oz",
                        violation_type=LayoutViolationType.LAYER_STACK,
                        severity="error",
                        details={
                            "layer_index": i,
                            "actual": layer.copper_weight,
                            "specified": spec.inner_copper_weight,
                        },
                    )
                )

    # Check board thickness
    if hasattr(layer_stack, "thickness") and abs(layer_stack.thickness - 1.6) > 0.05:
        violations.append(
            LayoutViolation(
                code="LAYER-006",
                message=f"Board thickness {layer_stack.thickness}mm != specified 1.6mm",
                violation_type=LayoutViolationType.LAYER_STACK,
                severity="error",
                details={"actual": layer_stack.thickness, "specified": 1.6},
            )
        )

    # Check controlled impedance requirement
    if spec.controlled_impedance and not hasattr(board, "controlled_impedance"):
        violations.append(
            LayoutViolation(
                code="LAYER-007",
                message="Controlled impedance required but not specified",
                violation_type=LayoutViolationType.LAYER_STACK,
                severity="warning",
            )
        )

    return LayoutReviewResult(
        passed=len([v for v in violations if v.severity == "error"]) == 0, violations=violations
    )


def check_critical_loop_areas(placement, loops) -> LayoutReviewResult:
    """
    Check critical loop areas per REQ-ELEC-06.

    Args:
        placement: Placement state with component positions
        loops: Dictionary of loop areas to check

    Returns:
        LayoutReviewResult with violations found
    """
    violations = []
    spec = CriticalLoopSpecification()

    # Check DC bus loop area
    if "dc_bus" in loops:
        dc_bus_area = loops["dc_bus"]
        if dc_bus_area > spec.dc_bus_max_area:
            violations.append(
                LayoutViolation(
                    code="LOOP-001",
                    message=f"DC bus loop area {dc_bus_area}cm² exceeds maximum {spec.dc_bus_max_area}cm²",
                    violation_type=LayoutViolationType.CRITICAL_LOOP,
                    severity="critical",
                    details={"actual": dc_bus_area, "maximum": spec.dc_bus_max_area},
                )
            )

    # Check gate drive loop areas
    if "gate_drive" in loops:
        for gate_net, area in loops["gate_drive"].items():
            if area > spec.gate_drive_max_area:
                violations.append(
                    LayoutViolation(
                        code="LOOP-002",
                        message=f"Gate drive loop {gate_net} area {area}cm² exceeds maximum {spec.gate_drive_max_area}cm²",
                        violation_type=LayoutViolationType.CRITICAL_LOOP,
                        severity="critical",
                        details={
                            "net": gate_net,
                            "actual": area,
                            "maximum": spec.gate_drive_max_area,
                        },
                    )
                )

    # Check buck converter switching loop
    if "buck_sw" in loops:
        buck_sw_area = loops["buck_sw"]
        if buck_sw_area > spec.buck_sw_max_area:
            violations.append(
                LayoutViolation(
                    code="LOOP-003",
                    message=f"Buck converter SW loop area {buck_sw_area}cm² exceeds maximum {spec.buck_sw_max_area}cm²",
                    violation_type=LayoutViolationType.CRITICAL_LOOP,
                    severity="critical",
                    details={"actual": buck_sw_area, "maximum": spec.buck_sw_max_area},
                )
            )

    # Check bootstrap loop minimization
    if "bootstrap" in loops and spec.bootstrap_minimized:
        bootstrap_area = loops["bootstrap"]
        # Bootstrap loop should be very small - flag if > 0.5 cm²
        if bootstrap_area > 0.5:
            violations.append(
                LayoutViolation(
                    code="LOOP-004",
                    message=f"Bootstrap loop area {bootstrap_area}cm² should be minimized (<0.5cm²)",
                    violation_type=LayoutViolationType.CRITICAL_LOOP,
                    severity="warning",
                    details={"actual": bootstrap_area, "recommended_max": 0.5},
                )
            )

    # Check CT burden loop minimization
    if "ct_burden" in loops and spec.ct_burden_minimized:
        ct_burden_area = loops["ct_burden"]
        # CT burden loop should be small - flag if > 1.0 cm²
        if ct_burden_area > 1.0:
            violations.append(
                LayoutViolation(
                    code="LOOP-005",
                    message=f"CT burden loop area {ct_burden_area}cm² should be minimized (<1.0cm²)",
                    violation_type=LayoutViolationType.CRITICAL_LOOP,
                    severity="warning",
                    details={"actual": ct_burden_area, "recommended_max": 1.0},
                )
            )

    return LayoutReviewResult(
        passed=len([v for v in violations if v.severity in ["error", "critical"]]) == 0,
        violations=violations,
    )


def check_ground_plane_integrity(ground_plane) -> LayoutReviewResult:
    """
    Check ground plane integrity per REQ-EMC-01.

    Args:
        ground_plane: Ground plane geometry and connectivity information

    Returns:
        LayoutReviewResult with violations found
    """
    violations = []
    spec = GroundPlaneSpecification()

    # Check for slots > 30mm in ground plane
    if "slots" in ground_plane:
        for i, slot in enumerate(ground_plane["slots"]):
            if "length" in slot and slot["length"] > spec.max_slot_length:
                violations.append(
                    LayoutViolation(
                        code="GND-001",
                        message=f"Ground plane slot {i} length {slot['length']}mm exceeds maximum {spec.max_slot_length}mm",
                        violation_type=LayoutViolationType.GROUND_PLANE,
                        severity="error",
                        location=slot.get("center"),
                        details={
                            "slot_index": i,
                            "actual": slot["length"],
                            "maximum": spec.max_slot_length,
                        },
                    )
                )

    # Check signal traces over solid ground
    if "signal_over_ground" in ground_plane:
        for trace in ground_plane["signal_over_ground"]:
            if not trace.get("has_ground_reference", True):
                violations.append(
                    LayoutViolation(
                        code="GND-002",
                        message=f"Signal trace {trace.get('id', 'unknown')} lacks ground reference",
                        violation_type=LayoutViolationType.GROUND_PLANE,
                        severity="warning",
                        location=trace.get("center"),
                        details={"trace_id": trace.get("id")},
                    )
                )

    # Check star ground point implementation
    if spec.star_ground_required:
        if not ground_plane.get("has_star_ground", False):
            violations.append(
                LayoutViolation(
                    code="GND-003",
                    message="Star ground point not implemented",
                    violation_type=LayoutViolationType.GROUND_PLANE,
                    severity="warning",
                )
            )

    # Check via stitching at boundaries
    if "boundary_vias" in ground_plane:
        boundary_vias = ground_plane["boundary_vias"]
        if len(boundary_vias) == 0:
            violations.append(
                LayoutViolation(
                    code="GND-004",
                    message="No via stitching found at ground plane boundaries",
                    violation_type=LayoutViolationType.GROUND_PLANE,
                    severity="warning",
                )
            )
        else:
            # Check via spacing (simplified check)
            via_spacing = boundary_vias.get("avg_spacing", 0)
            if via_spacing > spec.via_stitching_spacing:
                violations.append(
                    LayoutViolation(
                        code="GND-005",
                        message=f"Via stitching spacing {via_spacing}mm exceeds recommended {spec.via_stitching_spacing}mm",
                        violation_type=LayoutViolationType.GROUND_PLANE,
                        severity="warning",
                        details={"actual": via_spacing, "recommended": spec.via_stitching_spacing},
                    )
                )

    # Check ground plane separation (PGND/CGND/ISOGND)
    if spec.ground_separation_required:
        if not ground_plane.get("has_proper_separation", False):
            violations.append(
                LayoutViolation(
                    code="GND-006",
                    message="Ground plane separation (PGND/CGND/ISOGND) not properly implemented",
                    violation_type=LayoutViolationType.GROUND_PLANE,
                    severity="error",
                )
            )

    return LayoutReviewResult(
        passed=len([v for v in violations if v.severity == "error"]) == 0, violations=violations
    )


def check_clearance_and_creepage(board, spec: ClearanceSpecification) -> LayoutReviewResult:
    """
    Check clearance and creepage requirements per REQ-SAFE-01.

    Args:
        board: Board object with clearance information
        spec: Clearance specification to validate against

    Returns:
        LayoutReviewResult with violations found
    """
    violations = []

    # Check HV to LV clearance
    if hasattr(board, "clearance_violations"):
        for violation in board.clearance_violations:
            if violation.get("type") == "hv_lv_clearance":
                actual_clearance = violation.get("clearance", 0)
                if actual_clearance < spec.hv_lv_clearance:
                    violations.append(
                        LayoutViolation(
                            code="CLEAR-001",
                            message=f"HV-LV clearance {actual_clearance}mm < required {spec.hv_lv_clearance}mm",
                            violation_type=LayoutViolationType.CLEARANCE_CREEPAGE,
                            severity="critical",
                            location=violation.get("location"),
                            details={"actual": actual_clearance, "required": spec.hv_lv_clearance},
                        )
                    )

    # Check HV to LV creepage
    if hasattr(board, "creepage_violations"):
        for violation in board.creepage_violations:
            if violation.get("type") == "hv_lv_creepage":
                actual_creepage = violation.get("creepage", 0)
                if actual_creepage < spec.hv_lv_creepage:
                    violations.append(
                        LayoutViolation(
                            code="CLEAR-002",
                            message=f"HV-LV creepage {actual_creepage}mm < required {spec.hv_lv_creepage}mm",
                            violation_type=LayoutViolationType.CLEARANCE_CREEPAGE,
                            severity="critical",
                            location=violation.get("location"),
                            details={"actual": actual_creepage, "required": spec.hv_lv_creepage},
                        )
                    )

    # Check isolation slots
    if spec.isolation_slots_required:
        if not hasattr(board, "isolation_slots") or len(board.isolation_slots) == 0:
            violations.append(
                LayoutViolation(
                    code="CLEAR-003",
                    message="Isolation slots not found for HV-LV separation",
                    violation_type=LayoutViolationType.CLEARANCE_CREEPAGE,
                    severity="error",
                )
            )

    # Check UCC21550 barrier respect
    if hasattr(board, "component_barriers"):
        barriers = board.component_barriers
        if "UCC21550" in barriers:
            ucc_barrier = barriers["UCC21550"]
            if not ucc_barrier.get("respected", False):
                violations.append(
                    LayoutViolation(
                        code="CLEAR-004",
                        message="UCC21550 isolation barrier not respected",
                        violation_type=LayoutViolationType.CLEARANCE_CREEPAGE,
                        severity="critical",
                        details={"barrier_info": ucc_barrier},
                    )
                )

    # Check ADUM1250 barrier respect
    if "ADUM1250" in barriers:
        adum_barrier = barriers["ADUM1250"]
        if not adum_barrier.get("respected", False):
            violations.append(
                LayoutViolation(
                    code="CLEAR-005",
                    message="ADUM1250 isolation barrier not respected",
                    violation_type=LayoutViolationType.CLEARANCE_CREEPAGE,
                    severity="critical",
                    details={"barrier_info": adum_barrier},
                )
            )

    return LayoutReviewResult(
        passed=len([v for v in violations if v.severity in ["error", "critical"]]) == 0,
        violations=violations,
    )
