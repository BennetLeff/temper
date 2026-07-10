from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClearanceRule:
    """Clearance rule between net classes or components."""

    from_class: str
    to_class: str
    clearance_mm: float
    description: str = ""


@dataclass
class NetClassRule:
    """Design rules for a specific net class."""

    name: str  # e.g. "HighVoltage"
    trace_width_mm: float = 0.2
    clearance_mm: float = 0.2
    via_size_mm: float = 0.6
    via_drill_mm: float = 0.3
    via_template: str | None = None  # Via array template (e.g., "Via2x2")
    creepage_mm: float = 0.0
    allow_neckdown: bool = True
    description: str = ""

    voltage_v: float = 0.0  # Working voltage for creepage calculation
    max_current_rating: float | None = None  # Maximum current in Amps (e.g., 20.0)
    routing_strategy: str | None = (
        None  # Routing strategy: "plane_required", "plane_preferred", "wide_trace", "standard"
    )
    via_cost_multiplier: float = 1.0  # Multiplier for via cost (higher = fewer vias)
    target_impedance: float | None = None  # Target impedance in Ohms


@dataclass
class DifferentialPairRule:
    """Configuration for a differential pair from YAML.

    Attributes:
        net_pos: Positive net name (e.g., 'USB_D+')
        net_neg: Negative net name (e.g., 'USB_D-')
        spacing_mm: Nominal gap between traces in mm
        coupling_tolerance_mm: Maximum deviation from spacing in mm
        impedance_ohm: Target differential impedance (optional)
        max_skew_mm: Maximum length mismatch in mm
        description: Human-readable description
    """

    net_pos: str
    net_neg: str
    spacing_mm: float = 0.2
    coupling_tolerance_mm: float = 0.5
    impedance_ohm: float | None = None
    max_skew_mm: float = 0.5
    description: str = ""


@dataclass
class SignalToHVClearance:
    """Constraint ensuring signal paths maintain clearance from HV component pins.

    This validates that signal-carrying components (like gate drivers) are placed
    close enough to their destination pins (like MOSFET gates) that the signal
    path doesn't need to route near HV pins (like collector/emitter).

    Example: Gate driver output must be within 15mm of MOSFET gate pin so
    the gate signal doesn't route past the HV collector/emitter pins.

    Attributes:
        name: Unique identifier for the constraint
        signal_component: Component that outputs the signal (e.g., "U_GATE")
        signal_pin: Pin on signal_component (e.g., "15" for OUTA)
        target_component: Component receiving the signal (e.g., "Q1")
        target_pin: Pin on target_component (e.g., "1" for gate)
        hv_component: Component with HV pins to avoid (often same as target_component)
        hv_pins: List of pin numbers that carry HV (e.g., ["2", "3"] for collector/emitter)
        required_clearance_mm: Minimum clearance from signal path to any HV pin
        max_path_length_mm: Maximum allowed signal path length
        tier: "hard" (fail) or "soft" (warn)
        description: Human-readable description
    """

    name: str
    signal_component: str
    signal_pin: str
    target_component: str
    target_pin: str
    hv_component: str
    hv_pins: list[str]
    required_clearance_mm: float = 6.0  # IEC 60335 default  # allow-safety-constant: IEC standard clearance
    max_path_length_mm: float = 20.0
    tier: str = "hard"
    description: str = ""
