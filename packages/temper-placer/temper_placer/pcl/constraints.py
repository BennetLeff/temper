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
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


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
    """Types of topological constraints supported by PCL."""

    ADJACENT = "adjacent"  # Keep components close
    SEPARATED = "separated"  # Keep components apart
    ENCLOSING = "enclosing"  # Component inside zone
    ALIGNED = "aligned"  # Align components on axis
    ON_SIDE = "on_side"  # Component on board edge
    ANCHORED = "anchored"  # Component at specific position
    LOOP_AREA = "loop_area"  # Limit current loop area


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

    Subclasses implement specific constraint logic.
    """

    constraint_type: ConstraintType
    tier: ConstraintTier
    because: str
    id: str = ""

    def __post_init__(self):
        """Validate constraint fields."""
        if len(self.because) < 10:
            raise ValueError(
                f"Rationale 'because' must be ≥10 chars, got {len(self.because)}: '{self.because}'"
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


class AdjacentConstraint(BaseConstraint):
    """Constraint requiring two components to be close together.

    Used for:
    - Minimizing critical current loop areas
    - Reducing parasitic inductance in high-frequency paths
    - Thermal coupling
    - Short trace lengths

    Attributes:
        a: First component reference designator
        b: Second component reference designator
        max_distance_mm: Maximum allowed distance
        tier: Priority tier for constraint
        because: Mandatory rationale
        metric: How to measure distance (default: edge-to-edge)
        pin_a: Optional specific pin on component a
        pin_b: Optional specific pin on component b
        id: Optional unique identifier

    Example:
        >>> AdjacentConstraint(
        ...     a="Q1", b="Q2",
        ...     max_distance_mm=10.0,
        ...     tier=ConstraintTier.HARD,
        ...     because="Minimize commutation loop for half-bridge"
        ... )
    """

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


class SeparatedConstraint(BaseConstraint):
    """Constraint requiring two components to be far apart.

    Used for:
    - Safety isolation (HV/LV separation)
    - Thermal isolation (keep hot/cold apart)
    - EMI reduction (separate noisy/sensitive)
    - Crosstalk prevention

    Attributes:
        a: First component or zone reference
        b: Second component or zone reference
        min_distance_mm: Minimum required distance
        tier: Priority tier
        because: Mandatory rationale
        metric: How to measure distance (default: edge-to-edge)
        id: Optional unique identifier

    Example:
        >>> SeparatedConstraint(
        ...     a="HV_ZONE", b="MCU_ZONE",
        ...     min_distance_mm=10.0,
        ...     tier=ConstraintTier.HARD,
        ...     because="IEC 60335-1 reinforced isolation requirement"
        ... )
    """

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


class EnclosingConstraint(BaseConstraint):
    """Constraint requiring components to be inside a zone.

    Used for:
    - Functional grouping (all gate drive components in gate zone)
    - Safety zones (all HV components in HV zone)
    - Thermal zones (all heat generators in thermal zone)
    - Manufacturing constraints (all SMD in SMD zone)

    Attributes:
        outer: Zone reference (e.g., "HV_ZONE")
        inner: List of component references that must be inside
        tier: Priority tier
        because: Mandatory rationale
        margin_mm: Optional margin from zone boundary
        id: Optional unique identifier

    Example:
        >>> EnclosingConstraint(
        ...     outer="HV_ZONE",
        ...     inner=["Q1", "Q2", "D1", "C_DC"],
        ...     tier=ConstraintTier.HARD,
        ...     because="All high voltage components must stay in HV safety zone"
        ... )
    """

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


class AlignedConstraint(BaseConstraint):
    """Constraint requiring components to align on an axis.

    Used for:
    - Visual consistency
    - Routing simplification (aligned pins)
    - Signal flow (align along data path)
    - Manufacturing (pick-and-place efficiency)

    Attributes:
        components: List of component references to align
        axis: Alignment axis (X, Y, MAJOR, MINOR)
        tier: Priority tier
        because: Mandatory rationale
        tolerance_mm: Allowed deviation from perfect alignment
        id: Optional unique identifier

    Example:
        >>> AlignedConstraint(
        ...     components=["C1", "C2", "C3", "C4"],
        ...     axis=Axis.X,
        ...     tier=ConstraintTier.SOFT,
        ...     because="Align decoupling capacitors for visual consistency"
        ... )
    """

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


class OnSideConstraint(BaseConstraint):
    """Constraint requiring components on a board edge.

    Used for:
    - Connector placement (must be on edge for access)
    - Thermal management (heat sinks on edge)
    - Mechanical mounting (edge-mounted components)
    - User interface (buttons, LEDs on accessible edge)

    Attributes:
        components: List of component references
        side: Board edge (TOP, BOTTOM, LEFT, RIGHT)
        edge: How component relates to edge (FLUSH, NEAR, OVERHANG)
        tier: Priority tier
        because: Mandatory rationale
        max_distance_mm: For NEAR edge type, max distance from edge
        id: Optional unique identifier

    Example:
        >>> OnSideConstraint(
        ...     components=["J1", "J2"],
        ...     side=BoardSide.LEFT,
        ...     edge=EdgeType.FLUSH,
        ...     tier=ConstraintTier.HARD,
        ...     because="Connectors must be on left edge for external access"
        ... )
    """

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


class AnchoredConstraint(BaseConstraint):
    """Constraint fixing a component to a specific position or region.

    Used for:
    - Mechanical constraints (mounting holes, connectors)
    - Thermal constraints (heat sink must be at specific location)
    - User interface (display, buttons at specific positions)
    - Critical components that can't move

    Attributes:
        component: Component reference
        tier: Priority tier
        because: Mandatory rationale
        region: Rectangular region (x_min, y_min, x_max, y_max) in mm
        position: Optional exact position (x, y) in mm
        id: Optional unique identifier

    Example:
        >>> AnchoredConstraint(
        ...     component="J_AC_IN",
        ...     region=(0, 0, 10, 10),
        ...     tier=ConstraintTier.HARD,
        ...     because="AC inlet connector mechanically fixed by enclosure"
        ... )
    """

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

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        d = {
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


class LoopAreaConstraint(BaseConstraint):
    """Constraint limiting the area of a current loop.

    This is the primary electrical constraint for power electronics. Minimizing
    loop areas reduces:
    - Parasitic inductance (reduces voltage overshoot)
    - EMI emissions (smaller loop antenna)
    - Crosstalk (smaller magnetic field)

    Attributes:
        loop_name: Reference to loop defined in loop model
        max_area_mm2: Maximum allowed loop area in mm²
        tier: Priority tier
        because: Mandatory rationale
        id: Optional unique identifier

    Example:
        >>> LoopAreaConstraint(
        ...     loop_name="commutation",
        ...     max_area_mm2=500.0,
        ...     tier=ConstraintTier.STRONG,
        ...     because="Minimize commutation loop to reduce voltage overshoot"
        ... )
    """

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

    def involves_component(self, component: str) -> bool:
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
