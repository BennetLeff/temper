"""
Component-to-loop ownership mapping for loop-aware placement.

This module provides bidirectional mappings between components and the loops they
participate in. This information is used for:

- Loss function weighting: Components in critical loops get higher optimization priority
- Adjacency constraints: Loop members should be placed close together
- Visualization: Color-code components by loop membership

Example usage:
    >>> from temper_placer.core.loop_ownership import build_ownership_map
    >>> from temper_placer.core.loop import LoopCollection
    >>> from temper_placer.core.netlist import Netlist
    >>>
    >>> loops = LoopCollection(...)  # From auto-extraction or YAML
    >>> netlist = Netlist(...)
    >>> ownership = build_ownership_map(loops, netlist)
    >>>
    >>> # Query which loops a component belongs to
    >>> info = ownership.get_component_info("Q1")
    >>> print(f"Q1 is in {len(info.memberships)} loops")
    >>> print(f"Priority weight: {info.get_priority_weight(loops)}")
    >>>
    >>> # Find components that share loops
    >>> shared = ownership.get_shared_loops("Q1", "Q2")
    >>> print(f"Q1 and Q2 share {len(shared)} loops")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .loop import Loop, LoopCollection, LoopPriority
    from .netlist import Component, Netlist

from .loop_extractor import classify_component


@dataclass
class LoopMembership:
    """
    A component's membership in a single loop.

    Attributes:
        loop_name: Name of the loop this component participates in.
        role: Component's role in the loop (e.g., 'switch', 'capacitor', 'driver').
        pins_in_loop: List of pin names that participate in this loop.
    """

    loop_name: str
    role: str
    pins_in_loop: list[str] = field(default_factory=list)


@dataclass
class ComponentLoopInfo:
    """
    Complete loop information for a single component.

    A component can participate in multiple loops. For example, a half-bridge
    IGBT is in both the commutation loop and its gate drive loop.

    Attributes:
        component_ref: Reference designator (e.g., "Q1").
        memberships: List of loop memberships for this component.
    """

    component_ref: str
    memberships: list[LoopMembership] = field(default_factory=list)

    @property
    def loop_names(self) -> list[str]:
        """Get list of all loop names this component participates in."""
        return [m.loop_name for m in self.memberships]

    @property
    def is_in_critical_loop(self) -> bool:
        """
        Check if component is in any critical loop.

        This is a heuristic based on loop names. For precise checks, use
        get_priority_weight() with the actual LoopCollection.
        """
        return any(
            m.loop_name.startswith("commutation")
            or m.loop_name.startswith("gate_drive")
            or "commutation" in m.loop_name.lower()
            or "gate_drive" in m.loop_name.lower()
            for m in self.memberships
        )

    def get_priority_weight(self, loop_collection: "LoopCollection") -> float:
        """
        Calculate placement priority weight based on loop memberships.

        Components in multiple loops get the maximum priority of all their loops.

        Args:
            loop_collection: Collection containing priority information for each loop.

        Returns:
            Priority weight (0.0-1.0). Higher = more important to optimize.
                1.0 = CRITICAL (commutation, gate drive)
                0.7 = HIGH (bootstrap, sensing)
                0.4 = MEDIUM (auxiliary power)
                0.1 = LOW (decoupling, non-critical)
                0.0 = Not in any loop
        """
        from .loop import LoopPriority

        max_weight = 0.0
        for membership in self.memberships:
            loop = loop_collection.get_loop(membership.loop_name)
            if loop:
                weight = {
                    LoopPriority.CRITICAL: 1.0,
                    LoopPriority.HIGH: 0.7,
                    LoopPriority.MEDIUM: 0.4,
                    LoopPriority.LOW: 0.1,
                }.get(loop.priority, 0.0)
                max_weight = max(max_weight, weight)
        return max_weight


@dataclass
class LoopOwnershipMap:
    """
    Bidirectional mapping between components and loops.

    Provides efficient queries for:
    - Which loops does component X participate in?
    - Which components are in loop Y?
    - What loops do components A and B share?

    Attributes:
        component_to_loops: Map from component ref to ComponentLoopInfo.
        loop_to_components: Map from loop name to list of component refs.
    """

    component_to_loops: dict[str, ComponentLoopInfo] = field(default_factory=dict)
    loop_to_components: dict[str, list[str]] = field(default_factory=dict)

    def get_component_info(self, ref: str) -> ComponentLoopInfo | None:
        """
        Get loop information for a component.

        Args:
            ref: Component reference designator.

        Returns:
            ComponentLoopInfo if component is in any loops, None otherwise.
        """
        return self.component_to_loops.get(ref)

    def get_loop_components(self, loop_name: str) -> list[str]:
        """
        Get all components participating in a loop.

        Args:
            loop_name: Name of the loop to query.

        Returns:
            List of component references in this loop (empty if loop not found).
        """
        return self.loop_to_components.get(loop_name, [])

    def get_shared_loops(self, ref_a: str, ref_b: str) -> list[str]:
        """
        Find loops that contain both components.

        Useful for determining if two components should be placed close together.

        Args:
            ref_a: First component reference.
            ref_b: Second component reference.

        Returns:
            List of loop names containing both components.
        """
        info_a = self.component_to_loops.get(ref_a)
        info_b = self.component_to_loops.get(ref_b)

        if not info_a or not info_b:
            return []

        loops_a = set(info_a.loop_names)
        loops_b = set(info_b.loop_names)
        return list(loops_a & loops_b)

    def components_share_loop(
        self, ref_a: str, ref_b: str, loop_collection: "LoopCollection | None" = None
    ) -> bool:
        """
        Check if two components share any loop.

        Args:
            ref_a: First component reference.
            ref_b: Second component reference.
            loop_collection: Optional collection to check loop priorities.

        Returns:
            True if components share at least one loop.
        """
        return len(self.get_shared_loops(ref_a, ref_b)) > 0

    def components_share_critical_loop(
        self, ref_a: str, ref_b: str, loop_collection: "LoopCollection"
    ) -> bool:
        """
        Check if two components share a CRITICAL priority loop.

        Args:
            ref_a: First component reference.
            ref_b: Second component reference.
            loop_collection: Collection to check loop priorities.

        Returns:
            True if components share at least one CRITICAL loop.
        """
        from .loop import LoopPriority

        shared = self.get_shared_loops(ref_a, ref_b)
        for loop_name in shared:
            loop = loop_collection.get_loop(loop_name)
            if loop and loop.priority == LoopPriority.CRITICAL:
                return True
        return False


def classify_role(component: "Component", loop: "Loop") -> str:
    """
    Classify a component's role within a loop.

    Args:
        component: Component to classify.
        loop: Loop context for classification.

    Returns:
        Role string:
            - 'switch': Power switch (IGBT, MOSFET)
            - 'bus_capacitor': DC bus capacitor
            - 'bootstrap_capacitor': Bootstrap capacitor
            - 'decoupling_capacitor': Small decoupling cap
            - 'driver': Gate driver IC
            - 'gate_resistor': Gate resistor
            - 'bootstrap_diode': Bootstrap diode
            - 'other': Unknown role
    """
    classification = classify_component(component)

    if classification.category == "power_switch":
        return "switch"
    elif classification.category == "capacitor":
        return classification.subcategory + "_capacitor"
    elif classification.category == "gate_driver":
        return "driver"
    elif classification.category == "resistor":
        return "gate_resistor"
    elif classification.category == "diode":
        return "bootstrap_diode"
    else:
        return "other"


def build_ownership_map(loops: "LoopCollection", netlist: "Netlist") -> LoopOwnershipMap:
    """
    Build bidirectional ownership map from loops and netlist.

    This function processes all loops and creates:
    1. Component -> loops mapping (which loops each component is in)
    2. Loop -> components mapping (which components are in each loop)
    3. Role classification for each membership

    Args:
        loops: Collection of all loops in the design.
        netlist: Netlist with component information.

    Returns:
        LoopOwnershipMap with complete bidirectional mappings.

    Example:
        >>> ownership = build_ownership_map(loops, netlist)
        >>> q1_info = ownership.get_component_info("Q1")
        >>> print(f"Q1 participates in {len(q1_info.memberships)} loops")
        >>> for membership in q1_info.memberships:
        ...     print(f"  - {membership.loop_name} as {membership.role}")
    """
    ownership = LoopOwnershipMap()

    for loop in loops.loops:
        component_refs = loop.get_component_refs()

        for ref in component_refs:
            # Get component from netlist
            try:
                component = netlist.get_component(ref)
            except KeyError:
                # Component not in netlist - skip
                continue

            # Classify component's role in this loop
            role = classify_role(component, loop)

            # Find which pins are in this loop
            pins_in_loop = [pin.pin_name for pin in loop.pins if pin.component_ref == ref]

            # Create membership record
            membership = LoopMembership(
                loop_name=loop.name,
                role=role,
                pins_in_loop=pins_in_loop,
            )

            # Add to component -> loops map
            if ref not in ownership.component_to_loops:
                ownership.component_to_loops[ref] = ComponentLoopInfo(ref)
            ownership.component_to_loops[ref].memberships.append(membership)

            # Add to loop -> components map
            if loop.name not in ownership.loop_to_components:
                ownership.loop_to_components[loop.name] = []
            ownership.loop_to_components[loop.name].append(ref)

    return ownership
