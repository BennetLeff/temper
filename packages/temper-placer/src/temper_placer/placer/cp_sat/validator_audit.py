"""Validator-aligned post-solve audit for domain clearance (issue #523 gap 2).

**The gap this closes (measured, see
``docs/evidence/2026-08-01-k3-runb-not-validator-clean.md``).** The R24
post-solve audit for the domain-clearance constraint set
(``domain_clearance.audit_domain_clearance``) recomputes **center-to-center**
Euclidean distance from the resolved coordinates and compares it to the
encoded margin. Its own docstring admits this is "a cheaper, weaker check
than what ``clearance.py``'s validator actually measures (copper-to-copper
on exact pad geometry)". That distinction is not academic: the issue-#523
run-B scoped solve was *center-audit-clean* (0 ``audit_domain_clearance``
violations) while the actual REQ-SAFE-01 gate measured 12 violations across
9 pairs on the same placement (e.g. C27 landed 0.32mm from U24 -- the
solver's boxes were separated, the copper was not). Box separation is a
Chebyshev bound over each box's *courtyard/bounds*, which is a superset of
copper only when the box contains the copper; the exact validator measures
pad copper directly and is the truth that gates the board.

**What this module adds.** ``audit_domain_clearance_validator`` re-runs the
REQ-SAFE-01 validator itself (``verify_iec60335_compliance`` --
copper-to-copper on exact, rotation-aware pad geometry, the same function
the CI gate ``tests/requirements/safety/test_clearance.py::
TestClearanceIntegration::test_temper_board_clearance_compliance`` runs)
against a placement whose positions/rotations come from the *solve* rather
than the board. It mirrors how ``tests/requirements/safety/
_real_board_fixture.py`` builds the validator placement (component dicts
with ref + nets + pads from netlist pins + ``rotation_deg``); only the
position/rotation source changes. The existing center-distance audit stays
(cheap encoder check); this audit is additive and is the one that can see
copper-vs-copper.

**Classification** (per validator violation), so a solve that is
*validator-dirty* is attributed to the right cause rather than reported as
one undifferentiated list:

- **(a) HARD failure** -- an *inter-component* pair that the solve's
  generated ``SeparatedConstraint`` set covers. By
  ``domain_clearance.py``'s soundness proof, a SAT/optimal solve must have
  zero of these; any one means the encoding is unsound for this solve (the
  run-B case: box-separated but copper-touching). Same hard-failure
  contract as ``fixed_copper.audit_fixed_copper``.
- **(b) intra-footprint straddler** -- ``pair_kind == "intra"`` (or
  ``ref_a == ref_b``): one component whose own pads straddle a domain
  boundary. Placement cannot fix this (a rigid part's own pads move
  together), so it is reported as a separate, placement-independent list --
  never a solver-encoding failure. This is the K3 G5LE-1 coil-to-contact
  gap class.
- **(c) coverage gap** -- an *inter-component* pair the validator flags but
  the constraint set does NOT cover (the generator's ``component_refs``
  filter or the intra-footprint exemption excluded it). This is the
  "solver-validator pair-set alignment" finding: the audit is the place
  where a misalignment surfaces as data, not as a silent blind spot.

**R24 discipline.** The hard-failure list must be empty for a SAT/optimal
solve; ``_encoder_solve.py`` raises when it is not (same contract as
``audit_fixed_copper``). Intra-footprint and coverage-gap lists are
reportable, not raiseable -- the caller (e.g. ``solve_placement``) logs them
and surfaces them on the result.
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
        if rot is not None:
            # Quadrant index -> degrees, the same conversion
            # CpSatPlacementResult.to_rotations_dict uses.
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
        buckets.
    """
    validator_placement = build_validator_placement(
        placement, resolved_positions_mm, resolved_rotations, netlist_or_parse_result
    )
    result = verify_iec60335_compliance(validator_placement, voltage_domains)

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
    )


__all__ = [
    "DomainClearanceValidatorAuditResult",
    "DomainClearanceValidatorViolation",
    "audit_domain_clearance_validator",
    "build_validator_placement",
]
