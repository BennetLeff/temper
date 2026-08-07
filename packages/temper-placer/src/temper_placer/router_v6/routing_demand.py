"""
Router V6 Stage 2.7: Estimate Demand

Estimates routing demand based on nets and pins.
Part of temper-eccz (Stage 2 - Channel Analysis)

Wave 4 Phase B: ``estimate_routing_demand`` and
``RoutingDemand.routing_complexity`` delegate to ``temper_geometry``
(``routing_demand_estimate_py`` / ``routing_demand_complexity_py``) -- both
kernels mirror this module's real contract exactly (an arbitrary
``ParsedPCB``'s components/nets in, the same 9-field result out), so the
delegation is a full substitution rather than a partial one.
``RoutingDemandStage``/``validate_routing_demand`` stay Python unchanged
(process-global validator registration is a Python-only concern).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import temper_geometry as _tg

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
        return _tg.routing_demand_complexity_py(self.avg_pins_per_net, self.routable_nets)


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
    # Handle both dict and list formats for nets
    # Type annotation says list[Net] but tests and some code paths use dict
    as_dict = isinstance(pcb.nets, dict)
    # Narrow via an inline isinstance check rather than reusing `as_dict`:
    # mypy narrows `pcb.nets` inside a ternary's own `isinstance(...)`
    # condition, but does not propagate that narrowing through an
    # intermediate bool variable, so the `as_dict`-flag form left the
    # declared `list[Net]` type unnarrowed on this branch (attr-defined
    # on `.keys()`).
    net_names = (
        list(pcb.nets.keys()) if isinstance(pcb.nets, dict) else [net.name for net in pcb.nets]
    )

    # `pin.net` is `str | None`; the classification loop only ever compares
    # it against a real net name (never `None`), so a pin with no net is
    # marshalled as a sentinel that cannot collide with an actual net name
    # rather than as `""` (an empty net name, while unusual, is not
    # impossible, and `None` is never one).
    components = [
        (comp.ref, [(pin.number, pin.net if pin.net is not None else "\x00") for pin in comp.pins])
        for comp in pcb.components
    ]

    (
        total_nets,
        routable_nets,
        total_pins,
        signal_nets,
        power_nets,
        diff_pair_nets,
        avg_pins_per_net,
        max_pins_per_net,
        _routing_complexity,
    ) = _tg.routing_demand_estimate_py(components, net_names, as_dict)

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
    """Stage 2.7: Estimate routing demand from netlist."""

    @property
    def name(self) -> str:
        return "RoutingDemand"

    def run(self, state: BoardState) -> BoardState:
        assert state._parsed_pcb is not None
        pcb: ParsedPCB = state._parsed_pcb
        routing_demand = estimate_routing_demand(pcb)
        return replace(state, routing_demand=routing_demand)


@register_validator("RoutingDemand")
def validate_routing_demand(state: BoardState) -> list[StageDRCFailure]:
    """Validate routing demand invariants."""
    failures: list[StageDRCFailure] = []
    if state.routing_demand is None:
        failures.append(
            StageDRCFailure(
                field="routing_demand",
                value=None,
                reason="Routing demand not computed",
                stage="RoutingDemand",
            )
        )
        return failures

    rd = state.routing_demand
    if rd.signal_nets + rd.power_nets > rd.total_nets:
        failures.append(
            StageDRCFailure(
                field="routing_demand",
                value="signal="
                + repr(rd.signal_nets)
                + ", power="
                + repr(rd.power_nets)
                + ", total="
                + repr(rd.total_nets),
                reason="signal_nets + power_nets exceeds total_nets",
                stage="RoutingDemand",
            )
        )
    if rd.routable_nets < 0 or rd.total_pins < 0:
        failures.append(
            StageDRCFailure(
                field="routing_demand",
                value="routable=" + repr(rd.routable_nets) + ", pins=" + repr(rd.total_pins),
                reason="Negative net/pin counts",
                stage="RoutingDemand",
            )
        )

    return failures
