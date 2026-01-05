from dataclasses import replace
from typing import List, Tuple
from ..state import BoardState
from .base import Stage
from .astar import DeterministicAStar
from ...core.board import Trace, Via
from ...core.design_rules import DesignRules

class SequentialRoutingStage(Stage):
    def __init__(self, design_rules: DesignRules | None = None, 
                 trace_width_mm: float = 0.25, clearance_mm: float = 0.2,
                 cost_map_weights: any = None, pad_sizes: dict = None):
        self.design_rules = design_rules
        self.default_width = trace_width_mm
        self.default_clearance = clearance_mm
        self.pad_sizes = pad_sizes or {}

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
        all_vias = list(state.vias)
        
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
            
            # Find pin positions and refs
            pin_positions = []
            pin_info = [] # Store (ref, name) for lookup
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
                pin_info.append((comp_ref, pin.name))
                
            if len(pin_positions) < 2:
                continue
            
            # Helper to get unblock radius
            def get_unblock_radius(p_info):
                ref, name = p_info
                if self.pad_sizes:
                    real_pad = self.pad_sizes.get((ref, name))
                    if real_pad:
                        # Max dim / 2
                        pad_r = max(real_pad.size.X, real_pad.size.Y) / 2.0
                        # Match ClearanceGrid logic: pad_r + clearance + width/2 + mask_safety
                        # mask_safety=0.1, but we want to unblock enough to let the trace center leave
                        # The trace center is blocked if dist < pad_r + clearance + width/2 + mask
                        # So unblock radius MUST be >= that value.
                        return pad_r + 0.425 
                return 0.925

            # Temporarily unblock the target pin area on the routing layer
            for i, pos in enumerate(pin_positions):
                radius = get_unblock_radius(pin_info[i])
                grid.unblock_circle(pos, radius_mm=radius, layer=layer_idx)
                
            pathfinder = DeterministicAStar(grid)
            mst_edges = self._compute_mst(pin_positions)
            
            # pathfinder = DeterministicAStar(grid) # Duplicate
            net_paths = []
            
            # Route all edges in the MST
            for idx1, idx2 in mst_edges:
                p1 = pin_positions[idx1]
                p2 = pin_positions[idx2] # Fixed corruption
                
                # Route between these two pins
                path = pathfinder.find_path(start=p1, end=p2, layer=layer_idx)
                if path:
                    net_paths.append(path)
            
            # Commit all paths for this net
            for path in net_paths:
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
    
            
            # Generate Vias for pins if routed on inner layer
            if net_paths and layer_name != "F.Cu":
                via_d = 0.6
                via_drill = 0.3
                if self.design_rules and rules:
                    via_d = rules.via_diameter
                    via_drill = rules.via_drill
                
                # Assume all pins are on Top/Bottom and need Via to connect to Inner
                # Ideally check pin layer, but for MVP assuming Top SMD/THT
                for pos in pin_positions:
                    # Create Via
                    via = Via(
                        position=pos,
                        drill=via_drill,
                        width=via_d,
                        layers=("F.Cu", layer_name),
                        net=net_name
                    )
                    all_vias.append(via)
                    
                    # Block Via on ALL layers
                    # Iterate all grid layers
                    for l_idx in range(grid.layer_count):
                        grid.block_circle(pos, radius_mm=via_d/2, clearance_mm=clearance, layer=l_idx)

            # Re-block the pins on the routing layer
            # INFLATION FIX: Block with (clearance + trace_width/2 + mask_safety)
            # This ensures the router stays away considering its own width and mask rules.
            # Mask Safety = 0.1mm (heuristic for 0.05 expansion + 0.1 web vs 0.2 electrical)
            
            mask_safety_margin = 0.1 
            effective_clearance = clearance + (width / 2.0) + mask_safety_margin
            
            for i, pos in enumerate(pin_positions):
                radius = get_unblock_radius(pin_info[i])
                # Subtract 0.425 to get base pad radius? No, block_circle adds clearance.
                # Currently block_circle(radius, clearance) -> total = radius + clearance.
                # get_unblock_radius returns TOTAL radius (pad_r + 0.425).
                # So here we want: grid.block_circle(pos, radius_mm=pad_r, clearance_mm=effective_clearance, ...)
                # But effective_clearance is calculated as clearance + width/2 + mask (~0.425).
                # So we just need the PAD radius.
                
                real_pad_r = radius - 0.425 # Back-calculate or fetch again
                # Cleaner to fetch again or store.
                pad_r = 0.5
                if self.pad_sizes:
                    real_pad = self.pad_sizes.get(pin_info[i])
                    if real_pad:
                        pad_r = max(real_pad.size.X, real_pad.size.Y) / 2.0
                
                grid.block_circle(pos, radius_mm=pad_r, clearance_mm=effective_clearance, layer=layer_idx)
                
        return replace(state, routes=frozenset(all_traces), vias=frozenset(all_vias))


    def _compute_mst(self, points: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
        """Compute Minimum Spanning Tree using Prim's algorithm."""
        n = len(points)
        if n < 2:
            return []
            
        visited = {0}
        edges = []
        
        while len(visited) < n:
            min_dist_sq = float('inf')
            u_min, v_min = -1, -1
            
            # Find shortest edge from visited to unvisited
            for u in visited:
                for v in range(n):
                    if v in visited:
                        continue
                    
                    # Squared Euclidean distance
                    dist_sq = (points[u][0] - points[v][0])**2 + (points[u][1] - points[v][1])**2
                    
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        u_min = u
                        v_min = v
            
            if u_min != -1 and v_min != -1:
                visited.add(v_min)
                edges.append((u_min, v_min))
            else:
                break
                
        return edges
