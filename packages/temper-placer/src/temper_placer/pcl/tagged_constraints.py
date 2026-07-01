"""
Tag-based PCL constraint classes that use semantic tag expressions instead of
concrete component references.

Each class extends BaseConstraint and carries tag_expr fields that are
resolved against component tags at expansion time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import (
    Axis,
    BaseConstraint,
    BoardSide,
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
    EdgeType,
)

if TYPE_CHECKING:
    from temper_placer.pcl.tag_dispatch import TagExpr


@dataclass
class TaggedAdjacentConstraint(BaseConstraint):
    """Adjacent constraint using tag expressions instead of component refs.

    Expands to concrete AdjacentConstraint instances for all pairs of
    components matching tag_expr_a and tag_expr_b.
    """

    def __init__(
        self,
        tag_expr_a: TagExpr,
        tag_expr_b: TagExpr,
        max_distance_mm: float,
        tier: ConstraintTier,
        because: str,
        metric: DistanceMetric = DistanceMetric.EDGE_TO_EDGE,
        id: str = "",
    ):
        self.tag_expr_a = tag_expr_a
        self.tag_expr_b = tag_expr_b
        self.max_distance_mm = max_distance_mm
        self.metric = metric
        super().__init__(
            constraint_type=ConstraintType.ADJACENT,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        return f"tag_adj_{id(self)}"

    def involves_component(self, component: str) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "type": self.constraint_type.value,
            "tag_expr_a": str(type(self.tag_expr_a).__name__),
            "tag_expr_b": str(type(self.tag_expr_b).__name__),
            "max_distance_mm": self.max_distance_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }

    def collect_tag_exprs(self) -> list[TagExpr]:
        return [self.tag_expr_a, self.tag_expr_b]


@dataclass
class TaggedSeparatedConstraint(BaseConstraint):
    """Separated constraint using tag expressions instead of component refs.

    Expands to concrete SeparatedConstraint instances for all pairs of
    components matching tag_expr_a and tag_expr_b.
    """

    def __init__(
        self,
        tag_expr_a: TagExpr,
        tag_expr_b: TagExpr,
        min_distance_mm: float,
        tier: ConstraintTier,
        because: str,
        metric: DistanceMetric = DistanceMetric.EDGE_TO_EDGE,
        id: str = "",
    ):
        self.tag_expr_a = tag_expr_a
        self.tag_expr_b = tag_expr_b
        self.min_distance_mm = min_distance_mm
        self.metric = metric
        super().__init__(
            constraint_type=ConstraintType.SEPARATED,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        return f"tag_sep_{id(self)}"

    def involves_component(self, component: str) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "type": self.constraint_type.value,
            "tag_expr_a": str(type(self.tag_expr_a).__name__),
            "tag_expr_b": str(type(self.tag_expr_b).__name__),
            "min_distance_mm": self.min_distance_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }

    def collect_tag_exprs(self) -> list[TagExpr]:
        return [self.tag_expr_a, self.tag_expr_b]


@dataclass
class TaggedEnclosingConstraint(BaseConstraint):
    """Enclosing constraint using tag expressions for inner components.

    The outer is a zone name; inner components are resolved from tag_expr_inner.
    """

    def __init__(
        self,
        outer: str,
        tag_expr_inner: TagExpr,
        tier: ConstraintTier,
        because: str,
        margin_mm: float = 0.0,
        id: str = "",
    ):
        self.outer = outer
        self.tag_expr_inner = tag_expr_inner
        self.margin_mm = margin_mm
        super().__init__(
            constraint_type=ConstraintType.ENCLOSING,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        return f"tag_enc_{id(self)}"

    def involves_component(self, component: str) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "type": self.constraint_type.value,
            "outer": self.outer,
            "margin_mm": self.margin_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }

    def collect_tag_exprs(self) -> list[TagExpr]:
        return [self.tag_expr_inner]


@dataclass
class TaggedAlignedConstraint(BaseConstraint):
    """Aligned constraint using tag expression for component selection."""

    def __init__(
        self,
        tag_expr: TagExpr,
        axis: Axis,
        tier: ConstraintTier,
        because: str,
        tolerance_mm: float = 0.5,
        id: str = "",
    ):
        self.tag_expr = tag_expr
        self.axis = axis
        self.tolerance_mm = tolerance_mm
        super().__init__(
            constraint_type=ConstraintType.ALIGNED,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        return f"tag_align_{id(self)}"

    def involves_component(self, component: str) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "type": self.constraint_type.value,
            "axis": self.axis.value,
            "tolerance_mm": self.tolerance_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }

    def collect_tag_exprs(self) -> list[TagExpr]:
        return [self.tag_expr]


@dataclass
class TaggedOnSideConstraint(BaseConstraint):
    """On-side constraint using tag expression for component selection."""

    def __init__(
        self,
        tag_expr: TagExpr,
        side: BoardSide,
        edge: EdgeType,
        tier: ConstraintTier,
        because: str,
        max_distance_mm: float = 5.0,
        id: str = "",
    ):
        self.tag_expr = tag_expr
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
        return f"tag_side_{id(self)}"

    def involves_component(self, component: str) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "type": self.constraint_type.value,
            "side": self.side.value,
            "edge": self.edge.value,
            "max_distance_mm": self.max_distance_mm,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }

    def collect_tag_exprs(self) -> list[TagExpr]:
        return [self.tag_expr]


@dataclass
class TaggedAnchoredConstraint(BaseConstraint):
    """Anchored constraint using tag expression for component selection."""

    def __init__(
        self,
        tag_expr: TagExpr,
        tier: ConstraintTier,
        because: str,
        region: tuple[float, float, float, float] | None = None,
        position: tuple[float, float] | None = None,
        id: str = "",
    ):
        if region is None and position is None:
            raise ValueError("TaggedAnchoredConstraint requires either region or position")
        self.tag_expr = tag_expr
        self.region = region
        self.position = position
        super().__init__(
            constraint_type=ConstraintType.ANCHORED,
            tier=tier,
            because=because,
            id=id,
        )

    def _generate_id(self) -> str:
        return f"tag_anchor_{id(self)}"

    def involves_component(self, component: str) -> bool:
        return True

    def to_dict(self) -> dict:
        d: dict[str, object] = {
            "type": self.constraint_type.value,
            "tier": self.tier.value,
            "because": self.because,
            "id": self.id,
        }
        if self.region:
            d["region"] = self.region
        if self.position:
            d["position"] = self.position
        return d

    def collect_tag_exprs(self) -> list[TagExpr]:
        return [self.tag_expr]
