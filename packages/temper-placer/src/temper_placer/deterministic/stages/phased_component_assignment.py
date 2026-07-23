"""Phased component assignment using priority-based placement.

Implementation decomposed across internal mixin modules:
- _phase_core.py — orchestration (_PhaseCoreMixin)
- _phase_zones.py — placement methods (_PhasePlacementMixin)
- _phase_rotation.py — HV creepage (_PhaseHVMixin)
- _phase_validation.py — bottleneck validation (_PhaseValidationMixin)
"""

from __future__ import annotations

from ._phase_core import (
    CRITICAL_BOTTLENECK_INVARIANT,
    PhasedComponentAssignmentError,
    _PhaseCoreMixin,
)
from ._phase_rotation import _PhaseHVMixin
from ._phase_validation import _PhaseValidationMixin
from ._phase_zones import _PhasePlacementMixin
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
