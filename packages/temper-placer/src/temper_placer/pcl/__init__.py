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

    Parser functions:
        - parse_pcl_file: Load constraints from YAML file
        - parse_constraint_dict: Parse single constraint from dict
        - load_pcl_collection: Load all YAML files from directory

    Collections:
        - ConstraintCollection: Collection with validation methods

    Exceptions:
        - PCLParseError: Error parsing constraint definition
        - PCLValidationError: Error validating references

    Tier system:
        - EscalationReason: Why constraint was escalated
        - ConstraintStatus: Runtime status with violation history
        - EscalationConfig: Configuration for escalation behavior
        - TieredConstraintManager: Manages tiers during optimization
        - calculate_penalty: Penalty calculation by tier
        - check_hard_constraints: Verify hard constraints satisfied

Example:
    >>> from temper_placer.pcl import AdjacentConstraint, ConstraintTier, parse_pcl_file
    >>>
    >>> # Create constraint directly
    >>> constraint = AdjacentConstraint(
    ...     a="Q1", b="Q2",
    ...     max_distance_mm=10.0,
    ...     tier=ConstraintTier.HARD,
    ...     because="Minimize commutation loop for half-bridge"
    ... )
    >>>
    >>> # Or load from YAML
    >>> collection = parse_pcl_file("constraints.yaml")
    >>> print(len(collection))
    12
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

from .parser import (
    # Parser functions
    parse_pcl_file,
    parse_constraint_dict,
    load_pcl_collection,
    # Collection class
    ConstraintCollection,
    # Exceptions
    PCLParseError,
    PCLValidationError,
)

from .tiers import (
    # Tier system
    EscalationReason,
    ConstraintStatus,
    EscalationConfig,
    TieredConstraintManager,
    calculate_penalty,
    check_hard_constraints,
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
    # Parser functions
    "parse_pcl_file",
    "parse_constraint_dict",
    "load_pcl_collection",
    # Collection class
    "ConstraintCollection",
    # Exceptions
    "PCLParseError",
    "PCLValidationError",
    # Tier system
    "EscalationReason",
    "ConstraintStatus",
    "EscalationConfig",
    "TieredConstraintManager",
    "calculate_penalty",
    "check_hard_constraints",
]
