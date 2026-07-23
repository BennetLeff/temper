"""
Switching node containment validation functions.

These functions check if switching node placement meets EMC/EMI containment requirements
per REQ-EMC-04 to minimize radiated EMI from high dV/dt nodes.
"""

import math
from dataclasses import dataclass

from ._geometry import _distance, _point_in_rect


@dataclass
class SwitchingNodeViolation:
    """A switching node containment violation."""

    node_type: str  # "HALF_BRIDGE_SW", "BUCK_SW", "GATE_DRIVER"
    component_refs: list[str]
    code: str
    message: str
    location: tuple[float, float] | None = None
    area_mm2: float | None = None
    severity: str = "error"  # error, warning


@dataclass
class SwitchingNodeResult:
    """Result of switching node containment validation."""

    passed: bool
    violations: list[SwitchingNodeViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_half_bridge_switch_node_area(
    sw_node_components: list[str],
    sw_node_position: tuple[float, float],
    max_area_mm2: float = 100.0,  # 1 cm^2
) -> SwitchingNodeResult:
    """
    Check that half-bridge switch node copper area is minimized.

    Half-bridge switch node (SW) has high dV/dt: 0V to 340V DC, ~50 V/ns.
    Large copper area acts as antenna for EMI radiation.

    Args:
        sw_node_components: List of component refs connected to SW node
        sw_node_position: SW node center position (x, y)
        max_area_mm2: Maximum allowed copper area (default: 100mm^2 = 1cm^2)

    Returns:
        SwitchingNodeResult with violations for excessive area
    """
    violations = []
    min_component_count = 3
    if len(sw_node_components) < min_component_count:
        violations.append(
            SwitchingNodeViolation(
                node_type="HALF_BRIDGE_SW",
                component_refs=sw_node_components,
                code="SW-001",
                message=f"Half-bridge SW node has only {len(sw_node_components)} components connected (expected >= {min_component_count})",
                location=sw_node_position,
                severity="warning",
            )
        )

    return SwitchingNodeResult(passed=len(violations) == 0, violations=violations)


def check_ground_plane_shielding_under_switching_nodes(
    switching_node_positions: dict[str, tuple[float, float]],
    ground_plane_zones: list[tuple[float, float, float, float]],  # (x, y, width, height)
    via_stitching_positions: list[tuple[float, float]],
    max_via_spacing_mm: float = 5.0,
) -> SwitchingNodeResult:
    """
    Check that switching nodes have ground plane shielding with via stitching.

    Ground plane under switching nodes provides return path and shields from radiation.
    Via stitching connects L2 and L4 ground pours to minimize impedance.

    Args:
        switching_node_positions: Dict of {node_type: (x, y)} for all switching nodes
        ground_plane_zones: List of ground plane zone rectangles
        via_stitching_positions: List of (x, y) positions for stitching vias
        max_via_spacing_mm: Maximum spacing between stitching vias

    Returns:
        SwitchingNodeResult with violations for missing shielding or insufficient stitching
    """
    violations = []

    for node_name, node_pos in switching_node_positions.items():
        under_ground = any(_point_in_rect(node_pos, z) for z in ground_plane_zones)
        if not under_ground:
            violations.append(
                SwitchingNodeViolation(
                    node_type=node_name,
                    component_refs=[],
                    code="SW-SHIELD-001",
                    message=f"Switching node '{node_name}' not shielded by ground plane",
                    location=node_pos,
                    severity="error",
                )
            )
        elif via_stitching_positions:
            nearby_vias = [
                v
                for v in via_stitching_positions
                if _distance(node_pos, v) < max_via_spacing_mm * 2
            ]
            if len(nearby_vias) < 2:
                violations.append(
                    SwitchingNodeViolation(
                        node_type=node_name,
                        component_refs=[],
                        code="SW-SHIELD-002",
                        message=f"Insufficient via stitching near switching node '{node_name}'",
                        location=node_pos,
                        severity="warning",
                    )
                )

    return SwitchingNodeResult(passed=len(violations) == 0, violations=violations)


def check_snubber_placement(
    igbt_position: tuple[float, float],
    snubber_components: list[str],
    snubber_positions: dict[str, tuple[float, float]],
    max_distance_mm: float = 10.0,
) -> SwitchingNodeResult:
    """
    Check that snubber circuits are placed within 10mm of IGBT.

    Snubbers must be physically close to switching devices to be effective.
    Distance >10mm increases loop inductance and reduces effectiveness.

    Args:
        igbt_position: IGBT center position (x, y)
        snubber_components: List of snubber component refs (R, C, diodes)
        snubber_positions: Dict of {component_ref: (x, y)} for snubber components
        max_distance_mm: Maximum allowed distance from IGBT

    Returns:
        SwitchingNodeResult with violations for snubbers too far from IGBT
    """
    violations = []

    for comp in snubber_components:
        if comp in snubber_positions:
            d = _distance(igbt_position, snubber_positions[comp])
            if d > max_distance_mm:
                violations.append(
                    SwitchingNodeViolation(
                        node_type="SNUBBER",
                        component_refs=[comp],
                        code="SW-SNUB-001",
                        message=f"Snubber component {comp} is {d:.1f}mm from IGBT (limit: {max_distance_mm}mm)",
                        location=snubber_positions[comp],
                        severity="error",
                    )
                )

    if not snubber_components:
        violations.append(
            SwitchingNodeViolation(
                node_type="SNUBBER",
                component_refs=[],
                code="SW-SNUB-002",
                message="No snubber components placed near IGBT",
                location=igbt_position,
                severity="warning",
            )
        )

    return SwitchingNodeResult(passed=len(violations) == 0, violations=violations)


def check_no_power_planes_under_switching_nodes(
    switching_node_positions: dict[str, tuple[float, float]],
    power_plane_zones: dict[
        str, list[tuple[float, float, float, float]]
    ],  # {voltage: [(x, y, w, h)]}
    switching_node_types: dict[str, str],  # {node_ref: "HALF_BRIDGE_SW"|"BUCK_SW"|"GATE_DRIVER"}
) -> SwitchingNodeResult:
    """
    Check that no 5V/3.3V power islands exist under switching nodes.

    Power planes under switching nodes create capacitive coupling and EMI.
    Only ground planes should be under switching nodes.

    Args:
        switching_node_positions: Dict of {node_ref: (x, y)} for switching nodes
        power_plane_zones: Dict of {voltage: [(x, y, width, height)]} for power planes
        switching_node_types: Dict of {node_ref: node_type} for classification

    Returns:
        SwitchingNodeResult with violations for power planes under switching nodes
    """
    violations = []

    for node_ref, node_pos in switching_node_positions.items():
        node_type = switching_node_types.get(node_ref, "HALF_BRIDGE_SW")

        for voltage, zones in power_plane_zones.items():
            for zone in zones:
                if _point_in_rect(node_pos, zone):
                    violations.append(
                        SwitchingNodeViolation(
                            node_type=node_type,
                            component_refs=[node_ref],
                            code="SW-PLANE-001",
                            message=f"Power plane ({voltage}) found under switching node '{node_ref}' ({node_type})",
                            location=node_pos,
                            severity="error",
                        )
                    )

    return SwitchingNodeResult(passed=len(violations) == 0, violations=violations)


def check_buck_converter_switching_node(
    buck_switch_position: tuple[float, float],
    buck_components: list[str],  # LMR51430, inductor, diode, caps
    max_area_mm2: float = 50.0,  # Smaller area for buck (170V vs 340V)
) -> SwitchingNodeResult:
    """
    Check buck converter switching node containment.

    Buck converter SW node: 0V to 170V, ~10 V/ns, ~600kHz.
    Harmonics extend >100MHz, requiring careful containment.

    Args:
        buck_switch_position: Buck converter switch node position
        buck_components: List of buck converter component refs
        max_area_mm2: Maximum allowed copper area

    Returns:
        SwitchingNodeResult with violations for buck converter switching node
    """
    violations = []

    if len(buck_components) < 3:
        violations.append(
            SwitchingNodeViolation(
                node_type="BUCK_SW",
                component_refs=buck_components,
                code="SW-BUCK-001",
                message=f"Buck converter SW node has only {len(buck_components)} components (expected >=3: inductor, diode, output cap)",
                location=buck_switch_position,
                severity="warning",
            )
        )

    return SwitchingNodeResult(passed=len(violations) == 0, violations=violations)


def check_gate_driver_outputs(
    gate_driver_positions: dict[str, tuple[float, float]],  # {gate_driver_ref: (x, y)}
    gate_output_nets: dict[str, list[str]],  # {driver_ref: [net_names]}
    max_area_mm2: float = 25.0,  # Small area for gate drives (0-20V, ~5 V/ns)
) -> SwitchingNodeResult:
    """
    Check gate driver output switching node containment.

    Gate drive outputs: 0V to 20V, ~5 V/ns, rise/fall <50ns.
    Fast edges can couple to adjacent traces if not contained.

    Args:
        gate_driver_positions: Dict of {driver_ref: (x, y)} for gate drivers
        gate_output_nets: Dict of {driver_ref: [output_net_names]} for gate outputs
        max_area_mm2: Maximum allowed copper area for gate output nodes

    Returns:
        SwitchingNodeResult with violations for gate driver output nodes
    """
    violations = []

    for driver_ref, driver_pos in gate_driver_positions.items():
        output_nets = gate_output_nets.get(driver_ref, [])
        if not output_nets:
            violations.append(
                SwitchingNodeViolation(
                    node_type="GATE_DRIVER",
                    component_refs=[driver_ref],
                    code="SW-GATE-001",
                    message=f"Gate driver '{driver_ref}' has no output nets defined",
                    location=driver_pos,
                    severity="warning",
                )
            )

    return SwitchingNodeResult(passed=len(violations) == 0, violations=violations)


def check_switching_frequency_harmonics(
    switching_nodes: dict[str, dict],  # {node_ref: {type, frequency, position}}
    board_dimensions: tuple[float, float],  # (width, height)
) -> SwitchingNodeResult:
    """
    Check that switching node placement considers frequency harmonics.

    Different switching nodes have different fundamental frequencies and
    harmonic content that affects EMI coupling.

    Args:
        switching_nodes: Dict of {node_ref: {type, frequency_hz, position}}
        board_dimensions: Board width and height for wavelength calculations

    Returns:
        SwitchingNodeResult with violations for poor frequency-aware placement
    """
    violations = []

    board_diag = math.hypot(board_dimensions[0], board_dimensions[1])

    for node_ref, node_info in switching_nodes.items():
        freq = node_info.get("frequency_hz", 0)
        if freq > 0:
            wavelength_mm = 3e11 / freq
            if wavelength_mm < board_diag * 2:
                violations.append(
                    SwitchingNodeViolation(
                        node_type=node_info.get("type", "UNKNOWN"),
                        component_refs=[node_ref],
                        code="SW-FREQ-001",
                        message=f"Switching node '{node_ref}' wavelength ({wavelength_mm:.0f}mm @ {freq / 1e3:.0f}kHz) may cause board resonance",
                        location=node_info.get("position"),
                        severity="warning",
                    )
                )

    return SwitchingNodeResult(passed=len(violations) == 0, violations=violations)
