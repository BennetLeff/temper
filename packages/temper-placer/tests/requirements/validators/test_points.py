"""
Test Point Accessibility validation functions.

These functions check if PCB layout meets REQ-DFM-02: Test Point Accessibility
requirements for probe access, coverage, and spacing.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TestPointType(Enum):
    """Types of test points in Temper PCB."""

    POWER_RAIL = "power_rail"
    GROUND = "ground"
    CRITICAL_SIGNAL = "critical_signal"
    PROGRAMMING_HEADER = "programming_header"


class TestPointPadSize(Enum):
    """Standard test point pad sizes."""

    SMALL_1MM = 1.0  # For gate drives, enable, fault signals
    MEDIUM_1_5MM = 1.5  # For power rails, control ground
    LARGE_2MM = 2.0  # For high voltage, power ground


@dataclass
class TestPoint:
    """A test point on the PCB."""

    name: str
    net: str
    position: tuple[float, float]
    test_point_type: TestPointType
    pad_size_mm: float
    is_hv: bool = False  # High voltage indicator
    required: bool = True  # Whether this is a required test point


@dataclass
class TestPointViolation:
    """A test point accessibility violation."""

    code: str
    message: str
    location: tuple[float, float] | None = None
    severity: str = "error"  # error, warning
    test_point_name: str | None = None
    missing_net: str | None = None
    measured_spacing_mm: float | None = None
    required_spacing_mm: float | None = None


@dataclass
class TestPointResult:
    """Result of test point validation."""

    passed: bool
    violations: list[TestPointViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


# Required test points per REQ-DFM-02
REQUIRED_TEST_POINTS = {
    # Power Rails
    "TP_5V": TestPoint(
        "TP_5V", "5V", (0, 0), TestPointType.POWER_RAIL, TestPointPadSize.MEDIUM_1_5MM.value
    ),
    "TP_3V3": TestPoint(
        "TP_3V3", "3V3", (0, 0), TestPointType.POWER_RAIL, TestPointPadSize.MEDIUM_1_5MM.value
    ),
    "TP_VBOOT": TestPoint(
        "TP_VBOOT", "VBOOT", (0, 0), TestPointType.POWER_RAIL, TestPointPadSize.SMALL_1MM.value
    ),
    "TP_DC_BUS": TestPoint(
        "TP_DC_BUS",
        "DC_BUS",
        (0, 0),
        TestPointType.POWER_RAIL,
        TestPointPadSize.LARGE_2MM.value,
        is_hv=True,
    ),
    # Ground References
    "TP_PGND": TestPoint(
        "TP_PGND", "PGND", (0, 0), TestPointType.GROUND, TestPointPadSize.LARGE_2MM.value
    ),
    "TP_CGND": TestPoint(
        "TP_CGND", "CGND", (0, 0), TestPointType.GROUND, TestPointPadSize.MEDIUM_1_5MM.value
    ),
    # Critical Signals
    "TP_SW": TestPoint(
        "TP_SW",
        "SW",
        (0, 0),
        TestPointType.CRITICAL_SIGNAL,
        TestPointPadSize.MEDIUM_1_5MM.value,
        is_hv=True,
    ),
    "TP_GATE_H": TestPoint(
        "TP_GATE_H",
        "GATE_H",
        (0, 0),
        TestPointType.CRITICAL_SIGNAL,
        TestPointPadSize.SMALL_1MM.value,
    ),
    "TP_GATE_L": TestPoint(
        "TP_GATE_L",
        "GATE_L",
        (0, 0),
        TestPointType.CRITICAL_SIGNAL,
        TestPointPadSize.SMALL_1MM.value,
    ),
    "TP_CT_OUT": TestPoint(
        "TP_CT_OUT",
        "CT_OUT",
        (0, 0),
        TestPointType.CRITICAL_SIGNAL,
        TestPointPadSize.SMALL_1MM.value,
    ),
    "TP_EN": TestPoint(
        "TP_EN", "EN", (0, 0), TestPointType.CRITICAL_SIGNAL, TestPointPadSize.SMALL_1MM.value
    ),
    "TP_FAULT": TestPoint(
        "TP_FAULT", "FAULT", (0, 0), TestPointType.CRITICAL_SIGNAL, TestPointPadSize.SMALL_1MM.value
    ),
}


def check_test_point_coverage(
    test_points: list[TestPoint],
    critical_nets: set[str],
) -> TestPointResult:
    """
    Check that all critical nets have test point coverage.

    Args:
        test_points: List of test points on the PCB
        critical_nets: Set of critical net names that require test points

    Returns:
        TestPointResult with violations for missing test points
    """
    violations = []

    # Find which critical nets have test points
    covered_nets = {tp.net for tp in test_points}
    missing_nets = critical_nets - covered_nets

    for net in missing_nets:
        violations.append(
            TestPointViolation(
                code="DFM002-001",
                message=f"Missing test point for critical net: {net}",
                severity="error",
                missing_net=net,
            )
        )

    # Check for required test points
    required_names = {tp.name for tp in REQUIRED_TEST_POINTS.values() if tp.required}
    present_names = {tp.name for tp in test_points}

    for req_name in required_names:
        if req_name not in present_names:
            violations.append(
                TestPointViolation(
                    code="DFM002-002",
                    message=f"Missing required test point: {req_name}",
                    severity="error",
                    test_point_name=req_name,
                )
            )

    return TestPointResult(
        passed=len(violations) == 0,
        violations=violations,
    )


def check_test_point_accessibility(
    test_points: list[TestPoint],
    components: list[dict[str, Any]],
) -> TestPointResult:
    """
    Check that test points are accessible for probing (not blocked by components).

    Args:
        test_points: List of test points on the PCB
        components: List of components with positions and footprints

    Returns:
        TestPointResult with violations for inaccessible test points
    """
    violations = []

    for test_point in test_points:
        tp_x, tp_y = test_point.position

        # Check if any component blocks access to this test point
        for component in components:
            comp_x = component.get("x", 0)
            comp_y = component.get("y", 0)
            comp_width = component.get("width", 0)
            comp_height = component.get("height", 0)

            # Simple bounding box check (expand by probe clearance)
            probe_clearance_mm = 2.54  # Minimum probe clearance
            clearance_x = comp_width / 2 + probe_clearance_mm
            clearance_y = comp_height / 2 + probe_clearance_mm

            # Check if test point is within component clearance zone
            if abs(tp_x - comp_x) <= clearance_x and abs(tp_y - comp_y) <= clearance_y:
                violations.append(
                    TestPointViolation(
                        code="DFM002-003",
                        message=f"Test point {test_point.name} blocked by component {component.get('ref', 'UNKNOWN')}",
                        location=test_point.position,
                        severity="error",
                        test_point_name=test_point.name,
                    )
                )
                break

    return TestPointResult(
        passed=len(violations) == 0,
        violations=violations,
    )


def check_programming_header(header_position: tuple[float, float] | None) -> TestPointResult:
    """
    Check that UART programming header is properly positioned.

    Args:
        header_position: Position of J_PROG header (x, y) or None if missing

    Returns:
        TestPointResult with violations for header positioning
    """
    violations = []

    if header_position is None:
        violations.append(
            TestPointViolation(
                code="DFM002-004",
                message="Missing UART programming header J_PROG",
                severity="error",
            )
        )
        return TestPointResult(passed=False, violations=violations)

    header_x, header_y = header_position

    # Check if header is near board edge (easy access requirement)
    # Assuming board size constraints would be checked elsewhere
    # For now, just verify it exists and has reasonable coordinates

    if header_x < 0 or header_y < 0:
        violations.append(
            TestPointViolation(
                code="DFM002-005",
                message=f"Programming header position invalid: ({header_x}, {header_y})",
                location=header_position,
                severity="error",
            )
        )

    return TestPointResult(
        passed=len(violations) == 0,
        violations=violations,
    )


def check_test_point_spacing(
    test_points: list[TestPoint],
    min_spacing_mm: float = 2.54,
) -> TestPointResult:
    """
    Check that test points have adequate spacing for probe access.

    Args:
        test_points: List of test points on the PCB
        min_spacing_mm: Minimum spacing between test points in mm

    Returns:
        TestPointResult with violations for insufficient spacing
    """
    violations = []

    # Check spacing between all pairs of test points
    for i, tp1 in enumerate(test_points):
        for tp2 in test_points[i + 1 :]:
            x1, y1 = tp1.position
            x2, y2 = tp2.position

            # Calculate Euclidean distance
            distance = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

            if distance < min_spacing_mm:
                violations.append(
                    TestPointViolation(
                        code="DFM002-006",
                        message=f"Test points {tp1.name} and {tp2.name} too close: {distance:.2f}mm < {min_spacing_mm}mm",
                        location=((x1 + x2) / 2, (y1 + y2) / 2),
                        severity="error",
                        measured_spacing_mm=distance,
                        required_spacing_mm=min_spacing_mm,
                    )
                )

    return TestPointResult(
        passed=len(violations) == 0,
        violations=violations,
    )


def get_required_test_points() -> dict[str, TestPoint]:
    """
    Get the dictionary of required test points per REQ-DFM-02.

    Returns:
        Dictionary mapping test point names to TestPoint objects
    """
    return REQUIRED_TEST_POINTS.copy()


def get_critical_nets() -> set[str]:
    """
    Get the set of critical nets that require test points.

    Returns:
        Set of critical net names
    """
    return {
        "5V",
        "3V3",
        "VBOOT",
        "DC_BUS",  # Power rails
        "PGND",
        "CGND",  # Ground references
        "SW",
        "GATE_H",
        "GATE_L",
        "CT_OUT",
        "EN",
        "FAULT",  # Critical signals
    }
