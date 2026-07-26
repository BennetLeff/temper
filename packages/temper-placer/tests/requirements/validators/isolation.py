"""
Isolation barrier validation functions.

These functions check if PCB layout meets safety isolation requirements
per REQ-SAFE-02 for maintaining proper clearance and isolation between
high-voltage and low-voltage circuits.
"""

from dataclasses import dataclass
from typing import Any

from ._geometry import _distance


@dataclass
class IsolationViolation:
    """An isolation barrier violation."""

    barrier_type: str  # "MAIN_HV_LV", "UCC21550", "ADUM1250"
    component_refs: list[str]
    code: str
    message: str
    location: tuple[float, float] | None = None
    clearance_mm: float | None = None
    slot_width_mm: float | None = None
    severity: str = "error"  # error, warning


@dataclass
class IsolationResult:
    """Result of isolation barrier validation."""

    passed: bool
    violations: list[IsolationViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_isolation_slot(
    barrier: dict[str, Any],
    min_width_mm: float = 2.0,
) -> IsolationResult:
    """
    Check that isolation barriers have proper routed slot width.

    Isolation barriers require routed slots to maintain creepage distance
    and prevent contamination bridging between HV and LV sides. This is a
    direct scalar comparison of ``barrier["slot_width"]`` against
    *min_width_mm* -- the default of 2.0mm matches
    packages/temper-drc-rs/src/rules/routing/isolation_slot.rs's
    ``MIN_SLOT_WIDTH_MM`` constant, which performs the equivalent check on
    real board polygon geometry (bounding-box minimum width) rather than a
    caller-supplied scalar. The two are not swappable (this operates on a
    dict fixture with a pre-measured width; the Rust rule measures the
    width itself from a ``geo::Polygon``), but the threshold and intent are
    the same check at two different levels of the pipeline.

    Args:
        barrier: Dict with barrier information including:
            - type: "MAIN_HV_LV", "UCC21550", "ADUM1250"
            - position: (x, y) center position
            - slot_width: actual slot width in mm
            - slot_length: actual slot length in mm
            - board_width: total board width for main barrier
        min_width_mm: Minimum required slot width

    Returns:
        IsolationResult with violations for insufficient slot width
    """
    slot_width = barrier.get("slot_width")
    barrier_type = barrier.get("type", "")

    if slot_width is not None and slot_width < min_width_mm:
        violation = IsolationViolation(
            barrier_type=barrier_type,
            component_refs=[],
            code="SLOT_WIDTH_INSUFFICIENT",
            message=(
                f"{barrier_type} isolation slot width {slot_width}mm is below "
                f"the minimum required {min_width_mm}mm"
            ),
            location=barrier.get("position"),
            slot_width_mm=slot_width,
            severity="error",
        )
        return IsolationResult(passed=False, violations=[violation])

    return IsolationResult(passed=True, violations=[])


def check_no_traces_across_barrier(
    traces: list[dict[str, Any]],
    barrier: dict[str, Any],
) -> IsolationResult:
    """
    Check that no traces cross the isolation barrier.

    Only isolation components (transformers, optocouplers) should provide
    electrical connection across HV-LV barriers. The barrier is modeled as
    an infinite line through ``barrier["position"]``, perpendicular to its
    "orientation" axis: a "horizontal" barrier is the line y = position[1]
    (traces are checked for crossing in y); "vertical" is x = position[0].
    A trace crosses the barrier if its two endpoints fall on strictly
    opposite sides of that line (endpoint coordinates given a sign relative
    to the barrier coordinate, and the two signs differ) -- a trace that
    ends exactly on the barrier line, or stays entirely on one side, does
    not count as crossing.

    Real trace-vs-barrier crossing on the actual board is exactly
    packages/temper-drc-rs/src/rules/routing/isolation_barrier.rs's
    ``check_trace_barrier_intersections``, which does a real 2D line
    intersection (``geo::Intersects``) against a finite barrier segment
    (``barrier.y_span``) built from real trace/zone geometry, rather than
    this fixture's infinite-line/dict-based model. This function is the
    same *check* at the placement-fixture level this validator suite
    otherwise uses, not a re-implementation of the Rust engine.

    Args:
        traces: List of trace dictionaries with:
            - start: (x, y) start position
            - end: (x, y) end position
            - net: net name
            - layer: layer name
        barrier: Dict with barrier information including:
            - type: barrier type
            - position: (x, y) center
            - orientation: "horizontal" or "vertical"
            - clearance_mm: required clearance

    Returns:
        IsolationResult with violations for traces crossing barrier
    """
    orientation = barrier.get("orientation", "vertical")
    bx, by = barrier["position"]
    barrier_type = barrier.get("type", "")
    axis = 1 if orientation == "horizontal" else 0
    barrier_coord = by if axis == 1 else bx

    violations: list[IsolationViolation] = []
    for trace in traces:
        start = trace["start"]
        end = trace["end"]
        c1 = start[axis] - barrier_coord
        c2 = end[axis] - barrier_coord

        if c1 * c2 < 0:
            # Opposite signs -> the segment straddles the barrier line.
            # Linear interpolation of the crossing point along the segment.
            t = c1 / (c1 - c2)
            crossing = (
                start[0] + t * (end[0] - start[0]),
                start[1] + t * (end[1] - start[1]),
            )
            violations.append(
                IsolationViolation(
                    barrier_type=barrier_type,
                    component_refs=[],
                    code="TRACE_CROSSING_BARRIER",
                    message=(
                        f"Trace on net '{trace.get('net', '?')}' "
                        f"(layer {trace.get('layer', '?')}) crosses isolation "
                        f"barrier '{barrier_type}'"
                    ),
                    location=crossing,
                    clearance_mm=barrier.get("clearance_mm"),
                    severity="error",
                )
            )

    return IsolationResult(passed=len(violations) == 0, violations=violations)


def check_ucc21550_barrier(
    driver_position: tuple[float, float],
) -> IsolationResult:
    """
    Check UCC21550 gate driver isolation requirements.

    UCC21550 requires:
    - No traces under transformer area (pins 5-12)
    - Ground plane cutout under package center
    - Separate power domains: VCCI, VDDA, VDDB

    NOT IMPLEMENTED -- left raising NotImplementedError deliberately,
    per this task's explicit instruction to leave a check unimplemented
    rather than have it "inspect nothing and pass" when the data it needs
    isn't available. The signature takes only ``driver_position``: a bare
    (x, y) tuple. None of the three requirements above -- trace-under-
    package geometry, ground-plane-cutout geometry, or per-pin power-
    domain net assignment -- can be evaluated from a single point. There is
    no board/trace/ground-plane/net argument this function could consult.
    Implementing this faithfully needs, at minimum: the transformer
    keepout rectangle (pins 5-12 footprint extent), the trace list (as
    check_no_traces_across_barrier receives), and the ground-plane polygon
    list (as check_ground_plane_split receives) -- i.e. this function's
    signature itself is the missing piece, not the logic. Returning a
    fabricated "no violations" IsolationResult here would be indistinguishable
    from a genuinely-checked pass and is exactly what this task instructs
    against.

    Args:
        driver_position: UCC21550 center position (x, y)

    Returns:
        IsolationResult with violations for UCC21550 isolation violations
    """
    raise NotImplementedError(
        "check_ucc21550_barrier cannot be implemented faithfully: its "
        "signature provides only a bare (x, y) position, with no trace "
        "list, ground-plane geometry, or per-pin net assignment to check "
        "'no traces under transformer', 'ground plane cutout', or "
        "'separate VCCI/VDDA/VDDB power domains' against. See the "
        "docstring for what a faithful implementation would need."
    )


def check_adum1250_barrier(
    isolator_position: tuple[float, float],
) -> IsolationResult:
    """
    Check ADUM1250 I2C isolator isolation requirements.

    ADUM1250 requires:
    - 10mm clearance between isolated sides
    - Ground plane split under ADUM1250
    - Separate power supplies each side

    NOT IMPLEMENTED -- same reasoning as check_ucc21550_barrier, and left
    unimplemented for the same reason. The signature takes only
    ``isolator_position``: a bare (x, y) tuple, with no component-clearance
    data (as check_clearance_distances receives), ground-plane geometry (as
    check_ground_plane_split receives), or power-supply-domain data (as
    check_power_domain_separation receives) to check any of the three
    stated requirements against. This function's own docstring already
    describes checks this module implements elsewhere given the right
    inputs (check_clearance_distances, check_ground_plane_split,
    check_power_domain_separation) -- the gap here is specifically that
    this function is never given those inputs.

    Args:
        isolator_position: ADUM1250 center position (x, y)

    Returns:
        IsolationResult with violations for ADUM1250 isolation violations
    """
    raise NotImplementedError(
        "check_adum1250_barrier cannot be implemented faithfully: its "
        "signature provides only a bare (x, y) position, with no "
        "component/clearance data, ground-plane geometry, or power-supply "
        "domain data to check '10mm clearance', 'ground plane split', or "
        "'separate power supplies' against. See the docstring for what a "
        "faithful implementation would need."
    )


def check_ground_plane_split(
    ground_planes: dict[str, list[tuple[float, float, float, float]]],
    barriers: list[dict[str, Any]],
) -> IsolationResult:
    """
    Check that ground planes are properly split at isolation barriers.

    Ground planes must be split to prevent unwanted coupling between
    HV and LV domains while maintaining star-ground topology. For each
    barrier, treats its "orientation" (default "vertical") the same way
    check_no_traces_across_barrier does -- an infinite line through
    ``barrier["position"]`` -- and flags any ground-plane rectangle
    ``(x, y, width, height)`` whose span along the barrier's axis strictly
    straddles that line (i.e. the rectangle has copper on both sides,
    meaning the plane was never actually cut there).

    Args:
        ground_planes: Dict of {layer_name: [(x, y, width, height)]} for ground planes
        barriers: List of barrier dictionaries with position and type

    Returns:
        IsolationResult with violations for improper ground plane splits
    """
    violations: list[IsolationViolation] = []

    for barrier in barriers:
        orientation = barrier.get("orientation", "vertical")
        bx, by = barrier["position"]
        barrier_type = barrier.get("type", "")
        axis = 1 if orientation == "horizontal" else 0
        barrier_coord = by if axis == 1 else bx

        for layer_name, rects in ground_planes.items():
            for rect in rects:
                x, y, width, height = rect
                lo = y if axis == 1 else x
                extent = height if axis == 1 else width
                hi = lo + extent

                if lo < barrier_coord < hi:
                    violations.append(
                        IsolationViolation(
                            barrier_type=barrier_type,
                            component_refs=[],
                            code="GROUND_PLANE_NOT_SPLIT",
                            message=(
                                f"Ground plane on layer '{layer_name}' spans "
                                f"[{lo}, {hi}] and is not split at isolation "
                                f"barrier '{barrier_type}' (line at {barrier_coord})"
                            ),
                            location=(bx, by),
                            severity="error",
                        )
                    )

    return IsolationResult(passed=len(violations) == 0, violations=violations)


def check_clearance_distances(
    components: dict[str, dict[str, Any]],
    barriers: list[dict[str, Any]],
    min_clearance_mm: float = 10.0,
) -> IsolationResult:
    """
    Check minimum clearance distances between HV and LV components.

    Safety standards require minimum creepage and clearance distances
    based on working voltage and pollution degree. This checks every
    component's straight-line distance (via ``_geometry._distance``, the
    same helper reused throughout this validator suite) to each barrier's
    position -- a component sitting too close to the barrier line itself
    erodes the barrier's own effective clearance/creepage margin,
    regardless of which side it's nominally on. The required distance for
    a given barrier is ``max(min_clearance_mm, barrier["clearance_mm"])``:
    the stricter of the function's default/caller-supplied floor and any
    per-barrier requirement.

    Args:
        components: Dict of {ref: {position, voltage, type}} for all components
        barriers: List of barrier information
        min_clearance_mm: Minimum required clearance distance

    Returns:
        IsolationResult with violations for insufficient clearance
    """
    violations: list[IsolationViolation] = []

    for ref, comp in components.items():
        comp_position = comp["position"]
        for barrier in barriers:
            barrier_type = barrier.get("type", "")
            required = max(min_clearance_mm, barrier.get("clearance_mm", min_clearance_mm))
            dist = _distance(comp_position, barrier["position"])

            if dist < required:
                violations.append(
                    IsolationViolation(
                        barrier_type=barrier_type,
                        component_refs=[ref],
                        code="INSUFFICIENT_CLEARANCE",
                        message=(
                            f"Component {ref} is {dist:.3f}mm from isolation "
                            f"barrier '{barrier_type}', below required "
                            f"minimum {required}mm"
                        ),
                        location=comp_position,
                        clearance_mm=dist,
                        severity="error",
                    )
                )

    return IsolationResult(passed=len(violations) == 0, violations=violations)


def check_power_domain_separation(
    power_supplies: dict[str, dict[str, Any]],
    isolation_components: list[str],
) -> IsolationResult:
    """
    Check that power domains are properly separated by isolation.

    Each isolated side should have its own power supply with no
    direct electrical connection except through isolation components.
    Two checks:

    1. Any supply whose declared "domain" is missing or the literal string
       "SHARED" (case-insensitive) is flagged directly (error) -- an
       explicit signal that the domain was never actually split, the same
       failure mode documented for this design's real pre-redesign star
       join in docs/hardware/IEC60335_CRITICAL_COMPONENTS.md Sec 2 (the
       SELV secondary strapped back to the mains-referenced node).
    2. If 2+ distinct (non-SHARED) domains are declared across the
       supplies but no isolation_components are listed, that is flagged as
       a warning: multiple domains are claimed but nothing in the given
       data enforces the isolation between them.

    Args:
        power_supplies: Dict of {supply_ref: {voltage, position, domain}} for power supplies
        isolation_components: List of isolation component refs (UCC21550, ADUM1250, etc.)

    Returns:
        IsolationResult with violations for power domain coupling
    """
    violations: list[IsolationViolation] = []
    distinct_domains: set[str] = set()

    for ref, supply in power_supplies.items():
        domain = supply.get("domain")
        if domain is None or str(domain).upper() == "SHARED":
            violations.append(
                IsolationViolation(
                    barrier_type="POWER_DOMAIN",
                    component_refs=[ref],
                    code="POWER_DOMAIN_NOT_SEPARATED",
                    message=(
                        f"Power supply {ref} has an undifferentiated/shared "
                        f"domain ({domain!r}) -- HV and LV sides are not "
                        f"separated"
                    ),
                    location=supply.get("position"),
                    severity="error",
                )
            )
        else:
            distinct_domains.add(str(domain))

    if len(distinct_domains) >= 2 and not isolation_components:
        violations.append(
            IsolationViolation(
                barrier_type="POWER_DOMAIN",
                component_refs=list(power_supplies.keys()),
                code="MISSING_ISOLATION_COMPONENTS",
                message=(
                    f"Multiple power domains declared ({sorted(distinct_domains)}) "
                    f"but no isolation_components given to bridge them"
                ),
                severity="warning",
            )
        )

    passed = not any(v.severity == "error" for v in violations)
    return IsolationResult(passed=passed, violations=violations)
