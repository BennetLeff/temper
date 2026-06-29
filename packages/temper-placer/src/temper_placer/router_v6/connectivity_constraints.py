"""
Router V6 Stage 3.3: Add Connectivity Constraints

Adds connectivity constraints to ensure all nets are routed.
Part of temper-v02b (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.stage0_data import ParsedPCB


@dataclass
class ConnectivityConstraint:
    """Connectivity constraint for a net."""

    net_name: str
    pin_count: int
    requires_routing: bool  # True if >1 pin

    @property
    def is_routable(self) -> bool:
        """Check if net needs routing."""
        return self.requires_routing and self.pin_count > 1


@dataclass
class ConnectivityConstraints:
    """Collection of connectivity constraints."""

    constraints: list[ConnectivityConstraint]

    @property
    def routable_net_count(self) -> int:
        """Count of nets requiring routing."""
        return sum(1 for c in self.constraints if c.is_routable)

    @property
    def total_pin_count(self) -> int:
        """Total number of pins across all nets."""
        return sum(c.pin_count for c in self.constraints)


def add_connectivity_constraints(
    pcb: ParsedPCB,
) -> ConnectivityConstraints:
    """
    Generate connectivity constraints for all nets.

    Args:
        pcb: Parsed PCB from Stage 0

    Returns:
        ConnectivityConstraints with all net constraints

    Example:
        >>> constraints = add_connectivity_constraints(pcb)
        >>> constraints.routable_net_count > 0
        True
    """
    constraints = []

    for net in pcb.nets:  # type: ignore[attr-defined]
        net_name = net.name
        # Count pins in this net
        pin_count = sum(
            1 for comp in pcb.components
            for pin in comp.pins
            if pin.net == net_name
        )

        # Net needs routing if it has >1 pin
        requires_routing = pin_count > 1

        constraints.append(ConnectivityConstraint(
            net_name=net_name,
            pin_count=pin_count,
            requires_routing=requires_routing,
        ))

    return ConnectivityConstraints(constraints=constraints)
