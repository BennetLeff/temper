"""R1a differential: Rust PCL constraint-contract pyclasses vs the pinned oracle.

Wave 4, Phase 2/6 -- the ``temper_placer/pcl/constraints.py`` pure-data
contracts migrate to pyo3 pyclasses in ``temper-constraint-compiler``
(``src/pcl_contracts.rs``): the eight constraint classes' data surface, plus
``CompilationContext``. The pre-migration implementation is pinned verbatim in
the ORACLE block below (the six value enums, ``CompilationTarget``,
``SemanticTag``, ``ConstraintType``, ``CompilationContext``,
``BaseConstraint``, and the eight constraint classes).

One documented, mechanical transformation: the pre-migration constraint
classes were *plain* classes whose ``repr()`` was the address-dependent
``<... object at 0x...>`` form -- not a pin-able contract. The migrated
pyclasses provide a deterministic dataclass-style ``repr()``, so the oracle
re-declares the eight classes as ``@dataclass(unsafe_hash=True)`` with the
same fields in the same order and their ``__init__`` / method bodies copied
VERBATIM. ``BaseConstraint`` (oracle) is re-written as a plain ABC with a
manual ``__init__`` (the dataclass form cannot host non-default subclass
fields); its ``__post_init__`` validation, ``escalate`` and abstract surface
are verbatim. ``CompilationContext`` was already a dataclass and is copied
as-is.

Enum identity is asserted against the LIVE ``temper_placer.pcl.constraints``
enums: the migrated classes must hand back the very same singletons the rest
of the tree binds against (``unsat_compiler`` compares ``c.tier ==
ConstraintTier.HARD``; ``sat_bridge`` keys on ``constraint.constraint_type``).

The encoder registry (``BaseConstraint.backends``) and ``BaseConstraint``
itself stay Python (the tagged-constraint subclasses and the
sat bridge registration are the Phase-1 ortools-encoder KEEP slice);
the differential pins that the registry survives and that the migrated
classes are still ``isinstance``-compatible with ``BaseConstraint``.

Comparison is by type-carrying signature (``_pclsig``); exceptions compare by
qualname + exact message.
"""

from __future__ import annotations

import copy
import pickle
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pytest
from tests.pcl._pclsig import assert_same, call_signature

from temper_placer.pcl import constraints as live

# The SAT bridge registers into BaseConstraint.backends at import time;
# pull it in so the registry is populated exactly as in production.
from temper_placer.pcl import (
    sat_bridge,  # noqa: F401
)

# ============================================================================
# ORACLE -- pre-migration temper_placer/pcl/constraints.py pinned verbatim.
# ============================================================================
#
# Copied from the pre-migration file (commit 68ea250f). The enums, the
# CompilationContext dataclass and the BaseConstraint dataclass/ABC are
# verbatim. The eight concrete constraint classes are re-declared as
# dataclasses (unsafe_hash=True) so their repr()/eq()/hash() are
# deterministic; their __init__ and method bodies are copied verbatim.


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


class ConstraintTier(Enum):
    """
    Priority tier for a constraint.

    Tiers determine the penalty weight in the optimization objective:
    - HARD (1): weight=1e6 (Must be satisfied)
    - STRONG (2): weight=1e3 (Should be satisfied)
    - SOFT (3): weight=1e1 (Nice to have)
    """

    HARD = 1  # Never violate, fail if impossible
    STRONG = 2  # Heavy penalty (electrical, thermal, EMI)
    SOFT = 3  # Light penalty (aesthetics, convention)


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


@dataclass
class CompilationContext:
    """Context passed to backend compilation functions.

    Each backend callable receives (constraint, context) and returns
    backend-specific output (e.g., LossFunction, list[Constraint],
    list[DRCAssertion]).
    """

    netlist: Any
    board: Any = None
    skeletons: Any = None
    channel_widths: Any = None
    design_rules: Any = None
    extra: dict = field(default_factory=dict)


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

    def __init__(
        self,
        constraint_type: ConstraintType,
        tier: ConstraintTier,
        because: str,
        id: str = "",
        targets: list[str] | None = None,
    ):
        self.constraint_type = constraint_type
        self.tier = tier
        self.because = because
        self.id = id
        if targets is None:
            self.targets = ["sat"]
        else:
            self.targets = targets
        self.__post_init__()

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


@dataclass(unsafe_hash=True)
class AdjacentConstraint(BaseConstraint):
    """Constraint requiring two components to be close together.

    Used for:
    - Minimizing critical current loop areas
    - Reducing parasitic inductance in high-frequency paths
    - Thermal coupling
    - Short trace lengths
    """

    a: str
    b: str
    max_distance_mm: float
    tier: ConstraintTier
    because: str
    metric: DistanceMetric = DistanceMetric.EDGE_TO_EDGE
    pin_a: str | None = None
    pin_b: str | None = None
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.ADJACENT
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        a: str,
        b: str,
        max_distance_mm: float,
        tier: ConstraintTier,
        because: str,
        metric: DistanceMetric = DistanceMetric.EDGE_TO_EDGE,
        pin_a: str | None = None,
        pin_b: str | None = None,
        id: str = "",
    ):
        self.a = a
        self.b = b
        self.max_distance_mm = max_distance_mm
        self.metric = metric
        self.pin_a = pin_a
        self.pin_b = pin_b

        super().__init__(
            constraint_type=ConstraintType.ADJACENT,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        """Generate ID like 'adj_Q1_Q2'."""
        return f"adj_{self.a}_{self.b}"

    def involves_component(self, component: str) -> bool:
        """Check if constraint involves the component."""
        return component == self.a or component == self.b

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        d = {
            "type": self.constraint_type.value,
            "a": self.a,
            "b": self.b,
            "max_distance_mm": self.max_distance_mm,
            "metric": self.metric.value,
            "tier": self.tier.value,
            "because": self.because,
        }
        if self.pin_a:
            d["pin_a"] = self.pin_a
        if self.pin_b:
            d["pin_b"] = self.pin_b
        if self.id:
            d["id"] = self.id
        return d


@dataclass(unsafe_hash=True)
class SeparatedConstraint(BaseConstraint):
    """Constraint requiring two components to be far apart.

    Used for:
    - Safety isolation (HV/LV separation)
    - Thermal isolation (keep hot/cold apart)
    - EMI reduction (separate noisy/sensitive)
    - Crosstalk prevention
    """

    a: str
    b: str
    min_distance_mm: float
    tier: ConstraintTier
    because: str
    metric: DistanceMetric = DistanceMetric.EDGE_TO_EDGE
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.SEPARATED
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        a: str,
        b: str,
        min_distance_mm: float,
        tier: ConstraintTier,
        because: str,
        metric: DistanceMetric = DistanceMetric.EDGE_TO_EDGE,
        id: str = "",
    ):
        self.a = a
        self.b = b
        self.min_distance_mm = min_distance_mm
        self.metric = metric

        super().__init__(
            constraint_type=ConstraintType.SEPARATED,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        """Generate ID like 'sep_HV_LV'."""
        return f"sep_{self.a}_{self.b}"

    def involves_component(self, component: str) -> bool:
        """Check if constraint involves the component."""
        return component == self.a or component == self.b

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type.value,
            "a": self.a,
            "b": self.b,
            "min_distance_mm": self.min_distance_mm,
            "metric": self.metric.value,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }


@dataclass(unsafe_hash=True)
class EnclosingConstraint(BaseConstraint):
    """Constraint requiring components to be inside a zone.

    Used for:
    - Functional grouping (all gate drive components in gate zone)
    - Safety zones (all HV components in HV zone)
    - Thermal zones (all heat generators in thermal zone)
    - Manufacturing constraints (all SMD in SMD zone)
    """

    outer: str
    inner: list[str]
    tier: ConstraintTier
    because: str
    margin_mm: float = 0.0
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.ENCLOSING
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        outer: str,
        inner: list[str],
        tier: ConstraintTier,
        because: str,
        margin_mm: float = 0.0,
        id: str = "",
    ):
        self.outer = outer
        self.inner = inner
        self.margin_mm = margin_mm

        super().__init__(
            constraint_type=ConstraintType.ENCLOSING,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        """Generate ID like 'enc_HV_ZONE'."""
        return f"enc_{self.outer}"

    def involves_component(self, component: str) -> bool:
        """Check if constraint involves the component."""
        return component == self.outer or component in self.inner

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type.value,
            "outer": self.outer,
            "inner": self.inner,
            "margin_mm": self.margin_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }


@dataclass(unsafe_hash=True)
class KeepoutConstraint(BaseConstraint):
    """Constraint keeping components out of a keepout zone.

    Used for:
    - Safety isolation (no components in high-voltage zone)
    - Thermal isolation (no sensitive parts near hot components)
    - Mechanical clearance (no components near mounting holes)
    - EMI management (no components in noisy zones)
    """

    zone_name: str
    tier: ConstraintTier
    because: str
    margin_mm: float = 0.0
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.KEEPOUT
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        zone_name: str,
        tier: ConstraintTier,
        because: str,
        margin_mm: float = 0.0,
        id: str = "",
    ):
        self.zone_name = zone_name
        self.margin_mm = margin_mm

        super().__init__(
            constraint_type=ConstraintType.KEEPOUT,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        return f"keepout_{self.zone_name}"

    def involves_component(self, component: str) -> bool:
        return component == self.zone_name

    def to_dict(self) -> dict:
        return {
            "type": self.constraint_type.value,
            "zone_name": self.zone_name,
            "margin_mm": self.margin_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }


@dataclass(unsafe_hash=True)
class AlignedConstraint(BaseConstraint):
    """Constraint requiring components to align on an axis.

    Used for:
    - Visual consistency
    - Routing simplification (aligned pins)
    - Signal flow (align along data path)
    - Manufacturing (pick-and-place efficiency)
    """

    components: list[str]
    axis: Axis
    tier: ConstraintTier
    because: str
    tolerance_mm: float = 0.5
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.ALIGNED
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        components: list[str],
        axis: Axis,
        tier: ConstraintTier,
        because: str,
        tolerance_mm: float = 0.5,
        id: str = "",
    ):
        if len(components) < 2:
            raise ValueError("AlignedConstraint requires at least 2 components")

        self.components = components
        self.axis = axis
        self.tolerance_mm = tolerance_mm

        super().__init__(
            constraint_type=ConstraintType.ALIGNED,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        """Generate ID like 'align_x_C1_C2_C3'."""
        comp_str = "_".join(self.components[:3])  # First 3 components
        return f"align_{self.axis.value}_{comp_str}"

    def involves_component(self, component: str) -> bool:
        """Check if constraint involves the component."""
        return component in self.components

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type.value,
            "components": self.components,
            "axis": self.axis.value,
            "tolerance_mm": self.tolerance_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }


@dataclass(unsafe_hash=True)
class OnSideConstraint(BaseConstraint):
    """Constraint requiring components on a board edge.

    Used for:
    - Connector placement (must be on edge for access)
    - Thermal management (heat sinks on edge)
    - Mechanical mounting (edge-mounted components)
    - User interface (buttons, LEDs on accessible edge)
    """

    components: list[str]
    side: BoardSide
    edge: EdgeType
    tier: ConstraintTier
    because: str
    max_distance_mm: float = 5.0
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.ON_SIDE
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        components: list[str],
        side: BoardSide,
        edge: EdgeType,
        tier: ConstraintTier,
        because: str,
        max_distance_mm: float = 5.0,
        id: str = "",
    ):
        self.components = components
        self.side = side
        self.edge = edge
        self.max_distance_mm = max_distance_mm

        super().__init__(
            constraint_type=ConstraintType.ON_SIDE,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        """Generate ID like 'side_left_J1_J2'."""
        comp_str = "_".join(self.components[:3])
        return f"side_{self.side.value}_{comp_str}"

    def involves_component(self, component: str) -> bool:
        """Check if constraint involves the component."""
        return component in self.components

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type.value,
            "components": self.components,
            "side": self.side.value,
            "edge": self.edge.value,
            "max_distance_mm": self.max_distance_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }


@dataclass(unsafe_hash=True)
class AnchoredConstraint(BaseConstraint):
    """Constraint fixing a component to a specific position or region.

    Used for:
    - Mechanical constraints (mounting holes, connectors)
    - Thermal constraints (heat sink must be at specific location)
    - User interface (display, buttons at specific positions)
    - Critical components that can't move
    """

    component: str
    tier: ConstraintTier
    because: str
    region: tuple[float, float, float, float] | None = None
    position: tuple[float, float] | None = None
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.ANCHORED
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        component: str,
        tier: ConstraintTier,
        because: str,
        region: tuple[float, float, float, float] | None = None,
        position: tuple[float, float] | None = None,
        id: str = "",
    ):
        if region is None and position is None:
            raise ValueError("AnchoredConstraint requires either region or position")
        if region is not None and position is not None:
            raise ValueError("AnchoredConstraint cannot have both region and position")

        self.component = component
        self.region = region
        self.position = position

        super().__init__(
            constraint_type=ConstraintType.ANCHORED,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        """Generate ID like 'anchor_J1'."""
        return f"anchor_{self.component}"

    def involves_component(self, component: str) -> bool:
        """Check if constraint involves the component."""
        return component == self.component

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary."""
        d: dict[str, object] = {
            "type": self.constraint_type.value,
            "component": self.component,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }
        if self.region:
            d["region"] = self.region
        if self.position:
            d["position"] = self.position
        return d


@dataclass(unsafe_hash=True)
class LoopAreaConstraint(BaseConstraint):
    """Constraint limiting the area of a current loop.

    This is the primary electrical constraint for power electronics. Minimizing
    loop areas reduces:
    - Parasitic inductance (reduces voltage overshoot)
    - EMI emissions (smaller loop antenna)
    - Crosstalk (smaller magnetic field)
    """

    loop_name: str
    max_area_mm2: float
    tier: ConstraintTier
    because: str
    id: str = ""
    constraint_type: ConstraintType = ConstraintType.LOOP_AREA
    targets: list[str] = field(default_factory=lambda: ["sat"])

    def __init__(
        self,
        loop_name: str,
        max_area_mm2: float,
        tier: ConstraintTier,
        because: str,
        id: str = "",
    ):
        self.loop_name = loop_name
        self.max_area_mm2 = max_area_mm2

        super().__init__(
            constraint_type=ConstraintType.LOOP_AREA,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        """Generate ID like 'loop_commutation'."""
        return f"loop_{self.loop_name}"

    def involves_component(self, _component: str) -> bool:
        """Loop constraints don't directly involve components."""
        return False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type.value,
            "loop_name": self.loop_name,
            "max_area_mm2": self.max_area_mm2,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }


# ============================================================================
# End ORACLE block.
# ============================================================================


# ---------------------------------------------------------------------------
# Enum surface parity.
# ---------------------------------------------------------------------------

SIMPLE_ENUMS = [
    (live.ConstraintTier, ConstraintTier),
    (live.DistanceMetric, DistanceMetric),
    (live.Axis, Axis),
    (live.BoardSide, BoardSide),
    (live.EdgeType, EdgeType),
    (live.CompilationTarget, CompilationTarget),
    (live.SemanticTag, SemanticTag),
]


@pytest.mark.parametrize("pair", SIMPLE_ENUMS, ids=lambda p: p[0].__name__)
def test_enum_member_names_and_values_unchanged(pair):
    live_enum, oracle_enum = pair
    assert [m.name for m in live_enum] == [m.name for m in oracle_enum]
    assert [m.value for m in live_enum] == [m.value for m in oracle_enum]


def test_constraint_type_members_are_unchanged():
    assert [m.name for m in live.ConstraintType] == [m.name for m in ConstraintType]
    assert [m.label for m in live.ConstraintType] == [m.label for m in ConstraintType]
    assert [m.value for m in live.ConstraintType] == [m.value for m in ConstraintType]
    for name in [m.name for m in live.ConstraintType]:
        lv, ov = getattr(live.ConstraintType, name), getattr(ConstraintType, name)
        assert {t.name for t in lv.capabilities} == {t.name for t in ov.capabilities}
        assert {t.name for t in lv.supported_targets} == {
            t.name for t in ov.supported_targets
        }
    assert live.ConstraintType.ADJACENT.value == "adjacent"


# ---------------------------------------------------------------------------
# Per-type parity harness.
# ---------------------------------------------------------------------------


def _build_pair(cls_name, kwargs):
    """Build (live_instance, oracle_instance) from a kwargs spec.

    ``kwargs`` holds the values that are enum members in BOTH namespaces when
    the key is one of the enum-typed fields; the harness maps them per side.
    """
    live_enums = {
        "tier": live.ConstraintTier,
        "metric": live.DistanceMetric,
        "axis": live.Axis,
        "side": live.BoardSide,
        "edge": live.EdgeType,
    }
    oracle_enums = {
        "tier": ConstraintTier,
        "metric": DistanceMetric,
        "axis": Axis,
        "side": BoardSide,
        "edge": EdgeType,
    }
    live_kwargs = {}
    oracle_kwargs = {}
    for k, v in kwargs.items():
        if k in live_enums:
            live_kwargs[k] = getattr(live_enums[k], v.name)
            oracle_kwargs[k] = getattr(oracle_enums[k], v.name)
        else:
            live_kwargs[k] = v
            oracle_kwargs[k] = v
    return getattr(live, cls_name)(**live_kwargs), globals()[cls_name](**oracle_kwargs)


_CONSTRUCTOR_CASES = [
    (
        "AdjacentConstraint",
        {"a": "Q1", "b": "Q2", "max_distance_mm": 10.0, "tier": live.ConstraintTier.HARD,
             "because": "Minimize commutation loop area"},
    ),
    (
        "AdjacentConstraint",
        {"a": "U1", "b": "Q1", "max_distance_mm": 15.0, "tier": live.ConstraintTier.STRONG,
             "because": "Minimize gate drive loop inductance",
             "metric": live.DistanceMetric.PIN_TO_PIN, "pin_a": "OUT", "pin_b": "GATE"},
    ),
    (
        "SeparatedConstraint",
        {"a": "HV_ZONE", "b": "MCU_ZONE", "min_distance_mm": 10.0, "tier": live.ConstraintTier.HARD,
             "because": "IEC 60335-1 reinforced isolation requirement"},
    ),
    (
        "EnclosingConstraint",
        {"outer": "HV_ZONE", "inner": ["Q1", "Q2", "D1", "C_DC"], "tier": live.ConstraintTier.HARD,
             "because": "All high voltage components must stay in HV safety zone", "margin_mm": 2.0},
    ),
    (
        "KeepoutConstraint",
        {"zone_name": "HV_KEEPOUT", "tier": live.ConstraintTier.HARD,
             "because": "No components allowed in HV keepout for safety isolation", "margin_mm": 1.5},
    ),
    (
        "AlignedConstraint",
        {"components": ["C1", "C2", "C3", "C4"], "axis": live.Axis.X, "tier": live.ConstraintTier.SOFT,
             "because": "Align decoupling capacitors for visual consistency", "tolerance_mm": 0.8},
    ),
    (
        "OnSideConstraint",
        {"components": ["J1", "J2"], "side": live.BoardSide.LEFT, "edge": live.EdgeType.FLUSH,
             "tier": live.ConstraintTier.HARD,
             "because": "Connectors must be on left edge for external access", "max_distance_mm": 3.0},
    ),
    (
        "AnchoredConstraint",
        {"component": "J_AC_IN", "region": (0, 0, 10, 10), "tier": live.ConstraintTier.HARD,
             "because": "AC inlet connector mechanically fixed by enclosure"},
    ),
    (
        "AnchoredConstraint",
        {"component": "DISPLAY", "position": (50.0, 50.0), "tier": live.ConstraintTier.HARD,
             "because": "Display must be centered for UI requirements"},
    ),
    (
        "LoopAreaConstraint",
        {"loop_name": "commutation", "max_area_mm2": 500.0, "tier": live.ConstraintTier.STRONG,
             "because": "Minimize commutation loop to reduce voltage overshoot"},
    ),
    (
        "LoopAreaConstraint",
        {"loop_name": "bootstrap", "max_area_mm2": 25.0, "tier": live.ConstraintTier.STRONG,
             "because": "Minimize bootstrap loop for charge efficiency", "id": "custom_loop_id"},
    ),
]

_CONSTRUCTOR_IDS = [f"{c[0]}#{i}" for i, c in enumerate(_CONSTRUCTOR_CASES)]


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_constructor_and_id_generation_match(cls_name, kwargs):
    lv, ov = _build_pair(cls_name, kwargs)
    assert lv.id == ov.id


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_repr_is_byte_identical_to_the_dataclass_repr(cls_name, kwargs):
    lv, ov = _build_pair(cls_name, kwargs)
    got, want = repr(lv), repr(ov)
    assert got == want, f"{cls_name}\n  rust  = {got}\n  oracle= {want}"


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_to_dict_matches_byte_for_byte(cls_name, kwargs):
    lv, ov = _build_pair(cls_name, kwargs)
    assert_same(lv.to_dict(), ov.to_dict(), context=f"{cls_name}.to_dict()")


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_involves_component_matches(cls_name, kwargs):
    lv, ov = _build_pair(cls_name, kwargs)
    for comp in ("Q1", "Q2", "HV_ZONE", "MCU_ZONE", "C1", "J1", "J_AC_IN", "DISPLAY", "C_DC", ""):
        assert_same(
            lv.involves_component(comp),
            ov.involves_component(comp),
            context=f"{cls_name}.involves_component({comp!r})",
        )


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_equality_is_structural_and_matches_the_oracle(cls_name, kwargs):
    lv, ov = _build_pair(cls_name, kwargs)
    lv2, ov2 = _build_pair(cls_name, kwargs)
    assert (lv == lv2) == (ov == ov2)
    assert lv == lv2
    assert not (lv != lv2)  # noqa: SIM202 -- __ne__ is a separately implemented slot
    assert (lv != lv2) == (ov != ov2)


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_equality_with_different_values_disagrees_on_both_sides(cls_name, kwargs):
    lv, _ = _build_pair(cls_name, kwargs)
    altered = dict(kwargs)
    # Every constraint carries a `because` rationale; perturbing it makes the
    # instances different on both sides without touching any enum mapping.
    altered["because"] = altered["because"] + "_X"
    lv_diff, ov_diff = _build_pair(cls_name, altered)
    lv_orig, ov_orig = _build_pair(cls_name, kwargs)
    assert (lv_diff == lv_orig) is False
    assert (ov_diff == ov_orig) is False
    assert (lv_diff != lv_orig) is True
    assert (ov_diff != ov_orig) is True


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_equality_against_unrelated_objects_is_false(cls_name, kwargs):
    lv, _ = _build_pair(cls_name, kwargs)
    for other in ("a string", 1, None, object(), [1], 1.5):
        assert (lv == other) is False
        assert (lv != other) is True


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_hash_agrees_with_equality(cls_name, kwargs):
    lv, _ = _build_pair(cls_name, kwargs)
    lv2, _ = _build_pair(cls_name, kwargs)
    assert hash(lv) == hash(lv2)


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_deepcopy_round_trips(cls_name, kwargs):
    """`ConstraintCollection.copy()` deep-copies constraints."""
    lv, _ = _build_pair(cls_name, kwargs)
    clone = copy.deepcopy(lv)
    assert clone == lv
    assert clone is not lv
    assert repr(clone) == repr(lv)


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_pickle_round_trips(cls_name, kwargs):
    lv, _ = _build_pair(cls_name, kwargs)
    clone = pickle.loads(pickle.dumps(lv))
    assert clone == lv
    assert repr(clone) == repr(lv)


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_enum_identity_returned_by_getters(cls_name, kwargs):
    """The migrated objects hand back the LIVE Python singletons."""
    lv, _ = _build_pair(cls_name, kwargs)
    constraint_type_name = {
        "AdjacentConstraint": "ADJACENT",
        "SeparatedConstraint": "SEPARATED",
        "EnclosingConstraint": "ENCLOSING",
        "KeepoutConstraint": "KEEPOUT",
        "AlignedConstraint": "ALIGNED",
        "OnSideConstraint": "ON_SIDE",
        "AnchoredConstraint": "ANCHORED",
        "LoopAreaConstraint": "LOOP_AREA",
    }[cls_name]
    assert lv.tier is getattr(live.ConstraintTier, kwargs["tier"].name)
    assert lv.constraint_type is getattr(live.ConstraintType, constraint_type_name)
    if "metric" in kwargs:
        assert lv.metric is getattr(live.DistanceMetric, kwargs["metric"].name)
    if "axis" in kwargs:
        assert lv.axis is getattr(live.Axis, kwargs["axis"].name)
    if "side" in kwargs:
        assert lv.side is getattr(live.BoardSide, kwargs["side"].name)
    if "edge" in kwargs:
        assert lv.edge is getattr(live.EdgeType, kwargs["edge"].name)


def test_default_field_values_match():
    adj = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0, tier=live.ConstraintTier.HARD,
        because="Minimize commutation loop area",
    )
    oracle_adj = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0, tier=ConstraintTier.HARD,
        because="Minimize commutation loop area",
    )
    assert adj.metric is live.DistanceMetric.EDGE_TO_EDGE
    assert adj.metric.value == oracle_adj.metric.value
    assert adj.pin_a is None and adj.pin_b is None
    assert adj.targets == ["sat"] and oracle_adj.targets == ["sat"]
    assert adj.constraint_type is live.ConstraintType.ADJACENT


@pytest.mark.parametrize(
    "cls_name,kwargs",
    [
        ("EnclosingConstraint", {"outer": "HV_ZONE", "inner": ["Q1"], "tier": live.ConstraintTier.HARD,
                                     "because": "Default margin test for enclosing"}),
        ("KeepoutConstraint", {"zone_name": "HV_KEEPOUT", "tier": live.ConstraintTier.HARD,
                                   "because": "Default margin test for keepout"}),
        ("AlignedConstraint", {"components": ["C1", "C2"], "axis": live.Axis.X,
                                   "tier": live.ConstraintTier.SOFT,
                                   "because": "Default tolerance test"}),
        ("OnSideConstraint", {"components": ["J1", "J2"], "side": live.BoardSide.LEFT,
                                  "edge": live.EdgeType.FLUSH, "tier": live.ConstraintTier.HARD,
                                  "because": "Default max distance test"}),
    ],
)
def test_constructor_float_defaults_match_the_dataclass(cls_name, kwargs):
    """margin_mm=0.0 / tolerance_mm=0.5 / max_distance_mm=5.0 defaults."""
    lv, ov = _build_pair(cls_name, kwargs)
    assert repr(lv) == repr(ov), f"{cls_name} defaults diverged"


def test_type_module_is_temper_placer_pcl_constraints():
    """pyo3 pyclasses declare the original module so error messages / type()
    identity stay put."""
    c = live.SeparatedConstraint(
        a="A", b="B", min_distance_mm=1.0, tier=live.ConstraintTier.HARD,
        because="Module identity test",
    )
    assert type(c).__module__ == "temper_placer.pcl.constraints"
    assert type(c).__qualname__ == "SeparatedConstraint"


def test_targets_default_is_a_fresh_list_per_instance():
    a = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=1.0, tier=live.ConstraintTier.HARD,
        because="Targets freshness test",
    )
    b = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=1.0, tier=live.ConstraintTier.HARD,
        because="Targets freshness test",
    )
    assert a.targets is not b.targets
    a.targets.append("drc")
    assert b.targets == ["sat"]


def test_custom_id_is_respected_not_overwritten():
    lv = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0, tier=live.ConstraintTier.HARD,
        because="Minimize commutation loop area", id="custom_half_bridge",
    )
    assert lv.id == "custom_half_bridge"


# ---------------------------------------------------------------------------
# Validation parity.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda ns: ns.AdjacentConstraint(
            a="Q1", b="Q2", max_distance_mm=10.0, tier=ns.ConstraintTier.HARD,
            because="Too short",
        ),
        lambda ns: ns.SeparatedConstraint(
            a="HV_ZONE", b="MCU_ZONE", min_distance_mm=10.0, tier=ns.ConstraintTier.HARD,
            because="Too short",
        ),
        lambda ns: ns.KeepoutConstraint(
            zone_name="Z", tier=ns.ConstraintTier.HARD, because="Too short",
        ),
        lambda ns: ns.LoopAreaConstraint(
            loop_name="l", max_area_mm2=1.0, tier=ns.ConstraintTier.HARD, because="Too short",
        ),
    ],
)
def test_short_rationale_raises_the_same_valueerror(call):
    got = call_signature(call, live)
    want = call_signature(call, sys.modules[__name__])
    assert got == want
    assert got[0] == "raise" and got[2] == "ValueError"
    assert "≥10 chars" in got[3]


def test_because_exactly_ten_chars_is_accepted():
    lv = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0, tier=live.ConstraintTier.HARD,
        because="1234567890",
    )
    assert lv.because == "1234567890"


def test_invalid_targets_raise_the_same_valueerror():
    """``targets`` is part of the BaseConstraint data surface (the dataclass
    field); the migrated classes accept it at construction and validate it
    exactly like the pre-migration ``__post_init__`` loop.

    The oracle dataclass keeps the pre-migration concrete ``__init__``, which
    never accepted a ``targets`` kwarg, so there is no oracle path to exercise
    the validation — this pins the exact message literal instead (the
    ``sorted(valid_targets)`` is a constant string sort). See VERIFICATION.md
    for the widening record."""
    got = call_signature(
        live.AdjacentConstraint,
        a="Q1", b="Q2", max_distance_mm=10.0, tier=live.ConstraintTier.HARD,
        because="Invalid target test", targets=["gpu"],
    )
    assert got == (
        "raise",
        "builtins",
        "ValueError",
        "Invalid compilation target 'gpu'. Must be one of ['cp_sat', 'drc', 'jax', 'sat']",
    )


def test_all_valid_targets_are_accepted():
    for targets in (["jax"], ["drc"], ["sat", "drc"], ["cp_sat"]):
        c = live.AdjacentConstraint(
            a="Q1", b="Q2", max_distance_mm=1.0, tier=live.ConstraintTier.HARD,
            because="Valid targets test", targets=targets,
        )
        assert c.targets == targets


def test_aligned_constraint_requires_two_components():
    got = call_signature(
        live.AlignedConstraint,
        components=["C1"], axis=live.Axis.X, tier=live.ConstraintTier.SOFT,
        because="Need multiple components",
    )
    want = call_signature(
        AlignedConstraint,
        components=["C1"], axis=Axis.X, tier=ConstraintTier.SOFT,
        because="Need multiple components",
    )
    assert got == want
    assert got[0] == "raise" and "at least 2 components" in got[3]


def test_anchored_requires_region_or_position():
    got = call_signature(
        live.AnchoredConstraint, component="J1", tier=live.ConstraintTier.HARD,
        because="Mechanically fixed",
    )
    want = call_signature(
        AnchoredConstraint, component="J1", tier=ConstraintTier.HARD,
        because="Mechanically fixed",
    )
    assert got == want


def test_anchored_cannot_have_both_region_and_position():
    got = call_signature(
        live.AnchoredConstraint, component="J1", region=(0, 0, 10, 10), position=(5, 5),
        tier=live.ConstraintTier.HARD, because="Mechanically fixed",
    )
    want = call_signature(
        AnchoredConstraint, component="J1", region=(0, 0, 10, 10), position=(5, 5),
        tier=ConstraintTier.HARD, because="Mechanically fixed",
    )
    assert got == want


# ---------------------------------------------------------------------------
# escalate()
# ---------------------------------------------------------------------------


def test_escalate_soft_to_strong():
    c = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0, tier=live.ConstraintTier.SOFT,
        because="Escalation test",
    )
    assert c.tier is live.ConstraintTier.SOFT
    c.escalate()
    assert c.tier is live.ConstraintTier.STRONG


def test_escalate_strong_to_hard():
    c = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0, tier=live.ConstraintTier.STRONG,
        because="Escalation test",
    )
    c.escalate()
    assert c.tier is live.ConstraintTier.HARD


def test_escalate_hard_stays_hard():
    c = live.AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0, tier=live.ConstraintTier.HARD,
        because="Escalation test",
    )
    c.escalate()
    assert c.tier is live.ConstraintTier.HARD


def test_min_distance_mm_is_mutable_like_the_plain_class():
    """unsat_compiler._deduplicate_constraints mutates min_distance_mm."""
    c = live.SeparatedConstraint(
        a="A", b="B", min_distance_mm=1.0, tier=live.ConstraintTier.HARD,
        because="Mutation parity test",
    )
    c.min_distance_mm = max(c.min_distance_mm, 6.0)
    assert c.min_distance_mm == 6.0
    oracle_c = SeparatedConstraint(
        a="A", b="B", min_distance_mm=1.0, tier=ConstraintTier.HARD,
        because="Mutation parity test",
    )
    oracle_c.min_distance_mm = max(oracle_c.min_distance_mm, 6.0)
    assert oracle_c.min_distance_mm == 6.0


# ---------------------------------------------------------------------------
# CompilationContext
# ---------------------------------------------------------------------------


def test_compilation_context_repr_is_byte_identical():
    netlist = {"fake": "netlist"}
    board = object()
    lv = live.CompilationContext(
        netlist=netlist, board=board, skeletons=None, channel_widths={"w": 1},
        design_rules="dr", extra={"k": "v"},
    )
    ov = CompilationContext(
        netlist=netlist, board=board, skeletons=None, channel_widths={"w": 1},
        design_rules="dr", extra={"k": "v"},
    )
    assert repr(lv) == repr(ov)


def test_compilation_context_defaults():
    netlist = {"fake": "netlist"}
    lv = live.CompilationContext(netlist=netlist)
    ov = CompilationContext(netlist=netlist)
    assert repr(lv) == repr(ov)
    assert lv.board is None and ov.board is None
    assert lv.extra == {} and ov.extra == {}
    assert type(lv.extra) is dict


def test_compilation_context_field_access():
    netlist = {"fake": "netlist"}
    board = object()
    lv = live.CompilationContext(netlist=netlist, board=board)
    assert lv.netlist is netlist
    assert lv.board is board
    assert lv.skeletons is None
    assert lv.channel_widths is None
    assert lv.design_rules is None


def test_compilation_context_equality_matches():
    netlist = {"fake": "netlist"}
    board = object()
    lv = live.CompilationContext(netlist=netlist, board=board)
    lv2 = live.CompilationContext(netlist=netlist, board=board)
    ov = CompilationContext(netlist=netlist, board=board)
    ov2 = CompilationContext(netlist=netlist, board=board)
    assert (lv == lv2) == (ov == ov2)


# ---------------------------------------------------------------------------
# BaseConstraint compatibility (the encoder-registry slice stays Python).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls_name,kwargs", _CONSTRUCTOR_CASES, ids=_CONSTRUCTOR_IDS)
def test_migrated_constraints_are_still_baseconstraint_instances(cls_name, kwargs):
    """test_feedback asserts `isinstance(delta.constraint, BaseConstraint)`."""
    lv, _ = _build_pair(cls_name, kwargs)
    assert isinstance(lv, live.BaseConstraint)


def test_base_constraint_backends_registry_is_untouched():
    assert isinstance(live.BaseConstraint.backends, dict)
    assert "sat" in live.BaseConstraint.backends
    # The DRC bridge was retired (2026-08-09); only sat remains.
    assert "drc" not in live.BaseConstraint.backends


def test_targets_membership_used_by_parser_compile():
    c = live.LoopAreaConstraint(
        loop_name="commutation", max_area_mm2=500.0, tier=live.ConstraintTier.STRONG,
        because="Minimize commutation loop to reduce voltage overshoot",
    )
    assert "sat" in c.targets
    assert "jax" not in c.targets
