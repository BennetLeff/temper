"""
Constraint compilation and validation for deterministic placement.

This module transforms declarative constraints (from YAML) into executable
filter and scorer functions used by the placement engine.
"""

from .compiler import ConstraintCompiler, ValidationError
from .reporter import (
    ConstraintReporter,
    ConstraintReport,
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
]
