"""PCL-to-CP-SAT constraint encoder.

Maps all PCL constraint types to CP-SAT model constraints using the explicit,
validated handler table owned by ``cp_sat.handlers``.

Each handler returns a list of assumption literals for UNSAT-core extraction.

Public API re-exports from internal modules:
  _encoder_core  → EncoderContext, encode_constraints,
                    UnresolvedConstraintRefsError, validate_constraint_refs,
                    reconcile_constraint_refs, reconcile_loop_components,
                    ReferenceReconciliation, LoopReferenceReconciliation,
                    UNSUPPORTED_TYPES, _resolve_refs,
                    _generate_courtyard_separated_constraints,
                    AssumptionLiteral
  _encoder_solve → CpSatPlacementResult, solve_placement,
                    _resolve_loop_components
"""

from temper_placer.placer.cp_sat._encoder_core import (
    UNSUPPORTED_TYPES,
    AssumptionLiteral,
    EncoderContext,
    LoopReferenceReconciliation,
    ReferenceReconciliation,
    UnresolvedConstraintRefsError,
    _generate_courtyard_separated_constraints,
    _resolve_refs,
    encode_constraints,
    reconcile_constraint_refs,
    reconcile_loop_components,
    validate_constraint_refs,
)
from temper_placer.placer.cp_sat._encoder_solve import (
    CpSatPlacementResult,
    _resolve_loop_components,
    solve_placement,
)
from temper_placer.placer.cp_sat.errors import CpSatConstraintCompilationError

__all__ = [
    "AssumptionLiteral",
    "CpSatPlacementResult",
    "CpSatConstraintCompilationError",
    "EncoderContext",
    "LoopReferenceReconciliation",
    "ReferenceReconciliation",
    "UNSUPPORTED_TYPES",
    "UnresolvedConstraintRefsError",
    "_generate_courtyard_separated_constraints",
    "_resolve_loop_components",
    "_resolve_refs",
    "encode_constraints",
    "reconcile_constraint_refs",
    "reconcile_loop_components",
    "solve_placement",
    "validate_constraint_refs",
]
