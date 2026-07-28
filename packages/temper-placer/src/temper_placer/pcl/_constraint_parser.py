"""PCL constraint parser: dict dispatch and reference resolution."""

from __future__ import annotations

from typing import Any

from temper_placer.pcl._parse_utils import (
    PCLParseError,
    _parse_axis,
    _parse_board_side,
    _parse_distance_with_unit,
    _parse_edge_type,
    _parse_metric,
    _parse_tier,
)
from temper_placer.pcl._tag_parser import (
    _is_tag_expr_dict,
    _parse_constraint_ref,
    _parse_tag_expr,
)
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    CompilationContext,
    ConstraintType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.pcl.tagged_constraints import (
    TaggedAdjacentConstraint,
    TaggedAlignedConstraint,
    TaggedAnchoredConstraint,
    TaggedEnclosingConstraint,
    TaggedOnSideConstraint,
    TaggedSeparatedConstraint,
)


def _is_resolved(constraint: BaseConstraint, context: CompilationContext) -> bool:
    """Check if a constraint's component references can be resolved.

    Returns True if all referenced components/zones exist in the context.
    Returns False if any reference is unresolvable (R10: skip, not error).
    """
    from temper_placer.pcl.resolver import _resolve_to_indices

    try:
        if isinstance(constraint, (AdjacentConstraint, SeparatedConstraint)):
            a_ok = bool(
                _resolve_to_indices(constraint.a, context.netlist, context.board)
                or constraint.a.isupper()
            )
            b_ok = bool(
                _resolve_to_indices(constraint.b, context.netlist, context.board)
                or constraint.b.isupper()
            )
            return a_ok and b_ok
        elif isinstance(constraint, EnclosingConstraint):
            outer_ok = bool(
                constraint.outer.isupper()
                or _resolve_to_indices(constraint.outer, context.netlist, context.board)
            )
            # EnclosingConstraint.__init__ does not enforce a minimum length
            # on `inner` (unlike AlignedConstraint, which raises ValueError
            # below 2), and the "enclosing" parse path in this module passes
            # data["inner"] straight through with no length check either --
            # a PCL author can write `inner: []` and reach here. Without this
            # guard, all() over an empty `inner` is vacuously True, so a
            # zero-component enclosing constraint would report "resolved"
            # and proceed to compile instead of being treated as malformed.
            if not constraint.inner:
                return False
            inner_ok = all(
                _resolve_to_indices(ref, context.netlist, context.board) or ref.isupper()
                for ref in constraint.inner
            )
            return outer_ok and inner_ok
        elif isinstance(constraint, AnchoredConstraint):
            return bool(
                _resolve_to_indices(constraint.component, context.netlist, context.board)
                or constraint.component.isupper()
            )
        elif isinstance(constraint, (AlignedConstraint, OnSideConstraint)):
            # AlignedConstraint.__init__ raises ValueError below 2 components,
            # so `components` can never be empty for that half of this
            # isinstance check -- but OnSideConstraint enforces no minimum
            # (see constraints.py OnSideConstraint.__init__) and the
            # "on_side" parse path passes data["components"] through
            # unchecked, so `components: []` is a reachable PCL input for
            # OnSideConstraint specifically. Guard for the branch as a
            # whole rather than special-casing by type.
            if not constraint.components:
                return False
            return all(
                _resolve_to_indices(ref, context.netlist, context.board) or ref.isupper()
                for ref in constraint.components
            )
        elif isinstance(constraint, LoopAreaConstraint):
            return True
        else:
            return True
    except Exception:
        return False


def parse_constraint_dict(data: dict[str, Any]) -> BaseConstraint:
    """Parse a single constraint from a dictionary.

    Args:
        data: Dictionary containing constraint fields

    Returns:
        Parsed constraint object

    Raises:
        PCLParseError: If constraint type is invalid or required fields are missing
    """
    if "type" not in data:
        raise PCLParseError("Constraint missing required field: 'type'")
    if "tier" not in data:
        raise PCLParseError("Constraint missing required field: 'tier'")
    if "because" not in data:
        raise PCLParseError("Constraint missing required field: 'because'")

    constraint_type = data["type"]
    tier = _parse_tier(data["tier"])
    because = data["because"]
    constraint_id = data.get("id", "")

    a_is_tag = constraint_type in ("adjacent", "separated") and _is_tag_expr_dict(data.get("a"))
    b_is_tag = constraint_type in ("adjacent", "separated") and _is_tag_expr_dict(data.get("b"))
    has_tag_expr = a_is_tag or b_is_tag

    if constraint_type == "adjacent":
        if has_tag_expr:
            tag_expr_a = _parse_constraint_ref(data["a"], default_to_tag=True)
            tag_expr_b = _parse_constraint_ref(data["b"], default_to_tag=True)
            return TaggedAdjacentConstraint(
                tag_expr_a=tag_expr_a,
                tag_expr_b=tag_expr_b,
                max_distance_mm=_parse_distance_with_unit(data["max_distance_mm"]),
                tier=tier,
                because=because,
                metric=_parse_metric(data.get("metric")),
                id=constraint_id,
            )
        return AdjacentConstraint(
            a=data["a"],
            b=data["b"],
            max_distance_mm=_parse_distance_with_unit(data["max_distance_mm"]),
            tier=tier,
            because=because,
            metric=_parse_metric(data.get("metric")),
            pin_a=data.get("pin_a"),
            pin_b=data.get("pin_b"),
            id=constraint_id,
        )

    elif constraint_type == "separated":
        if has_tag_expr:
            tag_expr_a = _parse_constraint_ref(data["a"], default_to_tag=True)
            tag_expr_b = _parse_constraint_ref(data["b"], default_to_tag=True)
            return TaggedSeparatedConstraint(
                tag_expr_a=tag_expr_a,
                tag_expr_b=tag_expr_b,
                min_distance_mm=_parse_distance_with_unit(data["min_distance_mm"]),
                tier=tier,
                because=because,
                metric=_parse_metric(data.get("metric")),
                id=constraint_id,
            )
        return SeparatedConstraint(
            a=data["a"],
            b=data["b"],
            min_distance_mm=_parse_distance_with_unit(data["min_distance_mm"]),
            tier=tier,
            because=because,
            metric=_parse_metric(data.get("metric")),
            id=constraint_id,
        )

    elif constraint_type == "enclosing":
        inner_data = data["inner"]
        has_inner_tags = isinstance(inner_data, list) and any(
            _is_tag_expr_dict(item) for item in inner_data
        )
        if has_inner_tags:
            if _is_tag_expr_dict(inner_data):
                tag_expr_inner = _parse_tag_expr(inner_data)
            elif len(inner_data) == 1:
                tag_expr_inner = _parse_tag_expr(inner_data[0])
            else:
                tag_expr_inner = _parse_tag_expr({"and": inner_data})
            return TaggedEnclosingConstraint(
                outer=data["outer"],
                tag_expr_inner=tag_expr_inner,
                tier=tier,
                because=because,
                margin_mm=_parse_distance_with_unit(data.get("margin_mm", 0.0)),
                id=constraint_id,
            )
        return EnclosingConstraint(
            outer=data["outer"],
            inner=data["inner"],
            tier=tier,
            because=because,
            margin_mm=_parse_distance_with_unit(data.get("margin_mm", 0.0)),
            id=constraint_id,
        )

    elif constraint_type == "keepout":
        return KeepoutConstraint(
            zone_name=data["zone_name"],
            tier=tier,
            because=because,
            margin_mm=_parse_distance_with_unit(data.get("margin_mm", 0.0)),
            id=constraint_id,
        )

    elif constraint_type == "aligned":
        components_data = data["components"]
        has_tagged = isinstance(components_data, list) and any(
            _is_tag_expr_dict(item) for item in components_data
        )
        if has_tagged or _is_tag_expr_dict(components_data):
            if _is_tag_expr_dict(components_data):
                tag_expr = _parse_tag_expr(components_data)
            elif len(components_data) == 1:
                tag_expr = _parse_tag_expr(components_data[0])
            else:
                tag_expr = _parse_tag_expr({"and": components_data})
            return TaggedAlignedConstraint(
                tag_expr=tag_expr,
                axis=_parse_axis(data["axis"]),
                tier=tier,
                because=because,
                tolerance_mm=_parse_distance_with_unit(data.get("tolerance_mm", 0.5)),
                id=constraint_id,
            )
        return AlignedConstraint(
            components=data["components"],
            axis=_parse_axis(data["axis"]),
            tier=tier,
            because=because,
            tolerance_mm=_parse_distance_with_unit(data.get("tolerance_mm", 0.5)),
            id=constraint_id,
        )

    elif constraint_type == "on_side":
        components_data = data["components"]
        has_tagged = isinstance(components_data, list) and any(
            _is_tag_expr_dict(item) for item in components_data
        )
        if has_tagged or _is_tag_expr_dict(components_data):
            if _is_tag_expr_dict(components_data):
                tag_expr = _parse_tag_expr(components_data)
            elif len(components_data) == 1:
                tag_expr = _parse_tag_expr(components_data[0])
            else:
                tag_expr = _parse_tag_expr({"and": components_data})
            return TaggedOnSideConstraint(
                tag_expr=tag_expr,
                side=_parse_board_side(data["side"]),
                edge=_parse_edge_type(data["edge"]),
                tier=tier,
                because=because,
                max_distance_mm=_parse_distance_with_unit(data.get("max_distance_mm", 5.0)),
                id=constraint_id,
            )
        return OnSideConstraint(
            components=data["components"],
            side=_parse_board_side(data["side"]),
            edge=_parse_edge_type(data["edge"]),
            tier=tier,
            because=because,
            max_distance_mm=_parse_distance_with_unit(data.get("max_distance_mm", 5.0)),
            id=constraint_id,
        )

    elif constraint_type == "anchored":
        component_data = data["component"]
        if _is_tag_expr_dict(component_data):
            tag_expr = _parse_tag_expr(component_data)
            region = data.get("region")
            position = data.get("position")
            if region is not None:
                region = tuple(region)
            if position is not None:
                position = tuple(position)
            return TaggedAnchoredConstraint(
                tag_expr=tag_expr,
                tier=tier,
                because=because,
                region=region,
                position=position,
                id=constraint_id,
            )

        region = data.get("region")
        position = data.get("position")
        if region is not None:
            region = tuple(region)
        if position is not None:
            position = tuple(position)
        return AnchoredConstraint(
            component=data["component"],
            tier=tier,
            because=because,
            region=region,
            position=position,
            id=constraint_id,
        )

    elif constraint_type == "loop_area":
        max_area = float(data["max_area_mm2"])
        if max_area < 0:
            raise PCLParseError(f"max_area_mm2 cannot be negative: {max_area}")
        return LoopAreaConstraint(
            loop_name=data["loop_name"],
            max_area_mm2=max_area,
            tier=tier,
            because=because,
            id=constraint_id,
        )

    else:
        raise PCLParseError(
            f"Unknown constraint type: {constraint_type}. Valid types: "
            + ", ".join(t.value for t in ConstraintType)
        )
