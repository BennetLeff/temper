"""Classifier-wrapping gates for the default PlaceRouteLoop registry.

U2: ``DrcGate`` (PLACEMENT) and ``RoutingGate`` (ROUTING) compose the
existing ``FeedbackClassifier``, adapting its ``ClassificationResult``
into the three-state ``GateResult`` + ``Violation`` contract types
defined in ``gates.py``.

These are the *classifier-wrapping* gates — distinct from the truth-gate
implementations (e.g. ``gates.RoutingGate``, ``gates.DrcGate``) that
run kicad-cli and other measurement tools directly. The default loop
registry uses the classifier-wrapping gates here; the truth gates are
registered by U6 when ``--all-gates`` is requested.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.feedback import (
        ClassificationResult,
        ConstraintDelta,
        FeedbackClassifier,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DrcGate — PLACEMENT-stage DRC via run_drc
# ---------------------------------------------------------------------------


class DrcGate(Gate):
    """PLACEMENT-stage gate: runs DRC via ``run_drc`` on the routed PCB.

    Composes the ``AcceptanceGate.truth_gate`` pattern: calls ``run_drc``
    on ``state.routed_pcb_path`` (or a freshly written placement PCB) and
    adapts ``DrcResult`` errors into ``Violation(type=CLEARANCE, ...)``.
    ``UNMEASURED`` is returned when kicad-cli fails or the PCB path is
    missing — never a false ``CLEAN``.
    """

    stage = GateStage.PLACEMENT
    name = "drc"

    def __init__(self, classifier: FeedbackClassifier | None = None):
        self._classifier = classifier

    def check(self, state: BoardState) -> GateResult:  # noqa: C901
        pcb_path = state.routed_pcb_path
        if pcb_path is None or not pcb_path.exists():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No routed PCB available for DRC gate",
            )

        try:
            from temper_placer.validation.drc_runner import DrcRunnerError, run_drc
        except ImportError as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"drc_runner import failed: {exc}",
            )

        try:
            drc_result = run_drc(pcb_path)
        except (DrcRunnerError, FileNotFoundError, Exception) as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"DRC run failed: {exc}",
            )

        violations: list[Violation] = []
        for err in drc_result.errors:
            violations.append(
                Violation(
                    type=ViolationType.CLEARANCE,
                    components=tuple(err.components) if err.components else (),
                    severity=1.0,
                    threshold=0.0,
                    description=err.message,
                    context={
                        "rule": err.rule,
                        "location": err.location,
                    },
                )
            )

        if violations:
            return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
        return GateResult(GateStatus.CLEAN)

    def to_delta(self, violation: Violation) -> ConstraintDelta | None:
        from temper_placer.placer.cp_sat.feedback import ConstraintDelta

        if violation.type is not ViolationType.CLEARANCE:
            return None

        comps = violation.components
        if len(comps) < 2:
            return None

        try:
            from temper_placer.pcl.constraints import (
                ConstraintTier,
                SeparatedConstraint,
            )
        except ImportError:
            return None

        a, b = comps[0], comps[1]
        constraint = SeparatedConstraint(
            a=a,
            b=b,
            min_distance_mm=6.0,
            tier=ConstraintTier.HARD,
            because=f"DRC gate: {violation.description}",
            id=f"drc_gate_{a}_{b}",
        )
        return ConstraintDelta(
            constraint=constraint,
            reason=f"DRC clearance: {a}–{b}",
            priority=5,
        )


# ---------------------------------------------------------------------------
# RoutingGate — ROUTING-stage classifier wrapper
# ---------------------------------------------------------------------------


class RoutingGate(Gate):
    """ROUTING-stage gate: wraps ``FeedbackClassifier.classify()``.

    Delegates to the existing classifier's ``classify`` method and adapts
    the ``ClassificationResult`` into ``GateResult`` + ``Violation``.

    The classifier's DRC/unrouted/congestion logic is preserved verbatim
    (the "wraps, not replaces" decision).  ``to_delta`` maps each
    violation back to a ``ConstraintDelta`` using the same constraint
    types the classifier already produces.
    """

    stage = GateStage.ROUTING
    name = "routing"

    def __init__(self, classifier: FeedbackClassifier | None = None):
        if classifier is None:
            from temper_placer.placer.cp_sat.feedback import FeedbackClassifier

            classifier = FeedbackClassifier()
        self._classifier: FeedbackClassifier = classifier
        self._last_classification: ClassificationResult | None = None

    def check(self, state: BoardState) -> GateResult:  # noqa: C901
        if state.routing is None:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No routing data in BoardState",
            )

        routing = state.routing
        placement = state.placement

        completion_rate = getattr(routing, "completion_rate", 0.0)
        drc_violations = getattr(routing, "drc_violations", []) or []
        unrouted = getattr(routing, "unrouted_nets", []) or []

        # Fast-path: fully clean routing
        if completion_rate >= 1.0 and not drc_violations and not unrouted:
            return GateResult(GateStatus.CLEAN)

        classification = self._classifier.classify(
            routing_result=routing,
            placement=placement,
            round_number=0,
            previous_unclassified=[],
        )
        self._last_classification = classification

        violations: list[Violation] = []

        # Adapt classifier deltas into Violations
        for delta in classification.deltas:
            reason = delta.reason
            constraint = delta.constraint
            constraint_type = type(constraint).__name__

            if "Clearance" in constraint_type or "Separated" in constraint_type:
                a = getattr(constraint, "a", "")
                b = getattr(constraint, "b", "")
                violations.append(
                    Violation(
                        type=ViolationType.CLEARANCE,
                        components=(a, b) if a and b else (),
                        severity=getattr(constraint, "min_distance_mm", 0.0),
                        description=reason,
                        context={"constraint_type": constraint_type},
                    )
                )
            elif "Anchored" in constraint_type:
                comp = getattr(constraint, "component", "")
                region = getattr(constraint, "region", ())
                violations.append(
                    Violation(
                        type=ViolationType.UNROUTED,
                        components=(comp,) if comp else (),
                        description=reason,
                        context={"constraint_type": constraint_type, "region": region},
                    )
                )
            elif "Keepout" in constraint_type:
                zone = getattr(constraint, "zone_name", "")
                violations.append(
                    Violation(
                        type=ViolationType.SLOP,
                        nets=(zone,) if zone else (),
                        description=reason,
                        context={"constraint_type": constraint_type},
                    )
                )

        # Unclassified failures → UNROUTED violations
        for uf in classification.unclassified:
            violations.append(
                Violation(
                    type=ViolationType.UNROUTED,
                    nets=tuple(uf.nets) if uf.nets else (),
                    components=tuple(uf.components) if uf.components else (),
                    description=uf.description,
                )
            )

        if violations:
            return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
        return GateResult(GateStatus.CLEAN)

    def to_delta(self, violation: Violation) -> ConstraintDelta | None:
        from temper_placer.placer.cp_sat.feedback import ConstraintDelta

        if violation.type is ViolationType.CLEARANCE:
            comps = violation.components
            if len(comps) < 2:
                return None
            try:
                from temper_placer.pcl.constraints import (
                    ConstraintTier,
                    SeparatedConstraint,
                )
            except ImportError:
                return None

            a, b = comps[0], comps[1]
            constraint = SeparatedConstraint(
                a=a,
                b=b,
                min_distance_mm=max(violation.severity, 6.0),
                tier=ConstraintTier.HARD,
                because=violation.description,
                id=f"routing_gate_clearance_{a}_{b}",
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=violation.description,
                priority=5,
            )

        if violation.type is ViolationType.UNROUTED:
            comps = violation.components
            if not comps:
                return None
            comp_ref = comps[0]
            try:
                from temper_placer.pcl.constraints import (
                    AnchoredConstraint,
                    ConstraintTier,
                )
            except ImportError:
                return None

            region = violation.context.get("region", (45.0, 45.0, 55.0, 55.0))
            constraint = AnchoredConstraint(
                component=comp_ref,
                region=tuple(region) if region else (45.0, 45.0, 55.0, 55.0),
                tier=ConstraintTier.STRONG,
                because=violation.description,
                id=f"routing_gate_unrouted_{comp_ref}",
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=violation.description,
                priority=15,
            )

        return None
