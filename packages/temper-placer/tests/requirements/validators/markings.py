"""
Safety marking validation functions.

These functions check if PCB silkscreen markings meet IEC 60335 safety requirements
per REQ-SAFE-03 for proper warning symbols, polarity indicators, and identification.
"""

from dataclasses import dataclass


@dataclass
class MarkingViolation:
    """A safety marking violation."""

    component_ref: str
    code: str
    message: str
    location: tuple[float, float] | None = None
    severity: str = "error"  # error, warning
    required_symbol: str | None = None
    found_symbols: list[str] | None = None


@dataclass
class MarkingResult:
    """Result of safety marking validation."""

    passed: bool
    violations: list[MarkingViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_hv_warning_present(
    silkscreen_text: list[str],
    hv_zone: tuple[float, float, float, float],  # (x, y, width, height)
    min_height_mm: float = 10.0,
) -> MarkingResult:
    """
    Check that high voltage warning is present near DC bus capacitors.

    IEC 60417-5036: Lightning bolt in triangle symbol required.
    Text: "DANGER: HIGH VOLTAGE" or "CAUTION: 400V DC"

    Args:
        silkscreen_text: List of silkscreen text strings
        hv_zone: High voltage zone rectangle (x, y, width, height)
        min_height_mm: Minimum symbol height (default: 10mm)

    Returns:
        MarkingResult with violations for missing HV warnings
    """
    # TODO: Implement HV warning detection
    raise NotImplementedError("HV warning checking not yet implemented")


def check_pe_symbol_present(
    silkscreen_text: list[str],
    pe_connection: tuple[float, float],
    min_height_mm: float = 5.0,
) -> MarkingResult:
    """
    Check that protective earth symbol is present at PE connection point.

    IEC 60417-5019: Earth ground symbol required at PE connection.

    Args:
        silkscreen_text: List of silkscreen text strings
        pe_connection: PE connection point position (x, y)
        min_height_mm: Minimum symbol height (default: 5mm)

    Returns:
        MarkingResult with violations for missing PE symbols
    """
    # TODO: Implement PE symbol detection
    raise NotImplementedError("PE symbol checking not yet implemented")


def check_isolation_barrier_marked(
    silkscreen_text: list[str],
    barriers: list[tuple[float, float, float, float]],  # [(x, y, width, height)]
) -> MarkingResult:
    """
    Check that isolation barriers are properly marked.

    Dashed line or "ISOLATION BARRIER" text required along HV-LV boundary.

    Args:
        silkscreen_text: List of silkscreen text strings
        barriers: List of isolation barrier rectangles

    Returns:
        MarkingResult with violations for missing barrier markings
    """
    # TODO: Implement isolation barrier marking detection
    raise NotImplementedError("Isolation barrier marking checking not yet implemented")


def check_polarity_markings(
    silkscreen_text: list[str],
    polarized_components: list[str],  # ["C1", "C2", "D1", "D2"]
) -> MarkingResult:
    """
    Check that polarized components have polarity markings.

    +/- symbols required near polarized components (electrolytic caps, diodes).

    Args:
        silkscreen_text: List of silkscreen text strings
        polarized_components: List of polarized component refs

    Returns:
        MarkingResult with violations for missing polarity markings
    """
    # TODO: Implement polarity marking detection
    raise NotImplementedError("Polarity marking checking not yet implemented")


def check_pin1_indicators(
    silkscreen_text: list[str],
    ics: list[str],  # ["U1", "U2", "U3"]
    connectors: list[str],  # ["J1", "J2", "J3"]
) -> MarkingResult:
    """
    Check that all ICs and connectors have pin 1 indicators.

    Dot, triangle, or notch marking required at pin 1 of all ICs and connectors.

    Args:
        silkscreen_text: List of silkscreen text strings
        ics: List of IC reference designators
        connectors: List of connector reference designators

    Returns:
        MarkingResult with violations for missing pin 1 indicators
    """
    # TODO: Implement pin 1 indicator detection
    raise NotImplementedError("Pin 1 indicator checking not yet implemented")


def check_silkscreen_legibility(
    silkscreen_text: list[tuple[str, float, float, float]],  # [(text, x, y, height_mm)]
    min_height_mm: float = 1.0,
    min_line_width_mm: float = 0.15,
) -> MarkingResult:
    """
    Check that silkscreen text meets minimum legibility requirements.

    Min character height: 1mm (0.8mm acceptable for tight spaces)
    Line width: 0.15mm minimum
    Font: Sans-serif (vector)

    Args:
        silkscreen_text: List of (text, x, y, height_mm) tuples
        min_height_mm: Minimum character height (default: 1.0mm)
        min_line_width_mm: Minimum line width (default: 0.15mm)

    Returns:
        MarkingResult with violations for illegible text
    """
    # TODO: Implement silkscreen legibility checking
    raise NotImplementedError("Silkscreen legibility checking not yet implemented")


def check_component_identification(
    silkscreen_text: list[str],
    component_refs: list[str],
) -> MarkingResult:
    """
    Check that all components have reference designators on silkscreen.

    Every component should have its reference designator (R1, C2, U3, etc.) visible.

    Args:
        silkscreen_text: List of silkscreen text strings
        component_refs: List of all component reference designators

    Returns:
        MarkingResult with violations for missing component IDs
    """
    # TODO: Implement component identification checking
    raise NotImplementedError("Component identification checking not yet implemented")


def check_safety_symbol_compliance(
    silkscreen_text: list[str],
    required_symbols: dict[str, str],  # {"HV_WARNING": "IEC60417-5036", ...}
) -> MarkingResult:
    """
    Check that required safety symbols are present and compliant.

    Validates presence of IEC 60417 symbols and proper text warnings.

    Args:
        silkscreen_text: List of silkscreen text strings
        required_symbols: Dict of {symbol_name: IEC_standard} for required symbols

    Returns:
        MarkingResult with violations for missing or non-compliant symbols
    """
    # TODO: Implement safety symbol compliance checking
    raise NotImplementedError("Safety symbol compliance checking not yet implemented")
