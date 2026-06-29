"""
Router V6 Stage 2.7: Estimate Demand

Estimates routing demand based on nets and pins.
Part of temper-eccz (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


@dataclass
class RoutingDemand:
    """Routing demand estimate for the design."""

    total_nets: int  # Total number of nets
    routable_nets: int  # Nets requiring routing (>1 pin)
    total_pins: int  # Total pin count

    # Demand by net class
    signal_nets: int  # Regular signal nets
    power_nets: int  # Power/ground nets
    diff_pair_nets: int  # Differential pair nets

    # Complexity metrics
    avg_pins_per_net: float  # Average fanout
    max_pins_per_net: int  # Maximum fanout

    @property
    def routing_complexity(self) -> float:
        """Simple routing complexity score (0-1)."""
        # Higher pin count and fanout = higher complexity
        if self.routable_nets == 0:
            return 0.0
        return min(1.0, (self.avg_pins_per_net / 10.0) * (self.routable_nets / 100.0))


def estimate_routing_demand(
    pcb: ParsedPCB,
) -> RoutingDemand:
    """
    Estimate routing demand from PCB design.

    Args:
        pcb: Parsed PCB from Stage 0

    Returns:
        RoutingDemand with demand estimates

    Example:
        >>> demand = estimate_routing_demand(pcb)
        >>> demand.routable_nets > 0
        True
    """
    total_nets = len(pcb.nets)
    total_pins = sum(len(comp.pins) for comp in pcb.components)

    # Count routable nets (need >1 pin)
    routable_nets = 0
    pin_counts = []

    # Classify nets
    signal_nets = 0
    power_nets = 0
    diff_pair_nets = 0

    # Handle both dict and list formats for nets
    # Type annotation says list[Net] but tests and some code paths use dict
    if isinstance(pcb.nets, dict):
        net_items = pcb.nets.items()
    else:
        # Assume list[Net]
        net_items = [(net.name, net) for net in pcb.nets]

    for net_name, _net in net_items:
        # Count pins in this net
        pin_count = sum(
            1 for comp in pcb.components
            for pin in comp.pins
            if pin.net == net_name
        )

        if pin_count > 1:
            routable_nets += 1
            pin_counts.append(pin_count)

            # Classify by name heuristics
            net_upper = net_name.upper()
            if any(x in net_upper for x in ['GND', 'VCC', 'VDD', 'VSS', '+', '-']):
                power_nets += 1
            elif any(x in net_upper for x in ['_P', '_N', 'DP', 'DN']):
                diff_pair_nets += 1
            else:
                signal_nets += 1

    # Calculate statistics
    if pin_counts:
        avg_pins_per_net = sum(pin_counts) / len(pin_counts)
        max_pins_per_net = max(pin_counts)
    else:
        avg_pins_per_net = 0.0
        max_pins_per_net = 0

    return RoutingDemand(
        total_nets=total_nets,
        routable_nets=routable_nets,
        total_pins=total_pins,
        signal_nets=signal_nets,
        power_nets=power_nets,
        diff_pair_nets=diff_pair_nets,
        avg_pins_per_net=avg_pins_per_net,
        max_pins_per_net=max_pins_per_net,
    )


class RoutingDemandStage(Stage):
    '''Stage 2.7: Estimate routing demand from netlist.'''

    @property
    def name(self) -> str:
        return "RoutingDemand"

    def run(self, state: BoardState) -> BoardState:
        pcb: ParsedPCB = state._parsed_pcb
        routing_demand = estimate_routing_demand(pcb)
        return replace(state, routing_demand=routing_demand)


@register_validator("RoutingDemand")
def validate_routing_demand(state: BoardState) -> list[StageDRCFailure]:
    '''Validate routing demand invariants.'''
    failures: list[StageDRCFailure] = []
    if state.routing_demand is None:
        failures.append(StageDRCFailure(
            field="routing_demand", value=None,
            reason="Routing demand not computed", stage="RoutingDemand",
        ))
        return failures

    rd = state.routing_demand
    if rd.signal_nets + rd.power_nets > rd.total_nets:
        failures.append(StageDRCFailure(
            field="routing_demand",
            value="signal=" + repr(rd.signal_nets) + ", power=" + repr(rd.power_nets) + ", total=" + repr(rd.total_nets),
            reason="signal_nets + power_nets exceeds total_nets",
            stage="RoutingDemand",
        ))
    if rd.routable_nets < 0 or rd.total_pins < 0:
        failures.append(StageDRCFailure(
            field="routing_demand",
            value="routable=" + repr(rd.routable_nets) + ", pins=" + repr(rd.total_pins),
            reason="Negative net/pin counts",
            stage="RoutingDemand",
        ))

    return failures
