import pytest
import networkx as nx
import numpy as np
from temper_placer.router_v6.analysis.max_flow import MaxFlowAnalyzer
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.stage0_data import DesignRules

def test_max_flow_simple_bottleneck():
    """Test a simple channel with a bottleneck that should restrict flow."""
    # Create a simple linear skeleton: A --- B --- C
    G = nx.Graph()
    G.add_edge((0, 0), (10, 0), weight=10.0)
    G.add_edge((10, 0), (20, 0), weight=10.0)
    
    skeleton = ChannelSkeleton(graph=G, layer_name="F.Cu", total_length=20.0)
    
    # Define widths: A=5mm, B=1.5mm (bottleneck), C=5mm
    node_widths = {(0, 0): 5.0, (10, 0): 1.5, (20, 0): 5.0}
    edge_widths = {((0, 0), (10, 0)): 1.5, ((10, 0), (20, 0)): 1.5}
    
    widths = ChannelWidths(
        layer_name="F.Cu",
        node_widths=node_widths,
        edge_widths=edge_widths,
        min_width=1.5,
        max_width=5.0,
        avg_width=3.0
    )
    
    # Design rules: trace=0.4mm, clearance=0.6mm -> pitch=1.0mm
    rules = DesignRules(
        net_classes={},
        net_class_assignments={},
        default_trace_width_mm=0.4,
        default_clearance_mm=0.6,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3
    )
    
    # Define 3 nets that want to cross from (0,0) to (20,0)
    nets = {
        "NET1": ((0, 0), (20, 0)),
        "NET2": ((0, 0), (20, 0)),
        "NET3": ((0, 0), (20, 0))
    }
    
    analyzer = MaxFlowAnalyzer(skeleton, widths, rules)
    result = analyzer.compute_feasibility(nets)
    
    # Max flow should be 2.0 (capacity of bottleneck)
    assert result.max_flow == 2.0
    assert result.is_feasible is False
    assert len(result.min_cut_edges) > 0
    # Min-cut should involve the edge with capacity 2
    assert any(cap == 2.0 for u, v, cap in result.min_cut_edges)

def test_max_flow_feasible_scenario():
    """Test a scenario where enough capacity exists for all nets."""
    # A (source) --- B --- C (sink)
    G = nx.Graph()
    G.add_node((0, 0))
    G.add_node((10, 0))
    G.add_node((20, 0))
    G.add_edge((0, 0), (10, 0), weight=10.0)
    G.add_edge((10, 0), (20, 0), weight=10.0)
    
    skeleton = ChannelSkeleton(graph=G, layer_name="F.Cu", total_length=20.0)
    
    # Wider bottleneck: 2.5mm -> floor((2.5 - 0.4) / 1.0) + 1 = 2 + 1 = 3 traces
    node_widths = {(0, 0): 5.0, (10, 0): 2.5, (20, 0): 5.0}
    edge_widths = {((0, 0), (10, 0)): 2.5, ((10, 0), (20, 0)): 2.5}
    
    widths = ChannelWidths(
        layer_name="F.Cu",
        node_widths=node_widths,
        edge_widths=edge_widths,
        min_width=2.5,
        max_width=5.0,
        avg_width=4.0
    )
    
    rules = DesignRules(
        net_classes={},
        net_class_assignments={},
        default_trace_width_mm=0.4,
        default_clearance_mm=0.6,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3
    )
    
    # 3 nets should fit
    nets = {
        "NET1": ((0, 0), (20, 0)),
        "NET2": ((0, 0), (20, 0)),
        "NET3": ((0, 0), (20, 0))
    }
    
    analyzer = MaxFlowAnalyzer(skeleton, widths, rules)
    result = analyzer.compute_feasibility(nets)
    
    assert result.max_flow == 3.0
    assert result.is_feasible is True
