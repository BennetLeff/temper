"""PCL tag expression parser: boolean logic over component tags."""

from __future__ import annotations

import warnings
from typing import Any

from temper_placer.pcl._parse_utils import PCLParseError


def _is_tag_expr_dict(value: Any) -> bool:
    """Check if a value represents a tag expression dict."""
    if not isinstance(value, dict):
        return False
    return any(k in value for k in ("tag", "and", "or", "not", "ref"))


def _parse_tag_expr(value: Any):
    """Parse a tag expression from a YAML dict.

    Supports:
        {tag: POWER}            -> TagRef(ComponentTag.POWER)
        {ref: Q1}               -> ComponentRef("Q1")
        {and: [...]}            -> TagAnd(left, right)
        {or: [...]}             -> TagOr(left, right)
        {not: {...}}            -> TagNot(expr)

    Args:
        value: Dict with tag expression keys

    Returns:
        TagExpr instance

    Raises:
        PCLParseError: If value cannot be parsed as a tag expression
    """
    from temper_placer.pcl.tag_dispatch import (
        ComponentRef,
        ComponentTag,
        TagAnd,
        TagNot,
        TagOr,
        TagRef,
    )

    if not isinstance(value, dict):
        raise PCLParseError(f"Expected tag expression dict, got {type(value)}")

    if "tag" in value:
        tag_name = str(value["tag"])
        try:
            tag = ComponentTag(tag_name.lower())
        except ValueError:
            valid = [t.value for t in ComponentTag]
            warnings.warn(
                f"Unknown tag '{tag_name}', treating as literal ref. Valid tags: {sorted(valid)}",
                stacklevel=2,
            )
            return ComponentRef(tag_name.upper())
        return TagRef(tag)

    elif "ref" in value:
        return ComponentRef(str(value["ref"]))

    elif "not" in value:
        return TagNot(_parse_tag_expr(value["not"]))

    elif "and" in value:
        parts = value["and"]
        if not isinstance(parts, list) or len(parts) < 2:
            raise PCLParseError("'and' requires a list of at least 2 tag expressions")
        result = _parse_tag_expr(parts[0])
        for part in parts[1:]:
            result = TagAnd(result, _parse_tag_expr(part))
        return result

    elif "or" in value:
        parts = value["or"]
        if not isinstance(parts, list) or len(parts) < 2:
            raise PCLParseError("'or' requires a list of at least 2 tag expressions")
        result = _parse_tag_expr(parts[0])
        for part in parts[1:]:
            result = TagOr(result, _parse_tag_expr(part))
        return result

    else:
        raise PCLParseError(f"Unknown tag expression keys: {list(value.keys())}")


def _parse_constraint_ref(value: Any, default_to_tag: bool = False):
    """Parse a constraint reference field (a/b/inner/etc).

    If value is a string, treat as ComponentRef (existing behavior via string).
    If value is a dict with tag expression keys, parse as TagExpr.
    Returns the raw string (for concrete constraints) or a TagExpr (for tagged constraints).

    Args:
        value: The field value from YAML
        default_to_tag: If True, wrap strings as ComponentRef

    Returns:
        str or TagExpr
    """
    if isinstance(value, str):
        if default_to_tag:
            from temper_placer.pcl.tag_dispatch import ComponentRef

            return ComponentRef(value)
        return value

    if _is_tag_expr_dict(value):
        return _parse_tag_expr(value)

    raise PCLParseError(
        f"Invalid constraint reference: expected string or tag expression dict, got {type(value)}"
    )
