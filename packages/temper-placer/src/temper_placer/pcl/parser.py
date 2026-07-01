"""
PCL (Placement Constraint Language) parser for loading constraints from YAML.

This module provides functions to parse constraint definitions from YAML files
and convert them to typed constraint objects. The parser handles type dispatch,
validation, and unit conversion.

Example usage:
    >>> from temper_placer.pcl.parser import parse_pcl_file, ConstraintCollection
    >>>
    >>> # Load constraints from YAML file
    >>> collection = parse_pcl_file("configs/half_bridge_constraints.yaml")
    >>> print(len(collection.constraints))
    12
    >>>
    >>> # Validate against netlist
    >>> errors = collection.validate_component_refs(netlist)
    >>> if errors:
    ...     print(f"Found {len(errors)} validation errors")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]
from jsonschema import ValidationError, validate

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BaseConstraint,
    BoardSide,
    CompilationContext,
    CompilationTarget,
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
    EdgeType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


class PCLParseError(Exception):
    """Error parsing a PCL constraint definition."""

    pass


class PCLValidationError(Exception):
    """Error validating constraint references."""

    pass


def _is_resolved(constraint: BaseConstraint, context: CompilationContext) -> bool:
    """Check if a constraint's component references can be resolved.

    Returns True if all referenced components/zones exist in the context.
    Returns False if any reference is unresolvable (R10: skip, not error).
    """
    from temper_placer.pcl.loss_bridge import _resolve_to_indices

    try:
        if isinstance(constraint, (AdjacentConstraint, SeparatedConstraint)):
            a_ok = bool(_resolve_to_indices(constraint.a, context.netlist, context.board) or constraint.a.isupper())
            b_ok = bool(_resolve_to_indices(constraint.b, context.netlist, context.board) or constraint.b.isupper())
            return a_ok and b_ok
        elif isinstance(constraint, EnclosingConstraint):
            outer_ok = bool(constraint.outer.isupper() or _resolve_to_indices(constraint.outer, context.netlist, context.board))
            inner_ok = all(
                _resolve_to_indices(ref, context.netlist, context.board) or ref.isupper()
                for ref in constraint.inner
            )
            return outer_ok and inner_ok
        elif isinstance(constraint, AnchoredConstraint):
            return bool(_resolve_to_indices(constraint.component, context.netlist, context.board) or constraint.component.isupper())
        elif isinstance(constraint, (AlignedConstraint, OnSideConstraint)):
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


def load_pcl_schema() -> dict[str, Any]:
    """Load the PCL JSON schema from the package resources."""
    import importlib.resources as pkg_resources

    try:
        # Use files() API (KiCad 6+ / Python 3.9+)
        schema_file = pkg_resources.files("temper_placer.pcl.schemas").joinpath("pcl.schema.json")
        schema_text = schema_file.read_text()
        return json.loads(schema_text)
    except Exception as e:
        # Fallback for development/non-installed runs
        schema_path = Path(__file__).parent / "schemas" / "pcl.schema.json"
        if schema_path.exists():
            with open(schema_path) as f:
                return json.load(f)
        raise RuntimeError(f"Could not load PCL schema: {e}") from e


def validate_pcl_dict(data: dict[str, Any]) -> None:
    """Validate a PCL dictionary against the JSON schema.

    Args:
        data: PCL dictionary to validate

    Raises:
        PCLValidationError: If data does not match the schema
    """
    schema = load_pcl_schema()
    try:
        validate(instance=data, schema=schema)
    except ValidationError as e:
        raise PCLValidationError(f"PCL schema validation failed: {e.message}") from e


@dataclass
class ConstraintCollection:
    """Collection of PCL constraints with validation methods.

    Attributes:
        constraints: List of parsed constraints
        version: PCL schema version
        metadata: Optional metadata from YAML file
    """

    constraints: list[BaseConstraint]
    version: str = "1.0"
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def __len__(self) -> int:
        """Return number of constraints."""
        return len(self.constraints)

    def copy(self) -> ConstraintCollection:
        """Create a deep copy of the collection."""
        import copy
        return ConstraintCollection(
            constraints=copy.deepcopy(self.constraints),
            version=self.version,
            metadata=copy.deepcopy(self.metadata)
        )

    def add(self, constraint: BaseConstraint) -> None:
        """Add a constraint to the collection."""
        self.constraints.append(constraint)

    def compile(self, target: CompilationTarget, context: CompilationContext) -> list:
        """Dispatch all constraints to the target backend.

        Args:
            target: Compilation target (JAX, SAT, or DRC).
            context: CompilationContext with netlist, board, etc.

        Returns:
            List of backend-specific outputs (one entry per constraint
            that targets this backend).

        Raises:
            ValueError: If no backend is registered for the target.
        """
        backend_fn = BaseConstraint.backends.get(target.value)  # type: ignore[attr-defined]
        if backend_fn is None:
            raise ValueError(
                f"No backend registered for target '{target.value}'. "
                f"Available: {sorted(BaseConstraint.backends.keys())}"  # type: ignore[attr-defined]
            )
        results = []
        for constraint in self.constraints:
            if target.value not in constraint.targets:
                continue
            if not _is_resolved(constraint, context):
                warnings.warn(
                    f"Constraint '{constraint.id}' references unresolved "
                    f"components, skipping", stacklevel=2
                )
                continue
            try:
                results.append(backend_fn(constraint, context))
            except Exception as e:
                warnings.warn(
                    f"Constraint '{constraint.id}' failed to compile to "
                    f"'{target.value}': {e}, skipping", stacklevel=2
                )
        return results

    def by_type(self, constraint_type: ConstraintType) -> list[BaseConstraint]:
        """Filter constraints by type."""
        return [c for c in self.constraints if c.constraint_type == constraint_type]

    def by_tier(self, tier: ConstraintTier) -> list[BaseConstraint]:
        """Filter constraints by tier."""
        return [c for c in self.constraints if c.tier == tier]

    def lint(self, netlist: Netlist, board: Board) -> Any:
        """Lint the constraint collection.

        Args:
            netlist: Netlist for component reference validation
            board: Board for geometry validation

        Returns:
            LintResult with errors and warnings
        """
        from .linter import lint_constraints
        return lint_constraints(self.constraints, netlist, board)

    def involving_component(self, component: str) -> list[BaseConstraint]:
        """Get all constraints involving a component."""
        return [c for c in self.constraints if c.involves_component(component)]

    def validate_component_refs(self, component_refs: list[str]) -> list[str]:
        """Validate that all component references exist in the netlist.

        Args:
            component_refs: List of valid component reference designators

        Returns:
            List of error messages for invalid references
        """
        errors = []
        component_set = set(component_refs)

        for constraint in self.constraints:
            # Extract component refs based on constraint type
            if isinstance(constraint, (AdjacentConstraint, SeparatedConstraint)):
                refs = [constraint.a, constraint.b]
            elif isinstance(constraint, EnclosingConstraint):
                refs = [constraint.outer] + constraint.inner
            elif isinstance(constraint, (AlignedConstraint, OnSideConstraint)):
                refs = constraint.components
            elif isinstance(constraint, AnchoredConstraint):
                refs = [constraint.component]
            else:
                # LoopAreaConstraint doesn't reference components
                continue

            # Check for missing references
            for ref in refs:
                # Skip zone references (conventionally uppercase with _ZONE suffix)
                if ref.isupper() and "_ZONE" in ref:
                    continue

                if ref not in component_set:
                    errors.append(
                        f"Constraint '{constraint.id}' references unknown component '{ref}'"
                    )

        return errors

    def auto_enrich(self, netlist: "Netlist", board: "Board | None" = None) -> None:
        """Auto-generate constraints from design data.

        Three automatic enrichments:
        1. Decoupling detection: scan netlist for capacitor-IC pairs
        2. Keepout emission: emit KeepoutConstraint for zones with type='keepout'
        3. Tag expansion: expand tagged constraints into concrete constraints

        Args:
            netlist: The netlist to analyze
            board: Optional board for zone-based enrichments
        """
        import logging

        logger = logging.getLogger(__name__)

        # 1. Decoupling detection
        from temper_placer.losses.decoupling import auto_detect_decoupling

        rules = auto_detect_decoupling(netlist)
        if rules:
            count = len(rules)
            for rule in rules:
                from temper_placer.pcl.constraints import ConstraintTier as CT

                classification = getattr(rule, "_classification", None)
                if classification is not None:
                    tier = CT.HARD if getattr(classification, "name", "") == "BYPASS" else CT.STRONG
                else:
                    tier = CT.STRONG
                self.constraints.append(
                    AdjacentConstraint(
                        a=rule.cap_ref,
                        b=rule.ic_ref,
                        max_distance_mm=rule.max_distance_mm,
                        tier=tier,
                        because=(
                            f"Decoupling capacitor {rule.cap_ref} for {rule.ic_ref}"
                            f"{' on net ' + rule.power_pin if rule.power_pin else ''}"
                        ),
                        pin_b=rule.power_pin if rule.power_pin else None,
                    )
                )
            logger.info("Auto-detected %d decoupling constraints", count)

        # 2. Keepout emission from board zones
        if board is not None:
            keepout_count = 0
            for zone in board.zones:
                zone_type = getattr(zone, "zone_type", "placement")
                if zone_type == "keepout":
                    self.constraints.append(
                        KeepoutConstraint(
                            zone_name=zone.name,
                            tier=ConstraintTier.HARD,
                            because=f"Auto-generated from zone '{zone.name}' (type: keepout)",
                            margin_mm=0.0,
                        )
                    )
                    keepout_count += 1
            if keepout_count > 0:
                logger.info(
                    "Emitted %d keepout constraint(s) from board zones", keepout_count
                )

        # 3. Tag expansion
        from temper_placer.pcl.tagged_constraints import (
            TaggedAdjacentConstraint,
            TaggedAlignedConstraint,
            TaggedAnchoredConstraint,
            TaggedEnclosingConstraint,
            TaggedOnSideConstraint,
            TaggedSeparatedConstraint,
        )
        from temper_placer.pcl.tag_dispatch import _tag_to_component_refs

        tagged_types = (
            TaggedAdjacentConstraint,
            TaggedAlignedConstraint,
            TaggedAnchoredConstraint,
            TaggedEnclosingConstraint,
            TaggedOnSideConstraint,
            TaggedSeparatedConstraint,
        )

        expanded_count = 0
        new_constraints = []

        for constraint in list(self.constraints):
            if not isinstance(constraint, tagged_types):
                continue

            constraint_id = getattr(constraint, "id", "") or ""

            if isinstance(constraint, (TaggedAdjacentConstraint, TaggedSeparatedConstraint)):
                comps_a = _tag_to_component_refs(constraint.tag_expr_a, netlist)
                comps_b = _tag_to_component_refs(constraint.tag_expr_b, netlist)
                for a_ref in comps_a:
                    for b_ref in comps_b:
                        if a_ref == b_ref:
                            continue
                        if isinstance(constraint, TaggedAdjacentConstraint):
                            new_constraints.append(
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
                        elif isinstance(constraint, TaggedSeparatedConstraint):
                            new_constraints.append(
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
                self.constraints.remove(constraint)
                expanded_count += 1

            elif isinstance(constraint, TaggedEnclosingConstraint):
                comps_inner = _tag_to_component_refs(constraint.tag_expr_inner, netlist)
                if comps_inner:
                    new_constraints.append(
                        EnclosingConstraint(
                            outer=constraint.outer,
                            inner=comps_inner,
                            tier=constraint.tier,
                            because=constraint.because,
                            margin_mm=constraint.margin_mm,
                            id=constraint_id,
                        )
                    )
                self.constraints.remove(constraint)
                expanded_count += 1

            elif isinstance(constraint, TaggedAlignedConstraint):
                comps = _tag_to_component_refs(constraint.tag_expr, netlist)
                if len(comps) >= 2:
                    new_constraints.append(
                        AlignedConstraint(
                            components=comps,
                            axis=constraint.axis,
                            tier=constraint.tier,
                            because=constraint.because,
                            tolerance_mm=constraint.tolerance_mm,
                            id=constraint_id,
                        )
                    )
                self.constraints.remove(constraint)
                expanded_count += 1

            elif isinstance(constraint, TaggedOnSideConstraint):
                comps = _tag_to_component_refs(constraint.tag_expr, netlist)
                if comps:
                    new_constraints.append(
                        OnSideConstraint(
                            components=comps,
                            side=constraint.side,
                            edge=constraint.edge,
                            tier=constraint.tier,
                            because=constraint.because,
                            max_distance_mm=constraint.max_distance_mm,
                            id=constraint_id,
                        )
                    )
                self.constraints.remove(constraint)
                expanded_count += 1

            elif isinstance(constraint, TaggedAnchoredConstraint):
                comps = _tag_to_component_refs(constraint.tag_expr, netlist)
                for comp_ref in comps:
                    new_constraints.append(
                        AnchoredConstraint(
                            component=comp_ref,
                            tier=constraint.tier,
                            because=constraint.because,
                            region=constraint.region,
                            position=constraint.position,
                            id=f"{constraint_id}_{comp_ref}" if constraint_id else "",
                        )
                    )
                self.constraints.remove(constraint)
                expanded_count += 1

        if new_constraints:
            self.constraints.extend(new_constraints)
        if expanded_count > 0:
            logger.info(
                "Expanded %d tagged constraint(s) into %d concrete constraint(s)",
                expanded_count,
                len(new_constraints),
            )


def _parse_distance_with_unit(value: Any) -> float:
    """Parse distance value with optional unit suffix.

    Supports:
    - Plain float (assumed mm)
    - String with unit: "10mm", "5mil", "0.1in"

    Args:
        value: Distance value (float or string)

    Returns:
        Distance in millimeters

    Raises:
        PCLParseError: If unit is invalid or value cannot be parsed
    """
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        raise PCLParseError(f"Distance must be number or string with unit, got {type(value)}")

    # Parse string with unit
    value = value.strip()

    # Try to extract number and unit
    for i, char in enumerate(value):
        if not (char.isdigit() or char in ".-"):
            number_str = value[:i]
            unit_str = value[i:].strip().lower()
            break
    else:
        # No unit found, assume mm
        return float(value)

    try:
        number = float(number_str)
    except ValueError as e:
        raise PCLParseError(f"Invalid distance value: {value}") from e

    if number < 0:
        raise PCLParseError(f"Distance cannot be negative: {value}")

    # Convert to mm
    if unit_str in ("mm", ""):
        return number
    elif unit_str == "mil":
        return number * 0.0254  # 1 mil = 0.0254 mm
    elif unit_str == "in":
        return number * 25.4  # 1 inch = 25.4 mm
    elif unit_str == "cm":
        return number * 10.0  # 1 cm = 10 mm
    else:
        raise PCLParseError(f"Unknown distance unit: {unit_str}")


def _parse_tier(tier_value: Any) -> ConstraintTier:
    """Parse tier from integer or string."""
    if isinstance(tier_value, int):
        if tier_value == 1:
            return ConstraintTier.HARD
        elif tier_value == 2:
            return ConstraintTier.STRONG
        elif tier_value == 3:
            return ConstraintTier.SOFT
        else:
            raise PCLParseError(f"Invalid tier value: {tier_value}. Must be 1, 2, or 3")

    if isinstance(tier_value, str):
        tier_lower = tier_value.lower()
        if tier_lower in ("hard", "1"):
            return ConstraintTier.HARD
        elif tier_lower in ("strong", "2"):
            return ConstraintTier.STRONG
        elif tier_lower in ("soft", "3"):
            return ConstraintTier.SOFT
        else:
            raise PCLParseError(f"Invalid tier: {tier_value}. Must be HARD/STRONG/SOFT or 1/2/3")

    raise PCLParseError(f"Tier must be integer or string, got {type(tier_value)}")


def _parse_metric(metric_value: str | None) -> DistanceMetric:
    """Parse distance metric from string."""
    if metric_value is None:
        return DistanceMetric.EDGE_TO_EDGE  # Default

    metric_lower = metric_value.lower().replace("-", "_")
    for dm in DistanceMetric:
        if dm.value == metric_lower:
            return dm

    raise PCLParseError(
        f"Invalid metric: {metric_value}. Valid: edge_to_edge, center_to_center, pin_to_pin"
    )


def _parse_axis(axis_value: str) -> Axis:
    """Parse axis from string."""
    axis_lower = axis_value.lower()

    # Accept aliases
    if axis_lower in ("horizontal", "h"):
        return Axis.X
    elif axis_lower in ("vertical", "v"):
        return Axis.Y

    # Standard values
    for axis in Axis:
        if axis.value == axis_lower:
            return axis

    raise PCLParseError(
        f"Invalid axis: {axis_value}. Valid: x, y, major, minor, horizontal, vertical"
    )


def _parse_board_side(side_value: str) -> BoardSide:
    """Parse board side from string."""
    side_lower = side_value.lower()
    for side in BoardSide:
        if side.value == side_lower:
            return side

    raise PCLParseError(f"Invalid side: {side_value}. Valid: top, bottom, left, right")


def _parse_edge_type(edge_value: str) -> EdgeType:
    """Parse edge type from string."""
    edge_lower = edge_value.lower()
    for edge in EdgeType:
        if edge.value == edge_lower:
            return edge

    raise PCLParseError(f"Invalid edge type: {edge_value}. Valid: flush, near, overhang")


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
                f"Unknown tag '{tag_name}', treating as literal ref. "
                f"Valid tags: {sorted(valid)}"
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

    raise PCLParseError(f"Invalid constraint reference: expected string or tag expression dict, got {type(value)}")


def parse_constraint_dict(data: dict[str, Any]) -> BaseConstraint:
    """Parse a single constraint from a dictionary.

    Args:
        data: Dictionary containing constraint fields

    Returns:
        Parsed constraint object

    Raises:
        PCLParseError: If constraint type is invalid or required fields are missing
    """
    # Check for required fields
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

    # Detect tag expressions in a/b fields
    a_is_tag = constraint_type in ("adjacent", "separated") and _is_tag_expr_dict(data.get("a"))
    b_is_tag = constraint_type in ("adjacent", "separated") and _is_tag_expr_dict(data.get("b"))
    has_tag_expr = a_is_tag or b_is_tag

    # Dispatch based on type
    if constraint_type == "adjacent":
        if has_tag_expr:
            from temper_placer.pcl.tagged_constraints import TaggedAdjacentConstraint

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
            from temper_placer.pcl.tagged_constraints import TaggedSeparatedConstraint

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
        # Check if inner contains tag expressions
        inner_data = data["inner"]
        has_inner_tags = isinstance(inner_data, list) and any(
            _is_tag_expr_dict(item) for item in inner_data
        )
        if has_inner_tags:
            from temper_placer.pcl.tagged_constraints import TaggedEnclosingConstraint

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
            from temper_placer.pcl.tagged_constraints import TaggedAlignedConstraint

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
            from temper_placer.pcl.tagged_constraints import TaggedOnSideConstraint

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
            from temper_placer.pcl.tagged_constraints import TaggedAnchoredConstraint

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


def parse_pcl_file(path: Path | str) -> ConstraintCollection:
    """Load constraint collection from YAML file.

    Expected YAML format:
        version: "1.0"
        metadata:
          description: "Half-bridge constraints"
          author: "Designer"
        constraints:
          - type: adjacent
            a: Q1
            b: Q2
            max_distance_mm: 10
            tier: 1
            because: "Minimize commutation loop"
          - type: separated
            ...

    Args:
        path: Path to YAML file

    Returns:
        ConstraintCollection with parsed constraints

    Raises:
        PCLParseError: If file cannot be parsed or has invalid structure
    """
    path = Path(path)

    if not path.exists():
        raise PCLParseError(f"File not found: {path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PCLParseError(f"YAML parse error in {path}: {e}") from e

    if not isinstance(data, dict):
        raise PCLParseError(f"Expected YAML dict at top level, got {type(data)}")

    # Validate against schema
    try:
        validate_pcl_dict(data)
    except PCLValidationError as e:
        raise PCLParseError(str(e)) from e

    # Parse version
    version = data.get("version", "1.0")

    # Parse metadata
    metadata = data.get("metadata", {})

    # Parse constraints
    if "constraints" not in data:
        raise PCLParseError("Missing 'constraints' key in YAML")

    constraints_data = data["constraints"]
    if not isinstance(constraints_data, list):
        raise PCLParseError("'constraints' must be a list")

    constraints = []
    for i, constraint_data in enumerate(constraints_data):
        try:
            constraint = parse_constraint_dict(constraint_data)
            constraints.append(constraint)
        except PCLParseError as e:
            raise PCLParseError(f"Error parsing constraint {i}: {e}") from e

    return ConstraintCollection(
        constraints=constraints,
        version=version,
        metadata=metadata,
    )


def load_pcl_collection(directory: Path | str) -> ConstraintCollection:
    """Load all PCL files from a directory and merge into one collection.

    Args:
        directory: Path to directory containing .yaml/.yml files

    Returns:
        ConstraintCollection with all constraints from all files

    Raises:
        PCLParseError: If directory doesn't exist or files can't be parsed
    """
    directory = Path(directory)

    if not directory.exists():
        raise PCLParseError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise PCLParseError(f"Not a directory: {directory}")

    all_constraints = []
    all_metadata = {}

    # Find all YAML files
    yaml_files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))

    if not yaml_files:
        raise PCLParseError(f"No YAML files found in {directory}")

    for yaml_file in yaml_files:
        try:
            collection = parse_pcl_file(yaml_file)
            all_constraints.extend(collection.constraints)
            all_metadata[yaml_file.stem] = collection.metadata
        except PCLParseError as e:
            raise PCLParseError(f"Error loading {yaml_file}: {e}") from e

    return ConstraintCollection(
        constraints=all_constraints,
        version="1.0",
        metadata={"sources": all_metadata},
    )
