"""Fluent Python API for building placement constraints.

This module provides a ConstraintBuilder class that allows AI agents and
developers to programmatically construct placement constraints with a
chainable, fluent interface.

Wave 4, Phase 4: the compute of this module is migrated to Rust in the
``temper-constraint-compiler`` crate (see ``packages/temper-constraint-compiler/
VERIFICATION.md``). The fluent ``add_*`` construction methods stay Python —
they build pydantic ``_constraint_types`` objects (orchestration over Python
data, not compute); the migrated compute is ``validate()`` (error-string
assembly, byte-identical) and the ``to_yaml()`` serialization-shape logic
(which keys appear, in which order — the PyYAML ``yaml.dump`` call itself
stays Python, per the Wave-4 guide's PyYAML ruling). The pre-migration
implementation is pinned verbatim as the differential oracle
(``tests/constraints/_builder_py_oracle.py``).
"""

import yaml  # type: ignore[import-untyped]

import temper_constraint_compiler as _rust  # type: ignore[import-untyped]

from temper_placer._constraint_types import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)
from temper_placer.constraints._payload import build_payload


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

    def __init__(self, base: PlacementConstraints | None = None):
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
        group_name: str | None = None,
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
        clearance_mm: float | None = None,
        priority_sides: list[str] | None = None,
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
        nets: list[str] | None = None,
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
        components: list[str],
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
        components: list[str],
        max_spread_mm: float = 30.0,
        zone: str | None = None,
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
        _board_width: float,
        _board_height: float,
        available_components: list[str],
        available_zones: list[str] | None = None,
    ) -> list[str]:
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
        payload = build_payload(self._constraints, None)
        return _rust.builder_validate(  # type: ignore[attr-defined]
            payload,
            list(available_components),
            None if available_zones is None else list(available_zones),
        )

    def to_yaml(self) -> str:
        """Serialize constraints to YAML format.

        The data-shape logic (which keys appear, in which order) is Rust
        (``temper_constraint_compiler.builder_to_yaml_data``); the PyYAML dump
        itself stays here per the Wave-4 guide's PyYAML ruling (PyYAML is
        YAML 1.1 and not bit-reimplementable).

        Returns:
            YAML string representation
        """
        data = _rust.builder_to_yaml_data(build_payload(self._constraints, None))  # type: ignore[attr-defined]
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def _find_or_create_group(self, name: str, components: list[str]) -> ComponentGroup:
        """Find existing group by name or create new one.

        Stateful mutation of the pydantic object graph — orchestration over
        Python data, so it stays Python (the migrated compute is validate()/
        to_yaml()).

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
