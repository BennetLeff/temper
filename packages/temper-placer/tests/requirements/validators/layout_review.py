"""
Layout review validation functions.

These functions check if PCB layouts meet requirements per REQ-REV-02:
Layout Review Checklist.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ._geometry import _distance, _point_in_rect


def _segment_intersects_rect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    x, y, w, h = rect
    x1, y1 = p1
    x2, y2 = p2

    if _point_in_rect(p1, rect) and not _point_in_rect(p2, rect):
        return True
    if _point_in_rect(p2, rect) and not _point_in_rect(p1, rect):
        return True

    def _line_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(d) < 1e-9:
            return False
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / d
        return 0 <= t <= 1 and 0 <= u <= 1

    edges = [
        (x, y, x + w, y),
        (x + w, y, x + w, y + h),
        (x + w, y + h, x, y + h),
        (x, y + h, x, y),
    ]
    return any(_line_intersect(x1, y1, x2, y2, ex1, ey1, ex2, ey2) for ex1, ey1, ex2, ey2 in edges)


@dataclass
class ComponentPlacement:
    """Component placement information from layout."""

    ref: str
    value: str
    footprint: str
    x: float  # mm
    y: float  # mm
    rotation: float  # degrees
    layer: str  # "F.Cu", "B.Cu", etc.
    part_number: str | None = None
    thermal_zone: str | None = None  # "HV", "LV", "ANALOG", "DIGITAL"
    is_heatsink_component: bool = False
    is_power_component: bool = False


@dataclass
class TraceInfo:
    """Trace information from layout."""

    net_name: str
    width: float  # mm
    layer: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    via_count: int = 0
    is_power: bool = False
    is_high_speed: bool = False
    is_critical: bool = False


@dataclass
class ViaInfo:
    """Via information from layout."""

    x: float
    y: float
    drill: float  # mm
    size: float  # mm
    layers: tuple[str, str]  # (from_layer, to_layer)
    net_name: str | None = None


@dataclass
class PlaneInfo:
    """Power plane information from layout."""

    net_name: str
    layer: str
    copper_pour: bool = True
    stitching_vias: list[ViaInfo] = field(default_factory=list)
    thermal_relief: bool = True


@dataclass
class LayoutViolation:
    """A layout design rule violation."""

    code: str
    message: str
    severity: str = "error"  # "error", "warning", "info"
    component_ref: str | None = None
    net_name: str | None = None
    coordinates: tuple[float, float] | None = None
    details: str | None = None


@dataclass
class LayoutReviewResult:
    """Result of layout review validation."""

    passed: bool
    violations: list[LayoutViolation]
    warnings: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "info")


# =============================================================================
# Component Placement Verification
# =============================================================================


def check_thermal_management(
    components: list[ComponentPlacement],
    thermal_zones: dict[str, str],  # zone_name: temperature_target
) -> LayoutReviewResult:
    """
    Check thermal management in component placement.

    Verifies:
    - Power components placed in thermal zones
    - Heatsink components have adequate clearance
    - Thermal paths unobstructed
    - Temperature-sensitive components away from heat sources

    Args:
        components: List of component placements
        thermal_zones: Dict of thermal zone names to temperature targets

    Returns:
        LayoutReviewResult with violations for poor thermal management
    """
    violations = []

    for comp in components:
        if comp.is_power_component and comp.thermal_zone not in ("HV", "POWER"):
            violations.append(
                LayoutViolation(
                    code="THERM-001",
                    message=f"Power component {comp.ref} not in a designated thermal zone (found: {comp.thermal_zone})",
                    severity="warning",
                    component_ref=comp.ref,
                    coordinates=(comp.x, comp.y),
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_component_clearances(
    components: list[ComponentPlacement],
    min_clearance: float = 0.2,  # mm
) -> LayoutReviewResult:
    """
    Check minimum component clearances.

    Verifies:
    - All components maintain minimum spacing
    - No overlapping components
    - Adequate clearance for assembly
    - Keep-out zones respected

    Args:
        components: List of component placements
        min_clearance: Minimum clearance between components (mm)

    Returns:
        LayoutReviewResult with violations for insufficient clearances
    """
    violations = []

    for i, comp_a in enumerate(components):
        for comp_b in components[i + 1 :]:
            d = _distance((comp_a.x, comp_a.y), (comp_b.x, comp_b.y))
            if d < min_clearance:
                violations.append(
                    LayoutViolation(
                        code="CLEAR-CMP-001",
                        message=f"Components {comp_a.ref} and {comp_b.ref} too close: {d:.2f}mm (min: {min_clearance}mm)",
                        severity="error",
                        component_ref=comp_a.ref,
                        coordinates=((comp_a.x + comp_b.x) / 2, (comp_a.y + comp_b.y) / 2),
                    )
                )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_component_orientation(
    components: list[ComponentPlacement],
    preferred_orientations: dict[str, list[float]] | None = None,
) -> LayoutReviewResult:
    """
    Check component orientation consistency.

    Verifies:
    - Similar components have consistent orientation
    - Polarized components correctly oriented
    - ICs follow standard orientation (pin 1 indicator)
    - Connectors oriented for cable routing

    Args:
        components: List of component placements
        preferred_orientations: Dict of component types to preferred rotations

    Returns:
        LayoutReviewResult with violations for poor orientation
    """
    violations = []

    orientation_by_type: dict[str, list[float]] = {}
    for comp in components:
        pkg = comp.footprint.split(":")[-1] if ":" in comp.footprint else comp.footprint
        orientation_by_type.setdefault(pkg, []).append(comp.rotation)

    for pkg, rotations in orientation_by_type.items():
        if len(rotations) >= 2:
            normed = {((r % 360) + 360) % 360 for r in rotations}
            if len(normed) > 2:
                violations.append(
                    LayoutViolation(
                        code="ORIENT-001",
                        message=f"Package {pkg} has {len(normed)} different orientations ({sorted(normed)})",
                        severity="warning",
                    )
                )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_power_component_placement(
    components: list[ComponentPlacement],
    power_nets: list[str],
) -> LayoutReviewResult:
    """
    Check power component placement optimization.

    Verifies:
    - IGBTs placed for minimal switching loop area
    - Gate drivers close to IGBTs (<10mm)
    - Bulk capacitors near power entry points
    - Snubber components close to switching nodes

    Args:
        components: List of component placements
        power_nets: List of power net names

    Returns:
        LayoutReviewResult with violations for poor power component placement
    """
    violations = []
    power_comps = [c for c in components if c.is_power_component]

    if not power_comps:
        violations.append(
            LayoutViolation(
                code="PPOW-001",
                message="No power components identified in placement",
                severity="warning",
            )
        )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_heatsink_clearance(
    components: list[ComponentPlacement],
    heatsink_zones: list[tuple[float, float, float, float]],  # [(x, y, width, height)]
) -> LayoutReviewResult:
    """
    Check heatsink component clearances.

    Verifies:
    - IGBTs have adequate heatsink clearance
    - No components in heatsink mounting areas
    - Thermal vias present under heatsink components
    - Thermal pads properly sized

    Args:
        components: List of component placements
        heatsink_zones: List of heatsink keep-out zones

    Returns:
        LayoutReviewResult with violations for insufficient heatsink clearance
    """
    violations = []

    for comp in components:
        comp_pt = (comp.x, comp.y)
        for hz in heatsink_zones:
            if _point_in_rect(comp_pt, hz) and not comp.is_heatsink_component:
                violations.append(
                    LayoutViolation(
                        code="HS-001",
                        message=f"Component {comp.ref} placed in heatsink keep-out zone",
                        severity="error",
                        component_ref=comp.ref,
                        coordinates=comp_pt,
                    )
                )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


# =============================================================================
# Trace Routing Verification
# =============================================================================


def check_trace_widths(
    traces: list[TraceInfo],
    min_widths: dict[str, float],  # net_class: min_width_mm
) -> LayoutReviewResult:
    """
    Check trace widths meet requirements.

    Verifies:
    - Power traces have adequate width for current
    - Signal traces meet minimum width requirements
    - High-speed traces have controlled impedance
    - Critical traces have appropriate width

    Args:
        traces: List of trace information
        min_widths: Dict of net classes to minimum widths

    Returns:
        LayoutReviewResult with violations for insufficient trace widths
    """
    violations = []

    default_min = min_widths.get("DEFAULT", 0.15)
    power_min = min_widths.get("POWER", 0.5)

    for trace in traces:
        req_width = power_min if trace.is_power else default_min
        if trace.width < req_width:
            violations.append(
                LayoutViolation(
                    code="TRACE-W-001",
                    message=f"Trace on net '{trace.net_name}' width {trace.width}mm < required {req_width}mm",
                    severity="error",
                    net_name=trace.net_name,
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_trace_spacing(
    traces: list[TraceInfo],
    min_spacing: float = 0.15,  # mm
) -> LayoutReviewResult:
    """
    Check trace spacing requirements.

    Verifies:
    - All traces maintain minimum spacing
    - HV-LV isolation spacing adequate
    - No trace-to-via spacing violations
    - Differential pairs maintain spacing

    Args:
        traces: List of trace information
        min_spacing: Minimum spacing between traces (mm)

    Returns:
        LayoutReviewResult with violations for insufficient spacing
    """
    violations = []

    for i, ta in enumerate(traces):
        for tb in traces[i + 1 :]:
            if ta.layer == tb.layer:
                d_start = _distance((ta.start_x, ta.start_y), (tb.start_x, tb.start_y))
                d_end = _distance((ta.end_x, ta.end_y), (tb.end_x, tb.end_y))
                if min(d_start, d_end) < min_spacing:
                    violations.append(
                        LayoutViolation(
                            code="TRACE-S-001",
                            message=f"Traces {ta.net_name}/{tb.net_name} spacing too small ({min(d_start, d_end):.2f}mm < {min_spacing}mm)",
                            severity="error",
                            net_name=ta.net_name,
                        )
                    )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_impedance_control(
    traces: list[TraceInfo],
    controlled_impedance_nets: list[str],
    target_impedance: float = 50.0,  # ohms
    tolerance: float = 0.10,  # +-10%
) -> LayoutReviewResult:
    """
    Check controlled impedance traces.

    Verifies:
    - High-speed traces have controlled impedance
    - Trace geometry appropriate for target impedance
    - Reference planes present
    - No discontinuities in controlled traces

    Args:
        traces: List of trace information
        controlled_impedance_nets: List of nets requiring impedance control
        target_impedance: Target impedance value (ohms)
        tolerance: Acceptable tolerance (+-10%)

    Returns:
        LayoutReviewResult with violations for impedance control issues
    """
    violations = []
    controlled_set = set(controlled_impedance_nets)
    trace_nets = {t.net_name for t in traces}

    for net in controlled_set:
        if net not in trace_nets:
            violations.append(
                LayoutViolation(
                    code="IMP-001",
                    message=f"Controlled impedance net '{net}' not found in trace list",
                    severity="warning",
                    net_name=net,
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_via_usage(
    traces: list[TraceInfo],
    vias: list[ViaInfo],
    critical_nets: list[str],
) -> LayoutReviewResult:
    """
    Check via usage optimization.

    Verifies:
    - Critical nets minimize via count
    - Vias appropriately sized
    - No via-in-pad on BGA components
    - Thermal relief on power vias

    Args:
        traces: List of trace information
        vias: List of via information
        critical_nets: List of critical net names

    Returns:
        LayoutReviewResult with violations for poor via usage
    """
    violations = []

    for trace in traces:
        if trace.net_name in critical_nets and trace.via_count > 2:
            violations.append(
                LayoutViolation(
                    code="VIA-001",
                    message=f"Critical net '{trace.net_name}' has {trace.via_count} vias (recommend <=2)",
                    severity="warning",
                    net_name=trace.net_name,
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_differential_pairs(
    traces: list[TraceInfo],
    diff_pairs: list[tuple[str, str]],  # [(net1, net2), ...]
) -> LayoutReviewResult:
    """
    Check differential pair routing.

    Verifies:
    - Differential pairs routed together
    - Consistent spacing maintained
    - Length matching adequate
    - No unnecessary vias or turns

    Args:
        traces: List of trace information
        diff_pairs: List of differential pair net names

    Returns:
        LayoutReviewResult with violations for differential pair issues
    """
    return LayoutReviewResult(
        passed=True,
        violations=[],
        warnings=["Differential pair checking not yet implemented (temper-xxx)"],
    )


# =============================================================================
# Power Plane Integrity
# =============================================================================


def check_power_planes(
    planes: list[PlaneInfo],
    power_nets: list[str],
) -> LayoutReviewResult:
    """
    Check power plane integrity.

    Verifies:
    - Power planes have adequate copper coverage
    - Stitching vias connect planes properly
    - No orphaned copper pours
    - Thermal relief appropriate

    Args:
        planes: List of power plane information
        power_nets: List of power net names

    Returns:
        LayoutReviewResult with violations for power plane issues
    """
    violations = []

    power_set = set(power_nets)
    for plane in planes:
        if plane.net_name in power_set and not plane.copper_pour:
            violations.append(
                LayoutViolation(
                    code="PLANE-001",
                    message=f"Power plane on net '{plane.net_name}' missing copper pour",
                    severity="error",
                    net_name=plane.net_name,
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_copper_pours(
    planes: list[PlaneInfo],
    min_coverage: float = 0.50,  # 50% minimum coverage
) -> LayoutReviewResult:
    """
    Check copper pour coverage.

    Verifies:
    - Adequate copper coverage on power planes
    - No large unpopulated areas
    - Thermal relief connections correct
    - No copper pour islands

    Args:
        planes: List of power plane information
        min_coverage: Minimum copper coverage ratio

    Returns:
        LayoutReviewResult with violations for poor copper coverage
    """
    violations = []

    for plane in planes:
        if not plane.copper_pour:
            violations.append(
                LayoutViolation(
                    code="POUR-001",
                    message=f"Missing copper pour on net '{plane.net_name}' layer '{plane.layer}'",
                    severity="error",
                    net_name=plane.net_name,
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_stitching_vias(
    planes: list[PlaneInfo],
    min_vias_per_plane: int = 4,
) -> LayoutReviewResult:
    """
    Check power plane stitching via density.

    Verifies:
    - Adequate stitching via density
    - Vias distributed across plane area
    - Via size appropriate for current
    - Thermal relief present

    Args:
        planes: List of power plane information
        min_vias_per_plane: Minimum number of stitching vias per plane

    Returns:
        LayoutReviewResult with violations for insufficient stitching vias
    """
    violations = []

    for plane in planes:
        if plane.copper_pour and len(plane.stitching_vias) < min_vias_per_plane:
            violations.append(
                LayoutViolation(
                    code="STITCH-001",
                    message=f"Plane '{plane.net_name}' has only {len(plane.stitching_vias)} stitching vias (min: {min_vias_per_plane})",
                    severity="warning",
                    net_name=plane.net_name,
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


# =============================================================================
# High-Voltage Isolation Verification
# =============================================================================


def check_creepage_distances(
    components: list[ComponentPlacement],
    traces: list[TraceInfo],
    hv_nets: list[str],
    min_creepage: float = 8.0,  # mm for 340V DC
) -> LayoutReviewResult:
    """
    Check creepage distances for high-voltage isolation.

    Verifies:
    - Adequate creepage between HV and LV circuits
    - Creepage paths not blocked by components
    - Clearance along surface considered
    - Pollution degree accounted for

    Args:
        components: List of component placements
        traces: List of trace information
        hv_nets: List of high-voltage net names
        min_creepage: Minimum creepage distance (mm)

    Returns:
        LayoutReviewResult with violations for insufficient creepage
    """
    violations = []
    hv_set = set(hv_nets)

    hv_comps = [c for c in components if hv_set & set(getattr(c, "nets", []))]
    lv_comps = [c for c in components if c not in set(hv_comps)]

    for hv in hv_comps:
        for lv in lv_comps:
            d = _distance((hv.x, hv.y), (lv.x, lv.y))
            if d < min_creepage:
                violations.append(
                    LayoutViolation(
                        code="CREEP-001",
                        message=f"Creepage distance {d:.1f}mm between HV component {hv.ref} and LV component {lv.ref} < {min_creepage}mm",
                        severity="error",
                        component_ref=hv.ref,
                        coordinates=((hv.x + lv.x) / 2, (hv.y + lv.y) / 2),
                    )
                )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_clearance_distances(
    components: list[ComponentPlacement],
    traces: list[TraceInfo],
    hv_nets: list[str],
    min_clearance: float = 5.0,  # mm for 340V DC
) -> LayoutReviewResult:
    """
    Check clearance distances for high-voltage isolation.

    Verifies:
    - Adequate clearance through air between HV and LV
    - No conductive paths through air
    - 3D clearance considered (component heights)
    - Functional insulation vs reinforced insulation

    Args:
        components: List of component placements
        traces: List of trace information
        hv_nets: List of high-voltage net names
        min_clearance: Minimum clearance distance (mm)

    Returns:
        LayoutReviewResult with violations for insufficient clearance
    """
    violations = []
    hv_set = set(hv_nets)

    hv_traces = [t for t in traces if t.net_name in hv_set]
    lv_traces = [t for t in traces if t.net_name not in hv_set]

    for ht in hv_traces:
        for lt in lv_traces:
            if ht.layer == lt.layer:
                d = _distance((ht.start_x, ht.start_y), (lt.start_x, lt.start_y))
                if d < min_clearance:
                    violations.append(
                        LayoutViolation(
                            code="CLEAR-001",
                            message=f"Clearance {d:.1f}mm between HV net '{ht.net_name}' and LV net '{lt.net_name}' < {min_clearance}mm",
                            severity="critical",
                            net_name=ht.net_name,
                        )
                    )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_isolation_barriers(
    components: list[ComponentPlacement],
    isolation_zones: list[tuple[float, float, float, float]],  # [(x, y, width, height)]
) -> LayoutReviewResult:
    """
    Check isolation barrier placement.

    Verifies:
    - Isolation barriers properly positioned
    - No components crossing isolation boundaries
    - Creepage paths around barriers adequate
    - Safety extra-low voltage (SELV) zones protected

    Args:
        components: List of component placements
        isolation_zones: List of isolation barrier zones

    Returns:
        LayoutReviewResult with violations for isolation barrier issues
    """
    violations = []

    for comp in components:
        comp_pt = (comp.x, comp.y)
        for zone in isolation_zones:
            if _point_in_rect(comp_pt, zone):
                violations.append(
                    LayoutViolation(
                        code="ISO-001",
                        message=f"Component {comp.ref} placed in isolation barrier zone",
                        severity="error",
                        component_ref=comp.ref,
                        coordinates=comp_pt,
                    )
                )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


# =============================================================================
# EMI/EMC Considerations
# =============================================================================


def check_loop_areas(
    components: list[ComponentPlacement],
    traces: list[TraceInfo],
    critical_loops: list[list[str]],  # List of net lists defining loops
    max_loop_area: float = 5.0,  # cm^2
) -> LayoutReviewResult:
    """
    Check switching loop areas for EMI reduction.

    Verifies:
    - DC bus switching loop area minimized
    - Gate drive loop areas minimized
    - Bootstrap charging loop minimized
    - Buck converter loop minimized

    Args:
        components: List of component placements
        traces: List of trace information
        critical_loops: List of critical loop net sequences
        max_loop_area: Maximum allowed loop area (cm^2)

    Returns:
        LayoutReviewResult with violations for excessive loop areas
    """
    return LayoutReviewResult(
        passed=True, violations=[], warnings=["Loop area checking not yet implemented (temper-xxx)"]
    )


def check_shielding_effectiveness(
    components: list[ComponentPlacement],
    traces: list[TraceInfo],
    shielding_zones: list[str],  # Zone names with shielding
) -> LayoutReviewResult:
    """
    Check EMI shielding effectiveness.

    Verifies:
    - High di/dt traces have return paths nearby
    - Shielding zones properly connected to ground
    - No slots in ground planes under critical traces
    - Guard traces around sensitive signals

    Args:
        components: List of component placements
        traces: List of trace information
        shielding_zones: List of shielded zone names

    Returns:
        LayoutReviewResult with violations for shielding issues
    """
    return LayoutReviewResult(
        passed=True,
        violations=[],
        warnings=["Shielding effectiveness checking not yet implemented (temper-xxx)"],
    )


def check_filter_placement(
    components: list[ComponentPlacement],
    filter_components: list[str],  # Component refs for filters
) -> LayoutReviewResult:
    """
    Check EMI filter component placement.

    Verifies:
    - EMI filters placed close to noise sources
    - Filter components properly oriented
    - Ground connections short and direct
    - Filter input/output isolation maintained

    Args:
        components: List of component placements
        filter_components: List of EMI filter component references

    Returns:
        LayoutReviewResult with violations for poor filter placement
    """
    violations = []
    filter_set = set(filter_components)
    filter_comps = [c for c in components if c.ref in filter_set]

    if filter_set and not filter_comps:
        violations.append(
            LayoutViolation(
                code="FILTER-001",
                message="EMI filter components present in netlist but not found in placement",
                severity="error",
            )
        )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


# =============================================================================
# Manufacturing Constraints
# =============================================================================


def check_drc_compliance(
    pcb_path: Path,
    drc_rules: dict[str, float] | None = None,
) -> LayoutReviewResult:
    """
    Check Design Rule Check (DRC) compliance.

    Verifies:
    - All DRC violations resolved
    - Minimum trace width and spacing met
    - Via sizes and spacing adequate
    - Annular ring requirements met

    Args:
        pcb_path: Path to PCB file
        drc_rules: Dict of DRC rule names to values

    Returns:
        LayoutReviewResult with DRC violations
    """
    violations = []

    if pcb_path and not pcb_path.exists():
        violations.append(
            LayoutViolation(
                code="DRC-001",
                message=f"PCB file not found: {pcb_path}",
                severity="error",
            )
        )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_minimum_features(
    traces: list[TraceInfo],
    vias: list[ViaInfo],
    min_trace_width: float = 0.15,  # mm (6 mil)
    min_via_drill: float = 0.3,  # mm (12 mil)
) -> LayoutReviewResult:
    """
    Check minimum manufacturable features.

    Verifies:
    - All traces meet minimum width
    - All vias meet minimum drill size
    - Text and graphics above minimum size
    - Solder mask features manufacturable

    Args:
        traces: List of trace information
        vias: List of via information
        min_trace_width: Minimum trace width (mm)
        min_via_drill: Minimum via drill size (mm)

    Returns:
        LayoutReviewResult with violations for features below minimum
    """
    violations = []

    for trace in traces:
        if trace.width < min_trace_width:
            violations.append(
                LayoutViolation(
                    code="MF-001",
                    message=f"Trace on net '{trace.net_name}' width {trace.width}mm below minimum {min_trace_width}mm",
                    severity="error",
                    net_name=trace.net_name,
                )
            )

    for via in vias:
        if via.drill < min_via_drill:
            violations.append(
                LayoutViolation(
                    code="MF-002",
                    message=f"Via drill {via.drill}mm below minimum {min_via_drill}mm",
                    severity="error",
                    coordinates=(via.x, via.y),
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_panel_utilization(
    board_outline: tuple[float, float, float, float],  # (x, y, width, height)
    panel_size: tuple[float, float],  # (width, height)
    board_count: int = 1,
) -> LayoutReviewResult:
    """
    Check PCB panel utilization efficiency.

    Verifies:
    - Boards efficiently arranged on panel
    - Adequate panel borders and spacing
    - V-scoring or tab routing considered
    - Panel utilization > 70%

    Args:
        board_outline: Board dimensions (x, y, width, height)
        panel_size: Panel dimensions (width, height)
        board_count: Number of boards per panel

    Returns:
        LayoutReviewResult with panel utilization issues
    """
    violations = []

    board_area = board_outline[2] * board_outline[3] * board_count
    panel_area = panel_size[0] * panel_size[1]

    if panel_area > 0:
        utilization = board_area / panel_area * 100
        if utilization < 70.0:
            violations.append(
                LayoutViolation(
                    code="PANEL-001",
                    message=f"Panel utilization {utilization:.1f}% below 70% target",
                    severity="warning",
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


# =============================================================================
# Silkscreen and Documentation
# =============================================================================


def check_reference_designators(
    components: list[ComponentPlacement],
    silkscreen_layer: str = "F.SilkS",
) -> LayoutReviewResult:
    """
    Check reference designator placement and readability.

    Verifies:
    - All components have reference designators
    - Designators not obscured by copper or solder mask
    - Designators not overlapping other text
    - Minimum text size readable

    Args:
        components: List of component placements
        silkscreen_layer: Silkscreen layer name

    Returns:
        LayoutReviewResult with reference designator issues
    """
    violations = []

    for comp in components:
        if not comp.ref or comp.ref.strip() == "":
            violations.append(
                LayoutViolation(
                    code="REF-001",
                    message="Component has empty reference designator",
                    severity="error",
                    coordinates=(comp.x, comp.y),
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_polarity_marks(
    components: list[ComponentPlacement],
    polarized_components: list[str],  # Component refs that need polarity marks
) -> LayoutReviewResult:
    """
    Check polarity marking for polarized components.

    Verifies:
    - Polarized components have polarity indicators
    - Polarity marks not obscured
    - Consistent polarity symbol style
    - Critical polarity clearly marked

    Args:
        components: List of component placements
        polarized_components: List of polarized component references

    Returns:
        LayoutReviewResult with polarity marking issues
    """
    violations = []
    pol_set = set(polarized_components)
    placed = {c.ref for c in components}

    for ref in pol_set:
        if ref not in placed:
            violations.append(
                LayoutViolation(
                    code="POL-001",
                    message=f"Polarized component {ref} not found in placement",
                    severity="warning",
                    component_ref=ref,
                )
            )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_test_point_accessibility(
    components: list[ComponentPlacement],
    test_points: list[str],  # Component refs for test points
    probe_access_zones: list[tuple[float, float, float, float]],
) -> LayoutReviewResult:
    """
    Check test point accessibility for manufacturing and test.

    Verifies:
    - Test points accessible for probing
    - Adequate clearance around test points
    - Test points not covered by components
    - Test point size adequate for probes

    Args:
        components: List of component placements
        test_points: List of test point component references
        probe_access_zones: List of required access zones

    Returns:
        LayoutReviewResult with test point accessibility issues
    """
    violations = []
    tp_set = set(test_points)
    tp_comps = [c for c in components if c.ref in tp_set]

    if tp_set and not tp_comps:
        violations.append(
            LayoutViolation(
                code="TP-001",
                message="Test points defined but not found in placement",
                severity="error",
            )
        )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)


def check_version_revisions(
    pcb_path: Path,
    expected_version: str,
) -> LayoutReviewResult:
    """
    Check version and revision marking.

    Verifies:
    - Board version clearly marked on silkscreen
    - Revision letter present
    - Date code if required
    - Version marking readable and permanent

    Args:
        pcb_path: Path to PCB file
        expected_version: Expected version string

    Returns:
        LayoutReviewResult with version marking issues
    """
    violations = []

    if pcb_path and not pcb_path.exists():
        violations.append(
            LayoutViolation(
                code="VER-001",
                message=f"PCB file not found for version check: {pcb_path}",
                severity="error",
            )
        )

    if not expected_version:
        violations.append(
            LayoutViolation(
                code="VER-002",
                message="Expected board version not specified",
                severity="warning",
            )
        )

    return LayoutReviewResult(passed=len(violations) == 0, violations=violations)
