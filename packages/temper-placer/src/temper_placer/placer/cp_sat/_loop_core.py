"""Core loop orchestration mixin for the place-route loop controller.

Extracted from ``loop.py``: ``_call_solver``, ``run``, ``_run_with_gates``,
``_solve_with_delta``, and ``_solve_phase2``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
    from temper_placer.placer.cp_sat.feedback import (
        ConstraintDelta,
        UnclassifiedFailure,
    )
    from temper_placer.router_v6.adapter import RoutingResult

from temper_placer.placer.cp_sat._loop_types import (
    LoopExitReason,
    LoopResult,
    RoundRecord,
    UnsatError,
)
from temper_placer.placer.cp_sat._loop_utils import (
    deduplicate_deltas,
    load_netclass_rules,
)

logger = logging.getLogger(__name__)

# Solver statuses that mean "no usable placement came out of this solve".
# "audit_failed" is the post-solve audit's failure verdict (plan
# 2026-08-02-016 U3): the solver reported a feasible placement but the
# recomputed constraint values contradicted the encoding, so the run must
# not continue routing from it.
_NON_PLACEMENT_STATUSES: tuple[str, ...] = ("infeasible", "model_invalid", "audit_failed")


class _LoopCoreMixin:
    """Core orchestration methods for PlaceRouteLoop.

    Provides the main ``run`` entry point, the gate-driven
    ``_run_with_gates`` round loop, and the CP-SAT solve helpers.
    """

    def _call_solver(
        self,
        netlist,
        board,
        extra_constraints,
        timeout_ms,
        seed,
        zones=None,
        zone_components=None,
        loop_components=None,
    ):
        """Resolve the placement solver lazily and call it.

        When ``_placement_solver`` is None (default), imports
        ``solve_placement`` from encoder at call time so that
        ``mock.patch('...encoder.solve_placement')`` still works.
        When an injected stub is present, that stub is called directly.
        """
        solver = self._placement_solver
        if solver is None:
            from temper_placer.placer.cp_sat.encoder import solve_placement

            solver = solve_placement
        solver_kwargs = {
            "netlist": netlist,
            "board": board,
            "extra_constraints": extra_constraints,
            "timeout_ms": timeout_ms,
            "seed": seed,
            "zones": zones,
            "zone_components": zone_components,
            "loop_components": loop_components,
        }
        if getattr(self, "_reference_aliases", None):
            solver_kwargs["reference_aliases"] = self._reference_aliases
        if getattr(self, "_loop_aliases", None):
            solver_kwargs["loop_aliases"] = self._loop_aliases
        return solver(**solver_kwargs)

    def run(
        self,
        netlist: Netlist,
        board: Board,
        pcl_constraints: list | None = None,
        seed: int = 42,
        zones: dict | None = None,
        zone_components: dict[str, list[str]] | None = None,
        loop_components: dict[str, list[str]] | None = None,
        reference_aliases: dict[str, str] | None = None,
        loop_aliases: dict[str, str] | None = None,
        all_gates: bool = False,
        routed_pcb_path: Path | None = None,
        source_pcb_path: Path | None = None,
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
            reference_aliases: Optional source-backed config-to-netlist
                component reference map applied before validation.
            loop_aliases: Optional source-backed legacy loop-name map.
            all_gates: When True, register all 5 gates (DrcGate,
                RoutingGate, StackupGate, PhysicsGate, QualityGate).
                When False, use the default [DrcGate, RoutingGate].
            routed_pcb_path: Path to a routed PCB file for DRC gates.
            source_pcb_path: Authoritative KiCad source board. When supplied,
                routing applies CP-SAT coordinates to this board rather than
                manufacturing a synthetic footprint/pad approximation.

        Returns:
            LoopResult with success status, placement, and routing.
        """

        # Reset per-run state.
        self._unmeasured_streak = {}
        self._surfaced = []

        self._zones = zones
        self._zone_components = zone_components
        self._loop_components = loop_components
        self._reference_aliases = reference_aliases
        self._loop_aliases = loop_aliases
        self._netclass_rules = load_netclass_rules()
        if self._netclass_rules is not None:
            self.classifier.design_rules = self._netclass_rules.design_rules

        # ---- Build gate registry for all_gates path --------------------------
        if all_gates:
            from temper_placer.placer.cp_sat.gates import (
                DrcGate,
                PhysicsGate,
                QualityGate,
                RoutingGate,
                StackupGate,
            )

            gates = [DrcGate(), RoutingGate(), StackupGate(), PhysicsGate(), QualityGate()]
            logger.info("All-gates mode: 5 gates registered")
        else:
            gates = list(self.gates) if self.gates else []

        self._routed_pcb_path_override = routed_pcb_path
        self._source_pcb_path = source_pcb_path

        injected_deltas: list[ConstraintDelta] = []
        rounds: list[RoundRecord] = []
        placement_history: list[CpSatPlacementResult] = []
        previous_unclassified: list[UnclassifiedFailure] = []

        all_constraints = list(pcl_constraints) if pcl_constraints else []

        placement: CpSatPlacementResult | None = None
        routing: RoutingResult | None = None

        # ---- Gate-driven path (U4) -------------------------------------------
        # Dispatch on all_gates (the "register all 5 default gates"
        # convenience flag) OR self._gates_explicit (the caller passed a
        # custom gates= list to the constructor) -- either signals intent
        # to use gate-driven convergence rather than the legacy
        # classifier path. Checking all_gates alone ignored a caller's
        # explicit custom gate registry entirely.
        if all_gates or self._gates_explicit:
            return self._run_with_gates(
                netlist,
                board,
                pcl_constraints,
                all_constraints,
                gates,
                injected_deltas,
                rounds,
                placement_history,
                previous_unclassified,
                seed,
                zones,
                zone_components,
                loop_components,
                routed_pcb_path,
                placement,
                routing,
                0,
                0,
            )

        # ---- Legacy classifier-based path ------------------------------------
        # Backward-compatible: when all_gates=False (default), the original
        # completion_rate + drc_errors check + FeedbackClassifier.classify()
        # path is used unchanged.

        for round_num in range(1, self.MAX_ROUNDS + 1):
            logger.info(f"Round {round_num}/{self.MAX_ROUNDS}")

            injected_deltas = deduplicate_deltas(injected_deltas)

            # Phase 1: Solve CP-SAT
            t0 = time.monotonic()
            constraint_objects = all_constraints + [delta.constraint for delta in injected_deltas]
            # Round 1 is the cold, delta-free full-model solve — give it the
            # larger initial budget; later rounds are warm incremental re-solves
            # that must stay within the fast Phase-1 target.
            solve_budget_ms = (
                self.INITIAL_SOLVE_TIMEOUT_MS if round_num == 1 else self.RE_SOLVE_TIMEOUT_MS
            )
            placement = self._call_solver(
                netlist=netlist,
                board=board,
                extra_constraints=constraint_objects,
                timeout_ms=solve_budget_ms,
                seed=seed,
                zones=self._zones,
                zone_components=self._zone_components,
                loop_components=self._loop_components,
            )
            solve_time = (time.monotonic() - t0) * 1000.0

            if placement.status in _NON_PLACEMENT_STATUSES:
                if placement.status == "audit_failed":
                    logger.error(
                        "Placement rejected by post-solve audit at round %d: %s",
                        round_num,
                        [v.description for v in getattr(placement.audit_report, "violations", [])],
                    )
                    return LoopResult(
                        success=False,
                        reason=LoopExitReason.AUDIT_FAILED.value,
                        placement=placement,
                        rounds=rounds,
                        unsat_core={
                            "round": round_num,
                            "message": "post-solve audit rejected the placement",
                        },
                    )
                logger.warning(f"Placement UNSAT at round {round_num}")
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.ALL_FEEDBACK_UNSAT.value,
                    placement=placement,
                    rounds=rounds,
                    unsat_core={"round": round_num, "deltas": injected_deltas},
                )

            if self._detect_oscillation(placement, placement_history):
                logger.warning(f"Oscillation detected at round {round_num}")
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

            completion_rate = getattr(routing, "completion_rate", 0.0)
            drc_errors = routing.drc_errors if hasattr(routing, "drc_errors") else 0
            logger.info(
                f"Round {round_num}: completion={completion_rate:.1%}, "
                f"DRC errors={drc_errors}, solve={solve_time:.0f}ms, "
                f"route={route_time:.0f}ms"
            )

            rounds.append(
                RoundRecord(
                    round_number=round_num,
                    completion_rate=completion_rate,
                    drc_errors=drc_errors,
                    solve_time_ms=solve_time,
                    deltas_applied=list(injected_deltas),
                    route_time_ms=route_time,
                    status=placement.status,
                )
            )

            # ---- Legacy convergence check ------------------------------------
            if completion_rate >= 1.0 and drc_errors == 0:
                if getattr(self, "_source_pcb_path", None) is not None:
                    # Router V6 is deterministic for a fixed real KiCad board
                    # and fixed placement. Re-running the native routing stack
                    # with identical inputs is not an independent stability
                    # measurement; the authoritative artifact is instead sent
                    # immediately to the KiCad DRC truth gate by the CLI.
                    # Keep the two-round rule for synthetic/test-only flows.
                    return LoopResult(
                        success=True,
                        reason=LoopExitReason.SUCCESS.value,
                        placement=placement,
                        routing=routing,
                        rounds=rounds,
                    )
                stable = self._consecutive_stable_rounds(rounds) >= self.STABILITY_ROUNDS
                if stable:
                    placement = self._solve_phase2(
                        placement,
                        netlist,
                        board,
                        constraint_objects,
                        seed,
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
            if (
                not classification.deltas
                and classification.unclassified
                and (
                    round_num >= 3 and len(classification.unclassified) > len(classification.deltas)
                )
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
                        netlist,
                        board,
                        constraint_objects,
                        [delta],
                        seed,
                        placement,
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
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.ALL_FEEDBACK_UNSAT.value,
                    placement=placement,
                    routing=routing,
                    rounds=rounds,
                    unsat_core=self._extract_unsat_core(
                        injected_deltas,
                        classification,
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
        netlist,
        board,
        _pcl_constraints,
        all_constraints,
        gates,
        injected_deltas,
        rounds,
        placement_history,
        _previous_unclassified,
        seed,
        _zones,
        _zone_components,
        _loop_components,
        routed_pcb_path,
        placement,
        routing,
        sc1a_green_rounds,
        sc1b_green_rounds,
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
        from pathlib import Path as _Path

        import numpy as np  # U9

        from temper_placer.placer.cp_sat.gates import GateStage, GateStatus

        self._gate_results = {}

        field_active = self._field_compute_fn is not None  # U9

        for round_num in range(1, self.MAX_ROUNDS + 1):
            logger.info(f"Round {round_num}/{self.MAX_ROUNDS}")

            injected_deltas = deduplicate_deltas(injected_deltas)

            # ---- U9: Field round budget check ------------------------------
            if field_active and self._field_round_counter >= self.FIELD_CONVERGENCE_ROUND_LIMIT:
                logger.error(
                    "Field convergence round limit (%d / %d) exceeded; "
                    "exiting with UNMEASURED (never silent zero field).",
                    self._field_round_counter,
                    self.FIELD_CONVERGENCE_ROUND_LIMIT,
                )
                self._surface(
                    f"Field convergence round budget exceeded ({self._field_round_counter} rounds)"
                )
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.FIELD_ROUND_LIMIT_EXCEEDED.value,
                    placement=placement,
                    routing=routing,
                    rounds=rounds,
                    unmeasured_gates={
                        "thermal_field": (
                            f"Field round limit exceeded after {self._field_round_counter} rounds"
                        ),
                    },
                )

            # Phase 1: Solve CP-SAT
            t0 = time.monotonic()
            constraint_objects = all_constraints + [delta.constraint for delta in injected_deltas]
            # Round 1 is the cold, delta-free full-model solve — give it the
            # larger initial budget; later rounds are warm incremental re-solves
            # that must stay within the fast Phase-1 target.
            solve_budget_ms = (
                self.INITIAL_SOLVE_TIMEOUT_MS if round_num == 1 else self.RE_SOLVE_TIMEOUT_MS
            )
            placement = self._call_solver(
                netlist=netlist,
                board=board,
                extra_constraints=constraint_objects,
                timeout_ms=solve_budget_ms,
                seed=seed,
                zones=self._zones,
                zone_components=self._zone_components,
                loop_components=self._loop_components,
            )
            solve_time = (time.monotonic() - t0) * 1000.0

            # ---- U9: Solve-time trend monitor ------------------------------
            self._solve_times_history.append(solve_time)
            self._check_solve_time_trend()

            if placement.status in _NON_PLACEMENT_STATUSES:
                if placement.status == "audit_failed":
                    logger.error(
                        "Placement rejected by post-solve audit at round %d: %s",
                        round_num,
                        [v.description for v in getattr(placement.audit_report, "violations", [])],
                    )
                    return LoopResult(
                        success=False,
                        reason=LoopExitReason.AUDIT_FAILED.value,
                        placement=placement,
                        rounds=rounds,
                        unsat_core={
                            "round": round_num,
                            "message": "post-solve audit rejected the placement",
                        },
                    )
                logger.warning(f"Placement UNSAT at round {round_num}")
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.ALL_FEEDBACK_UNSAT.value,
                    placement=placement,
                    rounds=rounds,
                    unsat_core={
                        "round": round_num,
                        "deltas": injected_deltas,
                    },
                )

            if self._detect_oscillation(placement, placement_history):
                logger.warning(f"Oscillation detected at round {round_num}")
                return LoopResult(
                    success=False,
                    reason=LoopExitReason.OSCILLATION_DETECTED.value,
                    placement=placement,
                    rounds=rounds,
                )
            placement_history.append(placement)

            # ---- Stage 1: PLACEMENT-stage gates --------------------------
            placement_gates = self._gates_for_stage(
                gates,
                GateStage.PLACEMENT,
            )
            if placement_gates:
                pcb_path = self._get_placement_pcb_path(
                    placement,
                    netlist,
                    board,
                    seed,
                )
                state = self._build_board_state(
                    placement=placement,
                    routing=None,
                    netlist=netlist,
                    board=board,
                    routed_pcb_path_override=(pcb_path or routed_pcb_path),
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
                                    gate.name,
                                    v.type.value,
                                )

                unmeasured_exit = self._check_unmeasured_exit(
                    round_num,
                    placement,
                    routing,
                    rounds,
                )
                if unmeasured_exit is not None:
                    return unmeasured_exit

                if placement_violations:
                    delta_accepted = False
                    for delta in placement_deltas:
                        try:
                            test_placement = self._solve_with_delta(
                                netlist,
                                board,
                                constraint_objects,
                                [delta],
                                seed,
                                placement,
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

                    rounds.append(
                        RoundRecord(
                            round_number=round_num,
                            completion_rate=0.0,
                            drc_errors=0,
                            solve_time_ms=solve_time,
                            deltas_applied=list(injected_deltas),
                            route_time_ms=0.0,
                            status=placement.status,
                        )
                    )
                    sc1a_green_rounds = 0
                    sc1b_green_rounds = 0
                    continue  # Skip routing this round.

            # ---- U9: Prepare thermal field from previous round -----------
            _thermal_flat = None
            _thermal_weight = 0.0
            if field_active and len(self._field_history) > 0:
                prev_field = self._field_history[-1]
                _thermal_flat = np.ascontiguousarray(prev_field.ravel()).astype(np.float32)
                _thermal_weight = self._thermal_weight

            # ---- Route ----------------------------------------------------
            t_route = time.monotonic()
            routing = self._route_placement(
                placement,
                netlist,
                board,
                seed,
                thermal_flat=_thermal_flat,
                thermal_weight=_thermal_weight,
            )
            route_time = (time.monotonic() - t_route) * 1000.0

            completion_rate = getattr(routing, "completion_rate", 0.0)
            drc_errors = routing.drc_errors if hasattr(routing, "drc_errors") else 0
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
                    placement,
                    routing,
                    netlist,
                    board,
                )
                if field_result is not None and field_result.is_usable:
                    field_grid = field_result.field.grid

                    # Cycle detection BEFORE adding to history
                    if self._detect_field_cycle(field_grid):
                        logger.warning(
                            "Field period-%s cycle detected at round %d",
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
                            "Field stable for %d rounds (ε=%.2f °C)",
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

            rounds.append(
                RoundRecord(
                    round_number=round_num,
                    completion_rate=completion_rate,
                    drc_errors=drc_errors,
                    solve_time_ms=solve_time,
                    deltas_applied=list(injected_deltas),
                    route_time_ms=route_time,
                    status=placement.status,
                    field_grid=field_grid,
                    field_status=field_status_str,
                )
            )

            # ---- U9: Early exit on UNMEASURED field streak ---------------
            if field_active:
                unmeas = self._check_unmeasured_exit(
                    round_num,
                    placement,
                    routing,
                    rounds,
                )
                if unmeas is not None:
                    return unmeas

            # ---- Stage 2: ROUTING-stage gates -----------------------------
            routing_gates = self._gates_for_stage(
                gates,
                GateStage.ROUTING,
            )
            if routing_gates:
                routed_path = getattr(routing, "routed_pcb_path", None)
                if isinstance(routed_path, str):
                    routed_path = _Path(routed_path)
                state = self._build_board_state(
                    placement=placement,
                    routing=routing,
                    netlist=netlist,
                    board=board,
                    routed_pcb_path_override=(routed_path or routed_pcb_path),
                )

                for gate in routing_gates:
                    result = gate.check(state)
                    self._track_unmeasured(gate, result)
                    self._gate_results[gate.name] = result

                all_green = self._all_gates_green_results()
                # U9: field stability is an independent convergence axis
                field_stable = (
                    not field_active or self._field_stability_counter >= self.STABILITY_ROUNDS
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
                                "SC1a: DrcGate+RoutingGate green in %d rounds",
                                round_num,
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
                            "Converged: gates green %d rounds, field stable %d rounds",
                            max(sc1a_green_rounds, sc1b_green_rounds),
                            self._field_stability_counter,
                        )
                        placement = self._solve_phase2(
                            placement,
                            netlist,
                            board,
                            constraint_objects,
                            seed,
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
                    logger.warning("Routing gates not green but no deltas produced")
                else:
                    delta_accepted = False
                    for delta in gate_deltas:
                        try:
                            test_placement = self._solve_with_delta(
                                netlist,
                                board,
                                constraint_objects,
                                [delta],
                                seed,
                                placement,
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
                            reason=(LoopExitReason.ALL_FEEDBACK_UNSAT.value),
                            placement=placement,
                            routing=routing,
                            rounds=rounds,
                            unsat_core={
                                "message": ("All gate deltas produced UNSAT"),
                                "gate_results": {
                                    name: {
                                        "status": r.status.value,
                                        "violations": len(r.violations),
                                        "error": r.error_message,
                                    }
                                    for name, r in self._gate_results.items()
                                },
                            },
                        )

                unmeasured_exit = self._check_unmeasured_exit(
                    round_num,
                    placement,
                    routing,
                    rounds,
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

    # -------------------------------------------------------------------
    # Solve with delta
    # -------------------------------------------------------------------

    def _solve_with_delta(
        self,
        netlist,
        board,
        base_constraints: list,
        new_deltas: list[ConstraintDelta],
        seed: int,
        _warm_start_placement=None,
    ):
        """Try solving with an additional delta. Raises UnsatError on failure."""

        all_objects = list(base_constraints) + [delta.constraint for delta in new_deltas]

        result = self._call_solver(
            netlist=netlist,
            board=board,
            extra_constraints=all_objects,
            timeout_ms=self.RE_SOLVE_TIMEOUT_MS,
            seed=seed,
            zones=self._zones,
            zone_components=self._zone_components,
            loop_components=self._loop_components,
        )

        if result.status in _NON_PLACEMENT_STATUSES:
            raise UnsatError(
                deltas=new_deltas,
                message=f"UNSAT with delta(s): {[d.reason for d in new_deltas]}",
            )

        return result

    # -------------------------------------------------------------------
    # Phase 2: wirelength polish
    # -------------------------------------------------------------------

    def _solve_phase2(
        self,
        placement,
        netlist,
        board,
        constraint_objects: list,
        seed: int,
    ):
        """Run Phase 2 wirelength polish after stability.

        Phase 2 uses a longer timeout for better wirelength optimization
        but must not regress the completion rate below Phase 1's.
        """
        result = self._call_solver(
            netlist=netlist,
            board=board,
            extra_constraints=constraint_objects,
            timeout_ms=5000,  # 5s for polish
            seed=seed,
            zones=self._zones,
            zone_components=self._zone_components,
            loop_components=self._loop_components,
        )

        if result.status in _NON_PLACEMENT_STATUSES:
            # Don't regress — return Phase 1 placement
            logger.info("Phase 2 UNSAT — returning Phase 1 placement")
            return placement

        return result
