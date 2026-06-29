"""
Layer assignment solver for PCB routing (temper-wna.2).

This module assigns each net to optimal PCB layer(s) while respecting hard
constraints like HV nets on L1 only. Layer assignment is deterministic -
same inputs always produce the same assignments.

Layer Model (4-Layer Induction Cooker):
- L1 (Top): Signal routing, 2oz copper, HV traces
- L2 (GND): Ground plane, split (PGND, CGND, ISOGND)
- L3 (PWR): Power plane (VCC_15V, VCC_3V3)
- L4 (Bottom): Signal routing, 1oz copper

Example usage:
    >>> from temper_placer.routing.layer_assignment import assign_layers, Layer
    >>> from temper_placer.core.netlist import Netlist
    >>>
    >>> assignments = assign_layers(netlist)
    >>> for net_name, assignment in assignments.items():
    ...     print(f"{net_name}: {assignment.primary_layer.name}")
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Net, Netlist

import re
from dataclasses import dataclass, field
from enum import Enum

from jax import Array

from temper_placer.core.netlist import Netlist
from temper_placer.core.pin_geometry import pin_world_position


class Layer(Enum):
    """PCB layer enumeration for 4-layer stackup.

    The layer numbers correspond to typical 4-layer PCB stackup:
    - L1: Top signal layer (components mounted here, HV traces)
    - L2: Ground plane (reference for signals)
    - L3: Power plane (VCC distribution)
    - L4: Bottom signal layer (general routing)

    Attributes:
        L1_TOP: Top signal layer (value=1)
        L2_GND: Ground plane (value=2)
        L3_PWR: Power plane (value=3)
        L4_BOT: Bottom signal layer (value=4)
    """

    L1_TOP = 1
    L2_GND = 2
    L3_PWR = 3
    L4_BOT = 4


@dataclass
class LayerConstraint:
    """Constraint specifying allowed layers for matching nets.

    Layer constraints use regex patterns to match net names and specify
    which layers those nets are allowed to use.

    Attributes:
        net_pattern: Regex pattern to match net names (e.g., r"DC_BUS_.*")
        allowed_layers: Set of layers the net can be routed on
        preferred_layer: First choice layer within allowed set
        reason: Human-readable explanation of constraint

    Example:
        >>> constraint = LayerConstraint(
        ...     net_pattern=r"DC_BUS_.*|HV_.*",
        ...     allowed_layers={Layer.L1_TOP},
        ...     preferred_layer=Layer.L1_TOP,
        ...     reason="HV traces must stay on L1 for clearance"
        ... )
    """

    net_pattern: str
    allowed_layers: set[Layer]
    preferred_layer: Layer
    reason: str


@dataclass
class LayerAssignment:
    """Result of layer assignment for a single net.

    Contains the assigned layer(s) and metadata about the assignment.

    Attributes:
        net: Net name
        primary_layer: Main layer for routing this net
        allowed_layers: All layers this net can use
        vias_required: True if net spans multiple layers
        reason: Explanation for this assignment

    Example:
        >>> assignment = LayerAssignment(
        ...     net="DC_BUS_P",
        ...     primary_layer=Layer.L1_TOP,
        ...     allowed_layers={Layer.L1_TOP},
        ...     vias_required=False,
        ...     reason="HV constraint"
        ... )
    """

    net: str
    primary_layer: Layer
    allowed_layers: set[Layer] = field(default_factory=set)
    vias_required: bool = False
    reason: str = ""


@dataclass
class LayerConflict:
    """Represents a conflict between layer assignments.

    Attributes:
        net1: First conflicting net
        net2: Second conflicting net
        conflict_type: Type of conflict (e.g., "clearance_violation")
        description: Human-readable description
    """

    net1: str
    net2: str
    conflict_type: str
    description: str


def matches_pattern(net_name: str, pattern: str) -> bool:
    """Check if a net name matches a regex pattern.

    Args:
        net_name: Name of the net to check.
        pattern: Regex pattern to match against.

    Returns:
        True if the net name matches the pattern.

    Example:
        >>> matches_pattern("DC_BUS_P", r"DC_BUS_.*")
        True
        >>> matches_pattern("VCC_3V3", r"DC_BUS_.*")
        False
    """
    return bool(re.fullmatch(pattern, net_name))


# Default layer constraints for induction cooker design
# Order matters - first matching constraint wins
DEFAULT_LAYER_CONSTRAINTS: list[LayerConstraint] = [
    # High-voltage nets: L1 preferred (2oz copper)
    LayerConstraint(
        net_pattern=r"DC_BUS_.*|HV_.*|SW_NODE|AC_L|AC_N|RECT_.*",
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
        preferred_layer=Layer.L1_TOP,
        reason="High-voltage power distribution prefers Top layer (2oz copper)",
    ),
    # Gate drive nets: L1 preferred (close to ground plane on L2)
    LayerConstraint(
        net_pattern=r"GATE_.*|DRV_.*|DRIVER_.*",
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
        preferred_layer=Layer.L1_TOP,
        reason="Gate drive signals prefer L1 for tight coupling to L2 ground",
    ),
    # Sensitive Analog/Sensing: Top layer preferred (isolate from Digital)
    # Allow all layers for via transitions to enable routing flexibility
    LayerConstraint(
        net_pattern=r"SENSE_.*|ADC_.*|TEMP_.*|ANALOG_.*|I_SENSE",
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
        preferred_layer=Layer.L1_TOP,
        reason="Analog signals prefer Top layer, vias allowed for routing flexibility",
    ),
    # SPI Bus: Bottom layer preferred (isolate from HV/Analog on Top)
    # Allow L1 for via transitions since pads are on L1
    LayerConstraint(
        net_pattern=r"SPI_.*",
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
        preferred_layer=Layer.L4_BOT,
        reason="SPI prefers Bottom layer, visas allowed for pad access",
    ),
    # USB/Digital: prefer bottom
    LayerConstraint(
        net_pattern=r"USB_.*|PWM_.*|DIGITAL_.*",
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
        preferred_layer=Layer.L4_BOT,
        reason="General digital signals prefer bottom layer",
    ),
    # Ground nets: prefer bottom, can use top
    LayerConstraint(
        net_pattern=r"GND|PGND|CGND|ISOGND|AGND|DGND|.*_GND",
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
        preferred_layer=Layer.L4_BOT,
        reason="Ground connections prefer bottom layer",
    ),
    # Catch-all: default to bottom layer for general signals
    LayerConstraint(
        net_pattern=r".*",
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
        preferred_layer=Layer.L4_BOT,
        reason="Default signal routing prefers bottom layer",
    ),
]


def _get_net_class(net_name: str, netlist: Netlist) -> str | None:
    """Get the net class for a net from the netlist.

    Args:
        net_name: Name of the net.
        netlist: Netlist containing net definitions.

    Returns:
        Net class string, or None if not found.
    """
    for net in netlist.nets:
        if net.name == net_name:
            return getattr(net, "net_class", None)
    return None


def assign_layers(
    netlist: Netlist,
    constraints: list[LayerConstraint] | None = None,
    component_positions: Array | None = None,
) -> dict[str, LayerAssignment]:
    """Assign layers to all nets in a netlist.

    Uses constraint matching to determine allowed and preferred layers
    for each net. Constraints are evaluated in order - first match wins.

    Args:
        netlist: Netlist containing nets to assign.
        constraints: Layer constraints (defaults to DEFAULT_LAYER_CONSTRAINTS).

    Returns:
        Dictionary mapping net names to LayerAssignment objects.

    Example:
        >>> assignments = assign_layers(netlist)
        >>> assignments["DC_BUS_P"].primary_layer
        Layer.L1_TOP
    """
    if constraints is None:
        constraints = DEFAULT_LAYER_CONSTRAINTS

    assignments: dict[str, LayerAssignment] = {}

    for net in netlist.nets:
        # Find first matching constraint
        matched_constraint: LayerConstraint | None = None
        for constraint in constraints:
            if matches_pattern(net.name, constraint.net_pattern):
                matched_constraint = constraint
                break

        # If component positions are available and we fell through to a catch-all (or no constraint),
        # try to be smart about geometric assignment
        geometric_preferred_layer = None
        if component_positions is not None:
            # Check if we hit the catch-all constraint (usually ".*")
            # Or if we want to provide a hint for constraints that allow multiple layers
            is_catch_all = matched_constraint and matched_constraint.net_pattern == r".*"

            if matched_constraint is None or is_catch_all:
                direction = _get_net_dominant_direction(net, netlist, component_positions)
                if direction == "horizontal":
                    geometric_preferred_layer = Layer.L1_TOP
                elif direction == "vertical":
                    geometric_preferred_layer = Layer.L4_BOT

        if matched_constraint is None:
            # Should never happen with catch-all, but handle gracefully
            preferred = geometric_preferred_layer if geometric_preferred_layer else Layer.L4_BOT
            matched_constraint = LayerConstraint(
                net_pattern=r".*",
                allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
                preferred_layer=preferred,
                reason="No matching constraint, using default (Geometric)"
                if geometric_preferred_layer
                else "No matching constraint, using default",
            )
        elif geometric_preferred_layer and matched_constraint.net_pattern == r".*":
            # Enhance the catch-all with geometric preference
            matched_constraint = LayerConstraint(
                net_pattern=r".*",
                allowed_layers=matched_constraint.allowed_layers,
                preferred_layer=geometric_preferred_layer,
                reason=f"Geometric preference ({'Horizontal' if geometric_preferred_layer == Layer.L1_TOP else 'Vertical'})",
            )

        # Determine if vias are required (multi-layer routing)
        # For now, single-layer-only constraints don't need vias
        vias_required = len(matched_constraint.allowed_layers) > 1

        # Create assignment
        # Note: For single-layer constraints, vias_required should be False
        # because the net CAN'T use multiple layers, not because it doesn't need to
        if len(matched_constraint.allowed_layers) == 1:
            vias_required = False

        assignments[net.name] = LayerAssignment(
            net=net.name,
            primary_layer=matched_constraint.preferred_layer,
            allowed_layers=matched_constraint.allowed_layers.copy(),
            vias_required=vias_required,
            reason=matched_constraint.reason,
        )

    return assignments


def _get_net_dominant_direction(net: "Net", netlist: Netlist, positions: Array) -> str:
    """Determine dominant direction of a net based on pin positions.

    Args:
        net: Net object
        netlist: Netlist for component lookups
        positions: (N, 2) array of component positions

    Returns:
        "horizontal", "vertical", or "mixed"
    """
    if not net.pins:
        return "mixed"

    min_x, max_x = float("inf"), float("-inf")
    min_y, max_y = float("inf"), float("-inf")

    count = 0
    for comp_ref, pin_name in net.pins:
        comp_idx = netlist.get_component_index(comp_ref)
        if comp_idx is None:
            continue

        comp = netlist.components[comp_idx]
        pin = comp.get_pin(pin_name)
        if pin:
            _cx, _cy = float(positions[comp_idx, 0]), float(positions[comp_idx, 1])
            px, py = pin_world_position(pin, comp)

            min_x = min(min_x, px)
            max_x = max(max_x, px)
            min_y = min(min_y, py)
            max_y = max(max_y, py)
            count += 1

    if count < 2:
        return "mixed"

    dx = max_x - min_x
    dy = max_y - min_y

    # Hysteresis ratio to decide direction
    ratio = 1.2

    if dx > dy * ratio:
        return "horizontal"
    elif dy > dx * ratio:
        return "vertical"

    return "mixed"


def find_layer_conflicts(
    _assignments: dict[str, LayerAssignment],
) -> list[LayerConflict]:
    """Find conflicts in layer assignments.

    Currently checks for:
    - (Future) HV nets too close to LV nets on same layer
    - (Future) Nets that can't be routed without crossings

    Args:
        assignments: Dictionary of layer assignments.

    Returns:
        List of LayerConflict objects describing conflicts.

    Example:
        >>> conflicts = find_layer_conflicts(assignments)
        >>> if conflicts:
        ...     for c in conflicts:
        ...         print(f"Conflict: {c.description}")
    """
    conflicts: list[LayerConflict] = []

    # Currently a placeholder - real conflict detection would require
    # geometric analysis of actual routes, which happens in maze routing
    #
    # Future improvements:
    # 1. Check for HV/LV proximity violations
    # 2. Check for impossible crossing situations
    # 3. Verify ground/power plane splits are respected

    return conflicts


def get_routing_layers() -> list[Layer]:
    """Get layers available for signal routing.

    Returns:
        List of layers that can be used for routing.
        Now includes all 4 layers since inner layers support mixed routing.
    """
    return [Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT]


def get_plane_layers() -> list[Layer]:
    """Get layers that are primarily planes (but can also route signals).

    Returns:
        List of plane layers (L2 and L3).
        Note: These layers now support mixed-mode routing.
    """
    return [Layer.L2_GND, Layer.L3_PWR]


def get_signal_only_layers() -> list[Layer]:
    """Get layers that are signal-only (outer layers).

    Returns:
        List of signal-only layers (L1 and L4).
    """
    return [Layer.L1_TOP, Layer.L4_BOT]
