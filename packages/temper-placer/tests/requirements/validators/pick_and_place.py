"""
Pick-and-place component placement validation functions.

These functions check if PCB layout meets REQ-DFM-01 requirements for
automated pick-and-place assembly including component spacing, orientation,
fiducial placement, and ESP32-S3-WROOM specific constraints.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PackageType(Enum):
    """SMT package types for spacing requirements."""

    R0402 = "R0402"
    C0402 = "C0402"
    R0603 = "R0603"
    C0603 = "C0603"
    R0805 = "R0805"
    C0805 = "C0805"
    SOIC = "SOIC"
    QFN = "QFN"
    TQFN = "TQFN"
    ESP32_MODULE = "ESP32_MODULE"


class ComponentOrientation(Enum):
    """Component orientation options."""

    DEG_0 = 0
    DEG_90 = 90
    DEG_180 = 180
    DEG_270 = 270


@dataclass
class Fiducial:
    """Fiducial marker definition."""

    ref: str
    position: tuple[float, float]
    size_mm: float = 1.0
    mask_opening_mm: float = 2.0
    clearance_mm: float = 3.0
    is_global: bool = True


@dataclass
class PlacementViolation:
    """A pick-and-place placement violation."""

    code: str
    message: str
    location: tuple[float, float] | None = None
    severity: str = "error"  # error, warning
    component_ref: str | None = None
    violation_type: str | None = None  # spacing, orientation, fiducial, antenna
    measured_value: float | None = None
    required_value: float | None = None


@dataclass
class PlacementResult:
    """Result of pick-and-place placement validation."""

    passed: bool
    violations: list[PlacementViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


# REQ-DFM-01 Component Spacing Requirements
SPACING_REQUIREMENTS = {
    PackageType.R0402: {"min_pad_to_pad_mm": 0.15, "recommended_mm": 0.25},
    PackageType.C0402: {"min_pad_to_pad_mm": 0.15, "recommended_mm": 0.25},
    PackageType.R0603: {"min_pad_to_pad_mm": 0.20, "recommended_mm": 0.30},
    PackageType.C0603: {"min_pad_to_pad_mm": 0.20, "recommended_mm": 0.30},
    PackageType.R0805: {"min_pad_to_pad_mm": 0.25, "recommended_mm": 0.35},
    PackageType.C0805: {"min_pad_to_pad_mm": 0.25, "recommended_mm": 0.35},
    PackageType.SOIC: {"min_pad_to_pad_mm": 0.25, "recommended_mm": 0.40},
    PackageType.QFN: {"min_pad_to_pad_mm": 0.25, "recommended_mm": 0.40},
    PackageType.TQFN: {"min_pad_to_pad_mm": 0.25, "recommended_mm": 0.40},
    PackageType.ESP32_MODULE: {"min_pad_to_pad_mm": 1.0, "recommended_mm": 2.0},
}

# SMD to Through-Hole spacing requirements
SMD_TO_THT_MIN_MM = 1.0
SMD_TO_THT_RECOMMENDED_MM = 2.0

# ESP32-S3-WROOM specific requirements
ESP32_ANTENNA_KEEPOUT_MM = 15.0
ESP32_MODULE_SIZE_MM = (16.0, 37.0)  # Width x Height


def get_package_type(footprint: str) -> PackageType:
    """
    Map KiCad footprint to package type for spacing requirements.

    Args:
        footprint: KiCad footprint identifier

    Returns:
        PackageType enum value
    """
    footprint_upper = footprint.upper()

    if "ESP32" in footprint_upper or "WROOM" in footprint_upper:
        return PackageType.ESP32_MODULE
    elif "QFN" in footprint_upper:
        return PackageType.QFN
    elif "TQFN" in footprint_upper:
        return PackageType.TQFN
    elif "SOIC" in footprint_upper:
        return PackageType.SOIC
    elif "0402" in footprint_upper:
        if "R" in footprint_upper or "RES" in footprint_upper:
            return PackageType.R0402
        else:
            return PackageType.C0402
    elif "0603" in footprint_upper:
        if "R" in footprint_upper or "RES" in footprint_upper:
            return PackageType.R0603
        else:
            return PackageType.C0603
    elif "0805" in footprint_upper:
        if "R" in footprint_upper or "RES" in footprint_upper:
            return PackageType.R0805
        else:
            return PackageType.C0805
    else:
        # Default to most restrictive for unknown packages
        return PackageType.QFN


def check_component_spacing(
    placement: dict[str, Any],
    package_rules: dict[PackageType, dict[str, float]] | None = None,
) -> PlacementResult:
    """
    Check minimum spacing between SMD components per REQ-DFM-01.

    Args:
        placement: PCB placement data with component positions and footprints
        package_rules: Optional custom spacing rules (defaults to REQ-DFM-01)

    Returns:
        PlacementResult with spacing violations
    """
    if package_rules is None:
        package_rules = SPACING_REQUIREMENTS

    violations = []

    # TODO: Implement actual spacing validation
    # - Extract component positions and footprints
    # - Calculate pad-to-pad distances
    # - Check against minimum and recommended spacing
    # - Generate violations for insufficient spacing

    raise NotImplementedError("Component spacing validation not yet implemented")


def check_component_orientation(
    placement: dict[str, Any],
) -> PlacementResult:
    """
    Check component orientation consistency per REQ-DFM-01.

    Rules:
    - ICs: Pin 1 towards top-left or consistent orientation
    - Passives: Consistent 0° or 90° orientation per type
    - Polarized: Consistent polarity direction

    Args:
        placement: PCB placement data with component positions and orientations

    Returns:
        PlacementResult with orientation violations
    """
    violations = []

    # TODO: Implement orientation validation
    # - Identify ICs vs passives vs polarized components
    # - Check IC pin 1 orientation consistency
    # - Check passive orientation consistency within areas
    # - Check polarized component polarity consistency

    raise NotImplementedError("Component orientation validation not yet implemented")


def check_fiducial_placement(
    fiducials: list[Fiducial],
    board_dimensions: tuple[float, float] | None = None,
) -> PlacementResult:
    """
    Check fiducial placement per REQ-DFM-01 requirements.

    Requirements:
    - Quantity: 3 minimum (asymmetric placement)
    - Size: 1.0mm diameter copper pad
    - Clearance: 2.0mm keep-out around fiducial
    - Location: Near board corners, not in line

    Args:
        fiducials: List of fiducial definitions
        board_dimensions: Optional (width, height) for edge distance checks

    Returns:
        PlacementResult with fiducial violations
    """
    violations = []

    # TODO: Implement fiducial validation
    # - Check minimum quantity (3)
    # - Check size requirements (1.0mm copper, 2.0mm mask opening)
    # - Check clearance requirements (3.0mm keep-out)
    # - Check asymmetric placement (not collinear)
    # - Check distance from board edges (5.0mm minimum)

    raise NotImplementedError("Fiducial placement validation not yet implemented")


def check_antenna_keepout(
    esp32_position: tuple[float, float],
    copper_pours: list[dict[str, Any]],
    board_dimensions: tuple[float, float],
) -> PlacementResult:
    """
    Check ESP32-S3-WROOM antenna keepout requirements.

    Requirements:
    - Antenna facing board edge (no copper in keep-out)
    - Minimum 15mm to board edge for antenna
    - Ground pour under module (except antenna area)

    Args:
        esp32_position: (x, y) position of ESP32 module
        copper_pours: List of copper pour regions with positions and sizes
        board_dimensions: (width, height) of PCB

    Returns:
        PlacementResult with antenna keepout violations
    """
    violations = []

    # TODO: Implement antenna keepout validation
    # - Determine antenna direction (towards nearest board edge)
    # - Check for copper in 15mm keepout zone
    # - Verify ground pour under module (except antenna area)
    # - Check module position relative to board edges

    raise NotImplementedError("ESP32 antenna keepout validation not yet implemented")


def check_pick_and_place_compliance(
    placement: dict[str, Any],
    fiducials: list[Fiducial],
    board_dimensions: tuple[float, float],
) -> PlacementResult:
    """
    Verify complete REQ-DFM-01 compliance for pick-and-place assembly.

    Args:
        placement: PCB placement data with component positions and footprints
        fiducials: List of fiducial definitions
        board_dimensions: (width, height) of PCB

    Returns:
        PlacementResult with all pick-and-place violations
    """
    violations = []

    # Run all validation checks
    spacing_result = check_component_spacing(placement)
    violations.extend(spacing_result.violations)

    orientation_result = check_component_orientation(placement)
    violations.extend(orientation_result.violations)

    fiducial_result = check_fiducial_placement(fiducials, board_dimensions)
    violations.extend(fiducial_result.violations)

    # Check ESP32 antenna keepout if ESP32 module present
    esp32_found = False
    esp32_position = None

    for component in placement.get("components", []):
        if get_package_type(component.get("footprint", "")) == PackageType.ESP32_MODULE:
            esp32_found = True
            esp32_position = component.get("position")
            break

    if esp32_found and esp32_position:
        copper_pours = placement.get("copper_pours", [])
        antenna_result = check_antenna_keepout(esp32_position, copper_pours, board_dimensions)
        violations.extend(antenna_result.violations)

    passed = len([v for v in violations if v.severity == "error"]) == 0

    return PlacementResult(passed=passed, violations=violations)


def get_spacing_requirements() -> dict[str, dict[str, float]]:
    """
    Get the REQ-DFM-01 component spacing requirements matrix.

    Returns:
        Dictionary with package_type -> spacing requirements
    """
    return {
        package_type.value: requirements
        for package_type, requirements in SPACING_REQUIREMENTS.items()
    }
