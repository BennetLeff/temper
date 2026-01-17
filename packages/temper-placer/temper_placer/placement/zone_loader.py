"""
Zone Constraint Loader for Benders Optimization.

Loads zone constraints from temper_constraints.yaml and converts them
to ILP constraints for the Benders master problem.

This ensures a single source of truth for zone definitions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


def load_zone_constraints_from_yaml(
    yaml_path: Path | str, component_zones: dict[str, str] | None = None
) -> dict[str, list[tuple[str, str, float]]]:
    """
    Load zone constraints from temper_constraints.yaml.

    Args:
        yaml_path: Path to temper_constraints.yaml
        component_zones: Optional mapping of component ref -> zone name
                        If None, loads from 'groups' in YAML

    Returns:
        Dict of component_ref -> [(axis, direction, limit), ...]

    Example:
        >>> constraints = load_zone_constraints_from_yaml("temper_constraints.yaml")
        >>> constraints["U_MCU"]
        [('y', 'max', 70.0)]  # control_zone: Y < 70mm
    """
    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    # Parse zone definitions
    zones = {}
    for zone_def in config.get("zones", []):
        name = zone_def["name"]
        bounds = zone_def["bounds"]  # [x_min, y_min, x_max, y_max]
        zones[name] = {
            "x_min": bounds[0],
            "y_min": bounds[1],
            "x_max": bounds[2],
            "y_max": bounds[3],
        }

    # If component_zones not provided, extract from groups
    if component_zones is None:
        component_zones = {}
        for group in config.get("groups", []):
            zone_name = group.get("zone")
            if zone_name:
                for comp_ref in group.get("components", []):
                    component_zones[comp_ref] = zone_name

    # Convert to ILP constraints
    ilp_constraints = {}

    for comp_ref, zone_name in component_zones.items():
        if zone_name not in zones:
            continue

        zone_bounds = zones[zone_name]
        constraints = []

        # X constraints
        x_min = zone_bounds["x_min"]
        x_max = zone_bounds["x_max"]
        if x_min > 0:  # Only add if meaningful (not board edge)
            constraints.append(("x", "min", float(x_min)))
        if x_max < 1000:  # Only add if meaningful (not board edge)
            constraints.append(("x", "max", float(x_max)))

        # Y constraints
        y_min = zone_bounds["y_min"]
        y_max = zone_bounds["y_max"]
        if y_min > 0:
            constraints.append(("y", "min", float(y_min)))
        if y_max < 1000:
            constraints.append(("y", "max", float(y_max)))

        if constraints:
            ilp_constraints[comp_ref] = constraints

    return ilp_constraints


def validate_zone_constraints(
    ilp_constraints: dict[str, list[tuple[str, str, float]]],
    component_positions: dict[str, tuple[float, float]],
    verbose: bool = True,
) -> dict[str, list[str]]:
    """
    Validate that component positions satisfy zone constraints.

    Args:
        ilp_constraints: Zone constraints from load_zone_constraints_from_yaml()
        component_positions: Current positions {ref: (x, y)}
        verbose: Print violations

    Returns:
        Dict of component_ref -> [violation_messages]
    """
    violations = {}

    for comp_ref, constraints in ilp_constraints.items():
        if comp_ref not in component_positions:
            continue

        x, y = component_positions[comp_ref]
        comp_violations = []

        for axis, direction, limit in constraints:
            value = x if axis == "x" else y

            if direction == "min" and value < limit:
                comp_violations.append(f"{axis}={value:.1f} < {limit:.1f} (min)")
            elif direction == "max" and value > limit:
                comp_violations.append(f"{axis}={value:.1f} > {limit:.1f} (max)")

        if comp_violations:
            violations[comp_ref] = comp_violations
            if verbose:
                print(f"⚠️  {comp_ref}: {', '.join(comp_violations)}")

    return violations


def format_zone_summary(ilp_constraints: dict[str, list[tuple[str, str, float]]]) -> str:
    """
    Format zone constraints as human-readable summary.

    Args:
        ilp_constraints: Zone constraints

    Returns:
        Formatted string
    """
    lines = ["Zone Constraints Loaded:"]
    lines.append("=" * 60)

    # Group by zone boundaries
    by_y_bounds = {}
    for comp_ref, constraints in ilp_constraints.items():
        y_min = None
        y_max = None
        for axis, direction, limit in constraints:
            if axis == "y":
                if direction == "min":
                    y_min = limit
                elif direction == "max":
                    y_max = limit

        key = (y_min, y_max)
        if key not in by_y_bounds:
            by_y_bounds[key] = []
        by_y_bounds[key].append(comp_ref)

    for (y_min, y_max), comps in sorted(
        by_y_bounds.items(), key=lambda x: (x[0][0] or 0, x[0][1] or 999)
    ):
        y_range = ""
        if y_min is not None and y_max is not None:
            y_range = f"Y={y_min:.0f}-{y_max:.0f}mm"
        elif y_min is not None:
            y_range = f"Y≥{y_min:.0f}mm"
        elif y_max is not None:
            y_range = f"Y≤{y_max:.0f}mm"

        lines.append(f"\n{y_range}: {len(comps)} components")
        lines.append(f"  {', '.join(sorted(comps))}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test the loader
    import sys

    yaml_path = Path("packages/temper-placer/configs/temper_constraints.yaml")
    if not yaml_path.exists():
        yaml_path = Path("configs/temper_constraints.yaml")

    if not yaml_path.exists():
        print(f"Error: Could not find temper_constraints.yaml")
        sys.exit(1)

    print(f"Loading zones from: {yaml_path}")
    constraints = load_zone_constraints_from_yaml(yaml_path)

    print(f"\nLoaded {len(constraints)} component zone constraints")
    print(format_zone_summary(constraints))
