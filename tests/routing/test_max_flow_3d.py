import pytest
import networkx as nx
from temper_placer.router_v6.analysis.max_flow import MaxFlowAnalyzer
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.stage0_data import DesignRules

def test_max_flow_3d_bypass():
    """
    Test that 3D Max-Flow correctly finds a path through an alternate layer.
    Scenario:
    - Layer 1 (Top): Has a total blockage in the middle (0 capacity).
    - Layer 2 (Bottom): Has plenty of room (High capacity).
    - Net starts and ends on Top layer.
    Expected: Max Flow = 1.0 (bypass through Bottom layer).
    """
    # 1. Setup Skeletons for 2 layers
    # Top Layer Skeleton: (0,0) -> (5,0) -> (10,0)
    top_g = nx.Graph()
    top_g.add_edge((0.0, 0.0), (5.0, 0.0))
    top_g.add_edge((5.0, 0.0), (10.0, 0.0))
    top_skeleton = ChannelSkeleton(graph=top_g, layer_name="F.Cu", total_length=10.0)
    
    # Top Widths: (5,0) is blocked
    top_widths = ChannelWidths(
        layer_name="F.Cu",
        node_widths={},
        edge_widths={((0.0, 0.0), (5.0, 0.0)): 1.0, ((5.0, 0.0), (10.0, 0.0)): 0.05},
        min_width=0.05,
        max_width=1.0,
        avg_width=0.5
    )
    
    # Bottom Layer Skeleton: (0,0) -> (5,0) -> (10,0)
    bot_g = nx.Graph()
    bot_g.add_edge((0.0, 0.0), (5.0, 0.0))
    bot_g.add_edge((5.0, 0.0), (10.0, 0.0))
    bot_skeleton = ChannelSkeleton(graph=bot_g, layer_name="B.Cu", total_length=10.0)
    
    # Bottom Widths: wide open
    bot_widths = ChannelWidths(
        layer_name="B.Cu",
        node_widths={},
        edge_widths={((0.0, 0.0), (5.0, 0.0)): 1.0, ((5.0, 0.0), (10.0, 0.0)): 1.0},
        min_width=1.0,
        max_width=1.0,
        avg_width=1.0
    )
    
    rules = DesignRules(
        net_classes={},
        net_class_assignments={},
        default_clearance_mm=0.2,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.4,
        default_via_drill_mm=0.2,
    )
    
    # 2. Initialize 3D Analyzer
    skeletons = {"F.Cu": top_skeleton, "B.Cu": bot_skeleton}
    widths = {"F.Cu": top_widths, "B.Cu": bot_widths}
    
    analyzer = MaxFlowAnalyzer(skeletons, widths, rules)
    
    # 3. Define Net (Start on Top at (0,0), End on Top at (10,0))
    nets = {
        "NET1": {
            "source": (0.0, 0.0),
            "sink": (10.0, 0.0),
            "allowed_layers": ["F.Cu", "B.Cu"]
        }
    }
    
    result = analyzer.compute_feasibility(nets)
    
    # Without 3D bypass, flow would be 0 because (5,0)->(10,0) on Top is 0.05 ( < rules.trace_width 0.2)
    # With 3D bypass, it should be 1.0
    assert result.max_flow >= 0.99
    assert result.is_feasible is True

if __name__ == "__main__":
    try:
        test_max_flow_3d_bypass()
        print("3D Max-Flow Test PASSED")
    except Exception as e:
        print(f"3D Max-Flow Test FAILED: {e}")
        import traceback
        traceback.print_exc()
