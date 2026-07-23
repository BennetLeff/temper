"""Expand tagged constraints into concrete constraint instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    EnclosingConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.pcl.tag_dispatch import _tag_to_component_refs
from temper_placer.pcl.tagged_constraints import (
    TaggedAdjacentConstraint,
    TaggedAlignedConstraint,
    TaggedAnchoredConstraint,
    TaggedEnclosingConstraint,
    TaggedOnSideConstraint,
    TaggedSeparatedConstraint,
)


def _expand_tagged_adjacent(
    constraint: TaggedAdjacentConstraint, netlist: Netlist
) -> list[BaseConstraint]:
    comps_a = _tag_to_component_refs(constraint.tag_expr_a, netlist)
    comps_b = _tag_to_component_refs(constraint.tag_expr_b, netlist)
    constraint_id = constraint.id
    results: list[BaseConstraint] = []
    for a_ref in comps_a:
        for b_ref in comps_b:
            if a_ref == b_ref:
                continue
            results.append(
                AdjacentConstraint(
                    a=a_ref,
                    b=b_ref,
                    max_distance_mm=constraint.max_distance_mm,
                    tier=constraint.tier,
                    because=constraint.because,
                    metric=constraint.metric,
                    id=f"{constraint_id}_{a_ref}_{b_ref}" if constraint_id else "",
                )
            )
    return results


def _expand_tagged_separated(
    constraint: TaggedSeparatedConstraint, netlist: Netlist
) -> list[BaseConstraint]:
    comps_a = _tag_to_component_refs(constraint.tag_expr_a, netlist)
    comps_b = _tag_to_component_refs(constraint.tag_expr_b, netlist)
    constraint_id = constraint.id
    results: list[BaseConstraint] = []
    for a_ref in comps_a:
        for b_ref in comps_b:
            if a_ref == b_ref:
                continue
            results.append(
                SeparatedConstraint(
                    a=a_ref,
                    b=b_ref,
                    min_distance_mm=constraint.min_distance_mm,
                    tier=constraint.tier,
                    because=constraint.because,
                    metric=constraint.metric,
                    id=f"{constraint_id}_{a_ref}_{b_ref}" if constraint_id else "",
                )
            )
    return results


def _expand_tagged_enclosing(
    constraint: TaggedEnclosingConstraint, netlist: Netlist
) -> list[BaseConstraint]:
    comps_inner = _tag_to_component_refs(constraint.tag_expr_inner, netlist)
    if comps_inner:
        return [
            EnclosingConstraint(
                outer=constraint.outer,
                inner=comps_inner,
                tier=constraint.tier,
                because=constraint.because,
                margin_mm=constraint.margin_mm,
                id=constraint.id,
            )
        ]
    return []


def _expand_tagged_aligned(
    constraint: TaggedAlignedConstraint, netlist: Netlist
) -> list[BaseConstraint]:
    comps = _tag_to_component_refs(constraint.tag_expr, netlist)
    if len(comps) >= 2:
        return [
            AlignedConstraint(
                components=comps,
                axis=constraint.axis,
                tier=constraint.tier,
                because=constraint.because,
                tolerance_mm=constraint.tolerance_mm,
                id=constraint.id,
            )
        ]
    return []


def _expand_tagged_on_side(
    constraint: TaggedOnSideConstraint, netlist: Netlist
) -> list[BaseConstraint]:
    comps = _tag_to_component_refs(constraint.tag_expr, netlist)
    if comps:
        return [
            OnSideConstraint(
                components=comps,
                side=constraint.side,
                edge=constraint.edge,
                tier=constraint.tier,
                because=constraint.because,
                max_distance_mm=constraint.max_distance_mm,
                id=constraint.id,
            )
        ]
    return []


def _expand_tagged_anchored(
    constraint: TaggedAnchoredConstraint, netlist: Netlist
) -> list[BaseConstraint]:
    comps = _tag_to_component_refs(constraint.tag_expr, netlist)
    constraint_id = constraint.id
    results: list[BaseConstraint] = []
    for comp_ref in comps:
        results.append(
            AnchoredConstraint(
                component=comp_ref,
                tier=constraint.tier,
                because=constraint.because,
                region=constraint.region,
                position=constraint.position,
                id=f"{constraint_id}_{comp_ref}" if constraint_id else "",
            )
        )
    return results


_TAGGED_EXPANDERS = {
    TaggedAdjacentConstraint: _expand_tagged_adjacent,
    TaggedSeparatedConstraint: _expand_tagged_separated,
    TaggedEnclosingConstraint: _expand_tagged_enclosing,
    TaggedAlignedConstraint: _expand_tagged_aligned,
    TaggedOnSideConstraint: _expand_tagged_on_side,
    TaggedAnchoredConstraint: _expand_tagged_anchored,
}
