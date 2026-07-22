"""
Bypass capacitor placement validation functions.

These functions check if bypass capacitor placement meets EMC/EMI requirements
per REQ-EMC-02.
"""

import math
from dataclasses import dataclass

from ._geometry import _distance


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    """Shoelace formula area of a polygon."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


@dataclass
class BypassCapViolation:
    """A bypass capacitor placement violation."""

    ic_ref: str
    cap_ref: str | None
    code: str
    message: str
    distance_mm: float | None = None
    severity: str = "error"


@dataclass
class BypassCapResult:
    """Result of bypass capacitor validation."""

    passed: bool
    violations: list[BypassCapViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_decoupling_distance(
    ic_position: tuple[float, float],
    ic_ref: str,
    cap_positions: dict[str, tuple[float, float]],
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
    violations = []

    if not cap_positions:
        violations.append(
            BypassCapViolation(
                ic_ref=ic_ref,
                cap_ref=None,
                code="DECAP-001",
                message=f"IC {ic_ref} has no decoupling capacitors",
                severity="error",
            )
        )
        return BypassCapResult(passed=False, violations=violations)

    for cap_ref, cap_pos in cap_positions.items():
        d = _distance(ic_position, cap_pos)
        if d > max_distance_mm:
            violations.append(
                BypassCapViolation(
                    ic_ref=ic_ref,
                    cap_ref=cap_ref,
                    code="DECAP-002",
                    message=f"Decoupling cap {cap_ref} is {d:.1f}mm from {ic_ref} (limit: {max_distance_mm}mm)",
                    distance_mm=d,
                    severity="error",
                )
            )

    return BypassCapResult(passed=len(violations) == 0, violations=violations)


def check_bypass_loop_area(
    ic_position: tuple[float, float],
    ic_power_pin: tuple[float, float],
    cap_position: tuple[float, float],
    cap_ground_via: tuple[float, float],
    max_area_mm2: float = 10.0,
) -> BypassCapResult:
    """
    Check bypass capacitor loop area (VCC -> Cap -> GND -> IC_GND).

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
    violations = []

    power_pin_abs = (
        ic_position[0] + ic_power_pin[0],
        ic_position[1] + ic_power_pin[1],
    )
    ic_ground_abs = ic_position

    loop_area = _polygon_area([power_pin_abs, cap_position, cap_ground_via, ic_ground_abs])

    if loop_area > max_area_mm2:
        violations.append(
            BypassCapViolation(
                ic_ref="",
                cap_ref=None,
                code="LOOP-001",
                message=f"Bypass loop area {loop_area:.1f}mm^2 exceeds maximum {max_area_mm2}mm^2",
                distance_mm=loop_area,
                severity="error",
            )
        )

    return BypassCapResult(passed=len(violations) == 0, violations=violations)


def check_via_at_cap_ground(
    cap_position: tuple[float, float],
    cap_ref: str,
    ground_vias: list[tuple[float, float]],
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
    violations = []

    if not ground_vias:
        violations.append(
            BypassCapViolation(
                ic_ref="",
                cap_ref=cap_ref,
                code="VIA-001",
                message=f"No ground via found near capacitor {cap_ref}",
                severity="error",
            )
        )
        return BypassCapResult(passed=False, violations=violations)

    min_dist = min(_distance(cap_position, via) for via in ground_vias)

    if min_dist > max_distance_mm:
        violations.append(
            BypassCapViolation(
                ic_ref="",
                cap_ref=cap_ref,
                code="VIA-002",
                message=f"Ground via is {min_dist:.1f}mm from capacitor {cap_ref} (limit: {max_distance_mm}mm)",
                distance_mm=min_dist,
                severity="error",
            )
        )

    return BypassCapResult(passed=len(violations) == 0, violations=violations)


def check_component_specific_requirements(
    component_type: str,
    ic_position: tuple[float, float],
    ic_ref: str,
    cap_positions: dict[str, tuple[float, float]],
    cap_values: dict[str, str],
) -> BypassCapResult:
    """
    Check component-specific bypass capacitor requirements.

    Different ICs have different requirements (ESP32, UCC21550, MAX31865, etc.)

    Args:
        component_type: Type of IC (e.g., "ESP32-S3-WROOM", "UCC21550")
        ic_position: IC position
        ic_ref: IC reference designator
        cap_positions: Dict of {cap_ref: (x, y)}
        cap_values: Dict of {cap_ref: value_string} (e.g., "100nF", "10uF")

    Returns:
        BypassCapResult with violations for missing or incorrectly placed caps
    """
    violations = []

    if "ESP32" in component_type.upper():
        has_bulk = any("µ" in str(v).upper() or "u" in str(v).lower() for v in cap_values.values())
        has_hf = any("n" in str(v).lower() for v in cap_values.values())
        if not has_bulk:
            violations.append(
                BypassCapViolation(
                    ic_ref=ic_ref,
                    cap_ref=None,
                    code="ESP-001",
                    message=f"ESP32 {ic_ref} missing bulk capacitor (>=10uF required)",
                    severity="error",
                )
            )
        if not has_hf:
            violations.append(
                BypassCapViolation(
                    ic_ref=ic_ref,
                    cap_ref=None,
                    code="ESP-002",
                    message=f"ESP32 {ic_ref} missing high-frequency bypass capacitor (100nF required)",
                    severity="warning",
                )
            )
    elif "UCC21550" in component_type.upper():
        if len(cap_values) < 2:
            violations.append(
                BypassCapViolation(
                    ic_ref=ic_ref,
                    cap_ref=None,
                    code="UCC-001",
                    message=f"UCC21550 {ic_ref} requires bypass caps on VCCI, VDDA, VDDB domains",
                    severity="error",
                )
            )
    elif "MAX31865" in component_type.upper():
        if len(cap_values) < 1:
            violations.append(
                BypassCapViolation(
                    ic_ref=ic_ref,
                    cap_ref=None,
                    code="MAX-001",
                    message=f"MAX31865 {ic_ref} requires VDD and VREF bypass capacitors",
                    severity="error",
                )
            )
    elif "LMR" in component_type.upper():
        if len(cap_values) < 3:
            violations.append(
                BypassCapViolation(
                    ic_ref=ic_ref,
                    cap_ref=None,
                    code="BUCK-001",
                    message=f"{component_type} {ic_ref} requires input, output, and bootstrap capacitors",
                    severity="error",
                )
            )

    return BypassCapResult(passed=len(violations) == 0, violations=violations)
