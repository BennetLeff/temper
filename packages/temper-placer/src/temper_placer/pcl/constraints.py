"""
Placement Constraint Language (PCL) data structures.

This module defines the constraint language for expressing topological placement
requirements with mandatory rationale and tiered priorities. Constraints express
designer intent in a declarative way that translates to differentiable loss functions.

The PCL supports:
- Adjacency constraints (keep components close)
- Separation constraints (keep components apart)
- Enclosing constraints (component must be inside zone)
- Alignment constraints (align components on axis)
- Edge placement constraints (component on board edge)
- Anchoring constraints (component at specific position)
- Loop area constraints (limit current loop area)

Every constraint requires a 'because' field explaining the rationale (electrical,
thermal, EMI, safety, etc.). This ensures explainability and helps future maintainers
understand why constraints exist.

Example usage:
    >>> from temper_placer.pcl.constraints import (
    ...     AdjacentConstraint, ConstraintTier, DistanceMetric
    ... )
    >>>
    >>> # Critical adjacency for half-bridge
    >>> constraint = AdjacentConstraint(
    ...     a="Q1",
    ...     b="Q2",
    ...     max_distance_mm=10.0,
    ...     metric=DistanceMetric.EDGE_TO_EDGE,
    ...     tier=ConstraintTier.HARD,
    ...     because="Half-bridge pair must be close to minimize commutation loop area"
    ... )
    >>>
    >>> constraint.involves_component("Q1")
    True

The eight constraint classes and ``CompilationContext`` are pyo3 contract
objects implemented in the ``temper-constraint-compiler`` crate
(``src/pcl_contracts.rs``) — the Wave 4 Phase 2/6 "contracts-as-pyo3-pyclasses"
pivot. Construction validation, id generation, ``involves_component``,
``to_dict``, ``escalate`` and the dataclass-style ``repr``/``==``/``hash``
surface run in Rust; this module is the delegation shim that keeps every
existing import path working.

The value enums (``ConstraintType``, ``DistanceMetric``,
``Axis``, ``BoardSide``, ``EdgeType``, ``CompilationTarget``, ``SemanticTag``)
stay Python ``enum.Enum``: production does ``for t in ConstraintType`` and
``ConstraintType(value)``, which a ``#[pyclass]`` enum cannot provide.
``ConstraintTier`` is a Rust pyclass (it has no class-level iteration
anywhere — the one enum that IS tractable). The Rust objects hold the LIVE
singletons/Python enum members and hand them back through the getters.

``BaseConstraint`` stays Python. It is the ABC the tagged-constraint classes
subclass, and its ``backends`` registry is populated at import time by
``sat_bridge.py`` and dispatched by ``parser.py`` — the
Phase-1 ortools-encoder KEEP slice. The migrated pyclasses are registered as
*virtual* subclasses so ``isinstance(c, BaseConstraint)`` keeps holding.

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/pcl/test_constraints_rust_differential.py`` (the oracle is pinned
verbatim as deterministic dataclasses in that file); the structural argument
lives in ``packages/temper-constraint-compiler/VERIFICATION.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import temper_constraint_compiler as _rust

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    from temper_placer.router_v6.channel_widths import ChannelWidths
    from temper_placer.router_v6.stage0_data import DesignRules


class CompilationTarget(Enum):
    """Backend targets for constraint compilation."""

    JAX = "jax"
    SAT = "sat"
    DRC = "drc"
    CP_SAT = "cp_sat"


class SemanticTag(Enum):
    """Semantic capabilities of constraint types.

    Used by downstream compilers to select grounding strategies
    without type-specific dispatch. New constraint types auto-gain
    SAT/DRC grounding via these tags.
    """

    SEPARATION = "separation"
    PROXIMITY = "proximity"
    ORDERING = "ordering"
    ZONING = "zoning"
    ALIGNMENT = "alignment"


ConstraintTier = _rust.ConstraintTier
"""Priority tier for a constraint (HARD=1, STRONG=2, SOFT=3).

Migrated to the Rust ``ConstraintTier`` pyclass in
``temper-constraint-compiler`` (``src/pcl_contracts.rs``) — Wave 4,
tractable-slice unit. The pre-migration Python ``Enum`` is pinned in
``tests/pcl/test_constraints_rust_differential.py`` as the ``_oracle_*``
reference.

Differences from a Python ``Enum``:
- Members are not singletons: ``ConstraintTier.HARD is ConstraintTier.HARD``
  is False (pyo3 limitation — each attribute lookup returns a fresh wrapper).
  Use ``==`` for comparisons.
- There is no class-level iteration: ``for t in ConstraintTier`` fails. No
  in-repo consumer iterates ``ConstraintTier``.

Every other semantic (value/name/str/repr/==/hash/dict-key) is preserved.
"""


class ConstraintType(Enum):
    """Types of topological constraints supported by PCL.

    Each member carries (value, capabilities, supported_targets) as a 3-tuple.
    Use .value for the string form, .capabilities and .supported_targets
    for semantic dispatch.
    """

    ADJACENT = (
        "adjacent",
        frozenset({SemanticTag.PROXIMITY}),
        frozenset(
            {
                CompilationTarget.JAX,
                CompilationTarget.SAT,
                CompilationTarget.DRC,
                CompilationTarget.CP_SAT,
            }
        ),
    )
    SEPARATED = (
        "separated",
        frozenset({SemanticTag.SEPARATION, SemanticTag.ORDERING}),
        frozenset(
            {
                CompilationTarget.JAX,
                CompilationTarget.SAT,
                CompilationTarget.DRC,
                CompilationTarget.CP_SAT,
            }
        ),
    )
    ENCLOSING = (
        "enclosing",
        frozenset({SemanticTag.ZONING}),
        frozenset(
            {
                CompilationTarget.JAX,
                CompilationTarget.SAT,
                CompilationTarget.DRC,
                CompilationTarget.CP_SAT,
            }
        ),
    )
    KEEPOUT = (
        "keepout",
        frozenset({SemanticTag.ZONING, SemanticTag.SEPARATION}),
        frozenset({CompilationTarget.JAX, CompilationTarget.DRC}),
    )
    ALIGNED = (
        "aligned",
        frozenset({SemanticTag.ALIGNMENT}),
        frozenset({CompilationTarget.JAX, CompilationTarget.DRC}),
    )
    ON_SIDE = (
        "on_side",
        frozenset({SemanticTag.ZONING}),
        frozenset(
            {
                CompilationTarget.JAX,
                CompilationTarget.SAT,
                CompilationTarget.DRC,
                CompilationTarget.CP_SAT,
            }
        ),
    )
    ANCHORED = (
        "anchored",
        frozenset({SemanticTag.ZONING}),
        frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}),
    )
    LOOP_AREA = (
        "loop_area",
        frozenset({SemanticTag.PROXIMITY, SemanticTag.ORDERING}),
        frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}),
    )

    @property
    def label(self) -> str:
        """Return the string label (backward-compatible with old .value)."""
        return self._value_[0]

    @property
    def value(self) -> str:  # type: ignore[override]
        """Return the string label for serialization. Overrides Enum.value."""
        return self._value_[0]

    @property
    def capabilities(self) -> frozenset[SemanticTag]:
        """Semantic tags for capability-based dispatch."""
        return self._value_[1]

    @property
    def supported_targets(self) -> frozenset[CompilationTarget]:
        """Compilation targets this type supports."""
        return self._value_[2]


class DistanceMetric(Enum):
    """How to measure distance between components."""

    EDGE_TO_EDGE = "edge_to_edge"  # Closest point distance (default)
    CENTER_TO_CENTER = "center_to_center"  # Centroid distance
    PIN_TO_PIN = "pin_to_pin"  # Specific pin-to-pin distance


class Axis(Enum):
    """Axis for alignment constraints."""

    X = "x"  # Horizontal alignment
    Y = "y"  # Vertical alignment
    MAJOR = "major"  # Align along major component axis
    MINOR = "minor"  # Align along minor component axis


class BoardSide(Enum):
    """Board edge sides for placement."""

    TOP = "top"  # +Y edge
    BOTTOM = "bottom"  # -Y edge
    LEFT = "left"  # -X edge
    RIGHT = "right"  # +X edge


class EdgeType(Enum):
    """How component relates to board edge."""

    FLUSH = "flush"  # Component flush against edge
    NEAR = "near"  # Component near edge (within threshold)
    OVERHANG = "overhang"  # Component can overhang edge (connectors)


@dataclass
class BaseConstraint(ABC):
    """Base class for all PCL constraints.

    Every constraint must have:
    - constraint_type: The type of constraint
    - tier: Priority level (HARD/STRONG/SOFT)
    - because: Mandatory rationale (≥10 characters)
    - id: Optional unique identifier for debugging
    - targets: Compilation targets (default ["jax"])

    Subclasses implement specific constraint logic.
    """

    constraint_type: ConstraintType
    tier: ConstraintTier
    because: str
    id: str = ""
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __post_init__(self):
        """Validate constraint fields."""
        if len(self.because) < 10:
            raise ValueError(
                f"Rationale 'because' must be ≥10 chars, got {len(self.because)}: '{self.because}'"
            )

        # Validate targets against CompilationTarget values
        valid_targets = {t.value for t in CompilationTarget}
        for t in self.targets:
            if t not in valid_targets:
                raise ValueError(
                    f"Invalid compilation target '{t}'. Must be one of {sorted(valid_targets)}"
                )

        # Auto-generate ID if not provided
        if not self.id:
            self.id = self._generate_id()

    @abstractmethod
    def _generate_id(self) -> str:
        """Generate a unique ID for this constraint."""
        pass

    @abstractmethod
    def involves_component(self, component: str) -> bool:
        """Check if this constraint involves the given component."""
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        """Convert constraint to dictionary for serialization."""
        pass

    def escalate(self) -> None:
        """Escalate the constraint to the next tier.

        SOFT -> STRONG -> HARD
        """
        if self.tier == ConstraintTier.SOFT:
            self.tier = ConstraintTier.STRONG
        elif self.tier == ConstraintTier.STRONG:
            self.tier = ConstraintTier.HARD


# Class-level backend registry shared across all constraint instances.
# Each key maps a CompilationTarget.value string to a callable
# (constraint, context) -> backend_output.
# Populated by bridge modules at import time (lazy registration).
BaseConstraint.backends: dict[str, Callable] = {}  # type: ignore[attr-defined, misc]


# The constraint objects and CompilationContext are pyo3 contract classes in
# temper-constraint-compiler (src/pcl_contracts.rs). Re-exported under their
# original names so every existing `from temper_placer.pcl.constraints import
# AdjacentConstraint` keeps working.
AdjacentConstraint = _rust.AdjacentConstraint
SeparatedConstraint = _rust.SeparatedConstraint
EnclosingConstraint = _rust.EnclosingConstraint
KeepoutConstraint = _rust.KeepoutConstraint
AlignedConstraint = _rust.AlignedConstraint
OnSideConstraint = _rust.OnSideConstraint
AnchoredConstraint = _rust.AnchoredConstraint
LoopAreaConstraint = _rust.LoopAreaConstraint
CompilationContext = _rust.CompilationContext

# The migrated pyclasses are not *real* subclasses of the Python
# BaseConstraint (pyo3 classes cannot inherit an arbitrary Python base), but
# `isinstance(c, BaseConstraint)` is load-bearing (test_feedback asserts it
# on every feedback delta; the tagged-constraint classes subclass
# BaseConstraint directly). Register them as virtual subclasses so the ABC's
# isinstance/issubclass checks keep holding for the migrated objects.
BaseConstraint.register(AdjacentConstraint)  # type: ignore[arg-type]
BaseConstraint.register(SeparatedConstraint)  # type: ignore[arg-type]
BaseConstraint.register(EnclosingConstraint)  # type: ignore[arg-type]
BaseConstraint.register(KeepoutConstraint)  # type: ignore[arg-type]
BaseConstraint.register(AlignedConstraint)  # type: ignore[arg-type]
BaseConstraint.register(OnSideConstraint)  # type: ignore[arg-type]
BaseConstraint.register(AnchoredConstraint)  # type: ignore[arg-type]
BaseConstraint.register(LoopAreaConstraint)  # type: ignore[arg-type]
