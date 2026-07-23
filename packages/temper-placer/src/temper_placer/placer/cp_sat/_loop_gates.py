"""Gate management mixin for the place-route loop controller.

Extracted from ``loop.py``: gate registration, checking, delta
collection, UNMEASURED tracking, and board-state assembly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from temper_placer.placer.cp_sat.feedback import ConstraintDelta
    from temper_placer.placer.cp_sat.gates import BoardState

from temper_placer.placer.cp_sat._loop_types import (
    LoopExitReason,
    LoopResult,
    RoundRecord,
)

logger = logging.getLogger(__name__)


class _LoopGatesMixin:
    """Gate inspection and management methods for PlaceRouteLoop.

    Covers: gate registry checks, UNMEASURED streak tracking,
    corrective delta collection, surface escalation, and
    board-state assembly for gate consumption.
    """

    def _all_gates_green_results(self) -> bool:
        """Return True iff every gate in ``_gate_results`` is CLEAN.

        Uses cached results from ``check()`` calls; does not re-run
        gates.  An UNMEASURED gate is never green (core invariant).
        """
        from temper_placer.placer.cp_sat.gates import GateStatus

        return all(r.status is GateStatus.CLEAN for r in self._gate_results.values())

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
        from temper_placer.placer.cp_sat.gates import GateResult, GateStatus

        self._gate_results = {}
        for gate in self.gates:
            try:
                result = gate.check(state)
            except Exception as exc:
                logger.error(
                    "Gate %s check raised: %s",
                    gate.name,
                    exc,
                )
                result = GateResult(
                    GateStatus.UNMEASURED,
                    error_message=f"Gate check raised: {exc}",
                )
            self._gate_results[gate.name] = result
            if result.status is GateStatus.UNMEASURED:
                logger.error(
                    "Gate %s UNMEASURED: %s",
                    gate.name,
                    result.error_message,
                )

        return all(r.status is GateStatus.CLEAN for r in self._gate_results.values())

    def _track_unmeasured(self, gate, result) -> None:
        """Increment or reset the UNMEASURED streak for *gate*.

        A gate that measures this round resets its streak to 0.
        A gate that returns UNMEASURED increments by 1 and logs
        the error.
        """
        from temper_placer.placer.cp_sat.gates import GateStatus

        name = gate.name
        if result.status is GateStatus.UNMEASURED:
            self._unmeasured_streak[name] = self._unmeasured_streak.get(name, 0) + 1
            self._surface(
                f"Gate {name} UNMEASURED (streak "
                f"{self._unmeasured_streak[name]}): "
                f"{result.error_message}"
            )
        else:
            self._unmeasured_streak[name] = 0

    def _check_unmeasured_exit(
        self,
        round_num: int,
        placement,
        routing,
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
                msg = result.error_message if result is not None else ""
                logger.error(
                    "Gate %s UNMEASURED for %d rounds; exiting. Message: %s",
                    name,
                    streak,
                    msg,
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
                        name: msg for name, streak in self._unmeasured_streak.items() if streak >= 3
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
        from temper_placer.placer.cp_sat.gates import BoardState as _BS

        design_rules = None
        netclass_rules = getattr(self, "_netclass_rules", None)
        if netclass_rules is not None:
            design_rules = getattr(netclass_rules, "design_rules", None)

        routed_pcb_path = routed_pcb_path_override
        if routed_pcb_path is None and routing is not None:
            routed_pcb_path = getattr(routing, "routed_pcb_path", None)
            if isinstance(routed_pcb_path, str):
                from pathlib import Path as _Path

                routed_pcb_path = _Path(routed_pcb_path)

        return _BS(
            placement=placement,
            routing=routing,
            netlist=netlist,
            board=board,
            design_rules=design_rules,
            routed_pcb_path=routed_pcb_path,
        )

    def _gates_for_stage(self, gates: list, stage) -> list:
        """Return gates from *gates* registered for the given stage."""
        return [g for g in gates if g.stage is stage]

    def _collect_deltas_from_gates(
        self,
        gates: list | None = None,
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
                        gate.name,
                        violation.type.value,
                    )

        deltas.sort(key=lambda d: d.priority)
        return deltas
