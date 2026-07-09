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
    from pathlib import Path
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
    from temper_placer.placer.cp_sat.feedback import (
        ClassificationResult,
        ConstraintDelta,
        FeedbackClassifier,
        UnclassifiedFailure,
    )
    from temper_placer.placer.cp_sat.gates import BoardState, Gate
    from temper_placer.router_v6.adapter import RoutingResult

logger = logging.getLogger(__name__)


class LoopExitReason(Enum):
    """Why the place-route loop terminated."""

    SUCCESS = "success"
    ROUND_LIMIT_EXCEEDED = "round_limit_exceeded"
    NO_CLASSIFIABLE_FEEDBACK = "no_classifiable_feedback"
    ALL_FEEDBACK_UNSAT = "all_feedback_unsat"
    OSCILLATION_DETECTED = "oscillation_detected"
    GATE_UNMEASURED = "gate_unmeasured"
    FIELD_ROUND_LIMIT_EXCEEDED = "field_round_limit_exceeded"  # U9


@dataclass
class RoundRecord:
    """Record of a single round-trip through the loop.

    U9: ``field_grid`` and ``field_status`` form a parallel continuous
    channel distinct from ``deltas_applied`` (discrete constraint deltas).
    Audit consumers to avoid mistaking the field for a ConstraintDelta.
    """

    round_number: int
    completion_rate: float = 0.0
    drc_errors: int = 0
    solve_time_ms: float = 0.0
    deltas_applied: list[ConstraintDelta] = field(default_factory=list)
    route_time_ms: float = 0.0
    status: str = "unknown"
    field_grid: object | None = None  # U9: np.ndarray (h, w) or None
    field_status: str | None = None  # U9: GateStatus value string or None


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
    unmeasured_gates: dict[str, str] = field(default_factory=dict)


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
        FIELD_EPSILON: U9 — max-cell |T[i] - T[i-1]| threshold for
            continuous-field stability (degrees C).
        FIELD_OSCILLATION_WINDOW: U9 — rounds to check for field
            period-2 / period-4 cycle detection.
        FIELD_CONVERGENCE_ROUND_LIMIT: U9 — max field-feedback rounds
            before exiting with UNMEASURED.
    """

    MAX_ROUNDS: int = 10
    STABILITY_ROUNDS: int = 2
    RE_SOLVE_TIMEOUT_MS: int = 1000
    OSCILLATION_WINDOW: int = 3
    FIELD_EPSILON: float = 0.5  # U9: degrees C per-cell stability threshold
    FIELD_OSCILLATION_WINDOW: int = 4  # U9: period-4 cycle detection window
    FIELD_CONVERGENCE_ROUND_LIMIT: int = 8  # U9: distinct from MAX_ROUNDS

    def __init__(self, classifier=None, gates=None,
                 field_compute_fn=None, thermal_weight=0.0):
        if classifier is None:
            from temper_placer.placer.cp_sat.feedback import FeedbackClassifier
            classifier = FeedbackClassifier()
        self.classifier = classifier

        # Gate registry: when non-empty, gates drive convergence.
        # When empty (None passed explicitly), preserve backward-compat
        # direct-classifier path.
        if gates is None:
            from temper_placer.placer.cp_sat.gates import DrcGate, RoutingGate  # noqa: F811
            self.gates: list[Gate] = [
                DrcGate(),
                RoutingGate(),
            ]
        else:
            self.gates: list[Gate] = list(gates)

        from temper_placer.placer.cp_sat.gates import GateResult
        self._gate_results: dict[str, GateResult] = {}
        self._unmeasured_streak: dict[str, int] = {}
        self._surfaced: list[str] = []

        # U9: field-feedback state (opt-in; field-off when field_compute_fn is None)
        self._field_compute_fn = field_compute_fn  # Callable | None
        self._thermal_weight = thermal_weight  # float
        self._field_history: list = []  # list[np.ndarray] — post-route fields
        self._field_stability_counter: int = 0
        self._field_round_counter: int = 0
        self._solve_times_history: list[float] = []

    @staticmethod
    def _load_netclass_rules():
        import logging
        _logger = logging.getLogger(__name__)
        try:
            from temper_placer.io.netclass_loader import load_netclass_rules
            from pathlib import Path
            config_path = Path(__file__).parent.parent.parent.parent.parent / "configs" / "netclass_rules.yaml"
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
        all_gates: bool = False,
        routed_pcb_path: Path | None = None,
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
            all_gates: When True, register all 5 gates (DrcGate,
                RoutingGate, StackupGate, PhysicsGate, QualityGate).
                When False, use the default [DrcGate, RoutingGate].
            routed_pcb_path: Path to a routed PCB file for DRC gates.

        Returns:
            LoopResult with success status, placement, and routing.
        """
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult, solve_placement

        # Reset per-run state.
        self._unmeasured_streak = {}
        self._surfaced = []

        self._zones = zones
        self._zone_components = zone_components
        self._loop_components = loop_components
        self._netclass_rules = self._load_netclass_rules()
        if self._netclass_rules is not None:
            self.classifier.design_rules = self._netclass_rules.design_rules

        # ---- Build gate registry for all_gates path --------------------------
        if all_gates:
            from temper_placer.placer.cp_sat.gates import (
                DrcGate, PhysicsGate, QualityGate,
                RoutingGate, StackupGate,
            )
            gates = [DrcGate(), RoutingGate(), StackupGate(),
                     PhysicsGate(), QualityGate()]
            logger.info("All-gates mode: 5 gates registered")
        else:
            gates = list(self.gates) if self.gates else []

        self._routed_pcb_path_override = routed_pcb_path

        injected_deltas: list[ConstraintDelta] = []
        rounds: list[RoundRecord] = []
        placement_history: list[CpSatPlacementResult] = []
        previous_unclassified: list[UnclassifiedFailure] = []

        all_constraints = list(pcl_constraints) if pcl_constraints else []

        placement: CpSatPlacementResult | None = None
        routing: RoutingResult | None = None

        # ---- Gate-driven path (U4) -------------------------------------------
        if all_gates:
            return self._run_with_gates(
                netlist, board, pcl_constraints,
                all_constraints, gates, injected_deltas,
                rounds, placement_history, previous_unclassified,
                seed, zones, zone_components, loop_components,
                routed_pcb_path, placement, routing,
                0, 0,
            )

        # ---- Legacy classifier-based path (unchanged) ------------------------
        from temper_placer.placer.cp_sat.feedback import ConstraintDelta

        # ---- Legacy classifier-based path ------------------------------------
        # Backward-compatible: when all_gates=False (default), the original
        # completion_rate + drc_errors check + FeedbackClassifier.classify()
        # path is used unchanged.

        for round_num in range(1, self.MAX_ROUNDS + 1):
            logger.info(f"Round {round_num}/{self.MAX_ROUNDS}")

            injected_deltas = _deduplicate_deltas(injected_deltas)

            # Phase 1: Solve CP-SAT
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

            if self._detect_oscillation(placement, placement_history):
                logger.warning(
                    f"Oscillation detected at round {round_num}"
                )
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.OSCILLATION_DETECTED.value,
                    placement=placement,
                    rounds=rounds,
                )
            placement_history.append(placement)

            # ---- Stage 1: PLACEMENT-stage gates (U4) -----------------------
            # (Only active in _run_with_gates; legacy path skips gates.)

            # ---- Route (legacy) ----------------------------------------------
            t_route = time.monotonic()
            routing = self._route_placement(placement, netlist, board, seed)
            route_time = (time.monotonic() - t_route) * 1000.0

            completion_rate = getattr(routing, 'completion_rate', 0.0)
            drc_errors = (
                routing.drc_errors
                if hasattr(routing, 'drc_errors') else 0
            )
            logger.info(
                f"Round {round_num}: completion={completion_rate:.1%}, "
                f"DRC errors={drc_errors}, solve={solve_time:.0f}ms, "
                f"route={route_time:.0f}ms"
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

            # ---- Legacy convergence check ------------------------------------
            if completion_rate >= 1.0 and drc_errors == 0:
                stable = (
                    self._consecutive_stable_rounds(rounds)
                    >= self.STABILITY_ROUNDS
                )
                if stable:
                    placement = self._solve_phase2(
                        placement, netlist, board,
                        constraint_objects, seed,
                    )
                    return LoopResult(
                        success=True,
                        reason=LoopExitReason.SUCCESS.value,
                        placement=placement,
                        routing=routing,
                        rounds=rounds,
                    )
                else:
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
                if (
                    round_num >= 3
                    and len(classification.unclassified)
                    > len(classification.deltas)
                ):
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
                    logger.info(
                        f"  Delta UNSAT, trying next: {delta.reason}"
                    )
                    continue

            if not delta_accepted:
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.ALL_FEEDBACK_UNSAT.value,
                    placement=placement,
                    routing=routing,
                    rounds=rounds,
                    unsat_core=self._extract_unsat_core(
                        injected_deltas, classification,
                    ),
                )

        # MAX_ROUNDS exhausted
        return LoopResult(
            success=False,
            reason=LoopExitReason.ROUND_LIMIT_EXCEEDED.value,
            placement=placement,
            routing=routing,
            rounds=rounds,
        )

    # -------------------------------------------------------------------
    # Gate-driven round loop (U4, U5, U6)
    # -------------------------------------------------------------------

    def _run_with_gates(
        self,
        netlist, board, pcl_constraints,
        all_constraints, gates, injected_deltas,
        rounds, placement_history, previous_unclassified,
        seed, zones, zone_components, loop_components,
        routed_pcb_path, placement, routing,
        sc1a_green_rounds, sc1b_green_rounds,
    ) -> LoopResult:
        """Run the full gate-driven place-route loop (all_gates=True).

        Implements stage ordering (U4): PLACEMENT-stage gates run after
        CP-SAT solve and before routing; ROUTING-stage gates run after
        routing completes.  UNMEASURED discipline (U5) tracks consecutive
        failures per gate and exits after 3+ rounds.

        U9: when ``_field_compute_fn`` is set, a continuous thermal field
        is carried across rounds.  The field from round N-1 is injected
        into A* during round N; after routing a new post-route field is
        computed and compared for stability.
        """
        import numpy as np  # U9
        from pathlib import Path as _Path
        from temper_placer.placer.cp_sat.encoder import solve_placement
        from temper_placer.placer.cp_sat.gates import GateStage, GateStatus
        from temper_placer.placer.cp_sat.feedback import ConstraintDelta

        self._gate_results = {}

        field_active = self._field_compute_fn is not None  # U9

        for round_num in range(1, self.MAX_ROUNDS + 1):
            logger.info(f"Round {round_num}/{self.MAX_ROUNDS}")

            injected_deltas = _deduplicate_deltas(injected_deltas)

            # ---- U9: Field round budget check ------------------------------
            if field_active and self._field_round_counter >= self.FIELD_CONVERGENCE_ROUND_LIMIT:
                logger.error(
                    "Field convergence round limit (%d / %d) exceeded; "
                    "exiting with UNMEASURED (never silent zero field).",
                    self._field_round_counter,
                    self.FIELD_CONVERGENCE_ROUND_LIMIT,
                )
                self._surface(
                    "Field convergence round budget exceeded "
                    f"({self._field_round_counter} rounds)"
                )
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.FIELD_ROUND_LIMIT_EXCEEDED.value,
                    placement=placement,
                    routing=routing,
                    rounds=rounds,
                    unmeasured_gates={
                        "thermal_field": (
                            f"Field round limit exceeded after "
                            f"{self._field_round_counter} rounds"
                        ),
                    },
                )

            # Phase 1: Solve CP-SAT
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

            # ---- U9: Solve-time trend monitor ------------------------------
            self._solve_times_history.append(solve_time)
            self._check_solve_time_trend()

            if placement.status in ("infeasible", "model_invalid"):
                logger.warning(f"Placement UNSAT at round {round_num}")
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.ALL_FEEDBACK_UNSAT.value,
                    placement=placement,
                    rounds=rounds,
                    unsat_core={
                        "round": round_num, "deltas": injected_deltas,
                    },
                )

            if self._detect_oscillation(placement, placement_history):
                logger.warning(
                    f"Oscillation detected at round {round_num}"
                )
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.OSCILLATION_DETECTED.value,
                    placement=placement,
                    rounds=rounds,
                )
            placement_history.append(placement)

            # ---- Stage 1: PLACEMENT-stage gates --------------------------
            placement_gates = self._gates_for_stage(
                gates, GateStage.PLACEMENT,
            )
            if placement_gates:
                pcb_path = self._get_placement_pcb_path(
                    placement, netlist, board, seed,
                )
                state = self._build_board_state(
                    placement=placement,
                    routing=None,
                    netlist=netlist,
                    board=board,
                    routed_pcb_path_override=(
                        pcb_path or routed_pcb_path
                    ),
                )
                placement_deltas: list[ConstraintDelta] = []
                placement_violations = False
                for gate in placement_gates:
                    result = gate.check(state)
                    self._track_unmeasured(gate, result)
                    self._gate_results[gate.name] = result
                    if result.status is GateStatus.VIOLATIONS:
                        placement_violations = True
                        for v in result.violations:
                            delta = gate.to_delta(v)
                            if delta is not None:
                                placement_deltas.append(delta)
                            else:
                                logger.debug(
                                    "Gate %s violation %s has no delta",
                                    gate.name, v.type.value,
                                )

                unmeasured_exit = self._check_unmeasured_exit(
                    round_num, placement, routing, rounds,
                )
                if unmeasured_exit is not None:
                    return unmeasured_exit

                if placement_violations:
                    delta_accepted = False
                    for delta in placement_deltas:
                        try:
                            test_placement = self._solve_with_delta(
                                netlist, board, constraint_objects,
                                [delta], seed, placement,
                            )
                            injected_deltas.append(delta)
                            placement = test_placement
                            delta_accepted = True
                            logger.info(
                                "  Accepted placement delta: %s",
                                delta.reason,
                            )
                            break
                        except UnsatError:
                            logger.info(
                                "  Placement delta UNSAT: %s",
                                delta.reason,
                            )
                            continue

                    rounds.append(RoundRecord(
                        round_number=round_num,
                        completion_rate=0.0,
                        drc_errors=0,
                        solve_time_ms=solve_time,
                        deltas_applied=list(injected_deltas),
                        route_time_ms=0.0,
                        status=placement.status,
                    ))
                    sc1a_green_rounds = 0
                    sc1b_green_rounds = 0
                    continue  # Skip routing this round.

            # ---- U9: Prepare thermal field from previous round -----------
            _thermal_flat = None
            _thermal_weight = 0.0
            if field_active and len(self._field_history) > 0:
                prev_field = self._field_history[-1]
                _thermal_flat = np.ascontiguousarray(
                    prev_field.ravel()
                ).astype(np.float32)
                _thermal_weight = self._thermal_weight

            # ---- Route ----------------------------------------------------
            t_route = time.monotonic()
            routing = self._route_placement(
                placement, netlist, board, seed,
                thermal_flat=_thermal_flat,
                thermal_weight=_thermal_weight,
            )
            route_time = (time.monotonic() - t_route) * 1000.0

            completion_rate = getattr(routing, 'completion_rate', 0.0)
            drc_errors = (
                routing.drc_errors
                if hasattr(routing, 'drc_errors') else 0
            )
            logger.info(
                f"Round {round_num}: completion={completion_rate:.1%}, "
                f"DRC errors={drc_errors}, solve={solve_time:.0f}ms, "
                f"route={route_time:.0f}ms"
            )

            # ---- U9: Compute post-route thermal field --------------------
            field_grid = None
            field_status_str = None
            if field_active:
                field_result = self._compute_field(
                    placement, routing, netlist, board,
                )
                if field_result is not None and field_result.is_usable:
                    field_grid = field_result.field.grid

                    # Cycle detection BEFORE adding to history
                    if self._detect_field_cycle(field_grid):
                        logger.warning(
                            "Field period-%s cycle detected "
                            "at round %d",
                            self.FIELD_OSCILLATION_WINDOW,
                            round_num,
                        )
                        return LoopResult(
                            success=False,
                            reason=LoopExitReason.OSCILLATION_DETECTED.value,
                            placement=placement,
                            routing=routing,
                            rounds=rounds,
                        )

                    # Stability check
                    if self._check_field_stability(field_grid):
                        self._field_stability_counter += 1
                        logger.debug(
                            "Field stable for %d rounds "
                            "(ε=%.2f °C)",
                            self._field_stability_counter,
                            self.FIELD_EPSILON,
                        )
                    else:
                        self._field_stability_counter = 0

                    self._field_history.append(field_grid)
                    self._field_round_counter += 1
                    field_status_str = field_result.gate_result.status.value

                elif field_result is not None and not field_result.is_usable:
                    # UNMEASURED field: feed through the shared path
                    self._unmeasured_streak["thermal_field"] = (
                        self._unmeasured_streak.get("thermal_field", 0) + 1
                    )
                    self._surface(
                        f"Thermal field UNMEASURED (streak "
                        f"{self._unmeasured_streak['thermal_field']}): "
                        f"{field_result.error_message}"
                    )
                    field_status_str = GateStatus.UNMEASURED.value

            rounds.append(RoundRecord(
                round_number=round_num,
                completion_rate=completion_rate,
                drc_errors=drc_errors,
                solve_time_ms=solve_time,
                deltas_applied=list(injected_deltas),
                route_time_ms=route_time,
                status=placement.status,
                field_grid=field_grid,
                field_status=field_status_str,
            ))

            # ---- U9: Early exit on UNMEASURED field streak ---------------
            if field_active:
                unmeas = self._check_unmeasured_exit(
                    round_num, placement, routing, rounds,
                )
                if unmeas is not None:
                    return unmeas

            # ---- Stage 2: ROUTING-stage gates -----------------------------
            routing_gates = self._gates_for_stage(
                gates, GateStage.ROUTING,
            )
            if routing_gates:
                routed_path = getattr(routing, 'routed_pcb_path', None)
                if isinstance(routed_path, str):
                    routed_path = _Path(routed_path)
                state = self._build_board_state(
                    placement=placement,
                    routing=routing,
                    netlist=netlist,
                    board=board,
                    routed_pcb_path_override=(
                        routed_path or routed_pcb_path
                    ),
                )

                for gate in routing_gates:
                    result = gate.check(state)
                    self._track_unmeasured(gate, result)
                    self._gate_results[gate.name] = result

                all_green = self._all_gates_green_results()
                # U9: field stability is an independent convergence axis
                field_stable = (
                    not field_active
                    or self._field_stability_counter >= self.STABILITY_ROUNDS
                )
                if all_green:
                    sc1a_ok = self._are_named_gates_clean(
                        {"drc", "routing"},
                    )
                    sc1b_ok = all_green
                    if sc1a_ok:
                        sc1a_green_rounds += 1
                        if sc1a_green_rounds == self.STABILITY_ROUNDS:
                            logger.info(
                                "SC1a: DrcGate+RoutingGate green in "
                                "%d rounds", round_num,
                            )
                    else:
                        sc1a_green_rounds = 0
                    if sc1b_ok:
                        sc1b_green_rounds += 1
                        if sc1b_green_rounds == self.STABILITY_ROUNDS:
                            logger.info(
                                "SC1b: all gates green in %d rounds",
                                round_num,
                            )
                    else:
                        sc1b_green_rounds = 0

                    # U9: convergence requires gates + field all stable
                    gate_stable = (
                        sc1a_green_rounds >= self.STABILITY_ROUNDS
                        or sc1b_green_rounds >= self.STABILITY_ROUNDS
                    )
                    if gate_stable and field_stable:
                        logger.info(
                            "Converged: gates green %d rounds, "
                            "field stable %d rounds",
                            max(sc1a_green_rounds, sc1b_green_rounds),
                            self._field_stability_counter,
                        )
                        placement = self._solve_phase2(
                            placement, netlist, board,
                            constraint_objects, seed,
                        )
                        return LoopResult(
                            success=True,
                            reason=LoopExitReason.SUCCESS.value,
                            placement=placement,
                            routing=routing,
                            rounds=rounds,
                        )
                    continue
                else:
                    sc1a_green_rounds = 0
                    sc1b_green_rounds = 0

                gate_deltas = self._collect_deltas_from_gates(gates)
                if not gate_deltas:
                    logger.warning(
                        "Routing gates not green but no deltas produced"
                    )
                else:
                    delta_accepted = False
                    for delta in gate_deltas:
                        try:
                            test_placement = self._solve_with_delta(
                                netlist, board, constraint_objects,
                                [delta], seed, placement,
                            )
                            injected_deltas.append(delta)
                            placement = test_placement
                            delta_accepted = True
                            logger.info(
                                "  Accepted routing delta: %s",
                                delta.reason,
                            )
                            break
                        except UnsatError:
                            logger.info(
                                "  Routing delta UNSAT: %s",
                                delta.reason,
                            )
                            continue

                    if not delta_accepted:
                        return LoopResult(
                            success=False,
                            reason=(
                                LoopExitReason.ALL_FEEDBACK_UNSAT.value
                            ),
                            placement=placement,
                            routing=routing,
                            rounds=rounds,
                            unsat_core={
                                "message": (
                                    "All gate deltas produced UNSAT"
                                ),
                                "gate_results": {
                                    name: {
                                        "status": r.status.value,
                                        "violations": len(r.violations),
                                        "error": r.error_message,
                                    }
                                    for name, r
                                    in self._gate_results.items()
                                },
                            },
                        )

                unmeasured_exit = self._check_unmeasured_exit(
                    round_num, placement, routing, rounds,
                )
                if unmeasured_exit is not None:
                    return unmeasured_exit

        return LoopResult(
            success=False,
            reason=LoopExitReason.ROUND_LIMIT_EXCEEDED.value,
            placement=placement,
            routing=routing,
            rounds=rounds,
        )

    def _get_placement_pcb_path(
        self, placement, netlist, board, seed: int,
    ) -> Path | None:
        """Write a placement-only PCB to a temp file and return its path.

        Returns None if the placement or netlist is missing data.
        """
        import os as _os
        import tempfile as _tempfile
        from pathlib import Path as _Path

        placements_dict = getattr(placement, 'to_placements_dict', None)
        if placements_dict is None:
            return None
        placements = placements_dict()
        if not placements:
            return None

        raw_pcb = _build_minimal_pcb(
            netlist, board,
            getattr(self, '_netclass_rules', None),
        )
        try:
            from temper_placer.router_v6.adapter import (
                _apply_placements_to_pcb,
            )
            placed = _apply_placements_to_pcb(raw_pcb, placements)
        except ImportError:
            placed = raw_pcb

        fd, temp_path = _tempfile.mkstemp(suffix=".kicad_pcb")
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(placed)
        return _Path(temp_path)

    def _all_gates_green_results(self) -> bool:
        """Return True iff every gate in ``_gate_results`` is CLEAN.

        Uses cached results from ``check()`` calls; does not re-run
        gates.  An UNMEASURED gate is never green (core invariant).
        """
        from temper_placer.placer.cp_sat.gates import GateStatus
        return all(
            r.status is GateStatus.CLEAN
            for r in self._gate_results.values()
        )

    def _are_named_gates_clean(self, gate_names: set[str]) -> bool:
        """Return True iff every named gate in ``_gate_results`` is CLEAN."""
        from temper_placer.placer.cp_sat.gates import GateStatus
        for name in gate_names:
            result = self._gate_results.get(name)
            if result is None or result.status is not GateStatus.CLEAN:
                return False
        return True

    def all_gates_green(self, state: BoardState) -> bool:
        """Run every registered gate and return True iff all are CLEAN.

        Stores per-gate results in ``self._gate_results``.  A gate
        returning ``UNMEASURED`` is logged but never treated as green
        (the core three-state invariant).
        """
        from temper_placer.placer.cp_sat.gates import GateStatus, GateResult

        self._gate_results = {}
        for gate in self.gates:
            try:
                result = gate.check(state)
            except Exception as exc:
                logger.error(
                    "Gate %s check raised: %s", gate.name, exc,
                )
                result = GateResult(
                    GateStatus.UNMEASURED,
                    error_message=f"Gate check raised: {exc}",
                )
            self._gate_results[gate.name] = result
            if result.status is GateStatus.UNMEASURED:
                logger.error(
                    "Gate %s UNMEASURED: %s",
                    gate.name, result.error_message,
                )

        return all(
            r.status is GateStatus.CLEAN
            for r in self._gate_results.values()
        )

    def _track_unmeasured(self, gate, result) -> None:
        """Increment or reset the UNMEASURED streak for *gate*.

        A gate that measures this round resets its streak to 0.
        A gate that returns UNMEASURED increments by 1 and logs
        the error.
        """
        from temper_placer.placer.cp_sat.gates import GateStatus

        name = gate.name
        if result.status is GateStatus.UNMEASURED:
            self._unmeasured_streak[name] = (
                self._unmeasured_streak.get(name, 0) + 1
            )
            self._surface(
                f"Gate {name} UNMEASURED (streak "
                f"{self._unmeasured_streak[name]}): "
                f"{result.error_message}"
            )
        else:
            self._unmeasured_streak[name] = 0

    def _check_unmeasured_exit(
        self, round_num: int, placement, routing,
        rounds: list[RoundRecord],
    ) -> LoopResult | None:
        """Check for persistent UNMEASURED gates and exit if >= 3 rounds.

        Returns a ``LoopResult`` signalling ``GATE_UNMEASURED`` when any
        gate has been UNMEASURED for 3+ consecutive rounds; otherwise
        returns None (keep looping).
        """
        for name, streak in self._unmeasured_streak.items():
            if streak >= 3:
                result = self._gate_results.get(name)
                msg = (
                    result.error_message if result is not None else ""
                )
                logger.error(
                    "Gate %s UNMEASURED for %d rounds; exiting. "
                    "Message: %s",
                    name, streak, msg,
                )
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.GATE_UNMEASURED.value,
                    placement=placement,
                    routing=routing,
                    rounds=rounds,
                    unsat_core={
                        "gate": name,
                        "error_message": msg,
                        "round": round_num,
                    },
                    unmeasured_gates={
                        name: msg for name, streak
                        in self._unmeasured_streak.items()
                        if streak >= 3
                    },
                )
        return None

    def _surface(self, msg: str) -> None:
        """Log and record a surfaced message for the operator/CLI."""
        logger.error(msg)
        self._surfaced.append(msg)

    def _build_board_state(
        self,
        placement,
        routing,
        netlist,
        board,
        routed_pcb_path_override: Path | None = None,
    ) -> BoardState:
        """Assemble a frozen ``BoardState`` for gate inspection.

        Args:
            routed_pcb_path_override: Explicit PCB path to use instead
                of extracting from ``routing``.  Used when the loop
                writes a placement-only PCB for PLACEMENT-stage gates.
        """
        from temper_placer.placer.cp_sat.gates import BoardState

        design_rules = None
        netclass_rules = getattr(self, '_netclass_rules', None)
        if netclass_rules is not None:
            design_rules = getattr(netclass_rules, 'design_rules', None)

        routed_pcb_path = routed_pcb_path_override
        if routed_pcb_path is None and routing is not None:
            routed_pcb_path = getattr(routing, 'routed_pcb_path', None)
            if isinstance(routed_pcb_path, str):
                routed_pcb_path = Path(routed_pcb_path)

        return BoardState(
            placement=placement,
            routing=routing,
            netlist=netlist,
            board=board,
            design_rules=design_rules,
            routed_pcb_path=routed_pcb_path,
        )

    def _gates_for_stage(self, gates: list, stage) -> list:
        """Return gates from *gates* registered for the given stage."""
        from temper_placer.placer.cp_sat.gates import GateStage
        return [g for g in gates if g.stage is stage]

    def _collect_deltas_from_gates(
        self, gates: list | None = None,
    ) -> list[ConstraintDelta]:
        """Collect corrective deltas from all non-CLEAN gate results.

        Iterates every gate's violations, calls ``gate.to_delta(v)``,
        and returns the list of non-None ``ConstraintDelta`` objects
        sorted by priority.
        """
        from temper_placer.placer.cp_sat.gates import GateStatus

        source = gates if gates is not None else self.gates
        deltas: list[ConstraintDelta] = []
        for gate in source:
            result = self._gate_results.get(gate.name)
            if result is None or result.status is GateStatus.CLEAN:
                continue
            for violation in result.violations:
                delta = gate.to_delta(violation)
                if delta is not None:
                    deltas.append(delta)
                else:
                    logger.debug(
                        "Gate %s violation %s has no corrective delta",
                        gate.name, violation.type.value,
                    )

        deltas.sort(key=lambda d: d.priority)
        return deltas

    # -------------------------------------------------------------------
    # Routing
    # -------------------------------------------------------------------

    def _route_placement(
        self, placement, netlist, board, seed: int,
        thermal_flat=None, thermal_weight=0.0,
    ) -> "RoutingResult":
        """Route a placement through router_v6.

        U9: optional ``thermal_flat`` / ``thermal_weight`` thread
        the continuous field from the previous round into the
        A* kernel.  When ``thermal_weight=0.0`` the field-off
        path is byte-identical to today's routing.
        """
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
            return route_pcb(
                parsed,
                placements_dict,
                _seed=seed,
                design_rules=netclass_rules.design_rules if netclass_rules is not None else None,
                thermal_flat=thermal_flat,
                thermal_weight=thermal_weight,
            )
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

        for rp in recent_positions:
            if rp is None:
                return False
            if _positions_equal(positions, rp):
                return True

        return False

    # -------------------------------------------------------------------
    # U9: Continuous-field feedback (field stability, cycle detection,
    #     solve-time trend monitor)
    # -------------------------------------------------------------------

    def _compute_field(self, placement, routing, netlist, board):
        """Call the injected field-compute function; return FieldResult or None.

        When ``_field_compute_fn`` is None (field-off), returns None
        immediately — this is the zero-cost default path.
        """
        if self._field_compute_fn is None:
            return None
        try:
            return self._field_compute_fn(placement, routing, netlist, board)
        except Exception as exc:
            logger.error("Field compute raised: %s", exc)
            from temper_placer.placer.cp_sat.gates import GateResult, GateStatus
            from temper_placer.fields.result import FieldResult
            return FieldResult(
                gate_result=GateResult(
                    status=GateStatus.UNMEASURED,
                    error_message=f"Field compute raised: {exc}",
                ),
                field=None,
            )

    def _check_field_stability(self, current_field) -> bool:
        """Return True when |T[i] - T[i-1]|_max < FIELD_EPSILON."""
        import numpy as np
        if len(self._field_history) < 1:
            return False
        prev = self._field_history[-1]
        delta_max = float(np.max(np.abs(current_field - prev)))
        return delta_max < self.FIELD_EPSILON

    def _detect_field_cycle(self, current_field) -> bool:
        """Detect period-2 or period-4 place↔field cycles.

        Uses a FIELD_OSCILLATION_WINDOW (4) and ε_field max-norm
        criterion: if the current field matches any field in the
        last window rounds within epsilon, it is a cycle.
        """
        import numpy as np
        if len(self._field_history) < self.FIELD_OSCILLATION_WINDOW:
            return False
        recent = self._field_history[-self.FIELD_OSCILLATION_WINDOW:]
        for old_field in recent:
            if np.max(np.abs(current_field - old_field)) < self.FIELD_EPSILON:
                return True
        return False

    def _check_solve_time_trend(self) -> None:
        """Log a WARNING when solve_time_ms increases monotonically ≥3 rounds.

        A monotonically-growing solve time signals the CP-SAT feasible
        region shrinking — field detours can tighten constraints toward
        a timeout.  Log only; do not abort.
        """
        if len(self._solve_times_history) < 3:
            return
        recent = self._solve_times_history[-3:]
        if recent[0] < recent[1] < recent[2]:
            logger.warning(
                "U9: solve-time trend increasing across last 3 rounds "
                "(%0.f → %0.f → %0.f ms) — feasible region may be "
                "shrinking (field detours tightening constraints).",
                recent[0], recent[1], recent[2],
            )

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


def _positions_equal(a, b) -> bool:
    """Compare two position representations for equality within tolerance.

    Supports both numpy arrays (legacy) and dict[str, tuple[float, float]]
    (current CpSatPlacementResult.positions format).
    """
    if a is b:
        return True
    if type(a) is not type(b):
        return False

    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        for key in a:
            pa, pb = a[key], b[key]
            if abs(pa[0] - pb[0]) > 0.1 or abs(pa[1] - pb[1]) > 0.1:
                return False
        return True

    import numpy as np
    return bool(np.allclose(a, b, atol=0.1))


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
        dr = netclass_rules.design_rules
        for nc in sorted(dr.net_classes.values(), key=lambda nc: nc.name):
            lines.append(
                f"  (net_class \"{nc.name}\""
                f" (clearance {nc.clearance})"
                f" (trace_width {nc.trace_width})"
                f" (via_dia {nc.via_diameter})"
                f" (via_drill {nc.via_drill}))"
            )

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
