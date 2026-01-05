from dataclasses import replace
from ..state import BoardState
from .base import Stage
from ...routing.net_ordering import order_nets
from ...core.loop import LoopCollection

class NetOrderingStage(Stage):
    @property
    def name(self) -> str:
        return "net_ordering"
    
    def run(self, state: BoardState) -> BoardState:
        if not state.netlist:
            return state
            
        loops = state.loops or LoopCollection()
        ordered_nets = order_nets(state.netlist, loops)
        
        return replace(state, net_order=tuple(ordered_nets))
