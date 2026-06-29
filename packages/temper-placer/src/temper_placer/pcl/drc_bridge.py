"""
PCL to DRC assertion compilation bridge.

Maps all 7 PCL constraint types to DRC assertion specifications
for post-route validation. Each assertion carries the source PCL
constraint `id` and `because` for traceable violation reports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    CompilationContext,
    ConstraintType,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)


@dataclass
class DRCAssertion:
    """A DRC check derived from a PCL constraint.

    Attributes:
        source_id: PCL constraint id (R12 traceability).
        source_because: PCL constraint because string (R12).
        check_type: Type of check (distance, containment, alignment, area).
        subjects: Component references involved.
        threshold: Numeric threshold (min/max distance, max area, tolerance).
        metric: How distance is measured.
        pass_criteria: Human-readable pass condition.
    """

    source_id: str
    source_because: str
    check_type: str
    subjects: list[str]
    threshold: float
    metric: str = "edge_to_edge"
    pass_criteria: str = ""
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-type handlers (R11)
# ---------------------------------------------------------------------------


def _adjacent_to_drc(
    constraint: AdjacentConstraint, ctx: CompilationContext,  # noqa: ARG001
) -> list[DRCAssertion]:
    return [
        DRCAssertion(
            source_id=constraint.id,
            source_because=constraint.because,
            check_type="distance_max",
            subjects=[constraint.a, constraint.b],
            threshold=constraint.max_distance_mm,
            metric=constraint.metric.value,
            pass_criteria=f"Measured edge-to-edge distance ≤ {constraint.max_distance_mm}mm",
            metadata={"pin_a": constraint.pin_a, "pin_b": constraint.pin_b} if constraint.pin_a else {},
        )
    ]


def _separated_to_drc(
    constraint: SeparatedConstraint, ctx: CompilationContext,  # noqa: ARG001
) -> list[DRCAssertion]:
    return [
        DRCAssertion(
            source_id=constraint.id,
            source_because=constraint.because,
            check_type="distance_min",
            subjects=[constraint.a, constraint.b],
            threshold=constraint.min_distance_mm,
            metric=constraint.metric.value,
            pass_criteria=f"Measured edge-to-edge distance ≥ {constraint.min_distance_mm}mm; includes creepage path",
        )
    ]


def _enclosing_to_drc(
    constraint: EnclosingConstraint, ctx: CompilationContext,  # noqa: ARG001
) -> list[DRCAssertion]:
    assertions = []
    for comp_ref in constraint.inner:
        assertions.append(
            DRCAssertion(
                source_id=constraint.id,
                source_because=constraint.because,
                check_type="containment",
                subjects=[comp_ref, constraint.outer],
                threshold=constraint.margin_mm,
                metric="centroid_to_zone",
                pass_criteria=f"Component '{comp_ref}' centroid within zone '{constraint.outer}' (±{constraint.margin_mm}mm margin)",
            )
        )
    return assertions


def _aligned_to_drc(
    constraint: AlignedConstraint, ctx: CompilationContext,  # noqa: ARG001
) -> list[DRCAssertion]:
    return [
        DRCAssertion(
            source_id=constraint.id,
            source_because=constraint.because,
            check_type="alignment",
            subjects=constraint.components,
            threshold=constraint.tolerance_mm,
            metric=f"axis_{constraint.axis.value}",
            pass_criteria=f"Maximum deviation from {constraint.axis.value} alignment axis ≤ {constraint.tolerance_mm}mm",
        )
    ]


def _onside_to_drc(
    constraint: OnSideConstraint, ctx: CompilationContext,  # noqa: ARG001
) -> list[DRCAssertion]:
    overhang_note = " (overhang permitted)" if constraint.edge.value == "overhang" else ""
    return [
        DRCAssertion(
            source_id=constraint.id,
            source_because=constraint.because,
            check_type="edge_proximity",
            subjects=constraint.components,
            threshold=constraint.max_distance_mm,
            metric=f"edge_{constraint.side.value}",
            pass_criteria=f"Component center within {constraint.max_distance_mm}mm of {constraint.side.value} edge; bounding box does not overhang board{overhang_note}",
        )
    ]


def _anchored_to_drc(
    constraint: AnchoredConstraint, ctx: CompilationContext,  # noqa: ARG001
) -> list[DRCAssertion]:
    if constraint.position is not None:
        threshold = 0.0
        criteria = f"Component '{constraint.component}' center at position {constraint.position}"
    elif constraint.region is not None:
        threshold = 0.0
        criteria = f"Component '{constraint.component}' center within region {constraint.region}"
    else:
        return []

    return [
        DRCAssertion(
            source_id=constraint.id,
            source_because=constraint.because,
            check_type="position",
            subjects=[constraint.component],
            threshold=threshold,
            metric="center_to_target",
            pass_criteria=criteria,
        )
    ]


def _loop_area_to_drc(
    constraint: LoopAreaConstraint, ctx: CompilationContext,  # noqa: ARG001
) -> list[DRCAssertion]:
    return [
        DRCAssertion(
            source_id=constraint.id,
            source_because=constraint.because,
            check_type="area_max",
            subjects=[constraint.loop_name],
            threshold=constraint.max_area_mm2,
            metric="polygon_area",
            pass_criteria=f"Loop '{constraint.loop_name}' polygon area ≤ {constraint.max_area_mm2}mm²",
        )
    ]


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

TYPE_HANDLERS: dict[ConstraintType, Callable] = {
    ConstraintType.ADJACENT: _adjacent_to_drc,
    ConstraintType.SEPARATED: _separated_to_drc,
    ConstraintType.ENCLOSING: _enclosing_to_drc,
    ConstraintType.ALIGNED: _aligned_to_drc,
    ConstraintType.ON_SIDE: _onside_to_drc,
    ConstraintType.ANCHORED: _anchored_to_drc,
    ConstraintType.LOOP_AREA: _loop_area_to_drc,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def constraint_to_assertions(
    constraint: BaseConstraint, ctx: CompilationContext,
) -> list[DRCAssertion]:
    """Convert a PCL constraint to DRC assertions."""
    handler = TYPE_HANDLERS.get(constraint.constraint_type)
    if handler is None:
        return []
    return handler(constraint, ctx)


def _backend_adapter(
    constraint: BaseConstraint, context: CompilationContext,
) -> list[DRCAssertion]:
    """Adapter for BaseConstraint.backends["drc"] registration."""
    return constraint_to_assertions(constraint, context)


# Register the DRC backend (R5, R11).
BaseConstraint.backends["drc"] = _backend_adapter  # type: ignore[attr-defined]
