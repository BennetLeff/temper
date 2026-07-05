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
    TYPE_HANDLERS,
    UNSUPPORTED_TYPES,
    EncoderContext,
    encode_constraints,
)
from temper_placer.placer.cp_sat.gate import AcceptanceGate
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
    "CpSatModel",
    "CpSolverSolution",
    "EncoderContext",
    "Placement",
    "PlacementAuditor",
    "SolveStatus",
    "TYPE_HANDLERS",
    "UNSUPPORTED_TYPES",
    "encode_constraints",
]
