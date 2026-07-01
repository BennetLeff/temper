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
    # Constraint types
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    # Base class
    BaseConstraint,
    BoardSide,
    CompilationContext,
    CompilationTarget,
    # Enums
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
    EdgeType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SemanticTag,
    SeparatedConstraint,
)
from .tag_dispatch import (
    ComponentRef,
    ComponentTag,
    TagAnd,
    TagExpr,
    TagNot,
    TagOr,
    TagRef,
    TagValidationError,
    components as tag_components,
    resolve as tag_resolve,
)
from .tagged_constraints import (
    TaggedAdjacentConstraint,
    TaggedAlignedConstraint,
    TaggedAnchoredConstraint,
    TaggedEnclosingConstraint,
    TaggedOnSideConstraint,
    TaggedSeparatedConstraint,
)
from .parser import (
    # Collection class
    ConstraintCollection,
    # Exceptions
    PCLParseError,
    PCLValidationError,
    load_pcl_collection,
    parse_constraint_dict,
    # Parser functions
    parse_pcl_file,
)
from .tiers import (
    ConstraintStatus,
    EscalationConfig,
    # Tier system
    EscalationReason,
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
    "KeepoutConstraint",
    "AlignedConstraint",
    "OnSideConstraint",
    "AnchoredConstraint",
    "LoopAreaConstraint",
    # Tagged constraint types
    "TaggedAdjacentConstraint",
    "TaggedSeparatedConstraint",
    "TaggedEnclosingConstraint",
    "TaggedAlignedConstraint",
    "TaggedOnSideConstraint",
    "TaggedAnchoredConstraint",
    # Tags
    "ComponentTag",
    "TagRef",
    "TagAnd",
    "TagOr",
    "TagNot",
    "ComponentRef",
    "TagExpr",
    "TagValidationError",
    "tag_resolve",
    "tag_components",
    # Enums
    "CompilationTarget",
    "SemanticTag",
    "ConstraintTier",
    "ConstraintType",
    "DistanceMetric",
    "Axis",
    "BoardSide",
    "EdgeType",
    # Context
    "CompilationContext",
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
