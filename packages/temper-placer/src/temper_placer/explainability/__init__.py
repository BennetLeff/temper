"""Explainability module for temper-placer.

This module provides auditable decision tracking for placement and routing.
Every decision the placer makes can be traced back to its reason.

Key Components:
- Decision: Single auditable decision with reason and alternatives
- DecisionTrace: Complete audit trail for a pipeline run
- DecisionType: Types of decisions (placement, rotation, constraint, etc.)
- DecisionPhase: Pipeline phases (semantic, topological, geometric, routing)

Example:
    >>> from temper_placer.explainability import Decision, DecisionTrace, DecisionType, DecisionPhase
    >>> trace = DecisionTrace()
    >>> trace.add(Decision(
    ...     decision_type=DecisionType.INITIAL_POSITION,
    ...     phase=DecisionPhase.GEOMETRIC,
    ...     subject='Q1',
    ...     value=(45.2, 12.3),
    ...     reason='Thermal edge constraint requires IGBT within 5mm of top edge'
    ... ))
    >>> print(trace.why('Q1'))
    Q1 is at (45.2, 12.3) because: Thermal edge constraint requires IGBT within 5mm of top edge
"""

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)

__all__ = [
    "Alternative",
    "Decision",
    "DecisionPhase",
    "DecisionTrace",
    "DecisionType",
]
