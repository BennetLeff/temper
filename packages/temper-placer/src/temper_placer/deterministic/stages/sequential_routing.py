from dataclasses import replace
from typing import List, Tuple
from ..state import BoardState
from .base import Stage
from .astar import DeterministicAStar
from ...core.board import Trace

class SequentialRoutingStage(Stage):
    def __init__(self, trace_width_mm: float = 0.25, clearance_mm: float = 0.2):
        self.trace_width_mm = trace_width_mm
        self.clearance_mm = clearance_mm

    @property
    def name(self) -> str:
        return "sequential_routing"
    
    def run(self, state: BoardState) -> BoardState:
        if not state.board or not state.netlist or not state.net_order or not state.grid:
            return state
            
        grid = state.grid
        net_order = state.net_order
        net_by_name = {n.name: n for n in state.netlist.nets}
        comp_by_ref = {c.ref: c for c in state.netlist.components}
        
        all_traces = list(state.routes)
        
        for net_name in net_order:
            if net_name not in net_by_name:
                continue
            net = net_by_name[net_name]
            
            # Find pin positions
            pin_positions = []
            for comp_ref, pin_name in net.pins:
                if comp_ref not in comp_by_ref:
                    continue
                comp = comp_by_ref[comp_ref]
                pin = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
                if not pin:
                    continue
                pos = comp.initial_position or (0, 0)
                pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                pin_positions.append(pin_pos)
                
            if len(pin_positions) < 2:
                continue
                
            # Temporarily unblock target pins
            for pos in pin_positions:
                grid.unblock_circle(pos, radius_mm=0.5)
                
            pathfinder = DeterministicAStar(grid)
            # Route first two pins for MVP-1
            path = pathfinder.find_path(start=pin_positions[0], end=pin_positions[1])
            
            if path:
                # Block the routed trace
                grid.block_trace(path, width_mm=self.trace_width_mm, clearance_mm=self.clearance_mm)
                
                # Create Trace objects for state
                for i in range(len(path) - 1):
                    all_traces.append(Trace(
                        start=path[i],
                        end=path[i+1],
                        width=self.trace_width_mm,
                        layer="F.Cu", # Assume Top layer for MVP-1
                        net=net_name
                    ))
            
            # Re-block the pins
            for pos in pin_positions:
                grid.block_circle(pos, radius_mm=0.5, clearance_mm=self.clearance_mm)
                
        return replace(state, routes=frozenset(all_traces))
