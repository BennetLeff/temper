"""Data types for the Place→Route loop controller.

Extracted from ``loop.py`` to separate the pure-data layer from
the orchestration logic.  All types are re-exported through
``loop.py`` for backward-compatible import paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.feedback import ConstraintDelta


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
