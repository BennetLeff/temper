"""Typed failures raised while compiling placement constraints.

This module deliberately has no imports from the encoder or handler packages.
Both sides of the dispatch boundary can therefore report the same error
without introducing an import cycle.
"""

from __future__ import annotations


class CpSatConstraintCompilationError(ValueError):
    """Base error for a constraint that cannot be encoded safely."""


class UnresolvedConstraintRefsError(CpSatConstraintCompilationError):
    """A constraint names a component, zone, or loop absent from the model."""

