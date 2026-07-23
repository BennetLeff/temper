"""Place→Route Loop Controller.

Orchestrates the round-trip: place → route → measure → classify → re-place.

Public API re-exports from internal modules:
  _loop_types     → LoopExitReason, LoopResult, RoundRecord, UnsatError
  _loop_core      → _LoopCoreMixin
  _loop_routing   → _LoopRoutingMixin, _build_minimal_pcb
  _loop_gates     → _LoopGatesMixin
  _loop_stability → _LoopStabilityMixin
"""

from __future__ import annotations

import logging

from temper_placer.placer.cp_sat._loop_core import _LoopCoreMixin
from temper_placer.placer.cp_sat._loop_gates import _LoopGatesMixin
from temper_placer.placer.cp_sat._loop_routing import (
    _LoopRoutingMixin,
)
from temper_placer.placer.cp_sat._loop_stability import _LoopStabilityMixin
from temper_placer.placer.cp_sat._loop_types import (
    LoopExitReason,
    LoopResult,
    RoundRecord,
    UnsatError,
)

logger = logging.getLogger(__name__)


class PlaceRouteLoop(
    _LoopCoreMixin,
    _LoopRoutingMixin,
    _LoopGatesMixin,
    _LoopStabilityMixin,
):
    """Orchestrates the place→route feedback loop."""

    MAX_ROUNDS: int = 10
    STABILITY_ROUNDS: int = 2
    RE_SOLVE_TIMEOUT_MS: int = 1000
    INITIAL_SOLVE_TIMEOUT_MS: int = 30000
    OSCILLATION_WINDOW: int = 3
    FIELD_EPSILON: float = 0.5
    FIELD_OSCILLATION_WINDOW: int = 4
    FIELD_CONVERGENCE_ROUND_LIMIT: int = 8

    def __init__(
        self,
        classifier=None,
        gates=None,
        field_compute_fn=None,
        thermal_weight=0.0,
        _placement_solver=None,
    ):
        if classifier is None:
            from temper_placer.placer.cp_sat.feedback import FeedbackClassifier

            classifier = FeedbackClassifier()
        self.classifier = classifier

        self._gates_explicit = bool(gates)
        if gates is None:
            from temper_placer.placer.cp_sat.gates import DrcGate, RoutingGate

            self.gates = [DrcGate(), RoutingGate()]
        else:
            self.gates = list(gates)

        self._gate_results = {}
        self._unmeasured_streak = {}
        self._surfaced = []

        self._field_compute_fn = field_compute_fn
        self._thermal_weight = thermal_weight
        self._field_history = []
        self._field_stability_counter = 0
        self._field_round_counter = 0
        self._solve_times_history = []
        self._placement_solver = _placement_solver


__all__ = [
    "LoopExitReason",
    "LoopResult",
    "PlaceRouteLoop",
    "RoundRecord",
    "UnsatError",
]
