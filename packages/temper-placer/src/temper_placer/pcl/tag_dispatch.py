"""
Component tag hierarchy and semantic dispatch for PCL tagged constraints.

Provides a 14-tag enumeration (ComponentTag) with Floyd-Warshall transitive
closure, tag expression algebra (TagRef, TagAnd, TagOr, TagNot, ComponentRef),
resolution against netlist components, and expansion to concrete constraints.

The tag-expression node types and the resolution compute are implemented in
Rust in the ``temper-design-bundle`` crate (``temper_design_bundle_python``,
module ``pcl_tags.rs``) -- the Wave 4 Phase 2 "contracts-as-pyo3-pyclasses"
pivot. ``TagRef``/``TagAnd``/``TagOr``/``TagNot``/``ComponentRef`` are now
pyo3 ``#[pyclass(frozen)]`` contract objects, so an expression tree built
once here is walked entirely in Rust for a whole netlist sweep instead of
being re-marshalled per component.

``ComponentTag`` stays a Python ``enum.Enum``: production code does
``for t in ComponentTag`` and ``ComponentTag(value)``, neither of which a
pyo3 ``#[pyclass]`` enum can provide (class-level iteration needs a metaclass
hook pyo3 does not expose). Its ``__le__`` delegates to the Rust lattice.

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/pcl/test_tag_dispatch_rust_differential.py`` (oracle:
``tests/pcl/_tag_dispatch_py_oracle.py``); the structural/inductive argument
lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Union

import temper_design_bundle_python as _tdb

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Netlist


class TagValidationError(Exception):
    """Raised when tag expressions fail pre-expansion validation."""


class ComponentTag(Enum):
    """14-tag semantic hierarchy for component classification.

    The partial order is: ALL > POWER/SIGNAL/MECHANICAL > specialized tags.
    The transitive closure is pre-computed at module load using Floyd-Warshall
    (now in Rust: ``pcl_tags.rs::compute_closure``).
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
        """Check if self is more specific than or equal to other.

        Returns ``NotImplemented`` for a non-ComponentTag right-hand side --
        which is what makes ``ComponentTag.HV <= 'power'`` raise TypeError
        rather than quietly answering False.
        """
        return _tdb.pcl_tag_le(self, other)


# Parent-child relationships: key -> set of direct parents.
#
# Kept here as the declarative source of truth even though the closure is now
# computed in Rust: this table is what a reviewer reads to check the
# hierarchy, and `test_tag_dispatch_rust_differential.py` asserts the Rust
# lattice (`pcl_tags.rs::TAG_PARENTS`) still matches it edge for edge, so the
# two cannot drift silently.
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


# Each tag maps to all ancestors (including itself). Built by the Rust
# Floyd-Warshall port; insertion order matches `list(ComponentTag)`, as the
# Python's `for tag, i in idx_map.items()` produced.
_TAG_CLOSURE: dict[ComponentTag, frozenset[ComponentTag]] = _tdb.pcl_tag_closure()


# The tag-expression algebra: pyo3 #[pyclass(frozen)] contract objects.
# Re-exported under their original names so every existing
# `from temper_placer.pcl.tag_dispatch import TagRef` keeps working.
TagRef = _tdb.TagRef
TagAnd = _tdb.TagAnd
TagOr = _tdb.TagOr
TagNot = _tdb.TagNot
ComponentRef = _tdb.ComponentRef

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
    return _tdb.pcl_resolve(expr, comp)


def components(expr: TagExpr, netlist: Netlist) -> list[Component]:
    """Find all components in a netlist matching a tag expression.

    Args:
        expr: Tag expression to evaluate.
        netlist: Netlist to search.

    Returns:
        List of matching components.
    """
    return _tdb.pcl_components(expr, netlist)


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
    return _tdb.pcl_check_overconstrained(expanded)


def _tag_to_component_refs(tag_expr: TagExpr, netlist: Netlist) -> list[str]:
    """Get component refs matching a tag expression."""
    return _tdb.pcl_tag_to_component_refs(tag_expr, netlist)


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

    Note:
        Deliberately NOT migrated. This is `hasattr`-driven duck-typed
        dispatch over arbitrary Python constraint objects -- the shape
        discovery, not the compute, is the whole function. Porting it would
        mean a Rust `hasattr` chain that is strictly slower (one FFI hop per
        probe) and strictly more fragile than the Python. The compute it
        delegates to (`_tag_to_component_refs`, `components`,
        `_check_overconstrained`) is what moved.
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

    Note:
        Deliberately NOT migrated, for the same reason as `E`: the function
        is a `dir(tc)` reflection sweep over arbitrary Python objects.
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
