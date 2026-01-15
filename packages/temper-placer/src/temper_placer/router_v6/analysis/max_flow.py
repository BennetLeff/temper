from __future__ import annotations
from dataclasses import dataclass
import networkx as nx
import math
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.stage0_data import DesignRules

@dataclass
class MaxFlowResult:
    """Result of max-flow feasibility analysis."""
    max_flow: float
    total_demand: int
    is_feasible: bool
    min_cut_edges: list[tuple[any, any, float]]  # List of (u, v, capacity) forming the min-cut

class MaxFlowAnalyzer:
    """
    Analyzes routing feasibility using Max-Flow Min-Cut Theorem.
    Supports multi-layer (3D) flow networks.
    """
    
    def __init__(
        self, 
        skeletons: dict[str, ChannelSkeleton], 
        widths: dict[str, ChannelWidths], 
        design_rules: DesignRules
    ):
        self.skeletons = skeletons
        self.widths = widths
        self.design_rules = design_rules
        
    def compute_feasibility(self, nets: dict[str, dict]) -> MaxFlowResult:
        """
        Compute feasibility using max-flow in 3D.
        
        Args:
            nets: Mapping of net_name to {source, sink, allowed_layers}
            
        Returns:
            MaxFlowResult with diagnostic data
        """
        # Create flow network
        F = nx.DiGraph()
        
        SOURCE = "SUPER_SOURCE"
        SINK = "SUPER_SINK"
        
        trace_width = self.design_rules.default_trace_width_mm
        clearance = self.design_rules.default_clearance_mm
        pitch = trace_width + clearance
        
        # 1. Build Layer Grids
        for layer_name, skeleton in self.skeletons.items():
            layer_widths = self.widths[layer_name]
            
            for u, v in skeleton.graph.edges():
                # Get channel width
                w = layer_widths.edge_widths.get((u, v), layer_widths.edge_widths.get((v, u), 0.0))
                
                # Capacity calculation
                if w >= trace_width:
                    capacity = int((w - trace_width) // pitch) + 1
                else:
                    capacity = 0
                
                # Node IDs are (layer, (x, y))
                u_id = (layer_name, u)
                v_id = (layer_name, v)
                
                F.add_edge(u_id, v_id, capacity=capacity)
                F.add_edge(v_id, u_id, capacity=capacity)
                
        # 2. Add Inter-layer Transitions (Vias)
        # For simplicity, we connect any two nodes with the same coordinates on adjacent layers
        layer_list = list(self.skeletons.keys())
        for i in range(len(layer_list) - 1):
            l1 = layer_list[i]
            l2 = layer_list[i+1]
            
            # Find nodes that align vertically (within tolerance)
            # This is an N^2 search per layer pair, but skeletons are sparse
            nodes1 = list(self.skeletons[l1].graph.nodes())
            nodes2 = list(self.skeletons[l2].graph.nodes())
            
            for n1 in nodes1:
                for n2 in nodes2:
                    dist = math.sqrt((n1[0] - n2[0])**2 + (n1[1] - n2[1])**2)
                    if dist < 0.1: # 0.1mm alignment tolerance for via
                        u_id = (l1, n1)
                        v_id = (l2, n2)
                        # Via capacity is high, but not infinite (to model via congestion eventually)
                        # For now, 100 traces per via channel is effectively infinite for our scale
                        F.add_edge(u_id, v_id, capacity=100)
                        F.add_edge(v_id, u_id, capacity=100)
                        
        # 3. Connect Super-S and Super-T
        total_demand = 0
        for net_name, data in nets.items():
            source_pos = data["source"]
            sink_pos = data["sink"]
            allowed_layers = data.get("allowed_layers", list(self.skeletons.keys()))
            
            # Find nearest nodes across all allowed layers
            best_u = None
            best_v = None
            min_u_dist = float('inf')
            min_v_dist = float('inf')
            
            for layer in allowed_layers:
                if layer not in self.skeletons: continue
                u, d_u = self._find_nearest_node(source_pos, layer)
                v, d_v = self._find_nearest_node(sink_pos, layer)
                
                if d_u < min_u_dist:
                    min_u_dist = d_u
                    best_u = (layer, u)
                if d_v < min_v_dist:
                    min_v_dist = d_v
                    best_v = (layer, v)
                    
            if best_u and best_v:
                net_source = f"S_{net_name}"
                net_sink = f"T_{net_name}"
                
                F.add_edge(SOURCE, net_source, capacity=1)
                F.add_edge(net_source, best_u, capacity=1)
                
                F.add_edge(best_v, net_sink, capacity=1)
                F.add_edge(net_sink, SINK, capacity=1)
                
                total_demand += 1
                
        if total_demand == 0:
            return MaxFlowResult(0, 0, True, [])
            
        # 4. Compute Max Flow
        cut_value, (reachable, non_reachable) = nx.minimum_cut(F, SOURCE, SINK)
        
        # 5. Extract Min-Cut
        min_cut_edges = []
        for u, v in F.edges():
            if u in reachable and v in non_reachable:
                # Only report physical layer edges (not via or super-edges)
                if isinstance(u, tuple) and isinstance(v, tuple):
                    if u[0] == v[0]: # Same layer = horizontal edge
                        min_cut_edges.append((u, v, F[u][v]['capacity']))
                        
        return MaxFlowResult(
            max_flow=float(cut_value),
            total_demand=total_demand,
            is_feasible=cut_value >= total_demand,
            min_cut_edges=min_cut_edges
        )

    def _find_nearest_node(self, pos: tuple[float, float], layer: str) -> tuple[any, float]:
        """Find nearest node in a specific layer's skeleton."""
        skeleton = self.skeletons[layer]
        min_dist = float('inf')
        nearest = None
        for node in skeleton.graph.nodes():
            dist = math.sqrt((pos[0] - node[0])**2 + (pos[1] - node[1])**2)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest, min_dist
