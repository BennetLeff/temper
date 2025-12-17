"""
Bypass capacitor placement validation functions.

These functions check if bypass capacitor placement meets EMC/EMI requirements
per REQ-EMC-02.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional


@dataclass
class BypassCapViolation:
    """A bypass capacitor placement violation."""

    ic_ref: str
    cap_ref: Optional[str]
    code: str
    message: str
    distance_mm: Optional[float] = None
    severity: str = "error"


@dataclass
class BypassCapResult:
    """Result of bypass capacitor validation."""

    passed: bool
    violations: List[BypassCapViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_decoupling_distance(
    ic_position: Tuple[float, float],
    ic_ref: str,
    cap_positions: Dict[str, Tuple[float, float]],
    max_distance_mm: float = 3.0,
) -> BypassCapResult:
    """
    Check that decoupling capacitors are within maximum distance of IC.

    Close placement minimizes inductance in power delivery path.

    Args:
        ic_position: IC center position (x, y)
        ic_ref: IC reference designator
        cap_positions: Dict of {cap_ref: (x, y)} for decoupling caps
        max_distance_mm: Maximum allowed distance

    Returns:
        BypassCapResult with violations for caps too far from IC
    """
    # TODO: Implement distance checking
    raise NotImplementedError("Decoupling distance checking not yet implemented")


def check_bypass_loop_area(
    ic_position: Tuple[float, float],
    ic_power_pin: Tuple[float, float],
    cap_position: Tuple[float, float],
    cap_ground_via: Tuple[float, float],
    max_area_mm2: float = 10.0,
) -> BypassCapResult:
    """
    Check bypass capacitor loop area (VCC → Cap → GND → IC_GND).

    Smaller loop area = lower inductance = better high-frequency bypassing.

    Args:
        ic_position: IC center position
        ic_power_pin: IC power pin position (relative to center)
        cap_position: Capacitor position
        cap_ground_via: Ground via position at capacitor
        max_area_mm2: Maximum allowed loop area

    Returns:
        BypassCapResult with violations for excessive loop area
    """
    # TODO: Implement loop area calculation
    raise NotImplementedError("Loop area checking not yet implemented")


def check_via_at_cap_ground(
    cap_position: Tuple[float, float],
    cap_ref: str,
    ground_vias: List[Tuple[float, float]],
    max_distance_mm: float = 0.5,
) -> BypassCapResult:
    """
    Check that ground via is directly at capacitor ground pad.

    Via should be at the pad, not routed away, to minimize inductance.

    Args:
        cap_position: Capacitor position
        cap_ref: Capacitor reference designator
        ground_vias: List of ground via positions
        max_distance_mm: Maximum distance from cap to nearest via

    Returns:
        BypassCapResult with violations if no via at ground pad
    """
    # TODO: Implement via proximity checking
    raise NotImplementedError("Via at ground pad checking not yet implemented")


def check_component_specific_requirements(
    component_type: str,
    ic_position: Tuple[float, float],
    ic_ref: str,
    cap_positions: Dict[str, Tuple[float, float]],
    cap_values: Dict[str, str],
) -> BypassCapResult:
    """
    Check component-specific bypass capacitor requirements.

    Different ICs have different requirements (ESP32, UCC21550, MAX31865, etc.)

    Args:
        component_type: Type of IC (e.g., "ESP32-S3-WROOM", "UCC21550")
        ic_position: IC position
        ic_ref: IC reference designator
        cap_positions: Dict of {cap_ref: (x, y)}
        cap_values: Dict of {cap_ref: value_string} (e.g., "100nF", "10µF")

    Returns:
        BypassCapResult with violations for missing or incorrectly placed caps
    """
    # TODO: Implement component-specific checking
    raise NotImplementedError("Component-specific requirements checking not yet implemented")
