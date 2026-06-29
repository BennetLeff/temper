"""
Constraint compilation and validation for deterministic placement.

This module transforms declarative constraints (from YAML) into executable
filter and scorer functions used by the placement engine.
"""

from .builder import ConstraintBuilder
from .compiler import ConstraintCompiler, ValidationError
from .reporter import (
    ConstraintReport,
    ConstraintReporter,
    ConstraintResult,
    ConstraintStatus,
)

__all__ = [
    "ConstraintCompiler",
    "ValidationError",
    "ConstraintReporter",
    "ConstraintReport",
    "ConstraintResult",
    "ConstraintStatus",
    "ConstraintBuilder",
]
