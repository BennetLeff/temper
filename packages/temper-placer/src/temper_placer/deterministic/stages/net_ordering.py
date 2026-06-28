from dataclasses import replace
from typing import Dict, Optional
from ..state import BoardState
from .base import Stage
from temper_placer.router_v6.net_ordering import order_nets
from ...core.loop import LoopCollection


class NetOrderingStage(Stage):
    """Stage that determines the order in which nets are routed.

    EXP-6: Supports explicit net priorities from config to route
    critical nets (USB, SPI) first when board is least congested.
    """

    def __init__(self, net_priority: Optional[Dict[str, int]] = None):
        """Initialize net ordering stage.

        Args:
            net_priority: Optional dict mapping net names to priority (1=highest, 5=default).
                         Lower numbers route first.
        """
        self.net_priority = net_priority or {}

    @property
    def name(self) -> str:
        return "net_ordering"

    def run(self, state: BoardState) -> BoardState:
        if not state.netlist:
            return state

        loops = state.loops or LoopCollection()

        # EXP-6: Pass net_priority config to order_nets
        ordered_nets = order_nets(state.netlist, loops, self.net_priority)

        # Log if using config priorities
        if self.net_priority:
            prioritized = [n for n in ordered_nets if n in self.net_priority]
            if prioritized:
                print(
                    f"  EXP-6: {len(prioritized)} nets with explicit priority: {prioritized[:5]}..."
                )

        return replace(state, net_order=tuple(ordered_nets))
