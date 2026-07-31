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

**Soundness proof (R24 item 1) — REVISED 2026-07-30. Read this before
trusting anything below; the previous version of this proof described a
model the code no longer (and, on closer inspection, never actually)
matched.**

*What changed and why the old proof was stale.* The previous revision of
this proof concluded "SAT of the encoding ⇒ Euclidean **center-to-center**
distance >= margin" and stopped there, reasoning that the validator
measured center-to-center distance too. That premise was already false by
the time it was written: the validator (``clearance.py::_check_distance``,
rewritten 2026-07-28) measures **copper-to-copper distance on exact,
rotation-aware pad geometry**, restricted to pads whose own net is
classified into the relevant domain (``clearance.py`` module docstring) —
not component centers, and not whole-component boxes. A proof that a
center-distance bound holds is true but answers a question the validator
no longer asks; see
``docs/evidence/2026-07-30-domain-clearance-copper-aware-fix.md`` for the
measurement that surfaced this and the fix described below.

*The corrected proof: the Chebyshev box bound is copper-to-copper sound,
not just center-to-center sound, given one precondition on `comp.bounds`.*

``SeparatedConstraint``'s handler (``handlers/separated.py::encode_separated``)
bounds the gap between two components' **bounding boxes** — ``x_start``/
``x_end``/``y_start``/``y_end`` in ``model.py``, populated from
``comp.bounds`` (``_parse_modules.py::_calculate_footprint_bounds``, which
takes the union of courtyard/fab-layer graphics and every pad's copper
extent, then returns a box symmetric around a chosen centre point — see
next paragraph for why *which* centre point matters). The proof below
shows the SAT'd box bound is a lower bound not just on center-to-center
distance but on the distance between **any point in box A and any point in
box B** — including, in particular, every pad-to-pad pair, which is
exactly the copper-to-copper quantity the validator measures.

Let component A's box be ``[a.x_center - hw_a, a.x_center + hw_a] x
[a.y_center - hh_a, a.y_center + hh_a]`` (half-extents from ``comp.bounds``
/ 2), likewise B. Suppose the encoder's disjunction is SAT via the "left"
branch (WLOG; "right"/"below"/"above" are symmetric):

    a.x_end + margin <= b.x_start

For ANY point p_a in box A and p_b in box B (not just the centers):
``p_a.x <= a.x_end`` and ``p_b.x >= b.x_start``, so

    p_b.x - p_a.x >= b.x_start - a.x_end >= margin

    Euclidean distance(p_a, p_b) = sqrt(dx^2 + dy^2) >= |dx| >= margin.

This holds for **every** ``(p_a, p_b)`` pair, so in particular for every
pad-copper point on A paired with every pad-copper point on B — i.e. **SAT
of the encoding at margin M ⇒ every point of box A is >= M from every point
of box B**, a strictly stronger conclusion than the old center-only proof
(which is recovered as the special case p_a = a.x_center, p_b = b.x_center).

*The precondition this proof needs, and why it now holds by construction
rather than by observation:* the argument above requires box A to actually
**contain** every pad A places, in the SAME coordinate frame the box is
centred at when the solver places it — i.e. at ``Component.initial_position``.
Before 2026-07-30, ``_calculate_footprint_bounds`` computed its symmetric
half-extents around the footprint's raw KiCad anchor, while
``initial_position``/``Pin.position`` are expressed relative to a
*different* point (the pad centroid, ``center_offset`` in
``_extract_components_from_pcb``) — a latent frame mismatch that could, for
a footprint with asymmetric enough pad sizes, produce a box that does not
enclose real copper at the point the solver actually places it (see
``tests/placer/cp_sat/test_geometry_constraints_pbt.py::
test_bounds_computed_in_placement_frame_not_raw_anchor`` for a constructed
counter-example, and the evidence doc for why this did not manifest as an
actual violation on ``pcb/temper.kicad_pcb``'s current 168 components —
measured directly, not assumed). ``_calculate_footprint_bounds`` now takes
the placement centre as an explicit argument and computes its envelope
around *that* point, so "box ⊇ real copper at the placed position" is now
an invariant proven by construction (P10 in the test file above), not an
accident of this board's specific footprints.

Both ``min_clearance_mm`` and ``min_creepage_mm`` are matrix values for a
given (domain_a, domain_b, insulation_type) row; since the validator checks
both against the same copper-to-copper distance quantity (creepage is a
documented conservative *lower bound* using straight-line distance — see
``check_creepage_path``'s docstring), encoding at
``margin = max(min_clearance_mm, min_creepage_mm)`` for every applicable row
satisfies both checks simultaneously. In this project's current
``IEC60335_REQUIREMENTS`` matrix, ``min_creepage_mm >= min_clearance_mm`` in
every row, so ``margin`` reduces to ``min_creepage_mm``; the ``max()`` is
kept anyway so this does not silently invert if the matrix ever changes.

**What this proof does NOT cover — intra-footprint (self) pairs.** The
argument above is about box A vs. box B for two *distinct* components; it
says nothing about, and cannot be extended to cover, a single component
whose own pads sit in two different voltage domains (e.g. an isolator with
a primary-side pad and a secondary-side pad on the same physical part).
Placing a component only translates/rotates its box as a rigid whole — it
cannot change the distance between two of that component's own pads, so no
``SeparatedConstraint`` (or any other placement-time constraint) can ever
make an intra-footprint domain crossing compliant. This is not a gap in
the proof; it is a statement about what placement, as a category of fix,
can and cannot do. ``generate_domain_clearance_constraints`` therefore
never emits a self-pair (``handlers/separated.py``'s ``if ra == rb:
continue`` is defense-in-depth against ever encoding one, not the primary
mechanism — the primary exclusion is in the imported
``_domain_boundary_pairs`` itself). Previously this made such components
**silently invisible** to this module: no constraint, no log line, no
signal. ``find_intra_footprint_domain_conflicts`` (below) now enumerates
them explicitly, and ``generate_domain_clearance_constraints`` logs a
warning naming every one on every call that finds any, so a reader hits
this limitation in the logs of a normal run, not only in a docstring. The
validator's own ``_intra_component_boundary_components``
(``clearance.py``) is still the authoritative, pad-level check for these —
this module's version is a coarser, component-level early-warning that a
given ref is worth investigating, not a replacement for it.

**BMC-exhaustive validation (R24 item 2):** see
``tests/placer/cp_sat/test_domain_clearance.py::TestChebyshevSoundnessBMC`` —
an exhaustive sweep of the encoder's own Chebyshev-disjunction predicate
(reimplemented as pure Python matching ``encode_separated`` line-for-line,
not re-derived) against the validator's own ``_distance`` oracle, over every
integer-mm offset in a bounded window and several courtyard-size pairs,
asserting the implication above has zero counterexamples. This sweep
checks the box-vs-box (equivalently, center-vs-center, since it is
translation-invariant per size pair) geometry of the encoding itself; the
copper-vs-box containment precondition added above is checked separately,
per-component, by
``test_geometry_constraints_pbt.py``'s P8/P9/P10 (bounds ⊇ pads, including
in the correct frame) rather than re-derived here.

**Post-solve audit (R24 item 3):** ``audit_domain_clearance`` below
recomputes the actual Euclidean center-to-center distance from the
*resolved* placement coordinates for every generated constraint and compares
it against the constraint's ``min_distance_mm``, independent of whatever
the CP-SAT solver claims about feasibility. A mismatch (encoded constraint
present, solver reports SAT, but recomputed real distance < required) is
returned as a violation for the caller to hard-fail on. This is the "the
audit is the one that matters most" gate from ``AGENTS.md`` R24 — it does
not trust the solver's own bookkeeping, it recomputes from coordinates.
Note this audit still recomputes **center**-to-center distance (it is a
cheap, coordinate-only sanity check, not a re-run of the full copper
geometry pipeline); given the corrected proof above, center distance >=
margin is implied by, but weaker than, the box's actual copper guarantee —
this audit catches encoder/units bugs, it is not a substitute for
re-running the validator itself, which the "Standard of proof" section of
this fix's evidence doc does after every solve.
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
    _components_in_domain,
    _domain_boundary_pairs,
    _nets_domain_map,
)

__all__ = [
    "IEC60335_REQUIREMENTS",
    "VoltageDomain",
    "DomainClearanceAuditViolation",
    "IntraFootprintDomainConflict",
    "generate_domain_clearance_constraints",
    "find_intra_footprint_domain_conflicts",
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

    # R24-follow-up (2026-07-30): self-pairs never reach `constraints` above
    # (`_domain_boundary_pairs` excludes them, `handlers/separated.py`'s own
    # `if ra == rb: continue` is defense-in-depth) -- that exclusion is
    # correct (see module docstring: no placement constraint can separate a
    # component's own pads from each other), but it used to be silent. Log
    # every such ref loudly on every call that finds one, so "the solve
    # reported optimal" is never mistaken for "the board is compliant" when
    # an intra-footprint isolator is the actual remaining violation.
    conflicts = find_intra_footprint_domain_conflicts(placement, voltage_domains, component_refs)
    if conflicts:
        logger.warning(
            "generate_domain_clearance_constraints: %d component(s) straddle a "
            "domain boundary WITHIN their own footprint and therefore have NO "
            "SeparatedConstraint protecting them -- no placement can fix this "
            "(see module docstring). Verify with the REQ-SAFE-01 validator's "
            "own intra-footprint check, not this solve's status: %s",
            len(conflicts),
            ", ".join(
                f"{c.ref} ({c.domain_a.value}<->{c.domain_b.value}, {c.margin_mm}mm)"
                for c in conflicts
            ),
        )

    return constraints


@dataclass
class IntraFootprintDomainConflict:
    """One component whose OWN pads straddle a matrix-covered domain
    boundary -- a ref that ``generate_domain_clearance_constraints`` cannot
    emit any constraint for, no matter what placement is found (see module
    docstring for why placement categorically cannot fix this)."""

    ref: str
    domain_a: VoltageDomain
    domain_b: VoltageDomain
    margin_mm: float
    reason: str


def find_intra_footprint_domain_conflicts(
    placement: dict[str, Any],
    voltage_domains: dict[str, VoltageDomain],
    component_refs: set[str] | None = None,
) -> list[IntraFootprintDomainConflict]:
    """Enumerate components that ``generate_domain_clearance_constraints``
    structurally cannot protect: refs classified into BOTH sides of a
    matrix-covered domain boundary at once.

    This is a **component-level** check (does this ref have any net in
    domain_a AND any net in domain_b?), coarser than the validator's own
    **pad-level** ``clearance.py::_intra_component_boundary_components``
    (which additionally confirms the straddling pads' own nets -- not just
    the component's net *membership* -- resolve into each domain, and is
    the one that actually gates REQ-SAFE-01). A ref flagged here is not
    guaranteed to be a real violation (e.g. its DC_BUS-domain pad and its
    LV_CONTROL-domain pad might, in principle, already sit far enough apart
    within the footprint) -- but it IS guaranteed that no placement-time fix
    can ever be found for it if it is one, since every one of its pads
    moves together as a rigid unit under any placement. Use this to decide
    *where to look* (a footprint swap, a different part, a milled isolation
    slot), not as the safety gate itself -- that remains
    ``verify_iec60335_compliance``.

    Args:
        placement, voltage_domains, component_refs: identical contract to
            ``generate_domain_clearance_constraints`` -- same classifier
            (``_nets_domain_map``), same optional ref restriction.

    Returns:
        One ``IntraFootprintDomainConflict`` per (ref, worst-margin) pair,
        sorted by ref. A ref appearing in multiple matrix rows keeps only
        the strictest (max) margin, matching
        ``generate_domain_clearance_constraints``'s own per-pair margin
        selection.
    """
    nets_domain = _nets_domain_map(placement, voltage_domains)
    worst: dict[str, IntraFootprintDomainConflict] = {}

    for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items():
        if domain_a == domain_b:
            continue  # a same-domain row can't be "straddled" by definition
        margin = required_margin_mm(requirements)
        group_a = _components_in_domain(placement, domain_a, nets_domain)
        group_b_refs = {
            c.get("ref") for c in _components_in_domain(placement, domain_b, nets_domain)
        }
        for comp in group_a:
            ref = comp.get("ref")
            if not isinstance(ref, str) or ref not in group_b_refs:
                continue
            if component_refs is not None and ref not in component_refs:
                continue
            prior = worst.get(ref)
            if prior is None or margin > prior.margin_mm:
                worst[ref] = IntraFootprintDomainConflict(
                    ref=ref,
                    domain_a=domain_a,
                    domain_b=domain_b,
                    margin_mm=margin,
                    reason=(
                        f"{ref} carries a net classified {domain_a.value} and a net "
                        f"classified {domain_b.value} on the same footprint -- "
                        f"IEC 60335-2-6 {domain_a.value}<->{domain_b.value} "
                        f"({insulation_type.value}) requires {margin}mm, which no "
                        f"placement can supply between two pads of one rigid part."
                    ),
                )

    return sorted(worst.values(), key=lambda c: c.ref)


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
    centers and compares against ``constraint.min_distance_mm``. Note this
    is a cheaper, weaker check than what ``clearance.py``'s validator
    actually measures (copper-to-copper on exact pad geometry, per the
    module docstring's corrected soundness proof) — center distance ≥
    margin is *implied by* the box's full copper-to-copper guarantee, not
    identical to it, so this audit catches encoder/units bugs cheaply but
    is not a substitute for re-running the validator itself after a solve.
    Any mismatch here means the encoding's own soundness proof (module
    docstring) failed to hold for this solve (e.g. a bug in the handler, a
    units error, a component dropped from the model) and is returned for
    the caller to hard-fail on.

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
