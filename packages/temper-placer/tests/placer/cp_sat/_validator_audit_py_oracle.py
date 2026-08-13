"""Pinned Python oracle for the
``temper_placer/placer/cp_sat/validator_audit.py`` validator-aligned
post-solve audit (orchestration-port unit U-I, Wave-4).

This file is a VERBATIM copy of the pre-migration
``temper_placer/placer/cp_sat/validator_audit.py`` audit as of the U-I base
commit. Only the module docstring was replaced with this pin note.

DO NOT EDIT THE SEMANTICS. This is the oracle the Rust audit kernels
(``temper_orchestration``) must reproduce bit-identically; any edit here
silently weakens the differential proof. If the module's audit sequencing
changes, the oracle must be re-pinned from the new base first.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from temper_placer.pcl.constraints import SeparatedConstraint
from temper_placer.requirements.validators.clearance import (
    ClearanceViolation,
    verify_iec60335_compliance,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainClearanceValidatorViolation:
    """One REQ-SAFE-01 validator violation on the solved placement, carrying
    enough of the validator's own record to act on it directly."""

    ref_a: str
    ref_b: str
    boundary: str
    insulation_type: str
    metric: str  # "clearance" | "creepage"
    measured_mm: float
    required_mm: float
    pair_kind: str  # "inter" | "intra"
    closest_pads: str | None
    #: Why this violation landed in its bucket: the covered constraint id
    #: for (a), the placement-independence statement for (b), or the
    #: generator-vs-validator pair-set mismatch note for (c).
    reason: str

    @property
    def shortfall_mm(self) -> float:
        return self.required_mm - self.measured_mm


@dataclass
class DomainClearanceValidatorAuditResult:
    """Result of re-running the REQ-SAFE-01 validator on the solved
    placement, classified against the solve's domain-clearance constraint
    set (see module docstring for the three buckets)."""

    #: (a) inter-component pairs the constraint set covers: an encoding
    #: unsoundness for this solve. MUST be empty for a SAT/optimal solve.
    hard_failures: list[DomainClearanceValidatorViolation] = field(default_factory=list)
    #: (b) intra-footprint straddlers: placement-independent, never a solver
    #: failure (e.g. K3's own G5LE-1 coil-to-contact gap).
    intra_footprint: list[DomainClearanceValidatorViolation] = field(default_factory=list)
    #: (c) inter-component pairs the generator never constrained: the
    #: solver-validator pair-set alignment finding.
    coverage_gaps: list[DomainClearanceValidatorViolation] = field(default_factory=list)
    #: Distinct inter pairs the constraint set covered (diagnostic).
    covered_pair_count: int = 0
    #: Total validator violation records on the solved placement (all
    #: buckets combined).
    validator_violation_count: int = 0
    #: Raw validator ``ClearanceResult.stats`` from the top-level
    #: ``verify_iec60335_compliance`` call: ``components``,
    #: ``components_without_pads`` (sorted ref list), ``board_cutouts``,
    #: ``violating_pairs``, ``intra_component_violations``, and ``rows``
    #: (per requirement-row stats carrying ``pairs_origin_modelled``).
    #: Captured so a caller can see *why* a clean audit might still be
    #: untrustworthy (see ``geometry_trusted``).
    stats: dict[str, Any] = field(default_factory=dict)
    #: True when every placement component carried pad geometry: no
    #: ``stats["components_without_pads"]`` and no per-row
    #: ``pairs_origin_modelled``. False means the validator measured some
    #: pair origin-to-origin (a component modelled as a zero-extent point) --
    #: an OPTIMISTIC upper bound on copper separation, the run-B lie
    #: direction -- so a clean audit then proves nothing about real copper.
    #: Set False together with a ``logger.error`` in the audit.
    geometry_trusted: bool = True

    @property
    def clean(self) -> bool:
        """True when the solve is validator-clean for everything placement
        can fix (no hard failures, no coverage gaps). Intra-footprint
        records may remain -- they are unfixable by placement."""
        return not self.hard_failures and not self.coverage_gaps

    def report(self) -> str:
        """Worst-first, designer-readable summary of every bucket."""
        lines = [
            f"{self.validator_violation_count} REQ-SAFE-01 validator "
            f"violation(s) on the solved placement "
            f"({len(self.hard_failures)} hard, {len(self.intra_footprint)} "
            f"intra-footprint, {len(self.coverage_gaps)} coverage-gap) "
            f"over {self.covered_pair_count} constrained pair(s)."
        ]
        for label, bucket in (
            ("HARD (encoding-unsound, constraint-covered pair)", self.hard_failures),
            ("INTRA-FOOTPRINT (placement-independent)", self.intra_footprint),
            ("COVERAGE GAP (pair not in the solve's constraint set)", self.coverage_gaps),
        ):
            if not bucket:
                continue
            lines.append(f"{label}:")
            for v in sorted(bucket, key=lambda v: -v.shortfall_mm):
                lines.append(
                    f"  {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.3f} / "
                    f"{v.required_mm:.1f}mm ({v.boundary}, {v.insulation_type}) "
                    f"[{v.closest_pads or '?'}] {v.reason}"
                )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Solved-placement builder
# ---------------------------------------------------------------------------


def _pads_for_netlist_component(component: Any) -> list[dict[str, Any]]:
    """Serialize a parsed ``Component``'s pins into the validator's pad
    schema -- mirrors ``tests/requirements/safety/_real_board_fixture.py::
    _pads_for_component`` (same field names, same offset/width/height/
    rotation semantics). Used only when a placement component lacks ``pads``.
    """
    pads: list[dict[str, Any]] = []
    for pin in getattr(component, "pins", ()):
        pads.append(
            {
                "number": getattr(pin, "number", None) or getattr(pin, "name", None),
                "net": getattr(pin, "net", None),
                "offset": getattr(pin, "position", (0.0, 0.0)),
                "width": getattr(pin, "width", 1.0),
                "height": getattr(pin, "height", 1.0),
                "shape": getattr(pin, "shape", "rect"),
                "roundrect_ratio": getattr(pin, "roundrect_ratio", 0.0),
                "pad_rotation_deg": getattr(pin, "pad_rotation_deg", 0.0),
                "layer": getattr(pin, "layer", "F.Cu"),
            }
        )
    return pads


def _netlist_component_by_ref(netlist_or_parse_result: Any, ref: str) -> Any | None:
    """The parsed ``Component`` for *ref* from a Netlist or ParseResult."""
    for comp in getattr(netlist_or_parse_result, "components", ()):
        if getattr(comp, "ref", None) == ref:
            return comp
    return None


def build_validator_placement(
    placement: dict[str, Any],
    resolved_positions_mm: dict[str, tuple[float, float]],
    resolved_rotations: dict[str, int],
    netlist_or_parse_result: Any = None,
) -> dict[str, Any]:
    """Copy *placement* with component positions/rotations taken from the
    solve, producing the exact-copper placement ``verify_iec60335_compliance``
    consumes.

    Mirrors ``_real_board_fixture.load_real_board_placement``'s placement
    shape (ref + nets + pads + ``rotation_deg`` + board geometry); the only
    difference is the position/rotation source: the solved coordinates
    instead of the committed board. Components the solve did not move keep
    their base positions/rotations (they are pinned in the solve).

    Args:
        placement: validator-shape placement (the one the domain-clearance
            constraint generator consumed -- same classification, same pads).
        resolved_positions_mm: {ref: (x_mm, y_mm)} solved centers.
        resolved_rotations: {ref: 0-3 quadrant index} solved rotations
            (converted to ``rotation_deg = idx * 90`` for the validator).
            A ref present in BOTH ``resolved_positions_mm`` and
            ``resolved_rotations`` has its rotation overlaid
            UNCONDITIONALLY -- the solver's index is authoritative for a
            ref it rotated (the CLI writes ``idx * 90`` to the PCB), even
            when the board's base rotation is non-multiple-of-90. A ref
            ABSENT from ``resolved_rotations`` keeps its exact base
            rotation (the solve did not rotate it -- no rotation variable).
        netlist_or_parse_result: optional Netlist/ParseResult used to supply
            pad geometry for any placement component that carries no ``pads``
            key (same fallback the fixture provides by construction).
    """
    out = copy.deepcopy(placement)
    for comp in out.get("components", []):
        ref = comp.get("ref")
        if not isinstance(ref, str):
            continue
        pos = resolved_positions_mm.get(ref)
        if pos is not None:
            comp["position"] = tuple(pos)
        rot = resolved_rotations.get(ref)
        if rot is not None and pos is not None:
            # Quadrant index -> degrees, the same conversion
            # CpSatPlacementResult.to_rotations_dict uses. A ref the solve
            # TOUCHED (solved position AND solved rotation index) gets the
            # solver's rotation overlaid unconditionally: the CLI writes
            # ``rotation=cp_result.rotations.get(ref, 0) * 90.0`` to the PCB
            # for every solved ref (cli/__init__.py's ``optimize`` command),
            # so the audit must measure the post-solve geometry, and the
            # solver's index is authoritative even when the board's base
            # rotation is non-multiple-of-90 -- a ref the solve rotated WILL
            # be written as idx*90 on the PCB. Keep the base rotation only
            # when the ref is ABSENT from ``resolved_rotations``: the solve
            # did not rotate it (no rotation variable, e.g. a polarized part
            # pinned by construction), so the board keeps its exact base --
            # which for a non-quadrant ref the solver's 0-3 index could not
            # represent anyway (position-frame contract, handoff #523 gap 2
            # §6).
            comp["rotation_deg"] = float(int(rot) * 90.0)
        if "pads" not in comp and netlist_or_parse_result is not None:
            netlist_comp = _netlist_component_by_ref(netlist_or_parse_result, ref)
            if netlist_comp is not None:
                comp["pads"] = _pads_for_netlist_component(netlist_comp)
    return out


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------


def _classify_violation(
    v: ClearanceViolation,
    covered_pairs: set[frozenset[str]],
) -> tuple[str, str]:
    """Bucket (module docstring's (a)/(b)/(c)) + reason for one validator
    violation. Returns ``(bucket, reason)`` with bucket in
    {"hard", "intra", "gap"}.
    """
    ref_a = v.ref_a or "?"
    ref_b = v.ref_b or "?"
    if v.pair_kind == "intra" or ref_a == ref_b:
        return (
            "intra",
            (
                f"{ref_a}'s own pads straddle a domain boundary within one "
                "footprint; placement translates/rotates the part rigidly so no "
                "SeparatedConstraint (nor any placement) can fix it -- reported "
                "separately, not as a solver-encoding failure"
            ),
        )
    if frozenset((ref_a, ref_b)) in covered_pairs:
        return (
            "hard",
            (
                f"pair is covered by the solve's domain-clearance constraint set "
                f"but the validator still measures {v.measured_mm:.3f}mm "
                f"copper-to-copper < {v.required_mm}mm required -- the box "
                "separation the solver SAT did NOT imply the validator's exact "
                "copper separation (encoding unsound for this solve)"
            ),
        )
    return (
        "gap",
        (
            "pair is NOT in the solve's domain-clearance constraint set -- the "
            "generator's component_refs filter or the intra-footprint exemption "
            "excluded it (solver-validator pair-set misalignment)"
        ),
    )


def audit_domain_clearance_validator(
    constraints: list[SeparatedConstraint],
    resolved_positions_mm: dict[str, tuple[float, float]],
    resolved_rotations: dict[str, int],
    placement: dict[str, Any],
    voltage_domains: dict[str, Any],
    netlist_or_parse_result: Any = None,
) -> DomainClearanceValidatorAuditResult:
    """R24 item-3 audit against the EXACT REQ-SAFE-01 validator (issue #523
    gap 2).

    Re-runs ``verify_iec60335_compliance`` -- copper-to-copper on exact,
    rotation-aware pad geometry, the function the CI gate runs -- on a
    placement whose positions/rotations come from the solved coordinates
    (``build_validator_placement``), then classifies every violation into
    the module docstring's three buckets against the solve's
    domain-clearance ``SeparatedConstraint`` set.

    By ``domain_clearance.py``'s soundness proof, a SAT/optimal solve must
    produce an empty ``hard_failures`` list; a non-empty one means the
    encoding is unsound for this solve and the caller (``_encoder_solve``)
    treats it as a hard error -- the same contract as
    ``fixed_copper.audit_fixed_copper``. ``intra_footprint`` and
    ``coverage_gaps`` are reported, never raised.

    The result also carries the validator's ``stats`` and a
    ``geometry_trusted`` flag (False + ``logger.error`` when any component
    lacked pad geometry or any pair was measured origin-to-origin -- see the
    module docstring: those figures are an optimistic upper bound, so a
    clean-but-untrusted audit proves nothing about copper). The audit
    refuses to run when the placement does not describe the solve: zero
    components, or ``resolved_positions_mm`` refs disjoint from the
    placement's refs, raises ``ValueError`` (programmer error -- the
    alternative is a vacuous pass over the wrong geometry).

    Args:
        constraints: the domain-clearance SeparatedConstraint list the solve
            encoded (id prefix ``domain_clearance_``). Only the *pair set*
            is used -- coverage is a per-pair property, so margin values do
            not enter the classification.
        resolved_positions_mm: {ref: (x_mm, y_mm)} solved centers.
        resolved_rotations: {ref: 0-3} solved rotation indices.
        placement: validator-shape placement the generator consumed (same
            classification; positions are overlaid from the solve).
        voltage_domains: net -> domain map for the validator.
        netlist_or_parse_result: optional source of pad geometry for
            placement components lacking ``pads`` (see
            ``build_validator_placement``).

    Returns:
        A ``DomainClearanceValidatorAuditResult`` with the three classified
        buckets plus the validator's ``stats`` and ``geometry_trusted``.

    Raises:
        ValueError: the placement has zero components, or its refs share no
            overlap with ``resolved_positions_mm`` -- the placement does not
            describe the solve, so auditing it would be vacuous.
    """
    components = placement.get("components", [])
    if not components:
        raise ValueError(
            "audit_domain_clearance_validator: placement carries zero "
            "components -- re-running the REQ-SAFE-01 validator on it would "
            "vacuous-pass against an empty board; the placement does not "
            "describe the solve (programmer error)"
        )
    placement_refs = {c.get("ref") for c in components if isinstance(c.get("ref"), str)}
    solved_refs = set(resolved_positions_mm)
    if not placement_refs or not (placement_refs & solved_refs):
        raise ValueError(
            "audit_domain_clearance_validator: solved resolved_positions_mm "
            f"refs {sorted(solved_refs)} share no overlap with the placement's "
            f"component refs {sorted(placement_refs)} -- the placement does "
            "not describe the solve, so re-running the validator on it would "
            "audit the wrong geometry (programmer error)"
        )

    validator_placement = build_validator_placement(
        placement, resolved_positions_mm, resolved_rotations, netlist_or_parse_result
    )
    result = verify_iec60335_compliance(validator_placement, voltage_domains)
    stats = dict(result.stats or {})

    # Geometry trust: a component without pads is modelled as a zero-extent
    # point -- an OPTIMISTIC upper bound on copper separation (the run-B lie
    # direction: can miss violations, never invent them). Surface that state
    # loudly instead of letting a clean audit look like a proof of copper.
    components_without_pads = list(stats.get("components_without_pads", ()) or ())
    origin_modelled_pairs = sum(
        int(row.get("pairs_origin_modelled", 0) or 0) for row in stats.get("rows", [])
    )
    geometry_trusted = not components_without_pads and origin_modelled_pairs == 0
    if not geometry_trusted:
        logger.error(
            "REQ-SAFE-01 validator post-solve audit ran with DEGRADED geometry: "
            "%d component(s) carry no pads (%s) and %d candidate pair(s) were "
            "measured ORIGIN-TO-ORIGIN -- those figures are an OPTIMISTIC "
            "upper bound on true copper-to-copper separation (the run-B lie "
            "direction), so audit.geometry_trusted=False. Supply `pads` on "
            "every placement component before treating a clean audit as proof "
            "of copper separation.",
            len(components_without_pads),
            ", ".join(sorted(components_without_pads)) or "?",
            origin_modelled_pairs,
        )

    covered_pairs: set[frozenset[str]] = {
        frozenset((c.a, c.b))
        for c in constraints
        if isinstance(c.a, str) and isinstance(c.b, str)
    }

    hard: list[DomainClearanceValidatorViolation] = []
    intra: list[DomainClearanceValidatorViolation] = []
    gaps: list[DomainClearanceValidatorViolation] = []

    for v in result.violations:
        bucket, reason = _classify_violation(v, covered_pairs)
        violation = DomainClearanceValidatorViolation(
            ref_a=v.ref_a or "?",
            ref_b=v.ref_b or "?",
            boundary=v.boundary or "?",
            insulation_type=(
                v.insulation_type.value if v.insulation_type is not None else "?"
            ),
            metric=v.metric or "?",
            measured_mm=v.measured_mm if v.measured_mm is not None else float("nan"),
            required_mm=v.required_mm if v.required_mm is not None else float("nan"),
            pair_kind=v.pair_kind or ("intra" if v.ref_a == v.ref_b else "inter"),
            closest_pads=v.closest_pads,
            reason=reason,
        )
        if bucket == "hard":
            hard.append(violation)
        elif bucket == "intra":
            intra.append(violation)
        else:
            gaps.append(violation)

    if result.violations:
        logger.info(
            "REQ-SAFE-01 validator post-solve audit: %d violation(s) -> "
            "%d hard, %d intra-footprint, %d coverage-gap over %d constrained "
            "pair(s)",
            len(result.violations),
            len(hard),
            len(intra),
            len(gaps),
            len(covered_pairs),
        )

    return DomainClearanceValidatorAuditResult(
        hard_failures=hard,
        intra_footprint=intra,
        coverage_gaps=gaps,
        covered_pair_count=len(covered_pairs),
        validator_violation_count=len(result.violations),
        stats=stats,
        geometry_trusted=geometry_trusted,
    )


__all__ = [
    "DomainClearanceValidatorAuditResult",
    "DomainClearanceValidatorViolation",
    "audit_domain_clearance_validator",
    "build_validator_placement",
]
