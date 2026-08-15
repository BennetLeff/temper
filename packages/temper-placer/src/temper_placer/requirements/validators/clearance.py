"""
Clearance and creepage distance validation functions.

These functions check if PCB layout meets IEC 60335-2-6 safety requirements
for creepage and clearance distances per REQ-SAFE-01.

Wave 4, Phase 5: the validator compute — pairing, pruning, copper
measurement orchestration (through the ``temper-geometry`` kernels),
violation construction, stats and the WARNING records — now lives in the
``temper-drc-rs`` Rust crate (``req_safe_01.rs``). This module is a
delegation shim: the enums, dataclasses and the ``IEC60335_REQUIREMENTS``
matrix data stay Python; the check/report/matrix functions delegate to Rust,
which returns a payload dict plus the ordered WARNING messages the shim
emits. The pre-migration implementation is pinned verbatim as the oracle
(``tests/requirements/clearance_oracle/``).

**What this module measures.** Copper-to-copper distance between the two
components' actual pads, using the exact, rotation-aware, shape-aware pad
model in :mod:`temper_placer.core.pad_geometry` (the model landed by PR #388,
whose isolator figures -- T1 = 9.100mm, K1 = 8.000mm -- this module's
geometry reproduces; see ``tests/requirements/safety/test_clearance_copper.py``).
Only pads whose *own net* is classified into the relevant domain count as
that domain's copper: a DC_BUS component's GND pad is not DC_BUS copper.

**Exactness.** Distances come from ``pad_geometry.pad_pair_distance``, which
exploits the fact that every KiCad pad shape is ``core_rectangle ⊕ disk(r)``
to compute ``max(0, dist(core_a, core_b) - r_a - r_b)`` on exactly
representable rotated rectangles. No arc is polygonised, so there is no
approximation error term -- which matters because sub-millimeter shortfalls
(e.g. K1's HV<->SELV pad pair, exactly 8.000mm against the REINFORCED
creepage requirement corrected to 10.0mm -- see
``docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`` --
a 2.000mm shortfall) must be reported exactly, not smeared by a polygonised
approximation's error term in either direction.

**Layers.** Distances are measured in the board plane (2D). Two pads on
opposite copper layers are separated in 3D by at least the dielectric
thickness as well, so the 2D figure is a lower bound on the true separation
for a cross-layer pair -- again the safe direction. Cross-layer pairs are
not special-cased.

**Components with no pad data.** ``placement`` entries that carry no
``pads`` key are modelled as a zero-extent point at ``position`` -- exactly
the old behaviour. That is optimistic, so it is not silent: every such
component is counted in ``ClearanceResult.stats["components_without_pads"]``
and logged at WARNING once per check.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import temper_drc_rs as _rust

# The copper-geometry half of this check lives in ``_copper`` so this file
# stays under the repo's 1000-line cap. Re-exported here because
# ``CREEPAGE_MODEL_*`` are part of this module's public surface (they appear
# on every creepage violation) and the private names have existing importers.
from ._copper import (  # noqa: F401
    CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND,
    CREEPAGE_MODEL_UNBROKEN_SURFACE,
    _board_cutouts,
    _component_pads,
    _CopperModel,
    _creepage_from_clearance,
)

logger = logging.getLogger(__name__)


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
    """A clearance or creepage distance violation.

    The ``measured_*``/``required_*`` pairs are kept for backwards
    compatibility with existing readers. ``metric``/``measured_mm``/
    ``required_mm``/``shortfall_mm`` are the metric-agnostic view that
    :func:`format_clearance_report` sorts and tabulates on.
    """

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

    # --- Actionable detail (added with the copper-to-copper fix) ---
    ref_a: str | None = None
    ref_b: str | None = None
    metric: str | None = None  # "clearance" | "creepage"
    measured_mm: float | None = None
    required_mm: float | None = None
    #: How the measured distance was obtained: "copper" (real pad geometry on
    #: both sides) or "origin" (one or both components carried no pad data, so
    #: the optimistic origin-to-origin proxy was used).
    geometry_model: str | None = None
    #: For creepage only: which of the CREEPAGE_MODEL_* constants applies.
    creepage_model: str | None = None
    #: "inter" (two distinct components) or "intra" (one component whose own
    #: pads straddle the domain boundary -- unfixable by moving anything).
    pair_kind: str | None = None
    #: Human-readable identification of the two closest pads, e.g.
    #: "C17.2(hb.gate_hs.driver-p2) <-> R32.1(+3V3)".
    closest_pads: str | None = None

    @property
    def shortfall_mm(self) -> float | None:
        """How much distance is missing. ``None`` when not measurable."""
        if self.measured_mm is None or self.required_mm is None:
            return None
        return self.required_mm - self.measured_mm


@dataclass
class ClearanceResult:
    """Result of clearance/creepage validation."""

    passed: bool
    violations: list[ClearanceViolation]
    #: Diagnostic counters. Never used for pass/fail, but a 0-violation result
    #: whose ``pairs_checked`` is 0 is vacuous, not clean -- callers should
    #: inspect this rather than trust a bare ``passed``.
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")

    def report(self) -> str:
        """Worst-first, designer-readable table of every violation."""
        return format_clearance_report(self)


# IEC 60335-2-6 Requirements Matrix
#
# POLLUTION DEGREE PD3 ENFORCED, 2026-08-15. See
# ``docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`` for the full
# derivation; summary:
#
# IEC 60335-1's own clause 29.2 default is Pollution Degree 2 "unless ...
# insulation is subjected to conductive pollution, in which case pollution
# degree 3 applies." IEC 60335-2-6 (the particular standard for cooking
# ranges/hobs -- this appliance's actual category) clause 29.2 Addition
# overrides that default for this whole appliance class: "The
# microenvironment is pollution degree 3 unless the insulation is enclosed
# or located so that it is unlikely to be exposed to pollution during normal
# use of the appliance." PD3 is therefore the governing DEFAULT; PD2 is an
# exception that must be earned by an enclosure/sealing argument.
#
# OWNER DECISION, PD2 ADOPTED FOR PRODUCTION, 2026-07-30 (superseded). The
# project owner selected the PD2 enclosure exception (IEC 60335-2-6 cl.
# 29.2 Addition) as the production architecture on 2026-07-30: see
# ``docs/evidence/2026-07-30-pd2-enclosure-decision.md``. That selection
# was conditional on a real, gasketed PCB compartment, separate from the
# coil/heatsink forced-air path, that keeps grease/steam/aerosols off the
# PCB's own insulation. The compartment was never built, the board is
# forced-air vented with no cover/gasket/partition, and sealing it is
# thermally counterproductive (``docs/evidence/2026-07-30-pcb-compartment-
# thermal-bound.md``). The 2026-08-15 data-driven decision therefore
# supersedes the PD2 adoption and enforces PD3 as the governing bar. **The
# 12.6mm/6.3mm figures below are the enforced values; the 8.0mm/4.0mm PD2
# figures remain the documented fallback should a sealed compartment ever
# actually exist and be verified at production inspection -- they do not
# become true merely because this file says so.** This change moves the
# third of three enforcement points to the PD3 figure (the KiCad DRU
# generator's ``HV_CREEPAGE_ENFORCED_MM`` and
# ``scripts/check_isolation_keepout.py``'s ``MIN_BARRIER_WIDTH_MM`` move in
# the same commit), per the "move every point in the table together" rule.
#
# Creepage figures (``min_creepage_mm``/``design_value_mm``) for every
# HV<->SELV and HV<->ISOLATED row below are read off IEC 60335-1 Table 17
# ("Minimum Creepage Distances for Basic Insulation", clauses 29.2.1-29.2.3
# -- CITED-PRIMARY, IS 302-1:2008 Sec 29, identical adoption, independently
# re-read this session) at the **400V row (row iv, >250V and <=400V),
# Material Group IIIa/IIIb column**. PD3 (enforced): **6.3mm basic /
# 12.6mm reinforced** (clause 29.2.3: reinforced is at least double basic).
# PD2 fallback: **4.0mm basic / 8.0mm reinforced** -- both pollution-degree
# columns are read off the SAME row iv, so there is no voltage-row ambiguity
# between them. See ``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 5.1
# (Table 17, both columns shown side by side).
#
# ``min_clearance_mm`` is intentionally NOT changed by either the
# pollution-degree correction or the PD3 enforcement above, and is flagged
# **UNSOURCED** as of 2026-08-15: the 3.0mm basic / 6.0mm reinforced
# figures below are NOT IEC 60335-1 Table 16 values (Table 16 is keyed to
# rated impulse voltage -- rows 330/500/800/1500/2500/4000/6000/8000/10000 V
# -- and its entire value set is {0.5, 1.5, 3.0, 5.5, 8.0, 11.0}; the legacy
# "IEC 60335-1 Table 16 working isolation at 400V" citation attached to the
# 6.0 figure is debunked twice over: 400V is not a Table 16 row and 6.0mm is
# not a Table 16 value -- docs/evidence/2026-07-28-creepage-determination-
# brainstorm.md). The figures are non-binding on a flat board -- IEC 60664-1
# requires creepage >= clearance, so the 6.3/12.6mm creepage floor (the
# PD3-enforced figures, per the 2026-08-15 data-driven decision) dominates
# every clearance figure below it (cl. 29.2.3's double applies to creepage;
# the "governing number for a flat, ungrooved PCB gap is
# max(clearance, creepage) = creepage" result is derived in the same
# brainstorm doc) -- but they remain unsourced and must be re-derived
# before being relied on. The repo's cited derivation for the reinforced
# figure exists (`scripts/generate_kicad_dru.py`'s HV_INTERNAL_CLEARANCE_MM:
# Table 16 0.5mm at 1500V rated impulse -> cl. 29.1.3 next higher step
# 1.5mm + cl. 29.1 soldered-construction adder 0.5mm = 2.0mm); substituting
# it is a separate, attributed decision, not made here.
#
# The LV_CONTROL<->LV_CONTROL FUNCTIONAL row's min_creepage_mm is
# **CORRECTED 2026-08-15** from the legacy 1.0mm pin to **1.8mm**: IEC
# 60335-1 Table 18 row i (<=50V), Material Group IIIa/IIIb reads 1.1mm
# PD2 / 1.8mm PD3 (CITED-PRIMARY, docs/evidence/2026-08-12-hv-hv-creepage-
# determination.md), and the 1.0mm pin was a known-low value the code itself
# conceded sat under even the PD2 figure. PD3 governs the as-built board
# (forced-air vented, no cover/gasket/partition -- handoff 2026-08-15 §7.C;
# docs/specs/pd2_compartment_evidence.yaml does not exist), so the PD3 cell
# 1.8mm is the enforced value. Clause 29.2.4's short-circuit-test exemption
# is NOT claimed here; if it applies, that is a separate documented
# determination. Raising this row makes placement constraints stricter --
# pairs at 1.0-1.8mm creepage that previously passed now correctly fail.
#
# The matrix data lives here (Python) and is mirrored in
# ``temper-drc-rs/src/req_safe_01.rs``'s ``MATRIX_ROWS`` (pinned together by
# ``test_requirement_matrix_values_pinned``); the tuple-keyed rows below are
# consumed directly by the CP-SAT encoder.
IEC60335_REQUIREMENTS = {
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 6.3,
        "design_value_mm": 8.3,
    },
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 12.6,
        "design_value_mm": 14.6,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 6.3,
        "design_value_mm": 8.3,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 12.6,
        "design_value_mm": 14.6,
    },
    (VoltageDomain.MAINS, VoltageDomain.ISOLATED, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 12.6,
        "design_value_mm": 14.6,
    },
    (VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, InsulationType.FUNCTIONAL): {
        "min_clearance_mm": 0.5,
        "min_creepage_mm": 1.8,
        "design_value_mm": 2.0,
    },
}


def _domain_str(domain: VoltageDomain | str) -> str:
    """The domain as a string: ``.value`` for the Enum, as-is otherwise."""
    return domain.value if isinstance(domain, VoltageDomain) else domain


def _nets_domain_map(
    placement: dict[str, Any],
    overrides: dict[str, VoltageDomain] | None = None,
) -> dict[str, VoltageDomain]:
    """Build {net_name: VoltageDomain} from ``placement["nets"]``, with
    *overrides* (e.g. the ``voltage_domains`` argument of
    :func:`verify_iec60335_compliance`) taking precedence per net name.

    Wave 4, Phase 5: computed in Rust; the original domain objects are
    returned (str-mixin Enums compare equal to their strings, so both the
    CP-SAT encoder's ``==``/``in`` checks and the checks work).
    """
    return _rust.req_safe_01_nets_domain_map(placement, overrides)


def _components_in_domain(
    placement: dict[str, Any],
    domain: VoltageDomain,
    nets_domain: dict[str, VoltageDomain],
) -> list[dict[str, Any]]:
    """Every component with at least one net assigned to *domain*."""
    return list(_rust.req_safe_01_components_in_domain(
        placement, _domain_str(domain), nets_domain
    ))


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
    return list(_rust.req_safe_01_domain_boundary_pairs(
        placement, _domain_str(domain_a), _domain_str(domain_b), nets_domain
    ))


def _result_from_payload(payload: dict[str, Any]) -> ClearanceResult:
    """Materialize a ClearanceResult from the Rust payload dict, emitting
    the WARNING records in order (the logs are computed in Rust; the
    logging framework stays Python)."""
    for msg in payload["warnings"]:
        logger.warning(msg)
    violations = [_violation_from_dict(v) for v in payload["violations"]]
    return ClearanceResult(
        passed=payload["passed"], violations=violations, stats=payload["stats"]
    )


def _violation_from_dict(v: dict[str, Any]) -> ClearanceViolation:
    """Rebuild a ClearanceViolation from the Rust payload; the
    ``insulation_type`` string becomes the Enum member (matching the oracle,
    which assigns the member)."""
    if v.get("insulation_type") is not None:
        v = {**v, "insulation_type": InsulationType(v["insulation_type"])}
    return ClearanceViolation(**v)


# =============================================================================
# Reporting
# =============================================================================


def format_clearance_report(result: ClearanceResult, limit: int | None = None) -> str:
    """Render *result* as a worst-first table a designer can act on.

    One row per violation: pair, boundary, insulation, metric, measured,
    required, shortfall, and how it was measured. Sorted by shortfall
    descending, so the part that needs to move furthest is the first thing
    read. Replaces dumping repr'd dataclasses, which at ~30 violations is
    unreadable and therefore ignored.
    """
    return _rust.req_safe_01_format_clearance_report(result, limit)


def check_domain_clearance(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
) -> ClearanceResult:
    """
    Check minimum clearance distance between two voltage domains.

    Clearance is the shortest distance **through air** between two conductive
    parts -- a straight line between the nearest copper on each side. That is
    exactly what this function measures: the minimum distance between the two
    components' pad polygons, built from each pad's real width/height/shape/
    rotation via :mod:`temper_placer.core.pad_geometry`. It is **not** the
    distance between component origins, which is what this function returned
    before 2026-07-28 and which is optimistic by up to 8.4mm on this board
    (see module docstring).

    Domain membership of a component is derived from ``placement["nets"]``:
    a component is "in" *domain* if any of its nets maps to that domain
    (``placement["nets"][net]["domain"] == domain``). Within a component,
    only pads whose own net maps to *domain* count as that domain's copper.
    Every component in domain_a is checked against every component in
    domain_b (or, when domain_a == domain_b, every unique pair within that
    domain), plus -- for cross-domain boundaries -- every single component
    whose own pads straddle the boundary.

    Args:
        placement: PCB placement data with component positions, nets, and
            (strongly recommended -- see module docstring) per-component
            ``pads``. Optionally ``placement["board"]["surface_cutouts"]``.
        domain_a: First voltage domain
        domain_b: Second voltage domain
        min_mm: Minimum clearance distance in millimeters

    Returns:
        ClearanceResult with violations for insufficient clearance
    """
    payload = _rust.req_safe_01_check_domain_clearance(
        placement, _domain_str(domain_a), _domain_str(domain_b), min_mm
    )
    return _result_from_payload(payload)


def check_creepage_path(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
) -> ClearanceResult:
    """
    Check minimum creepage distance along PCB surface between two voltage domains.

    Creepage is the shortest path **along the insulating surface** between two
    conductive parts. It differs from clearance in that the path must go
    *around* slots, cutouts and board edges rather than across them, so
    creepage >= clearance always, with equality exactly when the surface
    between the two parts is unbroken.

    **What this function actually computes, stated plainly.** The nearest
    copper-to-copper straight line (the same geometry
    :func:`check_domain_clearance` measures), then
    :func:`_creepage_from_clearance`:

    - **No cutouts declared** (``placement["board"]["surface_cutouts"]``
      empty or absent) -- the surface is unbroken, the surface geodesic
      between two coplanar points *is* the straight line, and the reported
      figure is **exact**. Tagged ``CREEPAGE_MODEL_UNBROKEN_SURFACE`` on
      every violation. This is the case on ``pcb/temper.kicad_pcb`` today:
      it has exactly one rectangular ``Edge.Cuts`` outline and no isolation
      slot, which is why clearance and creepage currently coincide
      numerically. That is a property of *this board*, not of the metrics.
    - **Cutouts declared** -- the true path detours and is strictly longer.
      **Slot-aware surface pathing is not implemented.** The straight-line
      figure is returned as an explicit conservative *lower bound* (it can
      over-report violations near a slot, but can never mask one), tagged
      ``CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND`` on every violation and
      logged at WARNING on every call. It is deliberately never *silently*
      identical to clearance.

    Implementing the real surface path (visibility-graph geodesic over the
    board polygon with its holes) is the outstanding work; the repo already
    carries the board-outline machinery it would consume
    (``io/isolation_slot_geometry.py``, and the Rust DRC rule
    ``packages/temper-drc-rs/src/rules/routing/isolation_slot.rs``).

    Args:
        placement: PCB placement data with component positions, nets, pads,
            and optionally ``placement["board"]["surface_cutouts"]``
        domain_a: First voltage domain
        domain_b: Second voltage domain
        min_mm: Minimum creepage distance in millimeters

    Returns:
        ClearanceResult with violations for insufficient creepage
    """
    payload = _rust.req_safe_01_check_creepage_path(
        placement, _domain_str(domain_a), _domain_str(domain_b), min_mm
    )
    return _result_from_payload(payload)


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
    payload = _rust.req_safe_01_verify_iec60335(placement, voltage_domains)
    return _result_from_payload(payload)


def get_requirement_matrix() -> dict[tuple[str, str, str], dict[str, float]]:
    """
    Get the IEC 60335-2-6 requirements matrix.

    Returns:
        Dictionary with (domain_a, domain_b, insulation_type) -> requirements
    """
    return _rust.req_safe_01_requirement_matrix()
