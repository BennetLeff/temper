"""
Clearance and creepage distance validation functions.

These functions check if PCB layout meets IEC 60335-2-6 safety requirements
for creepage and clearance distances per REQ-SAFE-01.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ._geometry import _distance


class InsulationType(str, Enum):
    """Insulation type per IEC 60335-2-6.

    Mixes in ``str`` so ``InsulationType.BASIC == "basic"`` holds (required
    by TestClearanceIntegration.test_insulation_type_enum_values) --
    previously masked because that test was skipped along with the rest of
    this module while these functions raised NotImplementedError.
    """

    BASIC = "basic"
    REINFORCED = "reinforced"
    FUNCTIONAL = "functional"


class VoltageDomain(str, Enum):
    """Voltage domains in Temper PCB.

    Mixes in ``str`` so ``VoltageDomain.MAINS == "MAINS"`` holds (required
    by TestClearanceIntegration.test_voltage_domain_enum_values) -- see
    InsulationType docstring for why this was previously unnoticed.
    """

    MAINS = "MAINS"  # 240VAC (340V peak)
    DC_BUS = "DC_BUS"  # 340VDC (from doubler)
    BOOTSTRAP = "BOOTSTRAP"  # 340VDC (floating)
    LV_CONTROL = "LV_CONTROL"  # 3.3V/5V/12V
    ISOLATED = "ISOLATED"  # Floating


@dataclass
class ClearanceViolation:
    """A clearance or creepage distance violation."""

    code: str
    message: str
    location: tuple[float, float] | None = None
    severity: str = "error"  # error, warning
    boundary: str | None = None
    insulation_type: InsulationType | None = None
    measured_clearance_mm: float | None = None
    measured_creepage_mm: float | None = None
    required_clearance_mm: float | None = None
    required_creepage_mm: float | None = None


@dataclass
class ClearanceResult:
    """Result of clearance/creepage validation."""

    passed: bool
    violations: list[ClearanceViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


# IEC 60335-2-6 Requirements Matrix
IEC60335_REQUIREMENTS = {
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 4.0,
        "design_value_mm": 6.0,
    },
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 8.0,
        "design_value_mm": 10.0,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 4.0,
        "design_value_mm": 6.0,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 8.0,
        "design_value_mm": 10.0,
    },
    (VoltageDomain.MAINS, VoltageDomain.ISOLATED, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 8.0,
        "design_value_mm": 10.0,
    },
    (VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, InsulationType.FUNCTIONAL): {
        "min_clearance_mm": 0.5,
        "min_creepage_mm": 1.0,
        "design_value_mm": 2.0,
    },
}


def _nets_domain_map(
    placement: dict[str, Any],
    overrides: dict[str, VoltageDomain] | None = None,
) -> dict[str, VoltageDomain]:
    """Build {net_name: VoltageDomain} from ``placement["nets"]``, with
    *overrides* (e.g. the ``voltage_domains`` argument of
    :func:`verify_iec60335_compliance`) taking precedence per net name.
    """
    domain_map: dict[str, VoltageDomain] = {}
    for net_name, net_info in placement.get("nets", {}).items():
        domain = net_info.get("domain") if isinstance(net_info, dict) else None
        if domain is not None:
            domain_map[net_name] = domain
    if overrides:
        domain_map.update(overrides)
    return domain_map


def _components_in_domain(
    placement: dict[str, Any],
    domain: VoltageDomain,
    nets_domain: dict[str, VoltageDomain],
) -> list[dict[str, Any]]:
    """Every component with at least one net assigned to *domain*."""
    return [
        comp
        for comp in placement.get("components", [])
        if any(nets_domain.get(net) == domain for net in comp.get("nets", []))
    ]


def _domain_boundary_pairs(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    nets_domain: dict[str, VoltageDomain],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """All distinct component pairs straddling the *domain_a*/*domain_b*
    boundary. Every component in domain_a is checked against every
    component in domain_b (clearance/creepage is a property of any two
    conductive parts at different potentials, not just electrically
    connected ones). When domain_a == domain_b, every unique unordered pair
    within that single domain is checked instead (the FUNCTIONAL
    within-LV_CONTROL matrix entry).
    """
    group_a = _components_in_domain(placement, domain_a, nets_domain)
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []

    if domain_a == domain_b:
        for i in range(len(group_a)):
            for j in range(i + 1, len(group_a)):
                pairs.append((group_a[i], group_a[j]))
        return pairs

    group_b = _components_in_domain(placement, domain_b, nets_domain)
    for comp_a in group_a:
        for comp_b in group_b:
            if comp_a.get("ref") == comp_b.get("ref"):
                continue
            pairs.append((comp_a, comp_b))
    return pairs


def _check_distance(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
    *,
    metric: str,
    nets_domain: dict[str, VoltageDomain] | None = None,
) -> ClearanceResult:
    """Shared core for :func:`check_domain_clearance` and
    :func:`check_creepage_path`. *metric* is ``"clearance"`` or
    ``"creepage"`` and only affects violation wording/fields — both use the
    straight-line (Euclidean) distance between component positions as the
    measured value.

    This is a deliberate simplification: ``placement`` carries component
    positions only, not a board outline, isolation-slot geometry, or routed
    copper. Straight-line distance is an exact measure of *clearance*
    (through air). It is a conservative *lower bound* on true *creepage*
    (the along-surface path length is always >= the straight-line distance
    by the triangle inequality), so this check can produce false-positive
    creepage violations near a slot/cutout that lengthens the real surface
    path, but it can never mask a genuine creepage violation. See
    check_creepage_path's docstring.
    """
    if nets_domain is None:
        nets_domain = _nets_domain_map(placement)

    violations: list[ClearanceViolation] = []
    for comp_a, comp_b in _domain_boundary_pairs(placement, domain_a, domain_b, nets_domain):
        pos_a = comp_a["position"]
        pos_b = comp_b["position"]
        dist = _distance(pos_a, pos_b)
        if dist < min_mm:
            midpoint = ((pos_a[0] + pos_b[0]) / 2.0, (pos_a[1] + pos_b[1]) / 2.0)
            kwargs: dict[str, Any] = {
                "code": f"{metric.upper()}_INSUFFICIENT",
                "message": (
                    f"{metric.capitalize()} between {comp_a.get('ref')} ({domain_a.value}) "
                    f"and {comp_b.get('ref')} ({domain_b.value}) is {dist:.3f}mm, "
                    f"below required minimum {min_mm}mm"
                ),
                "location": midpoint,
                "severity": "error",
                "boundary": f"{domain_a.value}<->{domain_b.value}",
            }
            if metric == "clearance":
                kwargs["measured_clearance_mm"] = dist
                kwargs["required_clearance_mm"] = min_mm
            else:
                kwargs["measured_creepage_mm"] = dist
                kwargs["required_creepage_mm"] = min_mm
            violations.append(ClearanceViolation(**kwargs))

    return ClearanceResult(passed=len(violations) == 0, violations=violations)


def check_domain_clearance(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
) -> ClearanceResult:
    """
    Check minimum clearance distance between two voltage domains.

    Clearance is the shortest distance through air between two conductive parts.
    Domain membership of a component is derived from ``placement["nets"]``:
    a component is "in" *domain* if any of its nets maps to that domain
    (``placement["nets"][net]["domain"] == domain``). Every component in
    domain_a is checked against every component in domain_b (or, when
    domain_a == domain_b, every unique pair within that domain) using the
    straight-line distance between their ``position`` fields.

    Args:
        placement: PCB placement data with component positions and nets
        domain_a: First voltage domain
        domain_b: Second voltage domain
        min_mm: Minimum clearance distance in millimeters

    Returns:
        ClearanceResult with violations for insufficient clearance
    """
    return _check_distance(placement, domain_a, domain_b, min_mm, metric="clearance")


def check_creepage_path(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
) -> ClearanceResult:
    """
    Check minimum creepage distance along PCB surface between two voltage domains.

    Creepage is the shortest distance along the surface of insulation between
    two conductive parts. ``placement`` in this validator suite carries only
    component positions -- no board outline, isolation-slot polygon, or
    copper-pour geometry is available -- so the true along-surface path
    cannot be traced around slots/cutouts. This function instead uses the
    straight-line distance as a conservative *lower bound* on creepage: by
    the triangle inequality, the real surface path is always >= the
    straight-line distance, so this check never under-reports (masks) a
    real creepage violation, but it can over-report near a slot that
    lengthens the true path. Any board-level creepage measurement that
    needs to account for an actual routed isolation slot must be done with
    real board geometry (see the Rust DRC isolation-slot rule,
    packages/temper-drc-rs/src/rules/routing/isolation_slot.rs, which
    operates on real polygons rather than this dict-based placement
    fixture).

    Args:
        placement: PCB placement data with component positions and nets
        domain_a: First voltage domain
        domain_b: Second voltage domain
        min_mm: Minimum creepage distance in millimeters

    Returns:
        ClearanceResult with violations for insufficient creepage
    """
    return _check_distance(placement, domain_a, domain_b, min_mm, metric="creepage")


def verify_iec60335_compliance(
    placement: dict[str, Any],
    voltage_domains: dict[str, VoltageDomain],
) -> ClearanceResult:
    """
    Verify complete IEC 60335-2-6 compliance for all voltage domain boundaries.

    For every (domain_a, domain_b, insulation_type) entry in
    IEC60335_REQUIREMENTS, runs both check_domain_clearance and
    check_creepage_path (using that entry's min_clearance_mm/
    min_creepage_mm) against the domain boundary, using ``voltage_domains``
    (net name -> VoltageDomain) merged over -- and taking precedence over --
    any domain already recorded in ``placement["nets"]``. Every entry
    applicable to the domains actually present in ``placement`` is checked;
    boundaries with no components in one or both domains simply contribute
    no violations. Each resulting violation is annotated with its
    ``boundary`` and ``insulation_type`` so callers can tell which matrix
    row it came from.

    Args:
        placement: PCB placement data with component positions and nets
        voltage_domains: Mapping of net names to voltage domains

    Returns:
        ClearanceResult with all IEC 60335-2-6 violations
    """
    nets_domain = _nets_domain_map(placement, voltage_domains)

    all_violations: list[ClearanceViolation] = []
    for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items():
        clearance_result = _check_distance(
            placement,
            domain_a,
            domain_b,
            requirements["min_clearance_mm"],
            metric="clearance",
            nets_domain=nets_domain,
        )
        creepage_result = _check_distance(
            placement,
            domain_a,
            domain_b,
            requirements["min_creepage_mm"],
            metric="creepage",
            nets_domain=nets_domain,
        )
        for violation in (*clearance_result.violations, *creepage_result.violations):
            violation.insulation_type = insulation_type
            all_violations.append(violation)

    return ClearanceResult(passed=len(all_violations) == 0, violations=all_violations)


def get_requirement_matrix() -> dict[tuple[str, str, str], dict[str, float]]:
    """
    Get the IEC 60335-2-6 requirements matrix.

    Returns:
        Dictionary with (domain_a, domain_b, insulation_type) -> requirements
    """
    return {
        (domain_a.value, domain_b.value, insulation_type.value): requirements
        for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items()
    }
