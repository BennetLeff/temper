"""
Placement Constraint Language (PCL) module.

The PCL provides a declarative way to express topological placement requirements
with mandatory rationale and tiered priorities. Constraints translate to
differentiable loss functions for gradient-based optimization.

Public API:
    Constraint types:
        - AdjacentConstraint: Keep components close
        - SeparatedConstraint: Keep components apart
        - EnclosingConstraint: Components inside zone
        - AlignedConstraint: Align components on axis
        - OnSideConstraint: Components on board edge
        - AnchoredConstraint: Component at specific position
        - LoopAreaConstraint: Limit current loop area

    Enums:
        - ConstraintTier: HARD, STRONG, SOFT
        - ConstraintType: ADJACENT, SEPARATED, etc.
        - DistanceMetric: EDGE_TO_EDGE, CENTER_TO_CENTER, PIN_TO_PIN
        - Axis: X, Y, MAJOR, MINOR
        - BoardSide: TOP, BOTTOM, LEFT, RIGHT
        - EdgeType: FLUSH, NEAR, OVERHANG

    Base class:
        - BaseConstraint: Abstract base for all constraints

Example:
    >>> from temper_placer.pcl import AdjacentConstraint, ConstraintTier
    >>> constraint = AdjacentConstraint(
    ...     a="Q1", b="Q2",
    ...     max_distance_mm=10.0,
    ...     tier=ConstraintTier.HARD,
    ...     because="Minimize commutation loop for half-bridge"
    ... )
"""

from .constraints import (
    # Base class
    BaseConstraint,
    # Constraint types
    AdjacentConstraint,
    SeparatedConstraint,
    EnclosingConstraint,
    AlignedConstraint,
    OnSideConstraint,
    AnchoredConstraint,
    LoopAreaConstraint,
    # Enums
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
    Axis,
    BoardSide,
    EdgeType,
)

__all__ = [
    # Base class
    "BaseConstraint",
    # Constraint types
    "AdjacentConstraint",
    "SeparatedConstraint",
    "EnclosingConstraint",
    "AlignedConstraint",
    "OnSideConstraint",
    "AnchoredConstraint",
    "LoopAreaConstraint",
    # Enums
    "ConstraintTier",
    "ConstraintType",
    "DistanceMetric",
    "Axis",
    "BoardSide",
    "EdgeType",
]
