"""Voltage-domain clearance constraint generation for CP-SAT placement (R24).

**The gap this closes:** a survey of ``_encoder_core.py`` / ``model.py`` /
``encoder.py`` / ``_encoder_solve.py`` found exactly one clearance mechanism —
``EncoderContext.courtyard_clearance_mm``, a single scalar applied uniformly
to *every* component pair (see ``_generate_courtyard_separated_constraints``
in ``_encoder_core.py``). Nothing in the CP-SAT encoder classifies a
component by voltage domain or looks up a clearance requirement keyed by
*which two domains* a pair straddles. The placer was structurally incapable
of producing a domain-clearance-compliant board; this module is the fix.

**Reuse, not reinvention (per task instruction).** ``VoltageDomain`` and
``IEC60335_REQUIREMENTS`` — the matrix of clearance/creepage minimums per
(domain_a, domain_b, insulation_type) — and the pairing logic that walks a
placement's components against that matrix
(``_nets_domain_map``/``_domain_boundary_pairs``) are all imported directly
from ``tests/requirements/validators/clearance.py``, the safety validator
that the fixed board must satisfy. This constraint generator and the
validator that checks it share one classifier; they cannot drift apart by
construction, because the second one *is* the first one, imported.

This is a real cross-layer import (``src`` depending on ``tests``), which is
architecturally unusual and is called out plainly in
``docs/evidence/2026-07-27-domain-clearance-constraint.md`` rather than
hidden. ``tests/`` is a proper Python package
The validator now lives in ``temper_placer.requirements.validators.clearance``
(moved there 2026-07-27) so this module -- and therefore the CP-SAT encoder --
can import it without production depending on the test tree.

**Encoding strategy — reuse SeparatedConstraint, not a new constraint type.**
``SeparatedConstraint`` (``pcl/constraints.py``) already has a registered
CP-SAT handler (``handlers/separated.py::encode_separated``) with its own
documented soundness proof: SAT of the encoding implies a Chebyshev (L∞) gap
of at least ``min_distance_mm`` between the two components' courtyard
bounding boxes (edge-to-edge, one axis suffices). Rather than inventing a
new handler, this module generates ordinary ``SeparatedConstraint`` objects
— one per (domain-crossing) component pair, with ``min_distance_mm`` set to
the IEC 60335-2-6 requirement — and lets the existing handler encode them.
No new CP-SAT machinery is introduced; the gap was that nothing *called*
the existing machinery with domain-aware margins.

**Soundness proof (R24 item 1) — Chebyshev edge-to-edge bound implies
Euclidean center-to-center distance bound:**

The safety validator (``clearance.py::_check_distance``) measures the
straight-line (Euclidean) distance between component ``position`` fields —
in the CP-SAT model these are ``x_center``/``y_center`` (see
``model.py::ComponentVars``, "Position variables use centre-of-mass
coordinates"). The encoder's ``SeparatedConstraint`` handler instead bounds
the gap between courtyard **edges**. These are different quantities; the
proof below is that the encoded (edge) bound is a *conservative* bound on
the validator's (center) quantity — it never overestimates the true
separation the validator will measure.

Let component A have half-extents (hw_a, hh_a) and component B have
half-extents (hw_b, hh_b) (courtyard size / 2). Suppose the encoder's
disjunction is SAT via the "left" branch (WLOG; "right"/"below"/"above" are
symmetric):

    a.x_end + margin <= b.x_start
    where a.x_end = a.x_center + hw_a, b.x_start = b.x_center - hw_b

    => b.x_center - a.x_center >= margin + hw_a + hw_b >= margin   (hw >= 0)

    => |b.x_center - a.x_center| >= margin

    Euclidean center distance = sqrt(dx^2 + dy^2) >= |dx| >= margin.

The same argument holds for the "right"/"below"/"above" branches (swap
sign / axis). So: **SAT of the SeparatedConstraint encoding at margin M ⇒
Euclidean center-to-center distance >= M**, for any nonnegative courtyard
half-extents. Setting M = the IEC 60335-2-6 requirement (the exact
threshold the validator itself uses) therefore guarantees the validator
finds no violation on that pair, in any solution the solver returns. This
is a strict inequality in the safe direction: the *realized* center
distance is >= M + hw_a + hw_b, i.e. the encoding is conservative (it
delivers at least as much separation as required, generally more, because
of the half-extents it doesn't need to subtract).

Both ``min_clearance_mm`` and ``min_creepage_mm`` are matrix values for a
given (domain_a, domain_b, insulation_type) row; since the validator checks
both against the same Euclidean center-distance quantity (creepage is a
documented conservative *lower bound* using straight-line distance — see
``check_creepage_path``'s docstring), encoding at
``margin = max(min_clearance_mm, min_creepage_mm)`` for every applicable row
satisfies both checks simultaneously. In this project's current
``IEC60335_REQUIREMENTS`` matrix, ``min_creepage_mm >= min_clearance_mm`` in
every row, so ``margin`` reduces to ``min_creepage_mm``; the ``max()`` is
kept anyway so this does not silently invert if the matrix ever changes.

**BMC-exhaustive validation (R24 item 2):** see
``tests/placer/cp_sat/test_domain_clearance.py::TestChebyshevSoundnessBMC`` —
an exhaustive sweep of the encoder's own Chebyshev-disjunction predicate
(reimplemented as pure Python matching ``encode_separated`` line-for-line,
not re-derived) against the validator's own ``_distance`` oracle, over every
integer-mm offset in a bounded window and several courtyard-size pairs,
asserting the implication above has zero counterexamples.

**Post-solve audit (R24 item 3):** ``audit_domain_clearance`` below
recomputes the actual Euclidean center-to-center distance from the
*resolved* placement coordinates for every generated constraint and compares
it against the constraint's ``min_distance_mm``, independent of whatever
the CP-SAT solver claims about feasibility. A mismatch (encoded constraint
present, solver reports SAT, but recomputed real distance < required) is
returned as a violation for the caller to hard-fail on. This is the "the
audit is the one that matters most" gate from ``AGENTS.md`` R24 — it does
not trust the solver's own bookkeeping, it recomputes from coordinates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cross-layer import shim: tests/ is a real package but not an installed
# runtime dependency, so make sure packages/temper-placer is importable
# regardless of how this module is invoked (pytest already does this itself;
# this shim covers direct script/CLI invocation).
# ---------------------------------------------------------------------------
from temper_placer.requirements.validators.clearance import (
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    _domain_boundary_pairs,
    _nets_domain_map,
)

__all__ = [
    "IEC60335_REQUIREMENTS",
    "VoltageDomain",
    "DomainClearanceAuditViolation",
    "generate_domain_clearance_constraints",
    "audit_domain_clearance",
    "required_margin_mm",
]


def required_margin_mm(requirements: dict[str, float]) -> float:
    """The single margin to encode for one IEC60335_REQUIREMENTS row.

    ``max()`` of clearance and creepage minimums so a single
    ``SeparatedConstraint`` per pair satisfies both checks (see module
    docstring). Kept as ``max()`` rather than assuming
    ``min_creepage_mm >= min_clearance_mm`` so the code doesn't silently
    invert if the matrix is ever edited.
    """
    return max(requirements["min_clearance_mm"], requirements["min_creepage_mm"])


def generate_domain_clearance_constraints(
    placement: dict[str, Any],
    voltage_domains: dict[str, VoltageDomain],
    component_refs: set[str] | None = None,
) -> list[SeparatedConstraint]:
    """Generate one HARD SeparatedConstraint per domain-crossing component pair.

    Mirrors ``verify_iec60335_compliance``'s own walk of
    ``IEC60335_REQUIREMENTS`` exactly (same classifier, same pairing
    function, imported not reimplemented) so the constraint this function
    emits and the check the validator later runs cannot disagree about
    *which pairs* are subject to a requirement — only whether the resulting
    placement satisfies it.

    Args:
        placement: ``{"components": [{"ref": ..., "nets": [...]}, ...],
            "nets": {...}}`` — same shape ``clearance.py`` consumes.
            Positions are not required for pairing (only for the
            downstream validator's distance check).
        voltage_domains: net name -> VoltageDomain overrides, merged over
            (and taking precedence over) any domain in ``placement["nets"]``
            — same argument ``verify_iec60335_compliance`` takes.
        component_refs: if given, restricts generated constraints to pairs
            where both refs are in this set (e.g. ``model.component_map``
            for the current CP-SAT solve). ``None`` means unrestricted.

    Returns:
        SeparatedConstraint list, one per unique (ref_a, ref_b) pair that
        crosses an IEC60335_REQUIREMENTS-covered domain boundary, with
        ``min_distance_mm`` = the max required margin across every matrix
        row that applies to that pair (a pair can match more than one row,
        e.g. both the basic and reinforced tiers of the same domain pair;
        the stricter one wins).
    """
    nets_domain = _nets_domain_map(placement, voltage_domains)

    # (ref_a, ref_b) -> (margin_mm, [reasons]) ; order is stable per matrix
    # row (ref_a always drawn from domain_a's group), so no frozenset/sort
    # needed for the dict key -- distinct rows over the same unordered
    # domain pair always list domain_a/domain_b in the same order.
    pair_margin: dict[tuple[str, str], float] = {}
    pair_reason: dict[tuple[str, str], str] = {}

    for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items():
        margin = required_margin_mm(requirements)
        for comp_a, comp_b in _domain_boundary_pairs(placement, domain_a, domain_b, nets_domain):
            ra, rb = comp_a.get("ref"), comp_b.get("ref")
            if not isinstance(ra, str) or not isinstance(rb, str):
                continue
            if component_refs is not None and (ra not in component_refs or rb not in component_refs):
                continue
            key = (ra, rb)
            if margin > pair_margin.get(key, 0.0):
                pair_margin[key] = margin
                pair_reason[key] = (
                    f"IEC 60335-2-6 {domain_a.value}<->{domain_b.value} "
                    f"({insulation_type.value}): {margin}mm "
                    f"(max of clearance={requirements['min_clearance_mm']}mm, "
                    f"creepage={requirements['min_creepage_mm']}mm)"
                )

    constraints: list[SeparatedConstraint] = []
    for (ra, rb), margin in sorted(pair_margin.items()):
        constraints.append(
            SeparatedConstraint(
                a=ra,
                b=rb,
                min_distance_mm=margin,
                tier=ConstraintTier.HARD,
                because=pair_reason[(ra, rb)],
                id=f"domain_clearance_{ra}_{rb}",
            )
        )

    logger.info(
        "Generated %d domain-clearance SEPARATED constraints from %d matrix rows",
        len(constraints),
        len(IEC60335_REQUIREMENTS),
    )
    return constraints


@dataclass
class DomainClearanceAuditViolation:
    """A post-solve mismatch between the encoded bound and the real distance."""

    ref_a: str
    ref_b: str
    required_mm: float
    actual_mm: float
    reason: str


def audit_domain_clearance(
    constraints: list[SeparatedConstraint],
    resolved_positions_mm: dict[str, tuple[float, float]],
) -> list[DomainClearanceAuditViolation]:
    """Recompute real Euclidean center distance for every generated constraint.

    This is the R24 item-3 audit: it does not ask the CP-SAT solver whether
    the constraint was satisfied. It takes the *solved* placement's
    coordinates directly and recomputes ``math.dist`` between the two refs'
    centers — the exact quantity ``clearance.py``'s validator checks — and
    compares against ``constraint.min_distance_mm``. Any mismatch means the
    encoding's own soundness proof (module docstring) failed to hold for
    this solve (e.g. a bug in the handler, a units error, a component
    dropped from the model) and is returned for the caller to hard-fail on.

    Args:
        constraints: the SeparatedConstraint list this module generated
            (id must start with ``domain_clearance_`` to be audited here;
            other SeparatedConstraints -- courtyard, netclass -- are not
            this function's concern).
        resolved_positions_mm: {ref: (x_mm, y_mm)} from the solved
            placement (center coordinates, matching ``x_center``/
            ``y_center`` semantics).

    Returns:
        List of violations; empty means every audited constraint's real
        distance met or exceeded its required minimum.
    """
    import math

    violations: list[DomainClearanceAuditViolation] = []
    for c in constraints:
        if not c.id.startswith("domain_clearance_"):
            continue
        pos_a = resolved_positions_mm.get(c.a)
        pos_b = resolved_positions_mm.get(c.b)
        if pos_a is None or pos_b is None:
            violations.append(
                DomainClearanceAuditViolation(
                    ref_a=c.a,
                    ref_b=c.b,
                    required_mm=c.min_distance_mm,
                    actual_mm=float("nan"),
                    reason=f"missing resolved position for {c.a if pos_a is None else c.b}",
                )
            )
            continue
        actual = math.dist(pos_a, pos_b)
        if actual < c.min_distance_mm:
            violations.append(
                DomainClearanceAuditViolation(
                    ref_a=c.a,
                    ref_b=c.b,
                    required_mm=c.min_distance_mm,
                    actual_mm=actual,
                    reason=c.because,
                )
            )
    return violations
