"""
Component-to-loop ownership mapping for loop-aware placement.

This module provides bidirectional mappings between components and the loops they
participate in. This information is used for:

- Loss function weighting: Components in critical loops get higher optimization priority
- Adjacency constraints: Loop members should be placed close together
- Visualization: Color-code components by loop membership

The data classes (LoopMembership, ComponentLoopInfo, LoopOwnershipMap) are
Rust pyclasses in temper-design-bundle. The builder (build_ownership_map) and
role classifier (classify_role) stay Python because they depend on
classify_component from loop_extractor (owned by another migration session)
and perform complex imperative orchestration over LoopCollection/Netlist
objects.

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

from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

ComponentLoopInfo = _tdb.loop_ownership_contracts.ComponentLoopInfo
LoopMembership = _tdb.loop_ownership_contracts.LoopMembership
LoopOwnershipMap = _tdb.loop_ownership_contracts.LoopOwnershipMap

if TYPE_CHECKING:
    from .loop import Loop, LoopCollection
    from .netlist import Component, Netlist

from .loop_extractor import classify_component


# =============================================================================
# Re-exports from Rust pyclasses (data contracts)
# =============================================================================

__all__ = [
    "ComponentLoopInfo",
    "LoopMembership",
    "LoopOwnershipMap",
    "build_ownership_map",
    "classify_role",
]

# =============================================================================
# The following functions stay Python (JUSTIFIED-KEEP).
#
# classify_role depends on classify_component from loop_extractor, which is
# owned by another session's migrate/loop-extractor branch.
#
# build_ownership_map performs complex imperative orchestration over
# LoopCollection and Netlist objects, iterating loops, getting components,
# classifying roles, and building bidirectional maps.
# =============================================================================


def classify_role(component: Component, _loop: Loop) -> str:
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
        return (classification.subcategory or "unknown") + "_capacitor"
    elif classification.category == "gate_driver":
        return "driver"
    elif classification.category == "resistor":
        return "gate_resistor"
    elif classification.category == "diode":
        return "bootstrap_diode"
    else:
        return "other"


def build_ownership_map(loops: LoopCollection, netlist: Netlist) -> LoopOwnershipMap:
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
