"""Stability and field detection mixin for the place-route loop.

Extracted from ``loop.py``: oscillation detection, convergence counting,
continuous-field (U9) stability/cycle checks, solve-time trend monitoring,
and UNSAT core extraction.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat._loop_types import RoundRecord
    from temper_placer.placer.cp_sat.feedback import (
        ClassificationResult,
        ConstraintDelta,
    )

from temper_placer.placer.cp_sat._loop_utils import positions_equal

logger = logging.getLogger(__name__)


class _LoopStabilityMixin:
    """Stability, oscillation, and field-detection methods.

    Covers: placement oscillation detection, round stability counting,
    U9 continuous-field convergence (stability, cycle detection), and
    solve-time trend diagnostics.
    """

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

        positions = getattr(placement, "positions", None)
        if positions is None:
            return False

        recent = history[-self.OSCILLATION_WINDOW :]
        recent_positions = [getattr(p, "positions", None) for p in recent]

        for rp in recent_positions:
            if rp is None:
                return False
            if positions_equal(positions, rp):
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
            from temper_placer.fields.result import FieldResult
            from temper_placer.placer.cp_sat.gates import GateResult, GateStatus

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
        window — EXCLUDING the immediately-preceding round — within
        epsilon, it is a cycle.  A match against the immediately-
        preceding round is *stability* (monotone convergence), not a
        cycle, and is handled by ``_check_field_stability``; including it
        here would kill a slowly-converging field as a false oscillation.
        A genuine cycle repeats a state ≥2 rounds back (period-2 → [-2],
        period-4 → [-4]).
        """
        import numpy as np

        if len(self._field_history) < self.FIELD_OSCILLATION_WINDOW:
            return False
        # Exclude the immediately-preceding entry ([-1]) — that is stability.
        recent = self._field_history[-self.FIELD_OSCILLATION_WINDOW : -1]
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
                recent[0],
                recent[1],
                recent[2],
            )

    # -------------------------------------------------------------------
    # UNSAT core extraction
    # -------------------------------------------------------------------

    def _extract_unsat_core(
        self,
        injected_deltas: list[ConstraintDelta],
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
                {"reason": d.reason, "type": type(d.constraint).__name__} for d in injected_deltas
            ],
        }
