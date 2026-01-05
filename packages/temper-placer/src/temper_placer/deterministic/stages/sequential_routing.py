from dataclasses import replace
from typing import List, Tuple
from ..state import BoardState
from .base import Stage
from .astar import DeterministicAStar
from ...core.board import Trace, Via
from ...core.design_rules import DesignRules
from ...routing.constraints.spatial_index import Track as OracleTrack, Via as OracleVia
from ...routing.constraints.geometry import Point as OraclePoint
from ..geometry.via_placement import PadInfo, place_via_with_clearance
from ..geometry.grid_utils import snap_to_grid, add_endpoint_nudge

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
        is_plane_by_net = {}
        if state.layer_assignments:
            for assignment in state.layer_assignments:
                layer_by_net[assignment.net_name] = assignment.layer
                if hasattr(assignment, 'is_plane'):
                    is_plane_by_net[assignment.net_name] = assignment.is_plane
        
        # Layer name to index mapping
        layer_name_to_idx = {
            "F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3
        }
        layer_idx_to_name = {0: "F.Cu", 1: "In1.Cu", 2: "In2.Cu", 3: "B.Cu"}
        
        all_traces = list(state.routes)
        all_vias = list(state.vias)
        
        # Gather all pads for via clearance checking
        all_pads_info = []
        for component in state.netlist.components:
            comp_pos = comp_by_ref[component.ref].initial_position or (0, 0)
            for pin in component.pins:
                # Approximate pad radius (assuming circular for clearance)
                pad_r = 0.5
                if self.pad_sizes:
                    real_pad = self.pad_sizes.get((component.ref, pin.name))
                    if real_pad:
                        pad_r = max(real_pad.size.X, real_pad.size.Y) / 2.0
                
                all_pads_info.append(PadInfo(
                    position=(comp_pos[0] + pin.position[0], comp_pos[1] + pin.position[1]),
                    radius=pad_r,
                    mask_expansion=getattr(pin, 'mask_expansion', 0.1)
                ))
        
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
            pins = [] # Store actual Pin objects
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
                pins.append(pin)
                
            if len(pin_positions) < 2 and not is_plane_by_net.get(net_name, False):
                continue
            
            # Check if this is a plane net (GND/Power on inner layers)
            is_plane = is_plane_by_net.get(net_name, False)
            
            if is_plane:
                # For plane nets, we don't route traces.
                # We just generate a via at each pin to connect to the plane.
                via_d = 0.6
                via_drill = 0.3
                mask_expansion = 0.1
                if self.design_rules and rules:
                    via_d = rules.via_diameter
                    via_drill = rules.via_drill
                
                via_mask_radius = via_d / 2.0 + mask_expansion

                for pos in pin_positions:
                    # Find safe position for via
                    if state.drc_oracle:
                        sites = state.drc_oracle.get_valid_via_sites(pos, search_radius=2.0, net=net_name)
                        if sites:
                            safe_pos = sites[0]
                        else:
                            print(f"WARNING: DRCOracle could not find safe via position for {net_name} at {pos}")
                            safe_pos = pos
                    else:
                        safe_pos = place_via_with_clearance(pos, all_pads_info, via_mask_radius)
                        if not safe_pos:
                            print(f"WARNING: Could not find safe via position for {net_name} at {pos}")
                            safe_pos = pos # Fallback
                    
                    # Create Via connecting Top to Plane Layer
                    via = Via(
                        position=safe_pos,
                        drill=via_drill,
                        width=via_d,
                        layers=("F.Cu", layer_name),
                        net=net_name
                    )
                    all_vias.append(via)

                    # Register in DRCOracle
                    if state.drc_oracle:
                        state.drc_oracle.register_via(OracleVia(
                            center=OraclePoint(safe_pos[0], safe_pos[1]),
                            diameter=via_d,
                            drill=via_drill,
                            net=net_name
                        ))
                    
                    # If via shifted, add a short stub trace from pin to via
                    if safe_pos != pos:
                        all_traces.append(Trace(
                            start=pos,
                            end=safe_pos,
                            width=width,
                            layer="F.Cu",
                            net=net_name
                        ))
                        # Register stub in DRCOracle
                        if state.drc_oracle:
                            state.drc_oracle.register_track(OracleTrack(
                                start=OraclePoint(pos[0], pos[1]),
                                end=OraclePoint(safe_pos[0], safe_pos[1]),
                                width=width,
                                net=net_name,
                                layer=0 # F.Cu
                            ))
                    
                    # Block Via on ALL layers
                    for l_idx in range(grid.layer_count):
                        grid.block_circle(safe_pos, radius_mm=via_d/2, clearance_mm=clearance, layer=l_idx)
                
                # Skip trace routing for plane nets
                continue

            # Unblock THIS net's pads so A* can route to them
            unblock_radius = width / 2.0 + clearance + (0.15 if any(p.is_pth for p in pins) else 0.1)
            for i, pos in enumerate(pin_positions):
                # Calculate full unblock radius including pad size
                pad_r = 0.5
                if self.pad_sizes:
                    real_pad = self.pad_sizes.get(pin_info[i])
                    if real_pad:
                        pad_r = max(real_pad.size.X, real_pad.size.Y) / 2.0
                full_unblock_radius = pad_r + unblock_radius
                grid.unblock_circle(pos, radius_mm=full_unblock_radius, layer=layer_idx)

            pathfinder = DeterministicAStar(
                grid=grid,
                drc_oracle=state.drc_oracle,
                net_name=net_name,
                trace_width=width
            )
            mst_edges = self._compute_mst(pin_positions)

            # Snap pin positions to grid for A* pathfinding
            snapped_positions = [snap_to_grid(p, grid.cell_size_mm) for p in pin_positions]

            net_paths = []
            
            # Route all edges in the MST
            for idx1, idx2 in mst_edges:
                # Use snapped positions for grid-based pathfinding
                p1_snapped = snapped_positions[idx1]
                p2_snapped = snapped_positions[idx2]

                # Route between these two pins
                path = pathfinder.find_path(start=p1_snapped, end=p2_snapped, layer=layer_idx)
                if path:
                    # Add nudge segments to connect snapped path back to actual centers
                    nudged_path = add_endpoint_nudge(path, pin_positions[idx1], pin_positions[idx2])

                    # Validate path with DRCOracle before accepting
                    path_valid = True
                    if state.drc_oracle:
                        for i in range(len(nudged_path) - 1):
                            valid, reason = state.drc_oracle.can_place_track_segment(
                                nudged_path[i], nudged_path[i+1], layer_idx, net_name, width
                            )
                            if not valid:
                                print(f"  Path rejected for {net_name}: {reason}")
                                path_valid = False
                                break

                    if path_valid:
                        net_paths.append(nudged_path)
                    else:
                        print(f"  WARNING: Could not find DRC-compliant path for {net_name} segment {idx1}->{idx2}")
            
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
                    # Register in DRCOracle
                    if state.drc_oracle:
                        state.drc_oracle.register_track(OracleTrack(
                            start=OraclePoint(path[i][0], path[i][1]),
                            end=OraclePoint(path[i+1][0], path[i+1][1]),
                            width=width,
                            net=net_name,
                            layer=layer_idx
                        ))
    
            
            # Generate Vias for pins if routed on inner layer
            if net_paths and layer_name != "F.Cu":
                via_d = 0.6
                via_drill = 0.3
                mask_expansion = 0.1
                if self.design_rules and rules:
                    via_d = rules.via_diameter
                    via_drill = rules.via_drill
                
                via_mask_radius = via_d / 2.0 + mask_expansion
                
                # Assume all pins are on Top/Bottom and need Via to connect to Inner
                # Ideally check pin layer, but for MVP assuming Top SMD/THT
                for pos in pin_positions:
                    # Find safe position for via
                    if state.drc_oracle:
                        sites = state.drc_oracle.get_valid_via_sites(pos, search_radius=2.0, net=net_name)
                        if sites:
                            safe_pos = sites[0]
                        else:
                            print(f"WARNING: DRCOracle could not find safe via position for {net_name} at {pos}")
                            safe_pos = pos
                    else:
                        safe_pos = place_via_with_clearance(pos, all_pads_info, via_mask_radius)
                        if not safe_pos:
                            print(f"WARNING: Could not find safe via position for {net_name} at {pos}")
                            safe_pos = pos # Fallback

                    # Create Via
                    via = Via(
                        position=safe_pos,
                        drill=via_drill,
                        width=via_d,
                        layers=("F.Cu", layer_name),
                        net=net_name
                    )
                    all_vias.append(via)

                    # Register in DRCOracle
                    if state.drc_oracle:
                        state.drc_oracle.register_via(OracleVia(
                            center=OraclePoint(safe_pos[0], safe_pos[1]),
                            diameter=via_d,
                            drill=via_drill,
                            net=net_name
                        ))
                    
                    # If via shifted, add a short stub trace from pin to via
                    if safe_pos != pos:
                        all_traces.append(Trace(
                            start=pos,
                            end=safe_pos,
                            width=width,
                            layer="F.Cu",
                            net=net_name
                        ))
                        # Register stub in DRCOracle
                        if state.drc_oracle:
                            state.drc_oracle.register_track(OracleTrack(
                                start=OraclePoint(pos[0], pos[1]),
                                end=OraclePoint(safe_pos[0], safe_pos[1]),
                                width=width,
                                net=net_name,
                                layer=0 # F.Cu
                            ))
                    
                    # Block Via on ALL layers
                    # Iterate all grid layers
                    for l_idx in range(grid.layer_count):
                        grid.block_circle(safe_pos, radius_mm=via_d/2, clearance_mm=clearance, layer=l_idx)

            # Re-block THIS net's pads after routing to protect them from subsequent nets
            inflated_clearance = clearance + (width / 2.0) + (0.15 if any(p.is_pth for p in pins) else 0.1)
            for i, pos in enumerate(pin_positions):
                pad_r = 0.5
                if self.pad_sizes:
                    real_pad = self.pad_sizes.get(pin_info[i])
                    if real_pad:
                        pad_r = max(real_pad.size.X, real_pad.size.Y) / 2.0
                grid.block_circle(pos, radius_mm=pad_r, clearance_mm=inflated_clearance, layer=layer_idx)

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
