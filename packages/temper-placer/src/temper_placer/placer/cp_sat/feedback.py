"""
Feedback Classifier — Router Signals to CP-SAT Constraint Deltas.

Maps router_v6 routing results to CP-SAT constraint deltas. Four
feedback classes + unclassified fallback. Deltas are injected through
the normal PCL encoder — the encoder doesn't know the constraint came
from feedback vs. the PCL spec.

This module is a delegation shim. The ``FeedbackClassifier.classify()``
feedback-DECISION sequencing (the delta-mapping dispatch and the convergence
feedback) moved to ``temper-orchestration``'s ``feedback.rs`` (Rust
Orchestration Engine plan 2026-08-09-001, orchestration-port unit U-I) as
``classify_feedback``. What stays Python (the U-I boundary): the four
``_handle_*`` constraint-building handlers (they construct the PCL
``SeparatedConstraint`` / ``KeepoutConstraint`` / ``AnchoredConstraint``
objects and do the design-rules marshalling), and the ``ConstraintDelta`` /
``UnclassifiedFailure`` / ``ClassificationResult`` data carriers. The public
API is unchanged. The pre-migration module is pinned VERBATIM as
``tests/placer/cp_sat/_feedback_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json``); bit-identical parity is pinned by
``tests/placer/cp_sat/test_feedback_rust_differential.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules

import temper_orchestration as _orch

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

    def __init__(self, design_rules: DesignRules | None = None):
        self.design_rules = design_rules

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

        # The classification DECISION sequencing (routing-field extraction,
        # the clean early-return, the four-class dispatch in oracle order, the
        # unclassified collection and the priority sort) is delegated to
        # `classify_feedback` (temper-orchestration, unit U-I). Congestion
        # handling is Rust-owned; the method below remains a compatibility
        # adapter for direct callers and custom classifier subclasses. The
        # other constraint-building handlers stay Python object seams.
        return _orch.classify_feedback(
            self,
            routing_result,
            placement,
            round_number,
            previous_unclassified,
        )

    # -----------------------------------------------------------------------
    # Class 1: Congestion
    # -----------------------------------------------------------------------

    def _handle_congestion(self, region: object, placed_refs: list[str]) -> ConstraintDelta | None:
        """Compatibility adapter for the Rust-owned congestion handler."""
        return _orch.handle_congestion(region, placed_refs)

    # -----------------------------------------------------------------------
    # Class 2: DRC Clearance Violation
    # -----------------------------------------------------------------------

    def _handle_clearance_violation(self, violation: object) -> ConstraintDelta | None:
        """Handle DRC clearance violation by injecting stronger SeparatedConstraint."""
        comp_a = getattr(violation, "comp_a", None)
        comp_b = getattr(violation, "comp_b", None)
        required_mm = getattr(violation, "required_mm", 6.0)

        if not comp_a or not comp_b:
            components = getattr(violation, "components", [])
            if len(components) >= 2:
                comp_a, comp_b = components[0], components[1]

        if not comp_a or not comp_b:
            return None

        authoriative_mm = required_mm
        because_text = f"Post-route DRC clearance violation at {required_mm}mm — enforce separation"

        if self.design_rules is not None:
            net_a = getattr(violation, "net_a", None)
            net_b = getattr(violation, "net_b", None)
            if net_a and net_b:
                # CLASSIFIER FIXED 2026-08-19
                # (docs/evidence/2026-08-19-is-hv-net-blast-radius.md).
                # This used to classify by net NAME through
                # `core.net_classification.classify_net_type()` and then map
                # the four generic buckets onto class names:
                #
                #     _map = {"ground": "GND", "power": "Power",
                #             "hv": "HighVoltage", "signal": "Signal"}
                #     class_a = _map.get(classify_net_type(net_a), "Signal")
                #     rules_a = design_rules.get_rules_for_net("", net_class=class_a)
                #
                # `classify_net_type` is a keyword/word-boundary match over
                # `HV_NET_PATTERNS = {"AC_L","AC_N","PE","DC_BUS+","DC_BUS-",
                # "SW_NODE"}`, none of which is how this board spells its
                # HV nets. MEASURED (this repo's own `.venv`, freshly built
                # pyo3 extensions), old behaviour vs. the authoritative
                # `TEMPER_NET_ASSIGNMENTS`-backed answer:
                #
                #   net               classify_net_type -> clearance | authoritative
                #   +170V_BUS         signal -> Signal    0.15mm     | HighVoltage      2.0mm
                #   DC_BUS_RTN        signal -> Signal    0.15mm     | HighVoltage      2.0mm
                #   tank-out          signal -> Signal    0.15mm     | HighVoltage      2.0mm
                #   tank.c_tank1-p2   signal -> Signal    0.15mm     | HighVoltageTank  2.0mm
                #   hb-gnd            ground -> GND       0.30mm     | HighVoltage      2.0mm
                #   ac_l / ac_n       hv     -> HighVoltage 2.0mm    | ACMains          6.0mm
                #
                # i.e. the rectified 170V DC bus and the resonant tank were
                # being remediated at the 0.15mm unclassified-signal figure,
                # and the mains conductors themselves at 2.0mm instead of
                # 6.0mm, every time this feedback path injected a separation
                # constraint in response to a DRC clearance violation.
                # ("Signal" is not a declared net class at all -- it falls
                # through `get_rules_for_net`'s cascade to the LV default.)
                #
                # The fix is the SAME one PR #1323 applied to
                # `netclass_constraints.py` for the identical defect: ask
                # `design_rules.get_rules_for_net(net_name)` -- the
                # manifest/kicad_pro-backed `TEMPER_NET_ASSIGNMENTS`
                # classifier every other `DesignRules` consumer already
                # uses -- and take the class name it resolves to. No new
                # mechanism, no new figure, and no clearance value is
                # written here: `authoriative_mm` still comes entirely from
                # the resolved classes' own `clearance` / `class_pairs`.
                #
                # The `"Default" -> "Signal"` normalization below is NOT
                # cosmetic and is copied deliberately from
                # `netclass_constraints._pin_class_infos`, which PR #1323
                # added for this exact reason: `netclass_rules.yaml`'s
                # `class_pairs` table spells the generic-LV bucket
                # "Signal" (`HighVoltage-Signal: 6.0mm`,
                # `ACMains-Signal: 6.0mm`, ...) while `get_rules_for_net`
                # returns "Default" for a net with no assignment. Leaving
                # it as "Default" makes every `class_pairs` row miss and
                # drops an HV<->LV pair from that table's 6.0mm to
                # `max(HighVoltage.clearance, Default.clearance)` = 2.0mm.
                # MEASURED here before the normalization was added: `AC_L`
                # vs `SPI_CLK` fell from 6.0mm to 2.0mm. That is a
                # loosening and must not be introduced by a fix whose whole
                # point is that the old classifier was too loose.
                rules_a = self.design_rules.get_rules_for_net(net_a)
                rules_b = self.design_rules.get_rules_for_net(net_b)
                class_a = "Signal" if rules_a.name == "Default" else rules_a.name
                class_b = "Signal" if rules_b.name == "Default" else rules_b.name
                authoriative_mm = max(rules_a.clearance, rules_b.clearance)
                because_text = (
                    f"Post-route DRC clearance violation at {required_mm}mm between "
                    f"net {net_a} ({class_a}) and net {net_b} ({class_b}) — enforce "
                    f"the stricter of the two net classes' own clearance"
                )
                cp_key = tuple(sorted([class_a, class_b]))
                if (
                    hasattr(self.design_rules, "class_pairs")
                    and cp_key in self.design_rules.class_pairs
                ):
                    authoriative_mm = self.design_rules.class_pairs[cp_key].get(
                        "clearance", authoriative_mm
                    )
                    # CRASH FIXED 2026-08-19, same evidence doc. Both of the
                    # `because` assignments this branch used to make could
                    # produce the empty string -- `.get("because", "")` when a
                    # class_pairs entry carries no rationale, and a bare
                    # `else: because_text = ""` for every class pair with no
                    # entry at all -- and `SeparatedConstraint` rejects a
                    # rationale under 10 characters. Confirmed PRE-EXISTING on
                    # pristine origin/main (eb5022510): every one of
                    # `+170V_BUS`x`WDT_KICK`, `AC_L`x`WDT_KICK`,
                    # `WDT_KICK`x`BTN_UP` and `SW_NODE`x`GND` raised
                    # `ValueError: Rationale 'because' must be >=10 chars` from
                    # this method, i.e. the whole net-aware branch was unusable
                    # for any pair outside `class_pairs`. It went unnoticed
                    # because no test ever gave a violation object `net_a`/
                    # `net_b` attributes, so the branch was never entered (the
                    # mocks in `test_feedback.py` and
                    # `test_feedback_rust_differential.py` still do not, which
                    # is why the pinned differential oracle is unaffected by
                    # this change). The default rationale computed above is now
                    # kept whenever `class_pairs` has nothing better to say,
                    # rather than being blanked.
                    cp_because = self.design_rules.class_pairs[cp_key].get("because", "")
                    if cp_because:
                        because_text = cp_because

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
        positions = getattr(placement, "positions", None)
        placed_refs = list(
            getattr(placement, "placed_refs", [])
            or (positions.keys() if isinstance(positions, dict) else [])
        )

        try:
            idx = placed_refs.index(comp_ref)
        except ValueError:
            return None

        if isinstance(positions, dict) and comp_ref in positions:
            current_pos = tuple(map(float, positions[comp_ref]))
            heuristic_pos = _orch.compute_heuristic_position(comp_ref, current_pos, net_name)
        elif positions is not None and idx < len(positions):
            current_pos = (float(positions[idx][0]), float(positions[idx][1]))
            heuristic_pos = _orch.compute_heuristic_position(comp_ref, current_pos, net_name)
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
        positions = getattr(placement, "positions", None)
        placed_refs = list(
            getattr(placement, "placed_refs", [])
            or (positions.keys() if isinstance(positions, dict) else [])
        )

        try:
            idx = placed_refs.index(ic_ref)
        except ValueError:
            idx = -1

        if isinstance(positions, dict) and ic_ref in positions:
            x, y = map(float, positions[ic_ref])
        elif positions is not None and idx >= 0 and idx < len(positions):
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
        self,
        net_name: str,
        _placement: object,
        placed_refs: list[str],
        _netlist: object | None = None,
    ) -> list[str]:
        """Compatibility shim for the Rust-owned critical-net heuristic."""
        return _orch.find_critical_components(
            net_name, _placement, placed_refs, _netlist, self.CRITICAL_ICS
        )

    def _detect_persistent_ics(
        self,
        _unrouted_nets: list[str],
        previous_unclassified: list[UnclassifiedFailure],
        round_number: int,
    ) -> list[str]:
        """Compatibility shim for the Rust-owned persistence counter."""
        return _orch.detect_persistent_ics(
            _unrouted_nets,
            previous_unclassified,
            round_number,
            self.CRITICAL_ICS,
            self.PERSISTENCE_THRESHOLD,
        )
