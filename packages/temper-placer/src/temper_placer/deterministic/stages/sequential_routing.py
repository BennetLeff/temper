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
        
        # Build layer assignment lookup from BoardState
        layer_by_net = {}
        if state.layer_assignments:
            for assignment in state.layer_assignments:
                layer_by_net[assignment.net_name] = assignment.layer
        
        # Layer name to index mapping
        layer_name_to_idx = {
            "F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3
        }
        layer_idx_to_name = {0: "F.Cu", 1: "In1.Cu", 2: "In2.Cu", 3: "B.Cu"}
        
        all_traces = list(state.routes)
        
        for net_name in net_order:
            if net_name not in net_by_name:
                continue
            net = net_by_name[net_name]
            
            # Determine layer for this net
            layer_idx = layer_by_net.get(net_name, 0)  # Default to layer 0
            layer_name = layer_idx_to_name.get(layer_idx, "F.Cu")
            
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
                
            # Temporarily unblock target pins on the routing layer
            for pos in pin_positions:
                grid.unblock_circle(pos, radius_mm=1.0, layer=layer_idx)
                
            pathfinder = DeterministicAStar(grid)
            # Route first two pins on assigned layer
            path = pathfinder.find_path(start=pin_positions[0], end=pin_positions[1], layer=layer_idx)
            
            if path:
                # Block the routed trace on the same layer
                grid.block_trace(path, width_mm=width, clearance_mm=clearance, layer=layer_idx)
                
                # Create Trace objects for state with correct layer
                for i in range(len(path) - 1):
                    all_traces.append(Trace(
                        start=path[i],
                        end=path[i+1],
                        width=width,
                        layer=layer_name,
                        net=net_name
                    ))
            
            # Re-block the pins on the routing layer
            for pos in pin_positions:
                grid.block_circle(pos, radius_mm=0.5, clearance_mm=clearance, layer=layer_idx)
                
        return replace(state, routes=frozenset(all_traces))

