"""
Place→Route Loop Controller.

Orchestrates the round-trip: place → route → measure → classify → re-place.
Implements closed-loop automatic backtracking: on UNSAT from injected feedback,
try the next-strongest signal; if all fail, surface to operator.

Uses a two-phase solve: Phase 1 (feasibility, ≤1s re-solve target) runs every
round; Phase 2 (wirelength polish) runs after 2 consecutive stability rounds.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
    from temper_placer.placer.cp_sat.feedback import (
        ClassificationResult,
        ConstraintDelta,
        FeedbackClassifier,
        UnclassifiedFailure,
    )
    from temper_placer.router_v6.adapter import RoutingResult

logger = logging.getLogger(__name__)


class LoopExitReason(Enum):
    """Why the place-route loop terminated."""

    SUCCESS = "success"
    ROUND_LIMIT_EXCEEDED = "round_limit_exceeded"
    NO_CLASSIFIABLE_FEEDBACK = "no_classifiable_feedback"
    ALL_FEEDBACK_UNSAT = "all_feedback_unsat"
    OSCILLATION_DETECTED = "oscillation_detected"


@dataclass
class RoundRecord:
    """Record of a single round-trip through the loop."""

    round_number: int
    completion_rate: float = 0.0
    drc_errors: int = 0
    solve_time_ms: float = 0.0
    deltas_applied: list[ConstraintDelta] = field(default_factory=list)
    route_time_ms: float = 0.0
    status: str = "unknown"


@dataclass
class LoopResult:
    """Result of a full place-route loop execution.

    Attributes:
        success: Whether convergence was achieved.
        reason: Why the loop exited.
        placement: Final CP-SAT placement result.
        routing: Final routing result.
        rounds: Records of each round-trip.
        unsat_core: Structured diagnostic if all feedback was UNSAT.
    """

    success: bool = False
    reason: str = ""
    placement: object | None = None  # CpSatPlacementResult
    routing: object | None = None  # RoutingResult
    rounds: list[RoundRecord] = field(default_factory=list)
    unsat_core: dict[str, object] | None = None


class UnsatError(Exception):
    """Raised when a CP-SAT solve with injected deltas is UNSAT."""

    def __init__(self, deltas: list, message: str = "UNSAT with injected constraints"):
        self.deltas = deltas
        super().__init__(message)


class PlaceRouteLoop:
    """Orchestrates the place→route feedback loop.

    Attributes:
        MAX_ROUNDS: Maximum number of round-trips before giving up.
        STABILITY_ROUNDS: Consecutive stability rounds before Phase 2 polish.
        RE_SOLVE_TIMEOUT_MS: Target re-solve time for Phase 1.
        OSCILLATION_WINDOW: Rounds to check for oscillation detection.
    """

    MAX_ROUNDS: int = 10
    STABILITY_ROUNDS: int = 2
    RE_SOLVE_TIMEOUT_MS: int = 1000
    OSCILLATION_WINDOW: int = 3

    def __init__(self, classifier=None):
        if classifier is None:
            from temper_placer.placer.cp_sat.feedback import FeedbackClassifier
            classifier = FeedbackClassifier()
        self.classifier = classifier

    @staticmethod
    def _load_netclass_rules():
        import logging
        _logger = logging.getLogger(__name__)
        try:
            from temper_placer.core.netclass_rules import (
                get_default_rules_path,
                load_netclass_rules,
            )
            config_path = get_default_rules_path()
            if config_path.exists():
                return load_netclass_rules(config_path)
        except Exception:
            _logger.debug("netclass_rules.yaml not loaded", exc_info=True)
        return None

    def run(
        self,
        netlist: Netlist,
        board: Board,
        pcl_constraints: list | None = None,
        seed: int = 42,
        zones: dict | None = None,
        zone_components: dict[str, list[str]] | None = None,
        loop_components: dict[str, list[str]] | None = None,
    ) -> LoopResult:
        """Run the full place-route loop.

        Args:
            netlist: Component netlist.
            board: Board definition.
            pcl_constraints: Initial PCL constraints from config.
            seed: Random seed.
            zones: Optional pre-resolved zone bounds dict.
            zone_components: Optional zone-to-component mapping.
            loop_components: Optional loop-name-to-component mapping.

        Returns:
            LoopResult with success status, placement, and routing.
        """
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult, solve_placement

        self._zones = zones
        self._zone_components = zone_components
        self._loop_components = loop_components
        self._netclass_rules = self._load_netclass_rules()
        if self._netclass_rules is not None:
            self.classifier.netclass_rules = self._netclass_rules

        injected_deltas: list[ConstraintDelta] = []
        rounds: list[RoundRecord] = []
        previous_unclassified: list[UnclassifiedFailure] = []
        placement_history: list[CpSatPlacementResult] = []

        # Combine initial PCL with injected deltas
        all_constraints = list(pcl_constraints) if pcl_constraints else []

        placement: CpSatPlacementResult | None = None
        routing: RoutingResult | None = None

        for round_num in range(1, self.MAX_ROUNDS + 1):
            logger.info(f"Round {round_num}/{self.MAX_ROUNDS}")

            # Deduplicate accumulated deltas by constraint ID before each
            # round to prevent UNSAT from stale overlapping feedback.
            injected_deltas = _deduplicate_deltas(injected_deltas)

            # Phase 1: Solve CP-SAT with current constraints
            t0 = time.monotonic()
            constraint_objects = all_constraints + [
                delta.constraint for delta in injected_deltas
            ]
            placement = solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=constraint_objects,
                timeout_ms=self.RE_SOLVE_TIMEOUT_MS,
                seed=seed,
                zones=self._zones,
                zone_components=self._zone_components,
                loop_components=self._loop_components,
            )
            solve_time = (time.monotonic() - t0) * 1000.0

            if placement.status in ("infeasible", "model_invalid"):
                logger.warning(f"Placement UNSAT at round {round_num}")
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.ALL_FEEDBACK_UNSAT.value,
                    placement=placement,
                    rounds=rounds,
                    unsat_core={"round": round_num, "deltas": injected_deltas},
                )

            # Check for oscillation
            if self._detect_oscillation(placement, placement_history):
                logger.warning(f"Oscillation detected at round {round_num} — same placement repeats")
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.OSCILLATION_DETECTED.value,
                    placement=placement,
                    rounds=rounds,
                )
            placement_history.append(placement)

            # Route with router_v6
            t_route = time.monotonic()
            routing = self._route_placement(placement, netlist, board, seed)
            route_time = (time.monotonic() - t_route) * 1000.0

            completion_rate = getattr(routing, 'completion_rate', 0.0)
            drc_errors = routing.drc_errors if hasattr(routing, 'drc_errors') else 0
            logger.info(
                f"Round {round_num}: completion={completion_rate:.1%}, "
                f"DRC errors={drc_errors}, solve={solve_time:.0f}ms, route={route_time:.0f}ms"
            )

            rounds.append(RoundRecord(
                round_number=round_num,
                completion_rate=completion_rate,
                drc_errors=drc_errors,
                solve_time_ms=solve_time,
                deltas_applied=list(injected_deltas),
                route_time_ms=route_time,
                status=placement.status,
            ))

            # Check termination
            if completion_rate >= 1.0 and drc_errors == 0:
                stable = self._consecutive_stable_rounds(rounds) >= self.STABILITY_ROUNDS
                if stable:
                    placement = self._solve_phase2(placement, netlist, board, constraint_objects, seed)
                    return LoopResult(
                        success=True,
                        reason=LoopExitReason.SUCCESS.value,
                        placement=placement,
                        routing=routing,
                        rounds=rounds,
                    )
                else:
                    # Still going — continue with current deltas (stability check)
                    continue

            # Classify feedback
            classification = self.classifier.classify(
                routing_result=routing,
                placement=placement,
                round_number=round_num,
                previous_unclassified=previous_unclassified,
            )

            # Check for unclassifiable failures
            if not classification.deltas and classification.unclassified:
                # More than 50% unclassified after 3 rounds -> abort
                if round_num >= 3 and len(classification.unclassified) > len(classification.deltas):
                    return LoopResult(
                        success=False,
                        reason=LoopExitReason.NO_CLASSIFIABLE_FEEDBACK.value,
                        placement=placement,
                        routing=routing,
                        rounds=rounds,
                    )

            if not classification.deltas:
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.NO_CLASSIFIABLE_FEEDBACK.value,
                    placement=placement,
                    routing=routing,
                    rounds=rounds,
                )

            previous_unclassified = list(classification.unclassified)

            # Closed-loop backtracking: try deltas in priority order
            delta_accepted = False
            for delta in classification.deltas:
                try:
                    test_placement = self._solve_with_delta(
                        netlist, board, constraint_objects,
                        [delta], seed, placement,
                    )
                    injected_deltas.append(delta)
                    placement = test_placement
                    delta_accepted = True
                    logger.info(f"  Accepted delta: {delta.reason}")
                    break
                except UnsatError:
                    logger.info(f"  Delta UNSAT, trying next: {delta.reason}")
                    continue

            if not delta_accepted:
                # All deltas produced UNSAT
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.ALL_FEEDBACK_UNSAT.value,
                    placement=placement,
                    routing=routing,
                    rounds=rounds,
                    unsat_core=self._extract_unsat_core(injected_deltas, classification),
                )

        # N=10 rounds exhausted
        return LoopResult(
            success=False,
            reason=LoopExitReason.ROUND_LIMIT_EXCEEDED.value,
            placement=placement,
            routing=routing,
            rounds=rounds,
        )

    # -------------------------------------------------------------------
    # Routing
    # -------------------------------------------------------------------

    def _route_placement(
        self, placement, netlist, board, seed: int
    ) -> "RoutingResult":
        """Route a placement through router_v6."""
        import os
        import contextlib
        import tempfile

        from temper_placer.router_v6.adapter import RoutingResult, route_pcb

        placements_dict = placement.to_placements_dict()
        if not placements_dict:
            return RoutingResult(completion_rate=0.0)

        netclass_rules = getattr(self, '_netclass_rules', None)
        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_build_minimal_pcb(netlist, board, netclass_rules))
            parsed = type("ParsedPCB", (), {"source_path": temp_path})()
            return route_pcb(parsed, placements_dict, _seed=seed)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)

    # -------------------------------------------------------------------
    # Solve with delta
    # -------------------------------------------------------------------

    def _solve_with_delta(
        self, netlist, board, base_constraints: list,
        new_deltas: list[ConstraintDelta], seed: int,
        warm_start_placement=None,
    ):
        """Try solving with an additional delta. Raises UnsatError on failure."""
        from temper_placer.placer.cp_sat.encoder import solve_placement

        all_objects = list(base_constraints) + [
            delta.constraint for delta in new_deltas
        ]

        result = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=all_objects,
            timeout_ms=self.RE_SOLVE_TIMEOUT_MS,
            seed=seed,
            zones=self._zones,
            zone_components=self._zone_components,
            loop_components=self._loop_components,
        )

        if result.status in ("infeasible", "model_invalid"):
            raise UnsatError(
                deltas=new_deltas,
                message=f"UNSAT with delta(s): {[d.reason for d in new_deltas]}",
            )

        return result

    # -------------------------------------------------------------------
    # Phase 2: wirelength polish
    # -------------------------------------------------------------------

    def _solve_phase2(
        self, placement, netlist, board, constraint_objects: list, seed: int,
    ):
        """Run Phase 2 wirelength polish after stability.

        Phase 2 uses a longer timeout for better wirelength optimization
        but must not regress the completion rate below Phase 1's.
        """
        from temper_placer.placer.cp_sat.encoder import solve_placement

        result = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=constraint_objects,
            timeout_ms=5000,  # 5s for polish
            seed=seed,
            zones=self._zones,
            zone_components=self._zone_components,
            loop_components=self._loop_components,
        )

        if result.status in ("infeasible", "model_invalid"):
            # Don't regress — return Phase 1 placement
            logger.info("Phase 2 UNSAT — returning Phase 1 placement")
            return placement

        return result

    # -------------------------------------------------------------------
    # Stability and oscillation detection
    # -------------------------------------------------------------------

    def _consecutive_stable_rounds(self, rounds: list[RoundRecord]) -> int:
        """Count consecutive rounds with 100% completion and 0 DRC errors."""
        count = 0
        for record in reversed(rounds):
            if record.completion_rate >= 1.0 and record.drc_errors == 0:
                count += 1
            else:
                break
        return count

    def _detect_oscillation(
        self,
        placement,
        history: list,
    ) -> bool:
        """Detect if the placement is oscillating between two states."""
        if len(history) < self.OSCILLATION_WINDOW:
            return False

        positions = getattr(placement, 'positions', None)
        if positions is None:
            return False

        recent = history[-self.OSCILLATION_WINDOW:]
        recent_positions = [getattr(p, 'positions', None) for p in recent]

        import numpy as np
        for rp in recent_positions:
            if rp is None:
                return False
            if np.allclose(positions, rp, atol=0.1):
                return True

        return False

    # -------------------------------------------------------------------
    # UNSAT core extraction
    # -------------------------------------------------------------------

    def _extract_unsat_core(
        self, injected_deltas: list[ConstraintDelta],
        classification: ClassificationResult,
    ) -> dict[str, object]:
        """Extract structured diagnostic for all-feedback-UNSAT."""
        return {
            "message": "All feedback deltas produced UNSAT — constraint conflict",
            "attempted_deltas": [
                {"reason": d.reason, "type": type(d.constraint).__name__}
                for d in classification.deltas
            ],
            "active_injected": [
                {"reason": d.reason, "type": type(d.constraint).__name__}
                for d in injected_deltas
            ],
        }


def _deduplicate_deltas(deltas: list[ConstraintDelta]) -> list[ConstraintDelta]:
    """Deduplicate ConstraintDeltas by constraint ID, keeping latest.

    Prevents accumulated deltas from causing UNSAT when different
    rounds produce overlapping feedback for the same constraint.
    """
    seen: dict[str, ConstraintDelta] = {}
    for delta in deltas:
        cid = getattr(delta.constraint, 'id', str(id(delta)))
        seen[cid] = delta
    return list(seen.values())


def _build_minimal_pcb(netlist, board, netclass_rules=None) -> str:
    """Build a minimal KiCad PCB file for routing."""
    width_mm = getattr(board, 'width', 100)
    height_mm = getattr(board, 'height', 100)

    lines = [
        "(kicad_pcb (version 20221018) (generator temper-placer)",
        "  (general (thickness 1.6))",
        "  (paper A4)",
        "  (layers (0 \"F.Cu\" signal) (31 \"B.Cu\" signal) (44 \"Edge.Cuts\" edge))",
        "  (setup (pad_to_mask_clearance 0.1))",
    ]

    if netclass_rules is not None:
        from temper_placer.core.netclass_rules import format_netclass_sexpr_lines
        lines.extend(format_netclass_sexpr_lines(netclass_rules))

    # Board outline
    lines.append(f"  (gr_line (start 0 0) (end {width_mm} 0) (layer \"Edge.Cuts\") (width 0.1))")
    lines.append(f"  (gr_line (start {width_mm} 0) (end {width_mm} {height_mm}) (layer \"Edge.Cuts\") (width 0.1))")
    lines.append(f"  (gr_line (start {width_mm} {height_mm}) (end 0 {height_mm}) (layer \"Edge.Cuts\") (width 0.1))")
    lines.append(f"  (gr_line (start 0 {height_mm}) (end 0 0) (layer \"Edge.Cuts\") (width 0.1))")

    # Nets
    if netlist and hasattr(netlist, 'nets'):
        for i, net in enumerate(netlist.nets):
            lines.append(f"  (net {i + 1} \"{net.name}\")")

    # Components
    if netlist and hasattr(netlist, 'components'):
        for comp in netlist.components:
            footprint = getattr(comp, 'footprint', "Resistor_SMD:R_0805_2012Metric")
            ref = getattr(comp, 'ref', comp.__class__.__name__) if hasattr(comp, '__class__') else 'U1'
            lines.append(f"  (footprint \"{footprint}\" (layer \"F.Cu\")")
            lines.append("    (attr smd)")
            lines.append(f"    (property \"Reference\" \"{ref}\")")
            # Include pin pads so the router has pin positions to route.
            pins = getattr(comp, 'pins', [])
            if pins:
                for pin in pins:
                    pin_num = getattr(pin, 'number', '1')
                    pin_x = getattr(pin, 'position', (0.0, 0.0))[0]
                    pin_y = getattr(pin, 'position', (0.0, 0.0))[1]
                    pin_net = getattr(pin, 'net', '')
                    net_idx = 0
                    if netlist and hasattr(netlist, 'nets'):
                        for ni, n in enumerate(netlist.nets):
                            if getattr(n, 'name', '') == pin_net:
                                net_idx = ni + 1
                                break
                    lines.append(
                        f"    (pad \"{pin_num}\" smd rect"
                        f" (at {pin_x:.4f} {pin_y:.4f})"
                        f" (size 1 1) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\")"
                        f" (net {net_idx} \"{pin_net}\"))"
                    )
            lines.append(f"    (at 0 0)")
            lines.append("  )")

    lines.append(")")
    return "\n".join(lines)
