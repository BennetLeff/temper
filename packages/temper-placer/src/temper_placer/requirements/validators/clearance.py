"""
Clearance and creepage distance validation functions.

These functions check if PCB layout meets IEC 60335-2-6 safety requirements
for creepage and clearance distances per REQ-SAFE-01.

**What this module used to measure, and why that was unsafe.**
``_check_distance`` -- the single shared core behind
:func:`check_domain_clearance`, :func:`check_creepage_path` and
:func:`verify_iec60335_compliance` -- used to compute
``math.dist(comp_a["position"], comp_b["position"])``: the straight line
between two components' *origins*. ``position`` is
``Component.initial_position``, the centre of the footprint's pad bounding
box. No pad width, height, shape or rotation entered anywhere.

Copper extends **outward** from that origin, so origin-to-origin distance is
an **upper bound** on true copper-to-copper separation. Every clearance and
creepage figure this checker ever reported was therefore optimistic -- in the
unsafe direction. It could not over-report a violation; it could and did hide
them. Measured on ``pcb/temper.kicad_pcb``: mean optimism ~3.6mm over the
pairs it did flag, worst case ``C22``<->``L2`` reported at 10.341mm against a
true copper separation of 1.969mm -- 8.4mm of margin that does not exist. See
``docs/evidence/2026-07-28-req-safe-01-rederivation.md`` (the measurement) and
``docs/evidence/2026-07-28-clearance-copper-to-copper.md`` (this fix).

**What it measures now.** Copper-to-copper distance between the two
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
# POLLUTION DEGREE CORRECTED PD2 -> PD3, 2026-07-30 (this change). See
# ``docs/evidence/2026-07-30-pollution-degree-determination.md`` for the full
# derivation; summary:
#
# IEC 60335-1's own clause 29.2 default is Pollution Degree 2 "unless ...
# insulation is subjected to conductive pollution, in which case pollution
# degree 3 applies." IEC 60335-2-6 (the particular standard for cooking
# ranges/hobs -- this appliance's actual category) clause 29.2 Addition
# overrides that default for this whole appliance class: "The
# microenvironment is pollution degree 3 unless the insulation is enclosed
# or located so that it is unlikely to be exposed to pollution during normal
# use of the appliance." PD3 is therefore the governing default; PD2 is an
# exception that must be earned by an enclosure/sealing argument.
#
# That argument does not exist in this project's own mechanical documents,
# checked directly (not inherited): ``docs/CHASSIS_AIRFLOW_DESIGN.md``
# ducts forced, unfiltered kitchen air (bottom vents -> intake plenum ->
# fan -> transition duct -> IGBT heatsink -> exhaust) through the same
# chassis cavity the PCB sits in; ``docs/COIL_BRACKET_DESIGN.md`` describes
# "large triangular cutouts ... allow air from the bottom intake to flow
# directly through the Litz wire strands" (a baffle, not a seal);
# ``docs/ASSEMBLY_GUIDE.md`` mounts the PCB on M3 standoffs directly in that
# same vented cavity, with its only gasket sealing the glass-ceramic
# cooktop to the chassis, not the PCB compartment; and the board's own IP20
# rating states "No liquid ingress protection guaranteed." No enclosure/
# sealing argument for the PCB compartment exists today, so the PD2
# exception is not earned and PD3 governs.
#
# Creepage figures (``min_creepage_mm``/``design_value_mm``) for every
# HV<->SELV and HV<->ISOLATED row below are read off IEC 60335-1 Table 17
# ("Minimum Creepage Distances for Basic Insulation", clauses 29.2.1-29.2.3
# -- CITED-PRIMARY, IS 302-1:2008 Sec 29, identical adoption, independently
# re-read this session) at the **400V row (row iv, >250V and <=400V),
# Pollution Degree 3, Material Group IIIa/IIIb column: 6.3mm basic**.
# Clause 29.2.3: reinforced creepage is at least double basic -- **12.6mm**.
# This replaces the 10.0mm reinforced figure this table previously used at
# PD2. FLAGGED, NOT RE-DERIVED HERE: row iv's own PD2 column is actually
# 4.0mm basic / 8.0mm reinforced, not 10.0mm -- the previously-committed
# 10.0mm figure appears to match the *next* row (">400, <=500V": 5.0mm
# basic / 10.0mm reinforced) rather than row iv, which is where 400V
# literally falls ("<=400"). That voltage-row question was already
# adjudicated by a separate, already-merged change
# (``docs/evidence/2026-07-30-creepage-requirement-reconciliation.md``,
# PR #442) and re-litigating it is out of scope for this pollution-degree
# pass -- so 12.6mm is derived directly from row iv (matching every prior
# PD3 investigation in this repo's history, all of which used row iv), not
# by scaling the possibly-off-by-one-row 10.0mm figure. See
# ``docs/evidence/2026-07-30-pollution-degree-determination.md`` for the
# full disclosure and the primary-text image confirming both rows' values.
# See ``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 5.1 (also corrected
# this change; previously mislabeled this table "Table 16", which is
# IEC 60335-1's *clearance* table -- Table 17 is creepage).
#
# Every domain this table's HV side can classify -- MAINS (peak/transient
# 340V, spec Sec 2.1), DC_BUS (peak/transient 400V, spec Sec 2.1 -- and, per
# ``tests/requirements/safety/_real_board_fixture.py``, the bucket every
# declared-HV net that isn't literally ``ac_l``/``ac_n`` falls into, so it
# also covers HV nets that sit at raw mains potential, e.g. the CMC winding
# taps), and Gate Drive Isolated (peak-to-earth 355V, spec Sec 2.1) -- has a
# working voltage over 300V, so (as before) all round up to the same 400V
# row rather than the 300V row (IEC 60664-1/60335-1 tables are not
# interpolated). See
# ``docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`` for
# that voltage-row derivation (unaffected by the pollution-degree change)
# and ``docs/evidence/2026-07-30-pollution-degree-determination.md`` for the
# pollution-degree derivation layered on top of it here.
#
# ``design_value_mm`` is not read by ``verify_iec60335_compliance`` (only
# ``min_clearance_mm``/``min_creepage_mm`` gate anything); it is a
# documentary "add 2.0mm over the creepage minimum" design target, tested
# directly by ``test_requirement_matrix_values``.
#
# ``min_clearance_mm`` is intentionally NOT changed by this correction:
# IEC 60335-1 Table 16 (clearance) is keyed to rated impulse voltage (via
# Table 15's overvoltage-category lookup), not to pollution degree or
# material group -- the sole pollution-degree-dependent entry in Table 16 is
# a footnote bumping the lowest (1500V impulse) row from ~0.5mm to 0.8mm at
# PD3, a row and voltage class this project's >=2500V-impulse boundaries
# don't use. Every clearance figure below (6.0mm reinforced, 3.0mm basic)
# already meets or exceeds Table 16's 400V-row minimum regardless of
# pollution degree -- clearance was already conservative, only creepage
# moves with pollution degree. See the evidence doc for the full
# reconciliation of Sec 4.2's inconsistent "Design Value" column, which is
# not used as a basis for anything in this table.
#
# The LV_CONTROL<->LV_CONTROL FUNCTIONAL row is intentionally NOT corrected
# here even though the same PD3 microenvironment finding applies to it in
# principle (IEC 60335-1 Table 18 row i, <=50V, PD3, Material Group
# IIIa/IIIb reads 1.8mm, vs this row's current 1.0mm, which is already
# slightly under Table 18's own PD2 figure at 1.1mm). This pre-dates the
# pollution-degree correction, is a same-domain (SELV-to-SELV) functional
# boundary rather than a mains/DC_BUS-to-SELV safety barrier, and needs its
# own check of whether clause 29.2.4's short-circuit-test exemption already
# applies before changing -- flagged for a follow-up, not corrected in this
# pass; see the evidence doc Sec "What this determination does not do."
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



# =============================================================================
# The check
# =============================================================================


def _intra_component_boundary_components(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    nets_domain: dict[str, VoltageDomain],
    model: _CopperModel,
) -> list[dict[str, Any]]:
    """Single components whose OWN pads straddle the *domain_a*/*domain_b*
    boundary.

    ``_domain_boundary_pairs`` deliberately pairs only *distinct*
    components -- that contract is also relied on by
    ``placer.cp_sat.domain_clearance.generate_domain_clearance_constraints``,
    which would emit a nonsensical ``SeparatedConstraint(a=X, b=X)`` if it
    started seeing self-pairs. So intra-footprint crossings are enumerated
    here instead, and only for the distance check.

    Why they must be checked at all: a part whose own pads sit at different
    potentials across the barrier violates the barrier at *every* placement.
    On ``pcb/temper.kicad_pcb`` five such parts exist (C6, K2, K3, U3, U7)
    and were invisible to this checker at any position. They are real
    blockers, and they are not fixable by moving anything -- the remedy is a
    different footprint, a different part, or a milled isolation slot.

    Restricted to ``domain_a != domain_b`` on purpose. The one same-domain
    matrix row is LV_CONTROL<->LV_CONTROL FUNCTIONAL (0.5mm/1.0mm), and
    applying it inside a single footprint would flag the fixed, qualified pad
    pitch of essentially every multi-pad SELV part. Measured on this board
    rather than assumed: it adds **41 further violation records across 33
    parts**, whose closest pairs are a 0.35mm QFN/SOT pitch and a 0.65mm
    0402 pad gap -- i.e. the manufacturer's own footprint, identical on every
    unit ever shipped, not a layout decision. None of them is a barrier
    crossing and none is actionable (you cannot re-pitch a 0402). Functional
    insulation between two SELV nets of one part is governed by that part's
    own datasheet ratings, not by PCB layout; the cross-domain case is
    different precisely because it is a mains-to-SELV barrier crossing that a
    designer must resolve with a different part, a different footprint, or a
    milled slot.
    """
    if domain_a == domain_b:
        return []
    out: list[dict[str, Any]] = []
    for comp in placement.get("components", []):
        ref = str(comp.get("ref", "?"))
        if not model.has_pads(ref):
            continue
        if model.domain_restricted(ref, domain_a, nets_domain) and model.domain_restricted(
            ref, domain_b, nets_domain
        ):
            out.append(comp)
    return out


def _check_distance(
    placement: dict[str, Any],
    domain_a: VoltageDomain,
    domain_b: VoltageDomain,
    min_mm: float,
    *,
    metric: str,
    nets_domain: dict[str, VoltageDomain] | None = None,
    model: _CopperModel | None = None,
) -> ClearanceResult:
    """Shared core for :func:`check_domain_clearance` and
    :func:`check_creepage_path`.

    Measures **copper-to-copper** distance between the two components' pads
    (see module docstring), not origin-to-origin. *metric* selects which
    physical quantity is being asked for:

    - ``"clearance"``: shortest distance through air = the straight line
      between nearest copper. That is exactly what the pad-polygon distance
      computes, so clearance is reported directly.
    - ``"creepage"``: shortest path along the insulating surface, which must
      go *around* slots/cutouts. Routed through
      :func:`_creepage_from_clearance`, which is exact on an unbroken board
      and an explicitly-tagged conservative lower bound otherwise.

    Both metrics also cover intra-footprint crossings (see
    :func:`_intra_component_boundary_components`).
    """
    if nets_domain is None:
        nets_domain = _nets_domain_map(placement)
    if model is None:
        model = _CopperModel(placement)

    cutouts = _board_cutouts(placement)
    boundary = f"{domain_a.value}<->{domain_b.value}"

    inter = _domain_boundary_pairs(placement, domain_a, domain_b, nets_domain)
    intra = _intra_component_boundary_components(placement, domain_a, domain_b, nets_domain, model)
    candidates: list[tuple[dict[str, Any], dict[str, Any], str]] = [
        (a, b, "inter") for a, b in inter
    ]
    candidates.extend((c, c, "intra") for c in intra)

    violations: list[ClearanceViolation] = []
    pruned = 0
    origin_modelled = 0
    unrestricted = 0

    for comp_a, comp_b, pair_kind in candidates:
        ref_a = str(comp_a.get("ref", "?"))
        ref_b = str(comp_b.get("ref", "?"))

        if pair_kind == "inter" and model.lower_bound(ref_a, ref_b) >= min_mm:
            pruned += 1
            continue

        dist, geometry_model, closest = model.copper_distance(
            ref_a, domain_a, ref_b, domain_b, nets_domain
        )
        if geometry_model == "origin":
            origin_modelled += 1
        else:
            if not model.domain_restricted(ref_a, domain_a, nets_domain) or (
                not model.domain_restricted(ref_b, domain_b, nets_domain)
            ):
                unrestricted += 1

        creepage_model: str | None = None
        if metric == "creepage":
            dist, creepage_model = _creepage_from_clearance(dist, cutouts)

        if dist >= min_mm:
            continue

        pos_a = comp_a["position"]
        pos_b = comp_b["position"]
        midpoint = ((pos_a[0] + pos_b[0]) / 2.0, (pos_a[1] + pos_b[1]) / 2.0)
        where = (
            f"within {ref_a} ({domain_a.value} pad <-> {domain_b.value} pad)"
            if pair_kind == "intra"
            else f"between {ref_a} ({domain_a.value}) and {ref_b} ({domain_b.value})"
        )
        kwargs: dict[str, Any] = {
            "code": f"{metric.upper()}_INSUFFICIENT",
            "message": (
                f"{metric.capitalize()} {where} is {dist:.3f}mm "
                f"(copper-to-copper, closest pads {closest}), "
                f"below required minimum {min_mm}mm"
                if geometry_model == "copper"
                else (
                    f"{metric.capitalize()} {where} is {dist:.3f}mm "
                    f"(ORIGIN-TO-ORIGIN -- no pad geometry available, so this "
                    f"figure is optimistic), below required minimum {min_mm}mm"
                )
            ),
            "location": midpoint,
            "severity": "error",
            "boundary": boundary,
            "ref_a": ref_a,
            "ref_b": ref_b,
            "metric": metric,
            "measured_mm": dist,
            "required_mm": min_mm,
            "geometry_model": geometry_model,
            "creepage_model": creepage_model,
            "pair_kind": pair_kind,
            "closest_pads": closest,
        }
        if metric == "clearance":
            kwargs["measured_clearance_mm"] = dist
            kwargs["required_clearance_mm"] = min_mm
        else:
            kwargs["measured_creepage_mm"] = dist
            kwargs["required_creepage_mm"] = min_mm
        violations.append(ClearanceViolation(**kwargs))

    if origin_modelled:
        logger.warning(
            "REQ-SAFE-01 %s %s: %d of %d candidate pairs were measured "
            "ORIGIN-TO-ORIGIN because a component carried no pad geometry. That "
            "proxy is an UPPER bound on true copper-to-copper separation -- i.e. "
            "optimistic, in the unsafe direction. Supply `pads` on every "
            "placement component to get a real answer.",
            metric,
            boundary,
            origin_modelled,
            len(candidates),
        )

    stats = {
        "boundary": boundary,
        "metric": metric,
        "min_mm": min_mm,
        "pairs_checked": len(candidates),
        "pairs_inter": len(inter),
        "pairs_intra": len(intra),
        "pairs_pruned_by_bound": pruned,
        "pairs_origin_modelled": origin_modelled,
        "pairs_unrestricted_pads": unrestricted,
        "components_without_pads": sorted(model.components_without_pads),
        "board_cutouts": len(cutouts),
    }
    return ClearanceResult(passed=len(violations) == 0, violations=violations, stats=stats)


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
    if not result.violations:
        return "No clearance/creepage violations."

    rows = sorted(
        result.violations,
        key=lambda v: (-(v.shortfall_mm if v.shortfall_mm is not None else 0.0), v.ref_a or ""),
    )
    shown = rows if limit is None else rows[:limit]

    header = (
        f"{'pair':<16} {'boundary':<22} {'insul':<11} {'metric':<9} "
        f"{'meas':>8} {'req':>7} {'short':>8}  model"
    )
    lines = [
        f"{len(result.violations)} REQ-SAFE-01 violation(s), worst first:",
        header,
        "-" * len(header),
    ]
    for v in shown:
        pair = (
            f"{v.ref_a} (intra)"
            if v.pair_kind == "intra"
            else f"{v.ref_a}<->{v.ref_b}"
            if v.ref_a and v.ref_b
            else (v.ref_a or "?")
        )
        insul = v.insulation_type.value if v.insulation_type is not None else "-"
        meas = "n/a" if v.measured_mm is None else f"{v.measured_mm:.3f}"
        req = "n/a" if v.required_mm is None else f"{v.required_mm:.1f}"
        short = "n/a" if v.shortfall_mm is None else f"{v.shortfall_mm:.3f}"
        model = v.geometry_model or "?"
        if v.metric == "creepage" and v.creepage_model:
            model = f"{model}; {v.creepage_model}"
        lines.append(
            f"{pair:<16} {v.boundary or '-':<22} {insul:<11} {v.metric or '-':<9} "
            f"{meas:>8} {req:>7} {short:>8}  {model}"
        )
    if limit is not None and len(rows) > limit:
        lines.append(f"... and {len(rows) - limit} more")

    lines.append("")
    lines.append("Closest copper, per violating pair:")
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for v in shown:
        key = (v.ref_a, v.ref_b, v.closest_pads)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  {v.closest_pads}")
    return "\n".join(lines)


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
    return _check_distance(placement, domain_a, domain_b, min_mm, metric="clearance")


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
    # One shared copper model across all 12 sub-checks: the same pad polygons
    # and the same pair distances are reused by both metrics and by the basic
    # and reinforced tiers of the same boundary.
    model = _CopperModel(placement)

    all_violations: list[ClearanceViolation] = []
    per_row: list[dict[str, Any]] = []
    for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items():
        clearance_result = _check_distance(
            placement,
            domain_a,
            domain_b,
            requirements["min_clearance_mm"],
            metric="clearance",
            nets_domain=nets_domain,
            model=model,
        )
        creepage_result = _check_distance(
            placement,
            domain_a,
            domain_b,
            requirements["min_creepage_mm"],
            metric="creepage",
            nets_domain=nets_domain,
            model=model,
        )
        for violation in (*clearance_result.violations, *creepage_result.violations):
            violation.insulation_type = insulation_type
            all_violations.append(violation)
        for sub in (clearance_result, creepage_result):
            per_row.append({**sub.stats, "insulation": insulation_type.value})

    stats = {
        "rows": per_row,
        "components": len(placement.get("components", [])),
        "components_without_pads": sorted(model.components_without_pads),
        "board_cutouts": len(_board_cutouts(placement)),
        "violating_pairs": len(
            {
                (v.ref_a, v.ref_b)
                for v in all_violations
                if v.ref_a is not None and v.ref_b is not None
            }
        ),
        "intra_component_violations": sum(1 for v in all_violations if v.pair_kind == "intra"),
    }
    return ClearanceResult(passed=len(all_violations) == 0, violations=all_violations, stats=stats)


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
