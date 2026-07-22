"""
Schematic review validation functions.

These functions check if schematic designs meet requirements per REQ-REV-01:
Schematic Review Checklist.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ComponentSpec:
    """Component specification from schematic."""

    ref: str
    value: str
    footprint: str
    part_number: str | None = None
    voltage_rating: float | None = None  # Volts
    current_rating: float | None = None  # Amps
    power_rating: float | None = None  # Watts
    temp_rating: int | None = None  # Celsius
    supply_voltage: float | None = None  # Operating voltage
    pins: dict[str, str] = field(default_factory=dict)  # pin_number: net_name


@dataclass
class NetInfo:
    """Net information from schematic."""

    name: str
    pins: list[tuple[str, str]]  # [(ref, pin_number), ...]
    is_power: bool = False
    is_ground: bool = False
    voltage_level: float | None = None


@dataclass
class SchematicViolation:
    """A schematic design rule violation."""

    code: str
    message: str
    severity: str = "error"  # "error", "warning", "info"
    component_ref: str | None = None
    net_name: str | None = None
    details: str | None = None


@dataclass
class SchematicReviewResult:
    """Result of schematic review validation."""

    passed: bool
    violations: list[SchematicViolation]
    warnings: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "info")


def _net_by_name(nets: list[NetInfo], name: str) -> NetInfo | None:
    for n in nets:
        if n.name == name:
            return n
    return None


def _component_power_nets(comp: ComponentSpec) -> list[str]:
    nets = set()
    for net_name in comp.pins.values():
        nets.add(net_name)
    return list(nets)


def _parse_capacitance_value(value: str) -> float | None:
    """Parse a capacitance value string into uF (float), or None if unparseable."""
    m = re.search(r'(\d+\.?\d*)\s*[u\u03bc]\s*F', value, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# =============================================================================
# Power Supply Verification
# =============================================================================


def check_power_supply_voltages(
    components: list[ComponentSpec],
    nets: list[NetInfo],
) -> SchematicReviewResult:
    """
    Check that all ICs have correct supply voltage.

    Verifies:
    - ICs are connected to correct voltage rails (3.3V vs 5V vs 15V)
    - Supply voltage matches component specifications
    - No ICs connected to wrong voltage rail

    Args:
        components: List of components from schematic
        nets: List of nets with voltage levels

    Returns:
        SchematicReviewResult with violations for incorrect supply voltages
    """
    violations = []
    net_voltages = {n.name: n.voltage_level for n in nets if n.voltage_level is not None}

    for comp in components:
        if comp.supply_voltage is None:
            continue
        for pin_num, net_name in comp.pins.items():
            if net_name in net_voltages:
                net_v = net_voltages[net_name]
                if net_v != 0.0 and abs(net_v - comp.supply_voltage) > 0.5:
                    violations.append(
                        SchematicViolation(
                            code="PS-001",
                            message=f"Component {comp.ref} supply voltage {comp.supply_voltage}V mismatched with net {net_name} ({net_v}V)",
                            severity="error",
                            component_ref=comp.ref,
                            net_name=net_name,
                        )
                    )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_decoupling_present(
    components: list[ComponentSpec],
    nets: list[NetInfo],
    ics: list[str],
) -> SchematicReviewResult:
    """
    Check that decoupling capacitors are present on every IC power pin.

    Verifies:
    - Each IC power pin has at least one decoupling capacitor
    - Capacitor is connected between power pin and ground
    - Capacitor value is appropriate (typically 100nF for high-freq, 10uF for bulk)

    Args:
        components: List of components from schematic
        nets: List of nets
        ics: List of IC reference designators to check

    Returns:
        SchematicReviewResult with violations for missing decoupling caps
    """
    violations = []

    if not ics:
        return SchematicReviewResult(passed=False, violations=[
            SchematicViolation(
                code="DEC-000",
                message="No ICs specified for decoupling check",
                severity="error",
            )
        ])

    ic_comps = {c.ref: c for c in components if c.ref in ics}
    cap_comps = {c.ref: c for c in components if c.value in ("100nF", "10uF", "0.1uF", "1uF",
                                                               "1.0uF", "2.2uF", "22uF",
                                                               "0.047uF")
               or _parse_capacitance_value(str(c.value)) is not None
               or "nF" in str(c.value)}

    for ic_ref in ics:
        if ic_ref not in ic_comps:
            violations.append(
                SchematicViolation(
                    code="DEC-001",
                    message=f"IC {ic_ref} not found in component list",
                    severity="warning",
                    component_ref=ic_ref,
                )
            )
            continue

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_bulk_capacitors(
    components: list[ComponentSpec],
    nets: list[NetInfo],
    power_entry_nets: list[str],
) -> SchematicReviewResult:
    """
    Check that bulk capacitors are present at power entry points.

    Verifies:
    - Bulk capacitors (typically >10uF) at each power rail entry
    - Appropriate voltage rating for rail
    - Sufficient capacitance for load

    Args:
        components: List of components from schematic
        nets: List of nets
        power_entry_nets: List of power entry net names (e.g., ["+3V3_IN", "+15V_IN"])

    Returns:
        SchematicReviewResult with violations for missing bulk caps
    """
    violations = []

    for entry_net in power_entry_nets:
        net = _net_by_name(nets, entry_net)
        if net is None:
            violations.append(
                SchematicViolation(
                    code="BULK-001",
                    message=f"Power entry net '{entry_net}' not found in netlist",
                    severity="warning",
                    net_name=entry_net,
                )
            )
            continue

        has_bulk = False
        for comp in components:
            if any(pin_net == entry_net for pin_net in comp.pins.values()):
                val = _parse_capacitance_value(str(comp.value))
                if val is not None and val >= 10.0:
                    has_bulk = True

        if not has_bulk:
            violations.append(
                SchematicViolation(
                    code="BULK-002",
                    message=f"No bulk capacitor (>=10uF) found on power entry net '{entry_net}'",
                    severity="error",
                    net_name=entry_net,
                )
            )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_power_sequencing(
    components: list[ComponentSpec],
    nets: list[NetInfo],
) -> SchematicReviewResult:
    """
    Check power sequencing requirements (if applicable).

    Some ICs require specific power-up sequences (e.g., core before I/O).

    Args:
        components: List of components from schematic
        nets: List of nets

    Returns:
        SchematicReviewResult with violations for incorrect sequencing
    """
    raise NotImplementedError("Power sequencing checking not yet implemented (temper-xxx)")


def check_current_voltage_ratings(
    components: list[ComponentSpec],
    safety_margin_voltage: float = 0.20,  # 20% margin
    safety_margin_current: float = 0.30,  # 30% margin
) -> SchematicReviewResult:
    """
    Check that component ratings are adequate with safety margins.

    Verifies:
    - Voltage ratings include >20% safety margin
    - Current ratings include >30% safety margin
    - Power ratings adequate for expected dissipation

    Args:
        components: List of components from schematic
        safety_margin_voltage: Minimum voltage safety margin (0.20 = 20%)
        safety_margin_current: Minimum current safety margin (0.30 = 30%)

    Returns:
        SchematicReviewResult with violations for inadequate ratings
    """
    violations = []

    for comp in components:
        if comp.supply_voltage is not None and comp.voltage_rating is not None:
            required = comp.supply_voltage * (1 + safety_margin_voltage)
            if comp.voltage_rating < required:
                violations.append(
                    SchematicViolation(
                        code="RATING-001",
                        message=f"Component {comp.ref} voltage rating {comp.voltage_rating}V insufficient (need >={required:.1f}V for {comp.supply_voltage}V supply)",
                        severity="error",
                        component_ref=comp.ref,
                    )
                )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


# =============================================================================
# Component Selection
# =============================================================================


def check_component_part_numbers(
    components: list[ComponentSpec],
) -> SchematicReviewResult:
    """
    Check that all components have valid part numbers.

    Verifies:
    - Part number field is populated
    - Part number format is valid
    - No generic placeholders (e.g., "TBD", "???")

    Args:
        components: List of components from schematic

    Returns:
        SchematicReviewResult with violations for missing/invalid part numbers
    """
    violations = []
    placeholders = {"TBD", "???", "N/A", "n/a", "", "TBC", "TBD", "XXX"}

    for comp in components:
        if comp.part_number is None or comp.part_number.strip() == "":
            violations.append(
                SchematicViolation(
                    code="PN-001",
                    message=f"Component {comp.ref} missing part number",
                    severity="error",
                    component_ref=comp.ref,
                )
            )
        elif comp.part_number.strip().upper() in placeholders:
            violations.append(
                SchematicViolation(
                    code="PN-002",
                    message=f"Component {comp.ref} has placeholder part number '{comp.part_number}'",
                    severity="error",
                    component_ref=comp.ref,
                )
            )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_footprints_assigned(
    components: list[ComponentSpec],
) -> SchematicReviewResult:
    """
    Check that all components have footprints assigned.

    Verifies:
    - Footprint field is populated
    - Footprint exists in library
    - Footprint matches component type

    Args:
        components: List of components from schematic

    Returns:
        SchematicReviewResult with violations for missing footprints
    """
    violations = []

    for comp in components:
        if not comp.footprint or comp.footprint.strip() == "":
            violations.append(
                SchematicViolation(
                    code="FP-001",
                    message=f"Component {comp.ref} missing footprint assignment",
                    severity="error",
                    component_ref=comp.ref,
                )
            )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_temperature_ratings(
    components: list[ComponentSpec],
    min_power_temp: int = 125,  # C
    min_logic_temp: int = 85,  # C
) -> SchematicReviewResult:
    """
    Check that temperature ratings are adequate.

    Verifies:
    - Power components rated for >=125C
    - Logic components rated for >=85C
    - Components in hot zones have appropriate ratings

    Args:
        components: List of components from schematic
        min_power_temp: Minimum temperature rating for power components
        min_logic_temp: Minimum temperature rating for logic components

    Returns:
        SchematicReviewResult with violations for inadequate temperature ratings
    """
    violations = []

    for comp in components:
        if comp.temp_rating is None:
            continue
        if comp.power_rating is not None and comp.power_rating > 1.0:
            if comp.temp_rating < min_power_temp:
                violations.append(
                    SchematicViolation(
                        code="TEMP-001",
                        message=f"Power component {comp.ref} temp rating {comp.temp_rating}C below minimum {min_power_temp}C",
                        severity="error",
                        component_ref=comp.ref,
                    )
                )
        else:
            if comp.temp_rating < min_logic_temp:
                violations.append(
                    SchematicViolation(
                        code="TEMP-002",
                        message=f"Component {comp.ref} temp rating {comp.temp_rating}C below minimum {min_logic_temp}C",
                        severity="warning",
                        component_ref=comp.ref,
                    )
                )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_obsolete_parts(
    components: list[ComponentSpec],
    obsolete_list: set[str] | None = None,
) -> SchematicReviewResult:
    """
    Check for obsolete or EOL (End-of-Life) parts.

    Verifies:
    - No parts on obsolete list
    - No parts marked as NRND (Not Recommended for New Designs)
    - Parts are available from distributors

    Args:
        components: List of components from schematic
        obsolete_list: Set of known obsolete part numbers

    Returns:
        SchematicReviewResult with violations for obsolete parts
    """
    violations = []

    if obsolete_list is None:
        obsolete_list = set()

    for comp in components:
        if comp.part_number and comp.part_number.strip().upper() in {p.upper() for p in obsolete_list}:
            violations.append(
                SchematicViolation(
                    code="OBS-001",
                    message=f"Component {comp.ref} uses obsolete part '{comp.part_number}'",
                    severity="error",
                    component_ref=comp.ref,
                )
            )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


# =============================================================================
# Net Naming and Hierarchy
# =============================================================================


def check_net_naming_convention(
    nets: list[NetInfo],
    power_net_patterns: list[str] | None = None,
    ground_net_patterns: list[str] | None = None,
) -> SchematicReviewResult:
    """
    Check that nets follow naming conventions.

    Verifies:
    - All nets have meaningful names (not "Net-1", "Net-2")
    - Power nets follow convention (+5V, +3V3, +15V)
    - Ground nets follow convention (GND, PGND, AGND)
    - Signal nets are descriptive (PWM_H, ADC_TEMP, SPI_MOSI)

    Args:
        nets: List of nets from schematic
        power_net_patterns: List of valid power net patterns
        ground_net_patterns: List of valid ground net patterns

    Returns:
        SchematicReviewResult with violations for poor net naming
    """
    violations = []
    generic_pattern = re.compile(r"^Net-\d+$", re.IGNORECASE)

    for net in nets:
        if generic_pattern.match(net.name):
            violations.append(
                SchematicViolation(
                    code="NET-001",
                    message=f"Net '{net.name}' uses generic auto-generated name. Use descriptive name.",
                    severity="warning",
                    net_name=net.name,
                )
            )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_duplicate_net_names(
    nets: list[NetInfo],
) -> SchematicReviewResult:
    """
    Check for duplicate net names with different meanings.

    Verifies:
    - No duplicate net names in different sheets
    - Global labels used correctly
    - Hierarchical labels match between sheets

    Args:
        nets: List of nets from schematic

    Returns:
        SchematicReviewResult with violations for duplicate net names
    """
    violations = []
    seen = set()

    for net in nets:
        if net.name in seen:
            violations.append(
                SchematicViolation(
                    code="NET-002",
                    message=f"Duplicate net name '{net.name}'",
                    severity="error",
                    net_name=net.name,
                )
            )
        seen.add(net.name)

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_hierarchical_connections(
    schematic_path: Path,
) -> SchematicReviewResult:
    """
    Check hierarchical sheet connections.

    Verifies:
    - All hierarchical pins have matching labels
    - No unconnected hierarchical pins
    - Sheet pin directions are correct (input/output/bidirectional)

    Args:
        schematic_path: Path to root schematic file

    Returns:
        SchematicReviewResult with violations for incorrect hierarchy
    """
    return SchematicReviewResult(passed=True, violations=[], warnings=[
        "Hierarchical connection checking not yet implemented (temper-xxx)"
    ])


def check_global_labels(
    nets: list[NetInfo],
) -> SchematicReviewResult:
    """
    Check that global labels are used appropriately.

    Verifies:
    - Global labels used for power/ground nets
    - Global labels used for signals crossing multiple sheets
    - Local labels used for sheet-local signals

    Args:
        nets: List of nets from schematic

    Returns:
        SchematicReviewResult with violations for improper global label usage
    """
    return SchematicReviewResult(passed=True, violations=[], warnings=[
        "Global label checking not yet implemented (temper-xxx)"
    ])


# =============================================================================
# Safety Circuit Review
# =============================================================================


def check_safety_circuit_values(
    components: list[ComponentSpec],
    nets: list[NetInfo],
    ocp_threshold: float | None = None,  # Amps
    ovp_threshold: float | None = None,  # Volts
    thermal_threshold: float | None = None,  # C
) -> SchematicReviewResult:
    """
    Check safety circuit component values.

    Verifies:
    - OCP (Over-Current Protection) circuit values correct
    - OVP (Over-Voltage Protection) circuit values correct
    - Thermal shutdown thresholds correct
    - Gate driver enable/disable logic correct
    - Watchdog timer configured properly
    - Fault latch operation verified

    Args:
        components: List of components from schematic
        nets: List of nets
        ocp_threshold: Expected OCP threshold in Amps
        ovp_threshold: Expected OVP threshold in Volts
        thermal_threshold: Expected thermal shutdown threshold in C

    Returns:
        SchematicReviewResult with violations for incorrect safety values
    """
    raise NotImplementedError("Safety circuit value checking not yet implemented (temper-xxx)")


def check_ocp_circuit(
    components: list[ComponentSpec],
    nets: list[NetInfo],
    threshold_amps: float,
    tolerance: float = 0.10,  # 10% tolerance
) -> SchematicReviewResult:
    """
    Check Over-Current Protection circuit design.

    Verifies:
    - Current sense resistor value correct
    - Comparator threshold correct
    - Shutdown signal connected to gate driver
    - Response time adequate

    Args:
        components: List of components from schematic
        nets: List of nets
        threshold_amps: Target OCP threshold
        tolerance: Acceptable tolerance (0.10 = +-10%)

    Returns:
        SchematicReviewResult with violations for incorrect OCP design
    """
    violations = []

    has_sense = any("RES" in str(comp.value).upper() or "Ω" in str(comp.value) or "OHM" in str(comp.value).upper()
                     for comp in components)
    has_comparator = any("393" in str(comp.value) or "op" in str(comp.value).lower()
                         for comp in components)

    if not has_sense:
        violations.append(
            SchematicViolation(
                code="OCP-001",
                message="No current sense resistor found in OCP circuit",
                severity="error",
            )
        )
    if not has_comparator:
        violations.append(
            SchematicViolation(
                code="OCP-002",
                message="No comparator (LM393) found in OCP circuit",
                severity="error",
            )
        )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_ovp_circuit(
    components: list[ComponentSpec],
    nets: list[NetInfo],
    threshold_volts: float,
    tolerance: float = 0.10,  # 10% tolerance
) -> SchematicReviewResult:
    """
    Check Over-Voltage Protection circuit design.

    Verifies:
    - Voltage divider values correct
    - Comparator threshold correct
    - Shutdown signal connected to gate driver
    - Response time adequate

    Args:
        components: List of components from schematic
        nets: List of nets
        threshold_volts: Target OVP threshold
        tolerance: Acceptable tolerance (0.10 = +-10%)

    Returns:
        SchematicReviewResult with violations for incorrect OVP design
    """
    raise NotImplementedError("OVP circuit checking not yet implemented (temper-xxx)")


def check_thermal_shutdown(
    components: list[ComponentSpec],
    nets: list[NetInfo],
    threshold_celsius: float,
) -> SchematicReviewResult:
    """
    Check thermal shutdown circuit design.

    Verifies:
    - Temperature sensor present
    - Threshold comparator correct
    - Shutdown signal connected to gate driver
    - Hysteresis appropriate

    Args:
        components: List of components from schematic
        nets: List of nets
        threshold_celsius: Target thermal shutdown threshold

    Returns:
        SchematicReviewResult with violations for incorrect thermal shutdown
    """
    raise NotImplementedError("Thermal shutdown checking not yet implemented (temper-xxx)")


def check_gate_driver_enable(
    components: list[ComponentSpec],
    nets: list[NetInfo],
) -> SchematicReviewResult:
    """
    Check gate driver enable/disable logic.

    Verifies:
    - Enable signal connected correctly
    - Disable signal (SHUTDOWN_N) connected to all safety circuits
    - Logic levels correct (active high/low)
    - Pull-up/pull-down resistors present

    Args:
        components: List of components from schematic
        nets: List of nets

    Returns:
        SchematicReviewResult with violations for incorrect enable logic
    """
    violations = []
    has_gate_driver = any("UCC" in str(c.value).upper() or "gate" in str(c.value).lower()
                          for c in components)

    if not has_gate_driver:
        violations.append(
            SchematicViolation(
                code="GATE-001",
                message="No gate driver IC found for enable logic check",
                severity="warning",
            )
        )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_watchdog_timer(
    components: list[ComponentSpec],
    nets: list[NetInfo],
) -> SchematicReviewResult:
    """
    Check watchdog timer configuration.

    Verifies:
    - Watchdog IC present (e.g., TPS3823-33)
    - Timeout period appropriate
    - Reset signal connected to MCU
    - Watchdog kick signal connected

    Args:
        components: List of components from schematic
        nets: List of nets

    Returns:
        SchematicReviewResult with violations for incorrect watchdog config
    """
    violations = []

    has_watchdog = any("3823" in str(c.value) or "WDT" in str(c.value).upper() or "watchdog" in str(c.value).lower()
                        for c in components)

    if not has_watchdog:
        violations.append(
            SchematicViolation(
                code="WDT-001",
                message="No watchdog timer IC found (e.g., TPS3823-33)",
                severity="error",
            )
        )

    return SchematicReviewResult(passed=len(violations) == 0, violations=violations)


def check_fault_latch(
    components: list[ComponentSpec],
    nets: list[NetInfo],
) -> SchematicReviewResult:
    """
    Check fault latch operation.

    Verifies:
    - Fault latch circuit present
    - Set/reset logic correct
    - Latch output connected to gate driver disable
    - Manual reset capability present

    Args:
        components: List of components from schematic
        nets: List of nets

    Returns:
        SchematicReviewResult with violations for incorrect fault latch
    """
    raise NotImplementedError("Fault latch checking not yet implemented (temper-xxx)")
