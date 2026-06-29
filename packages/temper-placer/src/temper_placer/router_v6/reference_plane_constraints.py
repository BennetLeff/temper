"""
Router V6 Stage 3.6: Add Reference Plane Constraints

Adds constraints for routing over reference planes (GND/power).
Part of temper-blqt (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.stage0_data import ParsedPCB


@dataclass
class ReferencePlaneConstraint:
    """Constraint for routing over a reference plane."""

    signal_net: str
    required_plane: str  # "GND", "VCC", etc.
    layer_name: str  # Which layer this applies to
    is_mandatory: bool  # True if signal MUST route over this plane

    @property
    def plane_type(self) -> str:
        """Identify plane type (ground vs power)."""
        if "GND" in self.required_plane.upper() or "VSS" in self.required_plane.upper():
            return "ground"
        return "power"


@dataclass
class ReferencePlaneConstraints:
    """Collection of reference plane constraints."""

    constraints: list[ReferencePlaneConstraint]

    @property
    def constraint_count(self) -> int:
        """Number of plane constraints."""
        return len(self.constraints)

    def get_constraints_for_net(self, net_name: str) -> list[ReferencePlaneConstraint]:
        """Get all plane constraints for a specific net."""
        return [c for c in self.constraints if c.signal_net == net_name]


def add_reference_plane_constraints(
    pcb: ParsedPCB,
) -> ReferencePlaneConstraints:
    """
    Generate reference plane routing constraints.

    Ensures signals route over appropriate reference planes for:
    - Signal integrity (return path)
    - EMI reduction
    - Impedance control

    Args:
        pcb: Parsed PCB from Stage 0

    Returns:
        ReferencePlaneConstraints for all signal nets

    Example:
        >>> constraints = add_reference_plane_constraints(pcb)
        >>> constraints.constraint_count > 0
        True
    """
    constraints = []

    # Get layer information from stackup
    if not hasattr(pcb, 'stackup') or not pcb.stackup:
        return ReferencePlaneConstraints(constraints=[])

    # Identify plane layers
    plane_layers = {}  # layer_name -> plane_net
    for layer_info in pcb.stackup.layers:
        if layer_info.layer_type == "plane" and layer_info.plane_net:
            plane_layers[layer_info.name] = layer_info.plane_net

    # For each signal net, determine required reference plane
    for net in pcb.nets:  # type: ignore[attr-defined]
        net_name = net.name
        # Skip power/ground nets themselves
        if _is_power_or_ground_net(net_name):
            continue

        # Determine which plane this signal should route over
        required_plane = _determine_reference_plane(net_name, net.net_class if hasattr(net, 'net_class') else 'signal')

        # Apply to signal layers
        for layer_info in pcb.stackup.layers:
                if layer_info.layer_type in ["signal", "mixed"] and required_plane:
                    constraints.append(ReferencePlaneConstraint(
                        signal_net=net_name,
                        required_plane=required_plane,
                        layer_name=layer_info.name,
                        is_mandatory=True,  # Mandatory for high-speed signals
                    ))

    return ReferencePlaneConstraints(constraints=constraints)


def _is_power_or_ground_net(net_name: str) -> bool:
    """Check if net is a power or ground net."""
    name_upper = net_name.upper()
    power_keywords = ['GND', 'VCC', 'VDD', 'VSS', 'VDDA', 'VSSA', '+', '-']
    return any(kw in name_upper for kw in power_keywords)


def _determine_reference_plane(net_name: str, _net_class: str) -> str:
    """
    Determine which reference plane a signal should route over.

    Args:
        net_name: Signal net name
        net_class: Net class (signal, power, etc.)

    Returns:
        Reference plane net name (typically "GND")
    """
    name_upper = net_name.upper()

    # High-speed signals typically use GND
    if any(x in name_upper for x in ['USB', 'PCIE', 'HDMI', 'LVDS', 'CLK', 'CLOCK']):
        return "GND"

    # Differential pairs use GND
    if any(x in name_upper for x in ['_P', '_N', 'DP', 'DN']):
        return "GND"

    # Default: GND is the most common reference plane
    return "GND"
