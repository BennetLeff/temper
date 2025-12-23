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
from pathlib import Path
from typing import Any, List, Dict, Optional
from dataclasses import dataclass

import yaml
import json
from jsonschema import validate, ValidationError

from temper_placer.pcl.constraints import (
    BaseConstraint,
    AdjacentConstraint,
    SeparatedConstraint,
    EnclosingConstraint,
    AlignedConstraint,
    OnSideConstraint,
    AnchoredConstraint,
    LoopAreaConstraint,
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
    Axis,
    BoardSide,
    EdgeType,
)


class PCLParseError(Exception):
    """Error parsing a PCL constraint definition."""

    pass


class PCLValidationError(Exception):
    """Error validating constraint references."""

    pass


def load_pcl_schema() -> Dict[str, Any]:
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
        raise RuntimeError(f"Could not load PCL schema: {e}")


def validate_pcl_dict(data: Dict[str, Any]) -> None:
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

    constraints: List[BaseConstraint]
    version: str = "1.0"
    metadata: Optional[Dict[str, Any]] = None

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

    def by_type(self, constraint_type: ConstraintType) -> List[BaseConstraint]:
        """Filter constraints by type."""
        return [c for c in self.constraints if c.constraint_type == constraint_type]

    def by_tier(self, tier: ConstraintTier) -> List[BaseConstraint]:
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

    def involving_component(self, component: str) -> List[BaseConstraint]:
        """Get all constraints involving a component."""
        return [c for c in self.constraints if c.involves_component(component)]

    def validate_component_refs(self, component_refs: List[str]) -> List[str]:
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
    except ValueError:
        raise PCLParseError(f"Invalid distance value: {value}")

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


def _parse_metric(metric_value: Optional[str]) -> DistanceMetric:
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


def parse_constraint_dict(data: Dict[str, Any]) -> BaseConstraint:
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

    # Dispatch based on type
    if constraint_type == "adjacent":
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
        return EnclosingConstraint(
            outer=data["outer"],
            inner=data["inner"],
            tier=tier,
            because=because,
            margin_mm=_parse_distance_with_unit(data.get("margin_mm", 0.0)),
            id=constraint_id,
        )

    elif constraint_type == "aligned":
        return AlignedConstraint(
            components=data["components"],
            axis=_parse_axis(data["axis"]),
            tier=tier,
            because=because,
            tolerance_mm=_parse_distance_with_unit(data.get("tolerance_mm", 0.5)),
            id=constraint_id,
        )

    elif constraint_type == "on_side":
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
        region = data.get("region")
        position = data.get("position")

        # Convert region/position lists to tuples
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
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PCLParseError(f"YAML parse error in {path}: {e}")

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
            raise PCLParseError(f"Error parsing constraint {i}: {e}")

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
            raise PCLParseError(f"Error loading {yaml_file}: {e}")

    return ConstraintCollection(
        constraints=all_constraints,
        version="1.0",
        metadata={"sources": all_metadata},
    )
