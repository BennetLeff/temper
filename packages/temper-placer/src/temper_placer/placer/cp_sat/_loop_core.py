"""Core loop orchestration mixin for the place-route loop controller.

Extracted from ``loop.py``: ``_call_solver``, ``run``, ``_run_with_gates``,
``_solve_with_delta``, and ``_solve_phase2``.

This module is a delegation shim. The RESIDUAL non-ortools orchestration
(the loop SEQUENCING, the gate checks, and the convergence/stability/
feedback DECISIONS) moved to ``temper-orchestration``'s ``cpsat_loop.rs``
(Rust Orchestration Engine plan 2026-08-09-001, orchestration-port unit U-I):

- ``run()``'s legacy classifier loop -> ``cpsat_run_legacy_loop``,
- ``_run_with_gates()``'s gate-driven loop -> ``cpsat_run_gated_loop``,
- ``_solve_with_delta``'s non-solver core -> ``cpsat_solve_with_delta``,
- ``_solve_phase2``'s non-solver core -> ``cpsat_solve_phase2``.

What stays Python (the U-I boundary): ``_call_solver`` (the CP-SAT solve
boundary -- the lazy ``encoder.solve_placement`` import must keep resolving
``mock.patch('...encoder.solve_placement')``), ``run()``'s per-run state
reset / argument marshalling / gate-registry construction, and the leaf
helpers in the other mixins (``_loop_stability`` / ``_loop_gates`` /
``_loop_routing``), invoked by the Rust loop as call-backs in oracle order.
The pre-migration module is pinned VERBATIM as
``tests/placer/cp_sat/_loop_core_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json``); bit-identical parity is pinned by
``tests/placer/cp_sat/test_loop_core_rust_differential.py``. The public API
(the ``_LoopCoreMixin`` methods) is unchanged.
"""

from __future__ import annotations

import logging
import time  # noqa: F401  # load-bearing: cpsat_loop.rs reads `_loop_core.time.monotonic` (the mock target)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.cp_sat._loop_types import LoopResult
    from temper_placer.placer.cp_sat.feedback import (
        ConstraintDelta,
    )

import temper_orchestration as _orch

from temper_placer.placer.cp_sat._loop_utils import (
    load_netclass_rules,
)

logger = logging.getLogger(__name__)


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
        if getattr(self, "_validator_input", None):
            # Issue #523 gap 2 / #617: the REQ-SAFE-01 validator post-solve
            # audit (set by PlaceRouteLoop.run(validator_input=...)). Absent
            # (the default) keeps the solve byte-identical to pre-wiring.
            solver_kwargs["validator_input"] = self._validator_input
        if getattr(self, "_body_collision_input", None):
            # Fail-closed F.Fab body-collision post-solve audit (set by
            # PlaceRouteLoop.run(body_collision_input=...)). Absent (the
            # default) keeps the solve byte-identical to pre-wiring; see
            # body_collision.py's module docstring for what this guards
            # against.
            solver_kwargs["body_collision_input"] = self._body_collision_input
        # ---- Opt-in HARD safety constraint families (2026-08-19) ----------
        # These three `solve_placement` kwargs were reachable ONLY from
        # `temper optimize --no-loop` (tank_creepage), `repair-unplaced`
        # (isolation_barrier), or from nothing at all in `src/`
        # (heatsink_colocation). `--loop` is the DEFAULT and is what both
        # scripts/run_clean_flow.sh and scripts/run_physics_flow.sh run, so
        # every shipping placement solve was produced with all three dark --
        # not merely unset but UNREACHABLE: `run()` had no parameter to
        # carry them and this dict had no key to forward them through.
        # Wired in exactly the shape `validator_input` /
        # `body_collision_input` above already established (instance state
        # set by `run()`, forwarded only when supplied), because the Rust
        # loop calls `_call_solver` back with a FIXED kwarg set -- per-round
        # solver arguments must travel as instance state, not parameters.
        # None (the default) keeps a solve byte-identical to pre-wiring.
        if getattr(self, "_tank_creepage", None):
            solver_kwargs["tank_creepage"] = self._tank_creepage
        if getattr(self, "_isolation_barrier", None):
            solver_kwargs["isolation_barrier"] = self._isolation_barrier
        # Rotation index 0 is a legitimate value AND falsy, so this one
        # tests `is not None` rather than truthiness -- the getattr-truthy
        # idiom the four kwargs above use would silently drop
        # `heatsink_colocation=0` (the "both IGBTs at 0 degrees" request)
        # and leave the constraint dark exactly as it is today.
        if getattr(self, "_heatsink_colocation", None) is not None:
            solver_kwargs["heatsink_colocation"] = self._heatsink_colocation
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
        validator_input: dict | None = None,
        body_collision_input: dict | None = None,
        tank_creepage: dict | None = None,
        isolation_barrier: dict | None = None,
        heatsink_colocation: int | None = None,
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
            validator_input: Optional ``{"placement": ..., "voltage_domains":
                ...}`` forwarded into every ``solve_placement`` round so the
                REQ-SAFE-01 validator post-solve audit (issue #523 gap 2)
                runs on each feasible solved placement. ``None`` (the
                default) keeps every round byte-identical to pre-wiring.
            body_collision_input: Optional ``{"fab_bodies": ..., "allowlist":
                ...}`` forwarded into every ``solve_placement`` round so the
                fail-closed ``F.Fab`` body-collision post-solve audit runs on
                each feasible solved placement (see ``body_collision.py``).
                ``None`` (the default) keeps every round byte-identical to
                pre-wiring.
            tank_creepage: Optional kwargs forwarded to every round's
                ``solve_placement(tank_creepage=...)`` -- the tank-node
                functional-creepage HARD constraint (``tank_creepage.py``,
                #1089). ``None`` (the default) leaves it dark, which is
                what every ``--loop`` solve did before 2026-08-19.
            isolation_barrier: Optional kwargs forwarded to every round's
                ``solve_placement(isolation_barrier=...)`` -- the
                mains<->SELV physical isolation-barrier HARD constraint
                (``isolation_barrier.py``). ``None`` (the default) leaves
                it dark.
            heatsink_colocation: Optional common rotation index (0-3)
                forwarded to every round's
                ``solve_placement(heatsink_colocation=...)`` -- the shared
                heatsink co-location HARD constraint for every group in
                ``heatsink_colocation.HEATSINK_GROUPS`` (#1082). ``None``
                (the default) leaves it dark; ``0`` is a real request and
                is forwarded, not swallowed.

            **On all three:** they are per-round SOLVER arguments, so they
            travel to ``_call_solver`` as instance state rather than being
            threaded through the Rust loop's fixed call-back signature --
            the same mechanism ``validator_input`` uses. See
            ``_call_solver``'s own comment for why they were previously
            unreachable from this entry point rather than merely unset.

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
        self._validator_input = validator_input
        self._body_collision_input = body_collision_input
        self._tank_creepage = tank_creepage
        self._isolation_barrier = isolation_barrier
        self._heatsink_colocation = heatsink_colocation
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

        all_constraints = list(pcl_constraints) if pcl_constraints else []

        # ---- Gate-driven path (U4) -------------------------------------------
        # Dispatch on all_gates (the "register all 5 default gates"
        # convenience flag) OR self._gates_explicit (the caller passed a
        # custom gates= list to the constructor) -- either signals intent
        # to use gate-driven convergence rather than the legacy
        # classifier path. Checking all_gates alone ignored a caller's
        # explicit custom gate registry entirely.
        if all_gates or self._gates_explicit:
            return _orch.cpsat_run_gated_loop(
                self,
                netlist,
                board,
                all_constraints,
                gates,
                seed,
                routed_pcb_path,
            )

        # ---- Legacy classifier-based path (delegated to Rust) ---------------
        # Backward-compatible: when all_gates=False (default), the original
        # completion_rate + drc_errors check + FeedbackClassifier.classify()
        # path is used unchanged -- the SEQUENCING now lives in
        # `cpsat_run_legacy_loop`.
        return _orch.cpsat_run_legacy_loop(
            self,
            netlist,
            board,
            all_constraints,
            seed,
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
        _injected_deltas,
        _rounds,
        _placement_history,
        _previous_unclassified,
        seed,
        _zones,
        _zone_components,
        _loop_components,
        routed_pcb_path,
        _placement,
        _routing,
        _sc1a_green_rounds,
        _sc1b_green_rounds,
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

        The loop SEQUENCING (the round loop, the gate passes, the
        convergence/stability decisions) is delegated to
        ``cpsat_run_gated_loop``; the per-round call-backs (solve, route,
        gate checks, field compute) stay Python. The initial ``injected_deltas`` /
        ``rounds`` / ``placement_history`` / ``placement`` / ``routing`` /
        ``sc1a_green_rounds`` / ``sc1b_green_rounds`` are always the ``run()``
        defaults (empty / None / 0) -- the Rust loop initializes them the same
        way, so the leading parameters are accepted for signature
        compatibility and not forwarded.
        """
        return _orch.cpsat_run_gated_loop(
            self,
            netlist,
            board,
            all_constraints,
            gates,
            seed,
            routed_pcb_path,
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
        """Try solving with an additional delta. Raises UnsatError on failure.

        The non-solver sequencing (constraint-list assembly, the UNSAT check
        and the ``UnsatError`` raise) is delegated to ``cpsat_solve_with_delta``;
        the solve itself goes through ``_call_solver`` (Python boundary).
        """
        return _orch.cpsat_solve_with_delta(
            self,
            netlist,
            board,
            base_constraints,
            new_deltas,
            seed,
            _warm_start_placement,
        )

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

        The non-solver sequencing (the 5s polish solve + the
        don't-regress fallback) is delegated to ``cpsat_solve_phase2``; the
        solve itself goes through ``_call_solver`` (Python boundary).
        """
        return _orch.cpsat_solve_phase2(
            self,
            placement,
            netlist,
            board,
            constraint_objects,
            seed,
        )
