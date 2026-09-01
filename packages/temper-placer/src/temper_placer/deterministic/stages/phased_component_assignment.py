"""Phased component assignment using priority-based placement.

Implementation is a single internal module ``_phase_core.py`` holding the
four mixins (collapsed 2026-08-20; previously split across
``_phase_core`` / ``_phase_zones`` / ``_phase_rotation`` /
``_phase_validation``):
- _phase_core.py — orchestration (_PhaseCoreMixin)
- placement methods (_PhasePlacementMixin)
- HV creepage (_PhaseHVMixin)
- bottleneck validation (_PhaseValidationMixin)
"""

from __future__ import annotations

from ._phase_core import (
    CRITICAL_BOTTLENECK_INVARIANT,
    PhasedComponentAssignmentError,
    _PhaseCoreMixin,
    _PhaseHVMixin,
    _PhasePlacementMixin,
    _PhaseValidationMixin,
)
from .base import Stage


class PhasedComponentAssignmentStage(
    _PhaseCoreMixin,
    _PhasePlacementMixin,
    _PhaseHVMixin,
    _PhaseValidationMixin,
    Stage,
):
    """Phased component placement using placement_priority configuration.

    Phases are executed in order:
      1. Fixed/Template - Use explicit positions or templates
      2. Proximity - Place near reference components
      3. Optimize - Constraint-aware greedy placement
      4. Auto - Fill remaining components

    Each phase uses:
      - ConstraintCompiler.filter for hard constraints
      - ConstraintCompiler.scorer for soft constraints
      - HPWL wirelength minimization
    """


__all__ = [
    "CRITICAL_BOTTLENECK_INVARIANT",
    "PhasedComponentAssignmentError",
    "PhasedComponentAssignmentStage",
]
