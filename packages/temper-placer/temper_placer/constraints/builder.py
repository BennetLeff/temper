"""Fluent Python API for building placement constraints.

This module provides a ConstraintBuilder class that allows AI agents and
developers to programmatically construct placement constraints with a
chainable, fluent interface.
"""

from typing import Optional, List
from dataclasses import asdict
import yaml

from temper_placer.io.config_loader import (
    PlacementConstraints,
    ComponentSpacingRule,
    ProximityRule,
    ThermalConstraint,
    ComponentGroup,
    EscapeClearance,
    RoutingCorridor,
)
from temper_placer.constraints.compiler import ConstraintCompiler


class ConstraintBuilder:
    """Fluent API for building placement constraints.

    Example:
        >>> builder = ConstraintBuilder()
        >>> constraints = (builder
        ...     .add_spacing("Q1", "Q2", 15.0, tier="hard")
        ...     .add_proximity("U_GATE", "Q1", 8.0, tier="hard")
        ...     .add_escape_clearance("U_MCU", 10.0)
        ...     .build())
    """

    def __init__(self, base: Optional[PlacementConstraints] = None):
        """Initialize builder.

        Args:
            base: Optional existing constraints to extend
        """
        if base is not None:
            self._constraints = base
        else:
            self._constraints = PlacementConstraints()

    def add_spacing(
        self,
        comp_a: str,
        comp_b: str,
        min_mm: float,
        tier: str = "soft",
        weight: float = 1.0,
        description: str = "",
    ) -> "ConstraintBuilder":
        """Add a component spacing constraint.

        Args:
            comp_a: First component reference
            comp_b: Second component reference
            min_mm: Minimum separation in mm
            tier: "hard" (reject violations) or "soft" (penalize)
            weight: Weight for soft constraint scoring
            description: Human-readable description

        Returns:
            Self for chaining
        """
        rule = ComponentSpacingRule(
            component_a=comp_a,
            component_b=comp_b,
            min_separation_mm=min_mm,
            tier=tier,
            weight=weight,
            description=description,
        )
        self._constraints.component_spacing_rules.append(rule)
        return self

    def add_proximity(
        self,
        comp_a: str,
        comp_b: str,
        max_mm: float,
        tier: str = "soft",
        description: str = "",
        group_name: Optional[str] = None,
    ) -> "ConstraintBuilder":
        """Add a proximity constraint between two components.

        Args:
            comp_a: First component reference
            comp_b: Second component reference
            max_mm: Maximum distance in mm
            tier: "hard" (reject violations) or "soft" (penalize)
            description: Human-readable description
            group_name: Optional group name to add this rule to

        Returns:
            Self for chaining
        """
        rule = ProximityRule(
            component_a=comp_a,
            component_b=comp_b,
            max_distance_mm=max_mm,
            tier=tier,
            description=description,
        )

        # Find or create group
        if group_name:
            group = self._find_or_create_group(group_name, [comp_a, comp_b])
            group.proximity_rules.append(rule)
        else:
            # Create anonymous group
            group = ComponentGroup(
                name=f"proximity_{comp_a}_{comp_b}",
                components=[comp_a, comp_b],
                proximity_rules=[rule],
            )
            self._constraints.component_groups.append(group)

        return self

    def add_escape_clearance(
        self,
        component: str,
        clearance_mm: Optional[float] = None,
        priority_sides: Optional[List[str]] = None,
        tier: str = "soft",
        description: str = "",
    ) -> "ConstraintBuilder":
        """Add an escape clearance zone around a component.

        Args:
            component: Component reference (e.g., "U_MCU")
            clearance_mm: Clearance in mm (computed from pin density if None)
            priority_sides: Sides to prioritize for escape ["top", "bottom", "left", "right"]
            tier: "hard" (reject violations) or "soft" (penalize)
            description: Human-readable description

        Returns:
            Self for chaining
        """
        escape = EscapeClearance(
            component=component,
            clearance_mm=clearance_mm,
            priority_sides=priority_sides or [],
            tier=tier,
            description=description,
        )
        self._constraints.escape_clearances.append(escape)
        return self

    def add_routing_corridor(
        self,
        name: str,
        from_component: str,
        to_component: str,
        width_mm: float,
        keep_clear: bool = True,
        nets: Optional[List[str]] = None,
        tier: str = "hard",
    ) -> "ConstraintBuilder":
        """Add a routing corridor constraint.

        Args:
            name: Corridor name
            from_component: Starting component reference
            to_component: Ending component reference
            width_mm: Corridor width in mm
            keep_clear: Whether to keep corridor clear of other components
            nets: Optional list of nets that use this corridor
            tier: "hard" (reject violations) or "soft" (penalize)

        Returns:
            Self for chaining
        """
        corridor = RoutingCorridor(
            name=name,
            from_component=from_component,
            to_component=to_component,
            width_mm=width_mm,
            keep_clear=keep_clear,
            nets=nets or [],
            tier=tier,
        )
        self._constraints.routing_corridors.append(corridor)
        return self

    def add_thermal_constraint(
        self,
        components: List[str],
        prefer_edge: bool = True,
        max_distance_from_edge_mm: float = 20.0,
        min_spacing_mm: float = 5.0,
        description: str = "",
    ) -> "ConstraintBuilder":
        """Add a thermal constraint for heat-generating components.

        Args:
            components: List of component references
            prefer_edge: Whether to prefer edge placement
            max_distance_from_edge_mm: Maximum distance from board edge
            min_spacing_mm: Minimum spacing between thermal components
            description: Human-readable description

        Returns:
            Self for chaining
        """
        thermal = ThermalConstraint(
            components=components,
            prefer_edge=prefer_edge,
            max_distance_from_edge_mm=max_distance_from_edge_mm,
            min_spacing_mm=min_spacing_mm,
            description=description,
        )
        self._constraints.thermal_constraints.append(thermal)
        return self

    def add_group(
        self,
        name: str,
        components: List[str],
        max_spread_mm: float = 30.0,
        zone: Optional[str] = None,
        weight: float = 1.0,
        description: str = "",
    ) -> "ConstraintBuilder":
        """Add a component group constraint.

        Args:
            name: Group name
            components: List of component references in group
            max_spread_mm: Maximum bounding box diagonal in mm
            zone: Optional zone name to constrain group to
            weight: Weight for soft constraint scoring
            description: Human-readable description

        Returns:
            Self for chaining
        """
        group = ComponentGroup(
            name=name,
            components=components,
            max_spread_mm=max_spread_mm,
            zone=zone,
            proximity_rules=[],
            weight=weight,
            description=description,
        )
        self._constraints.component_groups.append(group)
        return self

    def build(self) -> PlacementConstraints:
        """Build and return the constraints.

        Returns:
            PlacementConstraints object
        """
        return self._constraints

    def validate(
        self,
        board_width: float,
        board_height: float,
        available_components: List[str],
        available_zones: Optional[List[str]] = None,
    ) -> List[str]:
        """Validate constraints and return error messages.

        This is a simplified validation that checks for common errors
        like missing component references. For full validation, use
        ConstraintCompiler.validate() with actual Board and Netlist objects.

        Args:
            board_width: Board width in mm
            board_height: Board height in mm
            available_components: List of available component references
            available_zones: Optional list of available zone names

        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        comp_set = set(available_components)
        zone_set = set(available_zones or [])

        # Check spacing rules
        for rule in self._constraints.component_spacing_rules:
            if rule.component_a not in comp_set:
                errors.append(f"ComponentSpacing: component '{rule.component_a}' not found")
            if rule.component_b not in comp_set:
                errors.append(f"ComponentSpacing: component '{rule.component_b}' not found")

        # Check proximity rules in groups
        for group in self._constraints.component_groups:
            for comp in group.components:
                if comp not in comp_set:
                    errors.append(f"ComponentGroup '{group.name}': component '{comp}' not found")
            if group.zone and group.zone not in zone_set and available_zones is not None:
                errors.append(f"ComponentGroup '{group.name}': zone '{group.zone}' not found")

        # Check escape clearances
        for escape in self._constraints.escape_clearances:
            if escape.component not in comp_set:
                errors.append(f"EscapeClearance: component '{escape.component}' not found")

        # Check routing corridors
        for corridor in self._constraints.routing_corridors:
            if corridor.from_component not in comp_set:
                errors.append(
                    f"RoutingCorridor '{corridor.name}': from_component '{corridor.from_component}' not found"
                )
            if corridor.to_component not in comp_set:
                errors.append(
                    f"RoutingCorridor '{corridor.name}': to_component '{corridor.to_component}' not found"
                )

        # Check thermal constraints
        for thermal in self._constraints.thermal_constraints:
            for comp in thermal.components:
                if comp not in comp_set:
                    errors.append(f"ThermalConstraint: component '{comp}' not found")

        return errors

    def to_yaml(self) -> str:
        """Serialize constraints to YAML format.

        Returns:
            YAML string representation
        """
        data = {}

        # Component spacing rules
        if self._constraints.component_spacing_rules:
            data["minimum_spacing"] = [
                {
                    "components": [r.component_a, r.component_b],
                    "min_separation_mm": r.min_separation_mm,
                    "tier": r.tier,
                    "weight": r.weight,
                    "description": r.description,
                }
                for r in self._constraints.component_spacing_rules
            ]

        # Component groups with proximity rules
        if self._constraints.component_groups:
            data["groups"] = []
            for group in self._constraints.component_groups:
                group_data = {
                    "name": group.name,
                    "components": group.components,
                    "max_spread_mm": group.max_spread_mm,
                }
                if group.zone:
                    group_data["zone"] = group.zone
                if group.weight != 1.0:
                    group_data["weight"] = group.weight
                if group.description:
                    group_data["description"] = group.description
                if group.proximity_rules:
                    group_data["proximity"] = [
                        {
                            "pair": [r.component_a, r.component_b],
                            "max_distance_mm": r.max_distance_mm,
                            "tier": r.tier,
                        }
                        for r in group.proximity_rules
                    ]
                data["groups"].append(group_data)

        # Escape clearances
        if self._constraints.escape_clearances:
            data["escape_clearances"] = [
                {
                    "component": ec.component,
                    "clearance_mm": ec.clearance_mm,
                    "priority_sides": ec.priority_sides,
                    "tier": ec.tier,
                    "description": ec.description,
                }
                for ec in self._constraints.escape_clearances
            ]

        # Routing corridors
        if self._constraints.routing_corridors:
            data["routing_corridors"] = [
                {
                    "name": rc.name,
                    "from_component": rc.from_component,
                    "to_component": rc.to_component,
                    "width_mm": rc.width_mm,
                    "keep_clear": rc.keep_clear,
                    "nets": rc.nets,
                    "tier": rc.tier,
                }
                for rc in self._constraints.routing_corridors
            ]

        # Thermal constraints
        if self._constraints.thermal_constraints:
            data["thermal_constraints"] = [
                {
                    "components": tc.components,
                    "prefer_edge": tc.prefer_edge,
                    "max_distance_from_edge_mm": tc.max_distance_from_edge_mm,
                    "min_spacing_mm": tc.min_spacing_mm,
                    "description": tc.description,
                }
                for tc in self._constraints.thermal_constraints
            ]

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def _find_or_create_group(self, name: str, components: List[str]) -> ComponentGroup:
        """Find existing group by name or create new one.

        Args:
            name: Group name
            components: Components to add if creating new group

        Returns:
            ComponentGroup instance
        """
        # Find existing group
        for group in self._constraints.component_groups:
            if group.name == name:
                # Add new components if not present
                for comp in components:
                    if comp not in group.components:
                        group.components.append(comp)
                return group

        # Create new group
        group = ComponentGroup(
            name=name,
            components=components,
            proximity_rules=[],
        )
        self._constraints.component_groups.append(group)
        return group
