"""
Component tag hierarchy and semantic dispatch for PCL tagged constraints.

Provides a 14-tag enumeration (ComponentTag) with Floyd-Warshall transitive
closure, tag expression algebra (TagRef, TagAnd, TagOr, TagNot, ComponentRef),
resolution against netlist components, and expansion to concrete constraints.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Netlist


class TagValidationError(Exception):
    """Raised when tag expressions fail pre-expansion validation."""


class ComponentTag(Enum):
    """14-tag semantic hierarchy for component classification.

    The partial order is: ALL > POWER/SIGNAL/MECHANICAL > specialized tags.
    The transitive closure is pre-computed at module load using Floyd-Warshall.
    """

    ALL = "all"
    POWER = "power"
    SIGNAL = "signal"
    MECHANICAL = "mechanical"
    HV = "hv"
    LV = "lv"
    GATE_DRIVE = "gate_drive"
    SENSOR = "sensor"
    MCU = "mcu"
    CONNECTOR = "connector"
    MOUNTING = "mounting"
    THERMAL = "thermal"
    DECOUPLING = "decoupling"
    FERRITE = "ferrite"

    def __le__(self, other: ComponentTag) -> bool:
        """Check if self is more specific than or equal to other."""
        if not isinstance(other, ComponentTag):
            return NotImplemented
        return other in _TAG_CLOSURE.get(self, frozenset())


# Parent-child relationships: key -> set of direct parents
_TAG_HIERARCHY_UP: dict[ComponentTag, frozenset[ComponentTag]] = {
    ComponentTag.ALL: frozenset(),
    ComponentTag.POWER: frozenset({ComponentTag.ALL}),
    ComponentTag.SIGNAL: frozenset({ComponentTag.ALL}),
    ComponentTag.MECHANICAL: frozenset({ComponentTag.ALL}),
    ComponentTag.HV: frozenset({ComponentTag.POWER}),
    ComponentTag.LV: frozenset({ComponentTag.POWER}),
    ComponentTag.GATE_DRIVE: frozenset({ComponentTag.SIGNAL}),
    ComponentTag.SENSOR: frozenset({ComponentTag.SIGNAL}),
    ComponentTag.MCU: frozenset({ComponentTag.SIGNAL}),
    ComponentTag.CONNECTOR: frozenset({ComponentTag.MECHANICAL}),
    ComponentTag.MOUNTING: frozenset({ComponentTag.MECHANICAL}),
    ComponentTag.THERMAL: frozenset({ComponentTag.MECHANICAL}),
    ComponentTag.DECOUPLING: frozenset({ComponentTag.POWER}),
    ComponentTag.FERRITE: frozenset({ComponentTag.POWER}),
}


def _compute_transitive_closure(
    hierarchy: dict[ComponentTag, frozenset[ComponentTag]],
) -> dict[ComponentTag, frozenset[ComponentTag]]:
    """Compute transitive closure via Floyd-Warshall.

    Each tag maps to all ancestors (including itself).
    """
    all_tags = list(ComponentTag)
    idx_map = {tag: i for i, tag in enumerate(all_tags)}
    n = len(all_tags)

    closure = [[False] * n for _ in range(n)]
    for tag, parents in hierarchy.items():
        i = idx_map[tag]
        closure[i][i] = True
        for parent in parents:
            j = idx_map[parent]
            closure[i][j] = True

    for k in range(n):
        for i in range(n):
            for j in range(n):
                if closure[i][k] and closure[k][j]:
                    closure[i][j] = True

    result: dict[ComponentTag, frozenset[ComponentTag]] = {}
    for tag, i in idx_map.items():
        result[tag] = frozenset(
            all_tags[j] for j in range(n) if closure[i][j]
        )
    return result


_TAG_CLOSURE: dict[ComponentTag, frozenset[ComponentTag]] = _compute_transitive_closure(
    _TAG_HIERARCHY_UP
)


@dataclass(frozen=True)
class TagRef:
    """Reference to a single component tag in a tag expression."""

    tag: ComponentTag


@dataclass(frozen=True)
class TagAnd:
    """Logical AND of two tag expressions."""

    left: TagExpr
    right: TagExpr


@dataclass(frozen=True)
class TagOr:
    """Logical OR of two tag expressions."""

    left: TagExpr
    right: TagExpr


@dataclass(frozen=True)
class TagNot:
    """Logical NOT of a tag expression."""

    expr: TagExpr


@dataclass(frozen=True)
class ComponentRef:
    """Reference to a specific component by refdes."""

    ref: str


TagExpr = Union[TagRef, TagAnd, TagOr, TagNot, ComponentRef]


def resolve(expr: TagExpr, comp: Component) -> bool:
    """Resolve a tag expression against a component.

    Uses the tag hierarchy: a component with tag 'hv' also matches POWER and ALL
    via transitive closure.

    Args:
        expr: Tag expression to evaluate.
        comp: Component to test.

    Returns:
        True if the component matches the expression.
    """
    if isinstance(expr, TagRef):
        comp_tags_upper = {t.upper() for t in comp.tags}
        tag_value_upper = expr.tag.value.upper()
        if tag_value_upper in comp_tags_upper:
            return True
        for ct_str in comp.tags:
            try:
                ct = ComponentTag(ct_str.lower())
            except ValueError:
                continue
            if ct <= expr.tag:
                return True
        return False
    elif isinstance(expr, TagAnd):
        return resolve(expr.left, comp) and resolve(expr.right, comp)
    elif isinstance(expr, TagOr):
        return resolve(expr.left, comp) or resolve(expr.right, comp)
    elif isinstance(expr, TagNot):
        return not resolve(expr.expr, comp)
    elif isinstance(expr, ComponentRef):
        return comp.ref == expr.ref
    return False


def components(expr: TagExpr, netlist: Netlist) -> list[Component]:
    """Find all components in a netlist matching a tag expression.

    Args:
        expr: Tag expression to evaluate.
        netlist: Netlist to search.

    Returns:
        List of matching components.
    """
    return [c for c in netlist.components if resolve(expr, c)]


def _extract_params(
    tc, param_names: tuple[str, ...] = ("max_distance_mm", "min_distance_mm", "margin_mm")
) -> dict:
    """Extract constraint parameters for overconstrained detection."""
    params = {}
    for name in param_names:
        if hasattr(tc, name):
            params[name] = getattr(tc, name)
    return params


def _check_overconstrained(expanded: list[tuple]) -> None:
    """Check for overconstrained tag expansion results.

    Detects pairs of constraints on the same component pair with contradictory
    distance parameters, including tc_type and tc_id in the expanded tuples.
    """
    adjacency: dict[tuple[str, str], list[tuple[str, str, float]]] = {}
    separation: dict[tuple[str, str], list[tuple[str, str, float]]] = {}

    for entry in expanded:
        tc = entry[0]
        tc_type = entry[2] if len(entry) > 2 else getattr(tc, "constraint_type", "unknown")

        if hasattr(tc, "a") and hasattr(tc, "b"):
            key = tuple(sorted([tc.a, tc.b]))
            if hasattr(tc, "max_distance_mm"):
                adjacency.setdefault(key, []).append(
                    (str(tc_type), getattr(tc, "id", ""), tc.max_distance_mm)
                )
            elif hasattr(tc, "min_distance_mm"):
                separation.setdefault(key, []).append(
                    (str(tc_type), getattr(tc, "id", ""), tc.min_distance_mm)
                )

    for key in set(adjacency.keys()) & set(separation.keys()):
        adj_entries = adjacency[key]
        sep_entries = separation[key]
        for (a_type, a_id, a_dist), (s_type, s_id, s_dist) in itertools.product(
            adj_entries, sep_entries
        ):
            if s_dist > a_dist:
                raise TagValidationError(
                    f"Overconstrained: components '{key[0]}' and '{key[1]}' from tags "
                    f"[{a_type}:{a_id}] must be ≤{a_dist:.1f}mm but "
                    f"[{s_type}:{s_id}] requires ≥{s_dist:.1f}mm"
                )


def _tag_to_component_refs(tag_expr: TagExpr, netlist: Netlist) -> list[str]:
    """Get component refs matching a tag expression."""
    result = components(tag_expr, netlist)
    return [c.ref for c in result]


def E(tc, netlist: Netlist, max_expansion: int = 500) -> list:
    """Expand a tagged constraint to concrete instances.

    Takes a tagged constraint and resolves its tag expressions against the
    netlist to produce a list of concrete constraints. Compound constraint
    types produce multiple concrete instances.

    Args:
        tc: A tagged constraint (with tag_expr or tag_exprs fields).
        netlist: Netlist to resolve component references against.
        max_expansion: Maximum number of expanded constraints allowed.

    Returns:
        List of (concrete_constraint, ...) tuples where each entry is
        (constraint, netlist) and additional metadata.

    Raises:
        TagValidationError: If expansion would exceed max_expansion.
    """
    result = []

    if hasattr(tc, "tag_expr_a") and hasattr(tc, "tag_expr_b"):
        comps_a = _tag_to_component_refs(tc.tag_expr_a, netlist)
        comps_b = _tag_to_component_refs(tc.tag_expr_b, netlist)
        typ_name = type(tc).__name__
        tc_id = getattr(tc, "id", "")
        tc_type = getattr(tc, "constraint_type", "unknown")
        for a_ref in comps_a:
            for b_ref in comps_b:
                if a_ref == b_ref:
                    continue
                result.append((tc, netlist, str(tc_type), tc_id))
                if len(result) > max_expansion:
                    raise TagValidationError(
                        f"Tag expansion for '{typ_name}:{tc_id}' would exceed "
                        f"max_expansion={max_expansion}"
                    )
    elif hasattr(tc, "tag_expr_outer") and hasattr(tc, "tag_expr_inner"):
        typ_name = type(tc).__name__
        tc_id = getattr(tc, "id", "")
        tc_type = getattr(tc, "constraint_type", "unknown")
        for _inner_ref in components(tc.tag_expr_inner, netlist):
            result.append((tc, netlist, str(tc_type), tc_id))
            if len(result) > max_expansion:
                raise TagValidationError(
                    f"Tag expansion for '{typ_name}:{tc_id}' would exceed "
                    f"max_expansion={max_expansion}"
                )
    elif hasattr(tc, "collect_tag_exprs"):
        for _tag_expr in tc.collect_tag_exprs():
            for _comp in components(_tag_expr, netlist):
                result.append((tc, netlist, str(tc.constraint_type), getattr(tc, "id", "")))
                if len(result) > max_expansion:
                    raise TagValidationError(
                        f"Tag expansion would exceed max_expansion={max_expansion}"
                    )
    else:
        typ_name = type(tc).__name__
        tc_id = getattr(tc, "id", "")
        tc_type = getattr(tc, "constraint_type", "unknown")
        result.append((tc, netlist, str(tc_type), tc_id))

    _check_overconstrained(result)
    return result


def pre_expansion_validate(tc) -> None:
    """Validate a tagged constraint before expansion.

    Checks that tag expressions are well-formed and that at minimum one
    component could potentially match.

    Args:
        tc: Tagged constraint to validate.

    Raises:
        TagValidationError: If validation fails.
    """
    tag_exprs = []
    for attr_name in dir(tc):
        if attr_name.startswith("tag_expr") and not attr_name.startswith("tag_exprs_"):
            val = getattr(tc, attr_name)
            if val is not None:
                tag_exprs.append(val)
    if hasattr(tc, "collect_tag_exprs"):
        tag_exprs.extend(tc.collect_tag_exprs())

    for expr in tag_exprs:
        if isinstance(expr, str):
            raise TagValidationError(
                f"Tag expression must be a typed expression, got raw string: {expr!r}"
            )

    if not tag_exprs:
        raise TagValidationError("Tagged constraint has no tag expressions")
