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
    
    Models the channel skeleton as a flow network where edge capacity 
    represents the number of parallel traces that can fit side-by-side.
    """
    
    def __init__(
        self, 
        skeleton: ChannelSkeleton, 
        widths: ChannelWidths, 
        design_rules: DesignRules
    ):
        self.skeleton = skeleton
        self.widths = widths
        self.design_rules = design_rules
        
    def compute_feasibility(self, nets: dict[str, tuple[tuple[float, float], tuple[float, float]]]) -> MaxFlowResult:
        """
        Compute feasibility using max-flow.
        
        Args:
            nets: Mapping of net_name to (source_pos, sink_pos)
            
        Returns:
            MaxFlowResult with diagnostic data
        """
        # Create flow network
        F = nx.DiGraph()
        
        # Super-source and Super-sink
        SOURCE = "SUPER_SOURCE"
        SINK = "SUPER_SINK"
        
        trace_width = self.design_rules.default_trace_width_mm
        clearance = self.design_rules.default_clearance_mm
        pitch = trace_width + clearance
        
        # Build edges with capacities
        for u, v in self.skeleton.graph.edges():
            # Get channel width (minimum along edge)
            w = self.widths.edge_widths.get((u, v), self.widths.edge_widths.get((v, u), 0.0))
            
            # Capacity formula: Number of parallel traces
            if w >= trace_width:
                capacity = int((w - trace_width) // pitch) + 1
            else:
                capacity = 0
                
            # Add bidirectional edges in flow network
            F.add_edge(u, v, capacity=capacity)
            F.add_edge(v, u, capacity=capacity)
            
        # Connect Super-S and Super-T
        total_demand = 0
        for net_name, (p1, p2) in nets.items():
            # Find nearest nodes in skeleton
            u = self._find_nearest_node(p1)
            v = self._find_nearest_node(p2)
            
            if u is not None and v is not None:
                # Flow demand of 1 for each net
                # Use sub-nodes for sources/sinks to avoid capacity overlap at nodes?
                # Actually, standard flow on edges is fine if we assume nodes have infinite capacity.
                # If cells are small, node capacity isn't the bottleneck, channel width is.
                
                # super-source -> net source node
                # We use internal node names to avoid collisions with coordinate tuples
                net_source = f"S_{net_name}"
                net_sink = f"T_{net_name}"
                
                F.add_edge(SOURCE, net_source, capacity=1)
                F.add_edge(net_source, u, capacity=1)
                
                F.add_edge(v, net_sink, capacity=1)
                F.add_edge(net_sink, SINK, capacity=1)
                
                total_demand += 1
                
        if total_demand == 0:
            return MaxFlowResult(0, 0, True, [])
            
        # Compute Max Flow / Min Cut
        cut_value, (reachable, non_reachable) = nx.minimum_cut(F, SOURCE, SINK)
        
        # Identify min-cut edges along the skeleton (not super-source/sink edges)
        min_cut_edges = []
        for u, v in F.edges():
            if u in reachable and v in non_reachable:
                # Only report edges that are part of the physical skeleton
                if isinstance(u, tuple) and isinstance(v, tuple):
                    min_cut_edges.append((u, v, F[u][v]['capacity']))
                    
        return MaxFlowResult(
            max_flow=float(cut_value),
            total_demand=total_demand,
            is_feasible=cut_value >= total_demand,
            min_cut_edges=min_cut_edges
        )

    def _find_nearest_node(self, pos: tuple[float, float]) -> any:
        """Find nearest node in skeleton graph."""
        min_dist = float('inf')
        nearest = None
        for node in self.skeleton.graph.nodes():
            dist = math.sqrt((pos[0] - node[0])**2 + (pos[1] - node[1])**2)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest
