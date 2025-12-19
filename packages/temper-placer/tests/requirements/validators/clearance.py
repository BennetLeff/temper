"""
Clearance and creepage distance validation functions.

These functions check if PCB layout meets IEC 60335-2-6 safety requirements
for creepage and clearance distances per REQ-SAFE-01.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class InsulationType(Enum):
    """Insulation type per IEC 60335-2-6."""

    BASIC = "basic"
    REINFORCED = "reinforced"
    FUNCTIONAL = "functional"


class VoltageDomain(Enum):
    """Voltage domains in Temper PCB."""

    MAINS = "MAINS"  # 240VAC (340V peak)
    DC_BUS = "DC_BUS"  # 340VDC (from doubler)
    BOOTSTRAP = "BOOTSTRAP"  # 340VDC (floating)
    LV_CONTROL = "LV_CONTROL"  # 3.3V/5V/12V
    ISOLATED = "ISOLATED"  # Floating


@dataclass
class ClearanceViolation:
    """A clearance or creepage distance violation."""

    code: str
    message: str
    location: tuple[float, float] | None = None
    severity: str = "error"  # error, warning
    boundary: str | None = None
    insulation_type: InsulationType | None = None
    measured_clearance_mm: float | None = None
    measured_creepage_mm: float | None = None
    required_clearance_mm: float | None = None
    required_creepage_mm: float | None = None


@dataclass
class ClearanceResult:
    """Result of clearance/creepage validation."""

    passed: bool
    violations: list[ClearanceViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


# IEC 60335-2-6 Requirements Matrix
IEC60335_REQUIREMENTS = {
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 4.0,
        "design_value_mm": 6.0,
    },
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 8.0,
        "design_value_mm": 10.0,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 4.0,
        "design_value_mm": 6.0,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 8.0,
        "design_value_mm": 10.0,
    },
    (VoltageDomain.MAINS, VoltageDomain.ISOLATED, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 8.0,
        "design_value_mm": 10.0,
    },
    (VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, InsulationType.FUNCTIONAL): {
        "min_clearance_mm": 0.5,
        "min_creepage_mm": 1.0,
        "design_value_mm": 2.0,
    },
}


def check_domain_clearance(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
) -> ClearanceResult:
    """
    Check minimum clearance distance between two voltage domains.

    Clearance is the shortest distance through air between two conductive parts.

    Args:
        placement: PCB placement data with component positions and nets
        domain_a: First voltage domain
        domain_b: Second voltage domain
        min_mm: Minimum clearance distance in millimeters

    Returns:
        ClearanceResult with violations for insufficient clearance
    """
    # TODO: Implement clearance checking between voltage domains
    raise NotImplementedError("Domain clearance checking not yet implemented")


def check_creepage_path(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
) -> ClearanceResult:
    """
    Check minimum creepage distance along PCB surface between two voltage domains.

    Creepage is the shortest distance along the surface of insulation between
    two conductive parts.

    Args:
        placement: PCB placement data with component positions and nets
        domain_a: First voltage domain
        domain_b: Second voltage domain
        min_mm: Minimum creepage distance in millimeters

    Returns:
        ClearanceResult with violations for insufficient creepage
    """
    # TODO: Implement creepage path checking along PCB surface
    raise NotImplementedError("Creepage path checking not yet implemented")


def verify_iec60335_compliance(
    placement: dict[str, Any],
    voltage_domains: dict[str, VoltageDomain],
) -> ClearanceResult:
    """
    Verify complete IEC 60335-2-6 compliance for all voltage domain boundaries.

    Checks all required clearance and creepage distances per the safety matrix.

    Args:
        placement: PCB placement data with component positions and nets
        voltage_domains: Mapping of net names to voltage domains

    Returns:
        ClearanceResult with all IEC 60335-2-6 violations
    """
    # TODO: Implement comprehensive IEC 60335-2-6 compliance checking
    raise NotImplementedError("IEC 60335-2-6 compliance verification not yet implemented")


def get_requirement_matrix() -> dict[tuple[str, str, str], dict[str, float]]:
    """
    Get the IEC 60335-2-6 requirements matrix.

    Returns:
        Dictionary with (domain_a, domain_b, insulation_type) -> requirements
    """
    return {
        (domain_a.value, domain_b.value, insulation_type.value): requirements
        for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items()
    }
