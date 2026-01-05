from dataclasses import replace
from typing import List, Tuple
from ..state import BoardState
from .base import Stage
from .astar import DeterministicAStar
from ...core.board import Trace
from ...core.design_rules import DesignRules

class SequentialRoutingStage(Stage):
    def __init__(self, design_rules: DesignRules | None = None, 
                 trace_width_mm: float = 0.25, clearance_mm: float = 0.2):
        self.design_rules = design_rules
        self.default_width = trace_width_mm
        self.default_clearance = clearance_mm

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
            
            # Determine width and clearance
            width = self.default_width
            clearance = self.default_clearance
            
            if self.design_rules:
                # Pass net_class from Net object to look up rules correctly
                net_class_name = getattr(net, "net_class", None)
                rules = self.design_rules.get_rules_for_net(net_name, net_class=net_class_name)
                width = rules.trace_width
                clearance = rules.clearance
            
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
            # Use a larger radius (1.0mm) to ensure we clear the pad + clearance blocking
            # applied by ClearanceGridStage (0.5mm pad + 0.2mm clearance = 0.7mm)
            for pos in pin_positions:
                grid.unblock_circle(pos, radius_mm=1.0)
                
            pathfinder = DeterministicAStar(grid)
            # Route first two pins for MVP-1
            path = pathfinder.find_path(start=pin_positions[0], end=pin_positions[1])
            
            if path:
                # Block the routed trace
                grid.block_trace(path, width_mm=width, clearance_mm=clearance)
                
                # Create Trace objects for state
                for i in range(len(path) - 1):
                    all_traces.append(Trace(
                        start=path[i],
                        end=path[i+1],
                        width=width,
                        layer="F.Cu", # Assume Top layer for MVP-1
                        net=net_name
                    ))
            
            # Re-block the pins
            for pos in pin_positions:
                grid.block_circle(pos, radius_mm=0.5, clearance_mm=clearance)
                
        return replace(state, routes=frozenset(all_traces))
