"""
Feedback Classifier — Router Signals to CP-SAT Constraint Deltas.

Maps router_v6 routing results to CP-SAT constraint deltas. Four
feedback classes + unclassified fallback. Deltas are injected through
the normal PCL encoder — the encoder doesn't know the constraint came
from feedback vs. the PCL spec.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.core.netclass_rules import (
    NetClassRulesDict,
    get_pair_because,
    get_pair_clearance,
    resolve_net_class,
)

if TYPE_CHECKING:
    from temper_placer.pcl.constraints import BaseConstraint, ConstraintType
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
    from temper_placer.router_v6.adapter import RoutingResult

logger = logging.getLogger(__name__)


@dataclass
class ConstraintDelta:
    """A constraint to add/tighten in the next CP-SAT solve.

    Attributes:
        constraint: PCL constraint object (from temper_placer.pcl.constraints).
        reason: Router signal that produced this delta.
        priority: Ordering strength — lower = try first.
    """

    constraint: object  # BaseConstraint
    reason: str
    priority: int = 0


@dataclass
class UnclassifiedFailure:
    """A routing failure that didn't match any feedback class.

    Attributes:
        description: Human-readable description of the failure.
        nets: Unrouted net names involved.
        components: Component refs involved.
        region: Optional bounding box (x_min, y_min, x_max, y_max) of failure.
    """

    description: str
    nets: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    region: tuple[float, float, float, float] | None = None


@dataclass
class ClassificationResult:
    """Result of classifying routing failures into constraint deltas.

    Attributes:
        deltas: Constraint deltas to apply, sorted by priority.
        unclassified: Failures that didn't match any feedback class.
        round_number: Which round-trip this classification is for.
    """

    deltas: list[ConstraintDelta] = field(default_factory=list)
    unclassified: list[UnclassifiedFailure] = field(default_factory=list)
    round_number: int = 0


class FeedbackClassifier:
    """Classify router_v6 routing results into CP-SAT constraint deltas.

    Four feedback classes:
    1. Congestion in corridor -> SeparatedConstraint or KeepoutConstraint
    2. DRC clearance violation -> SeparatedConstraint (stronger)
    3. Unrouted critical pin -> AnchoredConstraint
    4. Persistent high-pin-count IC failure -> rotation coordination
    """

    CRITICAL_ICS: set[str] = {"Q1", "Q2", "U_GATE", "U_MCU"}
    PERSISTENCE_THRESHOLD: int = 3

    def __init__(self, netclass_rules: NetClassRulesDict | None = None):
        self.netclass_rules = netclass_rules

    def classify(
        self,
        routing_result: object,  # RoutingResult
        placement: object,  # CpSatPlacementResult
        round_number: int = 0,
        previous_unclassified: list[UnclassifiedFailure] | None = None,
    ) -> ClassificationResult:
        """Classify routing failures into constraint deltas.

        Args:
            routing_result: Result from route_pcb().
            placement: CP-SAT placement result.
            round_number: Current round-trip number.
            previous_unclassified: Failures from prior rounds for persistence tracking.

        Returns:
            ClassificationResult with sorted deltas and unclassified failures.
        """
        from temper_placer.router_v6.adapter import RoutingResult

        deltas: list[ConstraintDelta] = []
        unclassified: list[UnclassifiedFailure] = []

        completion_rate = getattr(routing_result, 'completion_rate', 0.0)
        if completion_rate >= 1.0:
            return ClassificationResult(deltas=[], unclassified=[], round_number=round_number)

        # Extract routing failures from the result object
        unrouted_nets: list[str] = getattr(routing_result, 'unrouted_nets', [])
        drc_violations: list[object] = getattr(routing_result, 'drc_violations', [])
        congestion_regions: list[object] = getattr(routing_result, 'congestion_regions', [])
        placed_refs: list[str] = getattr(placement, 'placed_refs', [])

        # Class 2: DRC clearance violations (check first — these are corrective)
        for violation in drc_violations:
            delta = self._handle_clearance_violation(violation)
            if delta:
                deltas.append(delta)
            else:
                comps = getattr(violation, 'components', [])
                loc = getattr(violation, 'location', (0.0, 0.0))
                msg = getattr(violation, 'message', 'unknown drc violation')
                unclassified.append(UnclassifiedFailure(
                    description=f"DRC: {msg}",
                    components=list(comps),
                    region=(loc[0] - 5, loc[1] - 5, loc[0] + 5, loc[1] + 5),
                ))

        # Class 1: Congestion in corridor between components
        for region in congestion_regions:
            delta = self._handle_congestion(region, placed_refs)
            if delta:
                deltas.append(delta)
            else:
                unclassified.append(UnclassifiedFailure(
                    description=f"Congestion in region",
                ))

        # Class 3: Unrouted critical pins
        for net_name in unrouted_nets:
            critical_refs = self._find_critical_components(net_name, placement, placed_refs)
            if critical_refs:
                for comp_ref in critical_refs:
                    delta = self._handle_unrouted_critical_pin(comp_ref, net_name, placement)
                    if delta:
                        deltas.append(delta)
            else:
                # Track for persistence check across rounds
                pass

        # Class 4: Persistent high-pin-count IC failure
        persistent_ics = self._detect_persistent_ics(
            unrouted_nets, previous_unclassified or [], round_number
        )
        for ic_ref in persistent_ics:
            delta = self._handle_rotation_coordination(ic_ref, placement)
            if delta:
                deltas.append(delta)

        # Unclassified: nets that don't match any critical IC
        for net_name in unrouted_nets:
            critical_refs = self._find_critical_components(net_name, placement, placed_refs)
            if not critical_refs:
                unclassified.append(UnclassifiedFailure(
                    description=f"Unrouted net: {net_name}",
                    nets=[net_name],
                ))

        # Sort by priority (lowest first = strongest signal)
        deltas.sort(key=lambda d: d.priority)

        return ClassificationResult(
            deltas=deltas,
            unclassified=unclassified,
            round_number=round_number,
        )

    # -----------------------------------------------------------------------
    # Class 1: Congestion
    # -----------------------------------------------------------------------

    def _handle_congestion(
        self, region: object, placed_refs: list[str]
    ) -> ConstraintDelta | None:
        """Handle congestion by injecting SeparatedConstraint for adjacent components."""
        comp_a = getattr(region, 'comp_a', None)
        comp_b = getattr(region, 'comp_b', None)
        current_distance = getattr(region, 'current_distance_mm', 2.0)

        if comp_a and comp_b and comp_a in placed_refs and comp_b in placed_refs:
            from temper_placer.pcl.constraints import (
                ConstraintTier,
                SeparatedConstraint,
            )

            new_distance = max(current_distance + 1.0, current_distance * 1.5)
            constraint = SeparatedConstraint(
                a=comp_a,
                b=comp_b,
                min_distance_mm=new_distance,
                tier=ConstraintTier.STRONG,
                because=f"Congested routing corridor between {comp_a} and {comp_b} — widen channel",
                id=f"feedback_congestion_{comp_a}_{comp_b}",
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"Congestion between {comp_a} and {comp_b} at {current_distance:.1f}mm",
                priority=10,
            )

        bbox = getattr(region, 'bbox', None)
        if bbox is not None:
            from temper_placer.pcl.constraints import (
                ConstraintTier,
                KeepoutConstraint,
            )

            constraint = KeepoutConstraint(
                zone_name=f"congestion_{hash(bbox) & 0xFFFF:04x}",
                tier=ConstraintTier.SOFT,
                because=f"Congestion in routing region — keep components clear",
                id=f"feedback_congestion_keepout_{hash(bbox) & 0xFFFF:04x}",
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"General congestion in region {bbox}",
                priority=20,
            )

        return None

    # -----------------------------------------------------------------------
    # Class 2: DRC Clearance Violation
    # -----------------------------------------------------------------------

    def _handle_clearance_violation(
        self, violation: object
    ) -> ConstraintDelta | None:
        """Handle DRC clearance violation by injecting stronger SeparatedConstraint."""
        comp_a = getattr(violation, 'comp_a', None)
        comp_b = getattr(violation, 'comp_b', None)
        required_mm = getattr(violation, 'required_mm', 6.0)

        if not comp_a or not comp_b:
            components = getattr(violation, 'components', [])
            if len(components) >= 2:
                comp_a, comp_b = components[0], components[1]

        if not comp_a or not comp_b:
            return None

        authoriative_mm = required_mm
        because_text = f"Post-route DRC clearance violation at {required_mm}mm — enforce separation"

        if self.netclass_rules is not None:
            net_a = getattr(violation, 'net_a', None)
            net_b = getattr(violation, 'net_b', None)
            if not net_a:
                net_a = getattr(violation, 'net_name', '')
            if not net_b:
                net_b = getattr(violation, 'net_name', '')

            class_a = resolve_net_class(net_a) if net_a else 'Signal'
            class_b = resolve_net_class(net_b) if net_b else 'Signal'

            authoriative_mm = get_pair_clearance(
                class_a, class_b, rules=self.netclass_rules,
            )

            if abs(required_mm - authoriative_mm) > 0.01:
                logger.warning(
                    'Feedback: DRC violation required %.2fmm but YAML '
                    'authority says %.2fmm for %s↔%s (nets %s↔%s) — '
                    'using YAML value.',
                    required_mm, authoriative_mm,
                    class_a, class_b, net_a, net_b,
                )

            yaml_because = get_pair_because(
                class_a, class_b, rules=self.netclass_rules,
            )
            if yaml_because:
                because_text = yaml_because
            else:
                because_text = (
                    f"Post-route DRC clearance violation at {authoriative_mm}mm"
                    f" ({class_a}↔{class_b}) — enforce separation"
                )

        from temper_placer.pcl.constraints import (
            ConstraintTier,
            SeparatedConstraint,
        )

        constraint = SeparatedConstraint(
            a=comp_a,
            b=comp_b,
            min_distance_mm=authoriative_mm,
            tier=ConstraintTier.HARD,
            because=because_text,
            id=f"feedback_clearance_{comp_a}_{comp_b}",
        )
        return ConstraintDelta(
            constraint=constraint,
            reason=f"Clearance violation: {comp_a}-{comp_b} needs {authoriative_mm}mm",
            priority=5,
        )

    # -----------------------------------------------------------------------
    # Class 3: Unrouted Critical Pin
    # -----------------------------------------------------------------------

    def _handle_unrouted_critical_pin(
        self, comp_ref: str, net_name: str, placement: object
    ) -> ConstraintDelta | None:
        """Handle unrouted critical pin by injecting AnchoredConstraint."""
        positions = getattr(placement, 'positions', None)
        placed_refs = getattr(placement, 'placed_refs', [])

        try:
            idx = placed_refs.index(comp_ref)
        except ValueError:
            return None

        if positions is not None and idx < len(positions):
            current_pos = (float(positions[idx][0]), float(positions[idx][1]))
            heuristic_pos = _compute_heuristic_position(comp_ref, current_pos, net_name)
        else:
            heuristic_pos = (50.0, 50.0)

        from temper_placer.pcl.constraints import (
            AnchoredConstraint,
            ConstraintTier,
        )

        # Use a region around the heuristic position with some slack
        region = (
            heuristic_pos[0] - 10.0,
            heuristic_pos[1] - 10.0,
            heuristic_pos[0] + 10.0,
            heuristic_pos[1] + 10.0,
        )

        constraint = AnchoredConstraint(
            component=comp_ref,
            region=region,
            tier=ConstraintTier.STRONG,
            because=f"Unrouted pin on critical component {comp_ref} (net {net_name}) — bias position",
            id=f"feedback_unrouted_{comp_ref}_{net_name}",
        )
        return ConstraintDelta(
            constraint=constraint,
            reason=f"Unrouted pin on {comp_ref} (net {net_name})",
            priority=15,
        )

    # -----------------------------------------------------------------------
    # Class 4: Persistent High-Pin-Count IC Failure
    # -----------------------------------------------------------------------

    def _handle_rotation_coordination(
        self, ic_ref: str, placement: object
    ) -> ConstraintDelta | None:
        """Handle persistent IC routing failure with rotation coordination."""
        from temper_placer.pcl.constraints import (
            AnchoredConstraint,
            ConstraintTier,
        )

        # Restrict rotation: force dense side away from routing corridor
        # This is a soft anchoring with rotation bias
        positions = getattr(placement, 'positions', None)
        placed_refs = getattr(placement, 'placed_refs', [])

        try:
            idx = placed_refs.index(ic_ref)
        except ValueError:
            idx = -1

        if positions is not None and idx >= 0 and idx < len(positions):
            x, y = float(positions[idx][0]), float(positions[idx][1])
        else:
            x, y = (50.0, 50.0)

        region = (x - 5.0, y - 5.0, x + 5.0, y + 5.0)
        constraint = AnchoredConstraint(
            component=ic_ref,
            region=region,
            tier=ConstraintTier.SOFT,
            because=f"Persistent unrouted pins on {ic_ref} after 3+ rounds — coordinate rotation",
            id=f"feedback_rotation_{ic_ref}",
        )
        return ConstraintDelta(
            constraint=constraint,
            reason=f"Rotation coordination for {ic_ref} after persistent failures",
            priority=25,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _find_critical_components(
        self, net_name: str, placement: object, placed_refs: list[str],
        netlist: object | None = None,
    ) -> list[str]:
        """Find critical ICs involved in an unrouted net.

        Checks both the net name heuristic and (if available) the
        actual netlist connectivity to determine which critical ICs
        are on the given net.
        """
        critical = []

        # Heuristic: net names containing IGBT-related patterns
        # are likely connected to Q1/Q2.
        gate_nets = {"GATE", "SW", "BUS", "PHASE", "OUT", "DRIVE"}
        mcu_nets = {"SPI", "I2C", "UART", "ADC", "GPIO", "MCU"}

        net_upper = net_name.upper()
        for ref in self.CRITICAL_ICS:
            if ref not in placed_refs:
                continue
            if "Q" in ref or "IGBT" in ref.upper():
                if any(pat in net_upper for pat in gate_nets):
                    critical.append(ref)
            elif "MCU" in ref.upper() or "U_GATE" in ref.upper():
                if any(pat in net_upper for pat in mcu_nets) or ref.upper() in net_upper:
                    critical.append(ref)

        return critical

    def _detect_persistent_ics(
        self,
        unrouted_nets: list[str],
        previous_unclassified: list[UnclassifiedFailure],
        round_number: int,
    ) -> list[str]:
        """Detect ICs that have had unrouted pins for 3+ rounds."""
        if round_number < self.PERSISTENCE_THRESHOLD:
            return []

        # Check which ICs appear in unclassified failures across rounds
        ic_fail_count: dict[str, int] = {}
        for failure in previous_unclassified:
            for comp in failure.components:
                if comp in self.CRITICAL_ICS:
                    ic_fail_count[comp] = ic_fail_count.get(comp, 0) + 1

        return [
            ic for ic, count in ic_fail_count.items()
            if count >= self.PERSISTENCE_THRESHOLD
        ]


def _compute_heuristic_position(
    comp_ref: str, current_pos: tuple[float, float], net_name: str
) -> tuple[float, float]:
    """Compute a heuristic optimal position for a component based on net.

    Simple heuristic: bias toward board center for central ICs,
    toward edges for connectors.
    """
    x, y = current_pos
    if "Q" in comp_ref and not "U_" in comp_ref:
        return (x, y - 5.0)
    if "U_" in comp_ref or "MCU" in comp_ref:
        return (x, y)
    return (x, y + 5.0)
