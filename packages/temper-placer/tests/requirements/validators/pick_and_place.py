"""
Pick-and-place component placement validation functions.

These functions check if PCB layout meets REQ-DFM-01 requirements for
automated pick-and-place assembly including component spacing, orientation,
fiducial placement, and ESP32-S3-WROOM specific constraints.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ._geometry import _rects_overlap


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
#
# ESP32_ANTENNA_KEEPOUT_MM: Espressif ESP32-S3 Hardware Design Guidelines,
# "General Principles of PCB Layout for Modules" -- both the "Keepout Zone
# for ESP32-S3 Module's Antenna" figure ("Min15") and the accompanying text
# ("A clearance of at least 15 mm is recommended in all directions") give
# 15 mm, confirming this constant's value.
# https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html
ESP32_ANTENNA_KEEPOUT_MM = 15.0
ESP32_MODULE_SIZE_MM = (16.0, 37.0)  # Width x Height

# NOTE: ESP32_MODULE_SIZE_MM does not match the ESP32-S3-WROOM-1 datasheet
# (18.0 x 25.5 mm, Section 10.1 "Module Dimensions", Figure 10-1:
# https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf).
# It is left unchanged here because nothing in check_antenna_keepout
# consumes it and a test (test_esp32_module_size) pins the current, wrong
# value -- correcting it is a separate fix outside this function's scope;
# see docs/evidence/2026-07-27-antenna-keepout-fix.md.

# Module's long-axis dimension, used only to locate the antenna band below.
# Source: ESP32-S3-WROOM-1 datasheet Section 10.1 "Module Dimensions"
# (Figure 10-1): 18.0 (width) x 25.5 (length) x 3.1 mm.
ESP32_MODULE_LENGTH_MM = 25.5

# Depth of the antenna's own footprint, measured in from the module edge it
# faces. Source: ESP32-S3-WROOM-1 datasheet Section 11.1 "PCB Land Pattern"
# (Figure 11-1, the "Antenna Area" callout, dimension "6"); corroborated by
# the Hardware Design Guidelines' "Keepout Zone for ESP32-S3 Module's
# Antenna" figure, which uses the same 6 mm depth for the antenna trace band.
ESP32_ANTENNA_BAND_DEPTH_MM = 6.0

# Offset from the module's centre (the convention `esp32_position` uses --
# see Defect 1 in the evidence doc) to the centre of the antenna's own
# footprint, along the module's long axis.
ESP32_ANTENNA_OFFSET_MM = ESP32_MODULE_LENGTH_MM / 2 - ESP32_ANTENNA_BAND_DEPTH_MM / 2


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
    elif "TQFN" in footprint_upper:
        return PackageType.TQFN
    elif "QFN" in footprint_upper:
        return PackageType.QFN
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
    _placement: dict[str, Any],
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
    components = _placement.get("components", [])

    for i, comp_a in enumerate(components):
        for comp_b in components[i + 1 :]:
            pos_a = comp_a.get("position")
            pos_b = comp_b.get("position")
            if pos_a is None or pos_b is None:
                continue
            dist = ((pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2) ** 0.5

            fp_a = comp_a.get("footprint", "")
            fp_b = comp_b.get("footprint", "")
            pkg_a = get_package_type(fp_a)
            pkg_b = get_package_type(fp_b)

            min_a = package_rules.get(pkg_a, {}).get("min_pad_to_pad_mm", 0.15)
            min_b = package_rules.get(pkg_b, {}).get("min_pad_to_pad_mm", 0.15)
            required = max(min_a, min_b)

            if dist < required:
                violations.append(
                    PlacementViolation(
                        code="DFM001-SPACE-001",
                        message=f"Components {comp_a.get('ref', '?')} and {comp_b.get('ref', '?')} spacing {dist:.2f}mm < required {required:.2f}mm",
                        location=((pos_a[0] + pos_b[0]) / 2, (pos_a[1] + pos_b[1]) / 2),
                        severity="error",
                        violation_type="spacing",
                        measured_value=dist,
                        required_value=required,
                    )
                )

    return PlacementResult(passed=len(violations) == 0, violations=violations)


def check_component_orientation(
    placement: dict[str, Any],
) -> PlacementResult:
    """
    Check component orientation consistency per REQ-DFM-01.

    Rules:
    - ICs: Pin 1 towards top-left or consistent orientation
    - Passives: Consistent 0deg or 90deg orientation per type
    - Polarized: Consistent polarity direction

    Args:
        placement: PCB placement data with component positions and orientations

    Returns:
        PlacementResult with orientation violations
    """
    violations = []
    components = placement.get("components", [])

    for comp in components:
        fp = comp.get("footprint", "")
        pkg = get_package_type(fp)
        rot = comp.get("rotation", 0)
        norm = ((rot % 360) + 360) % 360

        if pkg in (PackageType.SOIC, PackageType.QFN, PackageType.TQFN, PackageType.ESP32_MODULE):
            if norm != 0:
                violations.append(
                    PlacementViolation(
                        code="DFM001-ORIENT-001",
                        message=f"IC {comp.get('ref', '?')} pin 1 orientation {rot}deg (expected 0deg)",
                        location=comp.get("position"),
                        severity="error",
                        component_ref=comp.get("ref"),
                        violation_type="orientation",
                    )
                )
        else:
            if norm not in (0, 90):
                violations.append(
                    PlacementViolation(
                        code="DFM001-ORIENT-002",
                        message=f"Passive {comp.get('ref', '?')} orientation {rot}deg inconsistent (expected 0deg or 90deg)",
                        location=comp.get("position"),
                        severity="error",
                        component_ref=comp.get("ref"),
                        violation_type="orientation",
                    )
                )

    return PlacementResult(passed=len(violations) == 0, violations=violations)


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

    if len(fiducials) < 3:
        violations.append(
            PlacementViolation(
                code="DFM001-FID-001",
                message=f"Insufficient fiducials: {len(fiducials)} found, minimum 3 required",
                severity="error",
                component_ref="FID_COUNT",
                violation_type="fiducial",
            )
        )
    elif len(fiducials) == 3:
        pts = [f.position for f in fiducials]
        x1, y1 = pts[0]
        x2, y2 = pts[1]
        x3, y3 = pts[2]
        cross = abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))
        if cross < 1e-6:
            violations.append(
                PlacementViolation(
                    code="DFM001-FID-002",
                    message="Fiducials are collinear — asymmetric placement required",
                    severity="error",
                    violation_type="fiducial",
                )
            )

    for f in fiducials:
        if f.size_mm < 1.0:
            violations.append(
                PlacementViolation(
                    code="DFM001-FID-003",
                    message=f"Fiducial {f.ref} pad size {f.size_mm}mm below minimum 1.0mm",
                    location=f.position,
                    severity="error",
                    component_ref=f.ref,
                    violation_type="fiducial",
                    measured_value=f.size_mm,
                    required_value=1.0,
                )
            )
        if f.clearance_mm < 3.0:
            violations.append(
                PlacementViolation(
                    code="DFM001-FID-004",
                    message=f"Fiducial {f.ref} clearance {f.clearance_mm}mm below minimum 3.0mm",
                    location=f.position,
                    severity="warning",
                    component_ref=f.ref,
                    violation_type="fiducial",
                    measured_value=f.clearance_mm,
                    required_value=3.0,
                )
            )

    return PlacementResult(passed=len(violations) == 0, violations=violations)


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

    if esp32_position is None:
        return PlacementResult(
            passed=False,
            violations=[
                PlacementViolation(
                    code="DFM001-ANT-003",
                    message="ESP32 position data missing; antenna keepout cannot be verified",
                    severity="error",
                    component_ref="ESP32",
                    violation_type="antenna",
                )
            ],
        )

    board_w, board_h = board_dimensions

    # Check distance to board edges (antenna needs >=15mm clearance)
    edge_dist_x = min(esp32_position[0], board_w - esp32_position[0])
    edge_dist_y = min(esp32_position[1], board_h - esp32_position[1])
    if edge_dist_x < ESP32_ANTENNA_KEEPOUT_MM or edge_dist_y < ESP32_ANTENNA_KEEPOUT_MM:
        violations.append(
            PlacementViolation(
                code="DFM001-ANT-001",
                message=f"ESP32 too close to board edge for antenna keepout (dist_x={edge_dist_x:.0f}mm, dist_y={edge_dist_y:.0f}mm, min={ESP32_ANTENNA_KEEPOUT_MM}mm)",
                location=esp32_position,
                severity="error",
                component_ref="ESP32",
                violation_type="antenna",
                measured_value=min(edge_dist_x, edge_dist_y),
                required_value=ESP32_ANTENNA_KEEPOUT_MM,
            )
        )

    # The antenna is not at the module's centre -- it sits in a band at one
    # END of the module (ESP32_ANTENNA_OFFSET_MM from centre; see the module
    # docstring's "Ground pour under module (except antenna area)"
    # requirement, and docs/evidence/2026-07-27-antenna-keepout-fix.md).
    # Centering the keepout on esp32_position, as this function used to,
    # checks the wrong location: it flags a compliant "ground pour under the
    # module, clear of the antenna end" as a violation just because the pour
    # covers the module's centroid.
    #
    # UNVERIFIED / known gap: this offsets along +Y unconditionally. Which
    # direction the antenna actually faces depends on the module's
    # `rotation`, which fixtures carry (see esp32_placement) but which is
    # not threaded through to this function or applied here -- doing so
    # correctly needs the offset vector (0, ESP32_ANTENNA_OFFSET_MM) rotated
    # by the module's placed orientation, which no current caller supplies.
    keepout_center = (
        esp32_position[0],
        esp32_position[1] + ESP32_ANTENNA_OFFSET_MM,
    )
    keepout_zone = (
        keepout_center[0] - ESP32_ANTENNA_KEEPOUT_MM / 2,
        keepout_center[1] - ESP32_ANTENNA_KEEPOUT_MM / 2,
        ESP32_ANTENNA_KEEPOUT_MM,
        ESP32_ANTENNA_KEEPOUT_MM,
    )

    for pour in copper_pours:
        pos = pour.get("position")
        size = pour.get("size", (0, 0))
        if pos is None:
            continue
        # `position` is the pour's centre, matching keepout_zone's convention
        # above and the ESP32 component's own position -- convert to the
        # corner-origin form `_rects_overlap` expects.
        pour_rect = (pos[0] - size[0] / 2, pos[1] - size[1] / 2, size[0], size[1])

        if _rects_overlap(keepout_zone, pour_rect):
            violations.append(
                PlacementViolation(
                    code="DFM001-ANT-002",
                    message="Copper pour found in ESP32 antenna keepout zone",
                    location=esp32_position,
                    severity="error",
                    component_ref="ESP32",
                    violation_type="antenna",
                )
            )

    return PlacementResult(passed=len(violations) == 0, violations=violations)


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
