"""CP-SAT constraint encoder for PCL constraint types.

Public API surface for the CP-SAT placement solver module.
"""

from temper_placer.placer.cp_sat.audit import (
    AuditReport,
    AuditViolation,
    Placement,
    PlacementAuditor,
)
from temper_placer.placer.cp_sat.encoder import (
    UNSUPPORTED_TYPES,
    CpSatPlacementResult,
    EncoderContext,
    encode_constraints,
    solve_placement,
)
from temper_placer.placer.cp_sat.feedback import ConstraintDelta, FeedbackClassifier
from temper_placer.placer.cp_sat.gate import AcceptanceGate
from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY
from temper_placer.placer.cp_sat.loop import LoopResult, PlaceRouteLoop
from temper_placer.placer.cp_sat.model import (
    ComponentVars,
    CpSatModel,
    CpSolverSolution,
    SolveStatus,
)

__all__ = [
    "AcceptanceGate",
    "AuditReport",
    "AuditViolation",
    "ComponentVars",
    "ConstraintDelta",
    "CpSatPlacementResult",
    "CpSatModel",
    "CpSolverSolution",
    "EncoderContext",
    "FeedbackClassifier",
    "LoopResult",
    "PlaceRouteLoop",
    "Placement",
    "PlacementAuditor",
    "SolveStatus",
    "solve_placement",
    "HANDLER_REGISTRY",
    "UNSUPPORTED_TYPES",
    "encode_constraints",
]
