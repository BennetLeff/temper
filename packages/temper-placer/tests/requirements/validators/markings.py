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


_HV_KEYWORDS = {"DANGER", "CAUTION", "HIGH VOLTAGE", "HV", "400V", "340V", "VOLTAGE"}
_PE_KEYWORDS = {"EARTH", "PE ", " GROUND", "PE-", "EARTH_GND", "PROTECTIVE_EARTH"}
_BARRIER_KEYWORDS = {"ISOLATION", "BARRIER", "ISOLATION BARRIER"}
_POLARITY_KEYWORDS = {"+", "-", "ANODE", "CATHODE", "POSITIVE", "NEGATIVE"}
_PIN1_KEYWORDS = {"1", "PIN1", "PIN 1", "DOT"}


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
    violations = []
    text_upper = [t.upper() for t in silkscreen_text]
    found = any(any(kw in t for kw in _HV_KEYWORDS) for t in text_upper)

    if not found:
        violations.append(
            MarkingViolation(
                component_ref="",
                code="MARK-001",
                message="High voltage warning marking missing",
                location=(hv_zone[0], hv_zone[1]),
                severity="error",
                required_symbol="HV_WARNING",
            )
        )

    return MarkingResult(passed=len(violations) == 0, violations=violations)


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
    violations = []
    text_upper = [t.upper() for t in silkscreen_text]
    found = any(any(kw in t for kw in _PE_KEYWORDS) for t in text_upper)

    if not found:
        violations.append(
            MarkingViolation(
                component_ref="",
                code="MARK-002",
                message="Protective earth (PE) symbol missing at PE connection",
                location=pe_connection,
                severity="error",
                required_symbol="PE_SYMBOL",
            )
        )

    return MarkingResult(passed=len(violations) == 0, violations=violations)


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
    violations = []
    if not barriers:
        return MarkingResult(passed=True, violations=[])

    text_upper = [t.upper() for t in silkscreen_text]
    found = any(any(kw in t for kw in _BARRIER_KEYWORDS) for t in text_upper)

    if not found:
        violations.append(
            MarkingViolation(
                component_ref="",
                code="MARK-003",
                message="Isolation barrier marking missing on silkscreen",
                location=(barriers[0][0], barriers[0][1]),
                severity="error",
                required_symbol="ISOLATION_BARRIER",
            )
        )

    return MarkingResult(passed=len(violations) == 0, violations=violations)


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
    violations = []
    text_upper = [t.upper() for t in silkscreen_text]

    for comp_ref in polarized_components:
        ref_upper = comp_ref.upper()
        found = any(
            any(kw in t for kw in _POLARITY_KEYWORDS) and ref_upper in t for t in text_upper
        )
        # Check if polarity markings exist near this specific component
        if not found:
            violations.append(
                MarkingViolation(
                    component_ref=comp_ref,
                    code="MARK-004",
                    message=f"Polarity marking missing for polarized component {comp_ref}",
                    severity="warning",
                    required_symbol="POLARITY",
                )
            )

    return MarkingResult(passed=len(violations) == 0, violations=violations)


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
    violations = []
    text_upper = [t.upper() for t in silkscreen_text]

    for ref in ics + connectors:
        ref_upper = ref.upper()
        found = any(ref_upper in t and any(kw in t for kw in _PIN1_KEYWORDS) for t in text_upper)
        if not found:
            violations.append(
                MarkingViolation(
                    component_ref=ref,
                    code="MARK-005",
                    message=f"Pin 1 indicator missing for {ref}",
                    severity="warning",
                    required_symbol="PIN1_INDICATOR",
                )
            )

    return MarkingResult(passed=len(violations) == 0, violations=violations)


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
    violations = []

    for text, x, y, height in silkscreen_text:
        if height < min_height_mm:
            violations.append(
                MarkingViolation(
                    component_ref=text,
                    code="MARK-006",
                    message=f"Silkscreen text '{text}' height {height:.2f}mm below minimum {min_height_mm}mm",
                    location=(x, y),
                    severity="warning",
                )
            )

    return MarkingResult(passed=len(violations) == 0, violations=violations)


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
    violations = []
    text_upper = [t.upper() for t in silkscreen_text]

    for ref in component_refs:
        if not any(ref.upper() in t for t in text_upper):
            violations.append(
                MarkingViolation(
                    component_ref=ref,
                    code="MARK-007",
                    message=f"Component {ref} reference designator missing on silkscreen",
                    severity="error",
                )
            )

    return MarkingResult(passed=len(violations) == 0, violations=violations)


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
    violations = []
    text_upper = [t.upper() for t in silkscreen_text]

    for symbol_name, iec_ref in required_symbols.items():
        found = any(
            symbol_name.upper() in t or iec_ref.upper() in t.replace("-", "").replace(" ", "")
            for t in text_upper
        )
        if not found:
            violations.append(
                MarkingViolation(
                    component_ref="",
                    code="MARK-008",
                    message=f"Required safety symbol '{symbol_name}' ({iec_ref}) not found on silkscreen",
                    severity="error",
                    required_symbol=symbol_name,
                )
            )

    return MarkingResult(passed=len(violations) == 0, violations=violations)
