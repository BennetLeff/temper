"""
EMI filter layout validation functions.

These functions check if EMI filter component placement meets EN 55014-1
requirements per REQ-EMC-03.
"""

from dataclasses import dataclass
from enum import Enum

from ._geometry import (
    _distance,
    _point_to_polyline_distance,
    _polyline_length,
    _polyline_min_distance,
)


class FilterComponent(Enum):
    """EMI filter component types."""

    FUSE = "fuse"
    MOV = "mov"
    L_DM = "l_dm"
    L_CM = "l_cm"
    C_X1 = "c_x1"
    C_X2 = "c_x2"
    C_Y1 = "c_y1"
    C_Y2 = "c_y2"


@dataclass
class EMIFilterViolation:
    """An EMI filter layout violation."""

    component: str
    code: str
    message: str
    location: tuple[float, float] | None = None
    severity: str = "error"


@dataclass
class EMIFilterResult:
    """Result of EMI filter validation."""

    passed: bool
    violations: list[EMIFilterViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")


# Canonical left-to-right topology order (EN 55014-1 Pi-filter pattern):
# FUSE; MOV (downstream of / protected by the fuse -- see the note on
# check_mov_placement below, corrected 2026-07-26); optional DM inductor;
# the "input side" X-cap; the CM choke; the Y-caps (line/neutral to PE,
# after the choke); the "output side" X-cap. Shared by both
# check_filter_signal_flow and check_filter_component_order -- they differ
# only in whether an input-connector reference point is included.
#
# FUSE precedes MOV, not the reverse: an MOV's dominant end-of-life failure
# mode is thermal runaway to a low-resistance short (it does not fail open).
# If the MOV sits upstream of the fuse -- directly across the incoming AC
# line with the fuse only protecting circuitry further downstream -- a
# shorted MOV draws fault current straight from the mains with nothing in
# this appliance to interrupt it, a fire mechanism. Placing the MOV
# downstream so the fuse's own current path includes it means a shorted MOV
# blows the fuse and de-energizes the appliance. This matches this design's
# actual wiring (elec/src/modules.ato:658-659: `fuse.p2 ~ mov.p1`,
# `mov.p2 ~ ac_n`) and multiple independent secondary engineering sources
# describing the same fuse-then-MOV topology for IEC 60335-class appliance
# input protection (e.g. a Digikey IEC 60335 power-supply design article
# citing a commercial reference design: "a 2A/300V slow-blow fuse is
# provided upfront, along with a metal oxide varistor... this sequential
# arrangement means the fuse sits between the AC source and the MOV,
# protecting the entire circuit including the varistor itself";
# corroborated by general MOV-fusing fire-safety literature describing
# external fusing of MOVs against short-circuit failure). **UNVERIFIED
# against the full primary text of UL 1449 / IEC 61051-1** (both paywalled,
# not fetched in this pass) -- this is secondary-source corroboration, not
# a primary-standard citation, but no source found in this research
# contradicted it. Before 2026-07-26 this order had MOV ahead of FUSE,
# which was backwards; a real-board check against that version flagged this
# design's correct MOV-after-fuse wiring as a violation. See
# docs/evidence/2026-07-26-emc-validators-implemented.md Sec "Addendum".
_CANONICAL_ORDER: tuple[FilterComponent, ...] = (
    FilterComponent.FUSE,
    FilterComponent.MOV,
    FilterComponent.L_DM,
    FilterComponent.C_X1,
    FilterComponent.L_CM,
    FilterComponent.C_Y1,
    FilterComponent.C_Y2,
    FilterComponent.C_X2,
)
_CANONICAL_RANK: dict[FilterComponent, int] = {c: i for i, c in enumerate(_CANONICAL_ORDER)}

_ALIGNMENT_TOLERANCE_MM = 5.0  # heuristic: components meaningfully off the flow axis warn


def _order_violations(
    ordered_points: list[tuple[str, int, tuple[float, float]]],
) -> list[EMIFilterViolation]:
    """Shared monotonic-order check.

    ``ordered_points`` is a list of (label, canonical_rank, position) for
    every entry to check, in canonical order already. Sorting the same list
    by x and comparing to the canonical-rank order surfaces any component
    that is out of place in physical left-to-right flow.
    """
    violations: list[EMIFilterViolation] = []
    by_x = sorted(ordered_points, key=lambda item: item[2][0])

    canonical_ranks = [item[1] for item in ordered_points]
    physical_ranks = [item[1] for item in by_x]

    if physical_ranks != canonical_ranks:
        # Report every adjacent pair in physical (x) order that is inverted
        # relative to the canonical rank -- i.e. a later-stage component
        # physically precedes an earlier-stage one.
        for i in range(len(by_x) - 1):
            label_a, rank_a, pos_a = by_x[i]
            label_b, rank_b, pos_b = by_x[i + 1]
            if rank_a > rank_b:
                violations.append(
                    EMIFilterViolation(
                        component=f"{label_a},{label_b}",
                        code="FLOW-001",
                        message=(
                            f"{label_b} (x={pos_b[0]:.1f}) should come before "
                            f"{label_a} (x={pos_a[0]:.1f}) in signal-flow order, "
                            "but is placed after it"
                        ),
                        location=pos_b,
                        severity="error",
                    )
                )
    return violations


def _alignment_warnings(
    ordered_points: list[tuple[str, int, tuple[float, float]]],
) -> list[EMIFilterViolation]:
    if len(ordered_points) < 2:
        return []
    ys = sorted(pos[1] for _label, _rank, pos in ordered_points)
    median_y = ys[len(ys) // 2]
    warnings: list[EMIFilterViolation] = []
    for label, _rank, pos in ordered_points:
        if abs(pos[1] - median_y) > _ALIGNMENT_TOLERANCE_MM:
            warnings.append(
                EMIFilterViolation(
                    component=label,
                    code="FLOW-ALIGN",
                    message=(
                        f"{label} is {abs(pos[1] - median_y):.1f}mm off the filter's "
                        f"flow axis (y={pos[1]:.1f} vs median {median_y:.1f})"
                    ),
                    location=pos,
                    severity="warning",
                )
            )
    return warnings


def check_filter_signal_flow(
    component_positions: dict[FilterComponent, tuple[float, float]],
    input_connector_position: tuple[float, float],
) -> EMIFilterResult:
    """
    Check that filter components follow left-to-right signal flow.

    Proper signal flow: AC_IN → FUSE → MOV → L_DM → C_X1 → L_CM → C_X2 →
    Rectifier (MOV shunts L-N *downstream of* the fuse, so a shorted MOV is
    interrupted by it -- see ``_CANONICAL_ORDER`` for why; Y-caps land
    between the choke and the output X-cap, per REQ-EMC-03's canonical
    topology).

    Args:
        component_positions: Dict of {component_type: (x, y)}
        input_connector_position: AC input connector position

    Returns:
        EMIFilterResult with violations for incorrect flow
    """
    ordered_points: list[tuple[str, int, tuple[float, float]]] = [
        ("AC_IN", -1, input_connector_position)
    ]
    for component, pos in component_positions.items():
        rank = _CANONICAL_RANK.get(component)
        if rank is None:
            continue
        ordered_points.append((component.value, rank, pos))
    ordered_points.sort(key=lambda item: item[1])

    violations = _order_violations(ordered_points)
    violations.extend(_alignment_warnings(ordered_points))

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)


def check_filter_component_order(
    component_positions: dict[FilterComponent, tuple[float, float]],
) -> EMIFilterResult:
    """
    Check that filter components are in correct topology order.

    Required order:
    1. FUSE
    2. MOV (downstream of / protected by the fuse -- see ``_CANONICAL_ORDER``)
    3. L_DM (optional)
    4. C_X1 (line-to-neutral)
    5. L_CM (common-mode choke)
    6. C_Y1, C_Y2 (line/neutral to PE)
    7. C_X2 (line-to-neutral)

    Args:
        component_positions: Dict of {component_type: (x, y)}

    Returns:
        EMIFilterResult with violations for incorrect order
    """
    ordered_points: list[tuple[str, int, tuple[float, float]]] = []
    for component, pos in component_positions.items():
        rank = _CANONICAL_RANK.get(component)
        if rank is None:
            continue
        ordered_points.append((component.value, rank, pos))
    ordered_points.sort(key=lambda item: item[1])

    violations = _order_violations(ordered_points)

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)


def check_x_cap_placement(
    x_cap_positions: dict[str, tuple[float, float]],
    line_trace: list[tuple[float, float]],
    neutral_trace: list[tuple[float, float]],
    pe_trace: list[tuple[float, float]],
) -> EMIFilterResult:
    """
    Check X-capacitor placement requirements.

    Requirements:
    - Short, fat traces to L and N
    - No connection to PE (line-to-neutral only)
    - Placed between DM inductor and CM choke

    Args:
        x_cap_positions: Dict of {cap_ref: (x, y)}
        line_trace: Line trace geometry
        neutral_trace: Neutral trace geometry
        pe_trace: PE trace geometry

    Returns:
        EMIFilterResult with violations
    """
    # Same 6mm figure check_line_neutral_pe_spacing uses as its L/N-to-PE
    # safety separation default: a cap whose body comes within that distance
    # of the PE trace is, in practice, a PE connection (a via/pad would land
    # inside the clearance zone), not a clean L-N-only part.
    pe_proximity_mm = 6.0
    lead_length_warn_mm = 10.0  # heuristic "short, fat trace" guideline; UNVERIFIED numeric source

    violations: list[EMIFilterViolation] = []
    for cap_ref, cap_pos in x_cap_positions.items():
        pe_dist = _point_to_polyline_distance(cap_pos, pe_trace)
        if pe_dist < pe_proximity_mm:
            violations.append(
                EMIFilterViolation(
                    component=cap_ref,
                    code="XCAP-001",
                    message=(
                        f"X-cap {cap_ref} is {pe_dist:.1f}mm from the PE trace "
                        f"(limit {pe_proximity_mm}mm) -- X-caps must be line-to-neutral "
                        "only, never PE-connected"
                    ),
                    location=cap_pos,
                    severity="error",
                )
            )

        # Guard on non-empty trace geometry: an empty trace list means "not
        # routed yet / not modeled", not "infinitely far away" -- reporting
        # a lead-length warning from missing data would be a false finding,
        # not a conservative one.
        line_dist = _point_to_polyline_distance(cap_pos, line_trace) if line_trace else None
        neutral_dist = (
            _point_to_polyline_distance(cap_pos, neutral_trace) if neutral_trace else None
        )
        if (line_dist is not None and line_dist > lead_length_warn_mm) or (
            neutral_dist is not None and neutral_dist > lead_length_warn_mm
        ):
            line_str = f"{line_dist:.1f}mm" if line_dist is not None else "unknown"
            neutral_str = f"{neutral_dist:.1f}mm" if neutral_dist is not None else "unknown"
            violations.append(
                EMIFilterViolation(
                    component=cap_ref,
                    code="XCAP-002",
                    message=(
                        f"X-cap {cap_ref} is {line_str} from line / "
                        f"{neutral_str} from neutral -- leads should be short and fat"
                    ),
                    location=cap_pos,
                    severity="warning",
                )
            )

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)


def check_y_cap_placement(
    y_cap_positions: dict[str, tuple[float, float]],
    y_cap_values: dict[str, float],  # Capacitance in nF
    pe_connection: tuple[float, float],
    max_total_capacitance_nf: float = 4.4,
) -> EMIFilterResult:
    """
    Check Y-capacitor placement requirements.

    Requirements:
    - Connect line and neutral to PE
    - Place after CM choke
    - Short, wide traces to PE
    - Total capacitance ≤4.4nF for <3.5mA leakage

    Args:
        y_cap_positions: Dict of {cap_ref: (x, y)}
        y_cap_values: Dict of {cap_ref: capacitance_nf}
        pe_connection: PE connection point position
        max_total_capacitance_nf: Maximum total Y-cap capacitance

    Returns:
        EMIFilterResult with violations
    """
    # The 4.4nF default (this function's own signature default, per
    # REQ-EMC-03's docstring: "<3.5mA leakage") is *accepted as given*, not
    # re-derived here: a check of C = I/(V*2*pi*f) at 3.5mA/250V/50Hz works
    # out to ~44.6nF, an order of magnitude off the stated 4.4nF -- UNVERIFIED
    # whether that gap is a different assumed leakage limit (e.g. 0.35mA),
    # a different reference voltage, or something else. Rather than silently
    # "fixing" the default to match my own back-of-envelope number, this
    # function enforces whatever `max_total_capacitance_nf` the caller
    # supplies (see docs/FUNCTIONAL_TEST_CRITERIA.md Sec 3 for the project's
    # CISPR 14-1 EMC reference; the touch-current figure itself is an IEC
    # 60335-1 Class-I number, not something CISPR 14-1 specifies).
    pe_trace_warn_mm = 15.0  # heuristic "short trace to PE"; UNVERIFIED numeric source

    violations: list[EMIFilterViolation] = []
    total_nf = sum(y_cap_values.get(ref, 0.0) for ref in y_cap_positions)
    if total_nf > max_total_capacitance_nf:
        violations.append(
            EMIFilterViolation(
                component=",".join(y_cap_positions) or "Y-caps",
                code="YCAP-001",
                message=(
                    f"Total Y-cap capacitance {total_nf:.2f}nF exceeds "
                    f"{max_total_capacitance_nf}nF leakage-current limit"
                ),
                severity="error",
            )
        )

    for cap_ref, cap_pos in y_cap_positions.items():
        dist = _distance(cap_pos, pe_connection)
        if dist > pe_trace_warn_mm:
            violations.append(
                EMIFilterViolation(
                    component=cap_ref,
                    code="YCAP-002",
                    message=(
                        f"Y-cap {cap_ref} is {dist:.1f}mm from the PE connection "
                        f"(guideline: <={pe_trace_warn_mm}mm short/wide trace)"
                    ),
                    location=cap_pos,
                    severity="warning",
                )
            )

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)


def check_mov_placement(
    mov_position: tuple[float, float],
    fuse_position: tuple[float, float],
    input_connector: tuple[float, float],
    line_trace: list[tuple[float, float]],
    neutral_trace: list[tuple[float, float]],
) -> EMIFilterResult:
    """
    Check MOV (Metal Oxide Varistor) placement.

    Requirements:
    - At the AC input, but electrically downstream of (protected by) the
      fuse -- **not** before or in parallel with it. Corrected 2026-07-26:
      this function previously required the MOV *before or parallel to* the
      fuse, which is backwards for a safety-certified mains appliance and
      flagged this design's actually-correct wiring
      (`elec/src/modules.ato:658-659`: `fuse.p2 ~ mov.p1`) as a violation.
      An MOV's characteristic end-of-life failure mode is thermal runaway to
      a low-resistance short, not an open circuit. If the MOV sits ahead of
      the fuse, a shorted MOV draws fault current directly from the mains
      with nothing in the appliance to interrupt it -- a fire mechanism.
      Downstream placement means the fuse's own current path includes the
      MOV, so a shorted MOV blows the fuse. See ``_CANONICAL_ORDER``'s
      comment for sourcing (secondary-source corroborated; UL 1449 /
      IEC 61051-1 primary text UNVERIFIED, both paywalled).
    - Short leads to L, N (minimize inductance)
    - Allow clearance for thermal expansion

    Args:
        mov_position: MOV position
        fuse_position: Fuse position
        input_connector: AC input connector position
        line_trace: Line trace geometry
        neutral_trace: Neutral trace geometry

    Returns:
        EMIFilterResult with violations
    """
    lead_length_warn_mm = 15.0  # heuristic "short leads minimize inductance"; UNVERIFIED numeric source
    x_tolerance_mm = 0.01  # float-compare slack for "at or after"

    violations: list[EMIFilterViolation] = []
    if mov_position[0] < input_connector[0] - x_tolerance_mm:
        violations.append(
            EMIFilterViolation(
                component="MOV",
                code="MOV-003",
                message=(
                    f"MOV (x={mov_position[0]:.1f}) is placed before the AC input "
                    f"connector (x={input_connector[0]:.1f})"
                ),
                location=mov_position,
                severity="warning",
            )
        )
    if mov_position[0] < fuse_position[0] - x_tolerance_mm:
        violations.append(
            EMIFilterViolation(
                component="MOV",
                code="MOV-001",
                message=(
                    f"MOV (x={mov_position[0]:.1f}) is placed before the fuse "
                    f"(x={fuse_position[0]:.1f}) -- an end-of-life MOV failure "
                    "shorts the mains with no overcurrent protection unless the "
                    "MOV is downstream of (protected by) the fuse"
                ),
                location=mov_position,
                severity="error",
            )
        )

    # Guard on non-empty trace geometry -- see the identical note in
    # check_x_cap_placement: missing routing data is not "infinitely far".
    line_dist = _point_to_polyline_distance(mov_position, line_trace) if line_trace else None
    neutral_dist = (
        _point_to_polyline_distance(mov_position, neutral_trace) if neutral_trace else None
    )
    if (line_dist is not None and line_dist > lead_length_warn_mm) or (
        neutral_dist is not None and neutral_dist > lead_length_warn_mm
    ):
        line_str = f"{line_dist:.1f}mm" if line_dist is not None else "unknown"
        neutral_str = f"{neutral_dist:.1f}mm" if neutral_dist is not None else "unknown"
        violations.append(
            EMIFilterViolation(
                component="MOV",
                code="MOV-002",
                message=(
                    f"MOV is {line_str} from line / {neutral_str} from "
                    "neutral -- leads should be short to minimize inductance"
                ),
                location=mov_position,
                severity="warning",
            )
        )

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)


def check_cm_choke_placement(
    cm_choke_position: tuple[float, float],
    x_cap_positions: dict[str, tuple[float, float]],
    y_cap_positions: dict[str, tuple[float, float]],
) -> EMIFilterResult:
    """
    Check common-mode choke placement.

    Requirements:
    - Place after X-caps in signal flow
    - Minimize trace length between choke and X-caps
    - Before Y-caps in signal flow

    Args:
        cm_choke_position: Common-mode choke position
        x_cap_positions: X-capacitor positions
        y_cap_positions: Y-capacitor positions

    Returns:
        EMIFilterResult with violations
    """
    x_tolerance_mm = 0.01

    violations: list[EMIFilterViolation] = []
    for cap_ref, cap_pos in x_cap_positions.items():
        if cap_pos[0] > cm_choke_position[0] + x_tolerance_mm:
            violations.append(
                EMIFilterViolation(
                    component=cap_ref,
                    code="CMC-001",
                    message=(
                        f"X-cap {cap_ref} (x={cap_pos[0]:.1f}) is after the CM choke "
                        f"(x={cm_choke_position[0]:.1f}) -- X-caps must precede the choke"
                    ),
                    location=cap_pos,
                    severity="error",
                )
            )

    for cap_ref, cap_pos in y_cap_positions.items():
        if cap_pos[0] < cm_choke_position[0] - x_tolerance_mm:
            violations.append(
                EMIFilterViolation(
                    component=cap_ref,
                    code="CMC-002",
                    message=(
                        f"Y-cap {cap_ref} (x={cap_pos[0]:.1f}) is before the CM choke "
                        f"(x={cm_choke_position[0]:.1f}) -- Y-caps must follow the choke"
                    ),
                    location=cap_pos,
                    severity="error",
                )
            )

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)


def check_pe_trace_requirements(
    pe_trace: list[tuple[float, float]],
    pe_connection: tuple[float, float],
    earth_stud: tuple[float, float],
    min_width_mm: float = 2.0,
) -> EMIFilterResult:
    """
    Check PE (protective earth) trace requirements.

    Requirements:
    - Wide trace (≥2mm)
    - Direct path to earth stud
    - Star ground at PE connection point

    Args:
        pe_trace: PE trace geometry
        pe_connection: PE connection point
        earth_stud: Earth stud/terminal position
        min_width_mm: Minimum PE trace width

    Returns:
        EMIFilterResult with violations
    """
    # `pe_trace` is typed as a bare list[tuple[float, float]] -- no width
    # metadata travels with plain XY points, so `min_width_mm` can only be
    # checked when a caller passes 3-tuples (x, y, width_mm); this is a
    # forward-compatible extension, not a change to the documented 2-tuple
    # contract every test fixture in this suite uses. When no width data is
    # present, the width requirement is left unverified rather than
    # fabricating a verdict from missing data -- see
    # docs/evidence/2026-07-26-emc-validators-implemented.md.
    directness_tolerance = 1.15  # 15% over straight-line distance; UNVERIFIED numeric source

    violations: list[EMIFilterViolation] = []
    widths = [pt[2] for pt in pe_trace if len(pt) > 2]  # type: ignore[misc]
    if widths:
        min_actual = min(widths)
        if min_actual < min_width_mm:
            violations.append(
                EMIFilterViolation(
                    component="PE",
                    code="PE-001",
                    message=(
                        f"PE trace width {min_actual:.2f}mm is below the "
                        f"{min_width_mm}mm minimum"
                    ),
                    severity="error",
                )
            )

    straight = _distance(pe_connection, earth_stud)
    path_length = _polyline_length(pe_trace) if pe_trace else 0.0
    if straight > 1e-9 and path_length > straight * directness_tolerance:
        violations.append(
            EMIFilterViolation(
                component="PE",
                code="PE-002",
                message=(
                    f"PE trace path length {path_length:.1f}mm is not a direct route "
                    f"to the earth stud (straight-line distance {straight:.1f}mm)"
                ),
                severity="error",
            )
        )

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)


def check_line_neutral_pe_spacing(
    line_trace: list[tuple[float, float]],
    neutral_trace: list[tuple[float, float]],
    pe_trace: list[tuple[float, float]],
    min_spacing_mm: float = 6.0,
) -> EMIFilterResult:
    """
    Check spacing between L/N and PE traces.

    Requirement: Maintain >6mm between L/N and PE traces for safety.

    Args:
        line_trace: Line trace geometry
        neutral_trace: Neutral trace geometry
        pe_trace: PE trace geometry
        min_spacing_mm: Minimum spacing requirement

    Returns:
        EMIFilterResult with violations
    """
    violations: list[EMIFilterViolation] = []

    line_dist = _polyline_min_distance(line_trace, pe_trace)
    if line_dist < min_spacing_mm:
        violations.append(
            EMIFilterViolation(
                component="LINE-PE",
                code="LNPE-001",
                message=(
                    f"Line trace is {line_dist:.1f}mm from PE trace "
                    f"(minimum {min_spacing_mm}mm required)"
                ),
                severity="error",
            )
        )

    neutral_dist = _polyline_min_distance(neutral_trace, pe_trace)
    if neutral_dist < min_spacing_mm:
        violations.append(
            EMIFilterViolation(
                component="NEUTRAL-PE",
                code="LNPE-002",
                message=(
                    f"Neutral trace is {neutral_dist:.1f}mm from PE trace "
                    f"(minimum {min_spacing_mm}mm required)"
                ),
                severity="error",
            )
        )

    passed = not any(v.severity == "error" for v in violations)
    return EMIFilterResult(passed=passed, violations=violations)
