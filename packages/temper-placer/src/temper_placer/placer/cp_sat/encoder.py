"""PCL-to-CP-SAT constraint encoder.

Maps all PCL constraint types to CP-SAT model constraints using a
HANDLER_REGISTRY dispatch pattern mirroring sat_bridge.py.

Each handler returns a list of assumption literals for UNSAT-core extraction.

Public API re-exports from internal modules:
  _encoder_core  → EncoderContext, encode_constraints,
                    UnresolvedConstraintRefsError, validate_constraint_refs,
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
    UnresolvedConstraintRefsError,
    _generate_courtyard_separated_constraints,
    _resolve_refs,
    encode_constraints,
    validate_constraint_refs,
)
from temper_placer.placer.cp_sat._encoder_solve import (
    CpSatPlacementResult,
    _resolve_loop_components,
    solve_placement,
)

__all__ = [
    "AssumptionLiteral",
    "CpSatPlacementResult",
    "EncoderContext",
    "UNSUPPORTED_TYPES",
    "UnresolvedConstraintRefsError",
    "_generate_courtyard_separated_constraints",
    "_resolve_loop_components",
    "_resolve_refs",
    "encode_constraints",
    "solve_placement",
    "validate_constraint_refs",
]
