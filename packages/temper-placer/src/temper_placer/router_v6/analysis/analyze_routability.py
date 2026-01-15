import sys
from pathlib import Path
import time
import json
import networkx as nx
import math

# Add packages to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.pipeline import build_occupancy_grid
from temper_placer.router_v6.routing_space import compute_routing_space
from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
from temper_placer.router_v6.channel_widths import compute_channel_widths
from temper_placer.router_v6.analysis.max_flow import MaxFlowAnalyzer

def analyze_temper_routability(pcb_path: Path):
    print(f"Analyzing routability for {pcb_path.name}...")
    
    # 1. Load PCB
    pcb = parse_kicad_pcb_v6(pcb_path)
    config_path = Path(__file__).parent.parent / "placement_constraints.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            config = json.load(f)
            overrides = config.get("overrides", {})
        for comp in pcb.components:
            if comp.ref in overrides:
                comp.initial_position = tuple(overrides[comp.ref]["position"])
    
    # 2. Extract Stage 2 data (Skeleton/Widths)
    # Exclude failed nets from obstacles so their pads don't block their own skeleton anchors
    failed_nets = [
        "SPI_CLK", "SPI_CS_TEMP", "VCC_BOOT", "PWM_L", "DC_BUS-", 
        "PWM_H", "GATE_L", "GATE_H", "I_SENSE", "SPI_MISO", "SW_NODE", "DC_BUS+"
    ]
    
    from temper_placer.router_v6.obstacle_map import build_obstacle_map
    from shapely.geometry import MultiPolygon, Polygon
    from shapely import STRtree
    
    # Re-implement compute_routing_space locally with exclusion
    obstacle_map = build_obstacle_map(pcb, [], exclude_nets=failed_nets)
    from temper_placer.router_v6.routing_space import _get_board_polygon, RoutingSpace
    board_polygon = _get_board_polygon(pcb)
    
    routing_spaces = {}
    for layer_info in pcb.stackup.layers:
        if layer_info.layer_type not in ["signal", "mixed"]: continue
        layer_name = layer_info.name
        obstacles = obstacle_map.get(layer_name, MultiPolygon())
        available_area = board_polygon.difference(obstacles)
        if isinstance(available_area, Polygon): available_area = MultiPolygon([available_area])
        
        obstacle_tree = STRtree(obstacles.geoms) if hasattr(obstacles, 'geoms') else None
        
        routing_spaces[layer_name] = RoutingSpace(
            layer_name=layer_name,
            available_area=available_area,
            total_area=board_polygon.area,
            obstacle_area=obstacles.area,
            routing_area=available_area.area,
            obstacles=obstacles,
            obstacle_tree=obstacle_tree
        )
    
    skeletons = {}
    channel_widths = {}
    for layer_name, space in routing_spaces.items():
        print(f"Extracting skeleton for {layer_name}...")
        skeleton = extract_channel_skeleton(space, pcb=pcb)
        skeletons[layer_name] = skeleton
        
        print(f"Computing channel widths for {layer_name}...")
        widths = compute_channel_widths(space, skeleton)
        channel_widths[layer_name] = widths
    
    # 3. Define Net Demands
    failed_nets = [
        "SPI_CLK", "SPI_CS_TEMP", "VCC_BOOT", "PWM_L", "DC_BUS-", 
        "PWM_H", "GATE_L", "GATE_H", "I_SENSE", "SPI_MISO", "SW_NODE", "DC_BUS+"
    ]
    
    net_demands = {}
    for net_name in failed_nets:
        pads = []
        for comp in pcb.components:
            for pin in comp.pins:
                if pin.net == net_name:
                    rotation_rad = math.radians(comp.initial_rotation * 90.0 if comp.initial_rotation else 0)
                    side = comp.initial_side if hasattr(comp, 'initial_side') else 0
                    abs_pos = pin.absolute_position(comp.initial_position, rotation_rad, side)
                    pads.append(abs_pos)
        
        if len(pads) >= 2:
            net_demands[net_name] = {
                "source": (pads[0][0], pads[0][1]),
                "sink": (pads[-1][0], pads[-1][1]),
                "allowed_layers": list(skeletons.keys())
            }
            
    print(f"Default Trace Width: {pcb.design_rules.default_trace_width_mm}mm")
    print(f"Default Clearance: {pcb.design_rules.default_clearance_mm}mm")
    
    # Check for terminal collisions (Top layer as proxy)
    print("\nChecking for terminal collisions (Top Layer)...")
    from shapely.geometry import Point
    top_space = routing_spaces.get("F.Cu", list(routing_spaces.values())[0])
    for net_name, data in net_demands.items():
        p1 = data["source"]
        p2 = data["sink"]
        if top_space.obstacles.contains(Point(p1)):
            print(f"  WARNING: {net_name} source {p1} is INSIDE Top Layer obstacle!")
        if top_space.obstacles.contains(Point(p2)):
            print(f"  WARNING: {net_name} sink {p2} is INSIDE Top Layer obstacle!")
            
    print(f"\nAnalyzing {len(net_demands)} failed nets via 3D Max-Flow...")
    
    analyzer = MaxFlowAnalyzer(skeletons, channel_widths, pcb.design_rules)
    res_std = analyzer.compute_feasibility(net_demands)
    
    print(f"Results for 3D Flow (All Signal Layers):")
    print(f"  Max Flow: {res_std.max_flow}")
    print(f"  Total Demand: {res_std.total_demand}")
    print(f"  Feasible? {res_std.is_feasible}")
    if not res_std.is_feasible:
        print(f"  Bottleneck identified at {len(res_std.min_cut_edges)} edges:")
        for u, v, cap in res_std.min_cut_edges[:5]:
            print(f"    Edge {u} -> {v}, Capacity: {cap}")
            
    # 5. Global Cut Analysis (Left to Right) - Multi-layer
    print(f"\nAnalyzing Global 3D Cut Capacity (X-direction):")
    F_global = nx.DiGraph()
    SOURCE = "GLOBAL_L"
    SINK = "GLOBAL_R"
    
    pitch = pcb.design_rules.default_trace_width_mm + pcb.design_rules.default_clearance_mm
    tw = pcb.design_rules.default_trace_width_mm
    
    # Combine all layers into one global flow graph
    for layer_name, skeleton in skeletons.items():
        widths = channel_widths[layer_name]
        nodes_x = [n[0] for n in skeleton.graph.nodes()]
        if not nodes_x: continue
        min_lx, max_lx = min(nodes_x), max(nodes_x)
        
        for u, v in skeleton.graph.edges():
            w = widths.edge_widths.get((u, v), widths.edge_widths.get((v, u), 0.0))
            capacity = int((w - tw) // pitch) + 1 if w >= tw else 0
            F_global.add_edge((layer_name, u), (layer_name, v), capacity=capacity)
            F_global.add_edge((layer_name, v), (layer_name, u), capacity=capacity)
        
        # Connect to global source/sink
        for n in skeleton.graph.nodes():
            if n[0] < min_lx + 5.0:
                F_global.add_edge(SOURCE, (layer_name, n), capacity=999)
            if n[0] > max_lx - 5.0:
                F_global.add_edge((layer_name, n), SINK, capacity=999)
    
    # Add interlayer vias for global cut
    layer_list = list(skeletons.keys())
    for i in range(len(layer_list)-1):
        l1, l2 = layer_list[i], layer_list[i+1]
        for n1 in skeletons[l1].graph.nodes():
            for n2 in skeletons[l2].graph.nodes():
                if math.sqrt((n1[0]-n2[0])**2 + (n1[1]-n2[1])**2) < 0.2:
                    F_global.add_edge((l1, n1), (l2, n2), capacity=100)
                    F_global.add_edge((l2, n2), (l1, n1), capacity=100)
    
    global_cut_val, _ = nx.minimum_cut(F_global, SOURCE, SINK)
    print(f"  Aggregate Max Flow (Left -> Right) across {len(skeletons)} layers: {global_cut_val} traces")

if __name__ == "__main__":
    analyze_temper_routability(Path("pre_routed_v5.kicad_pcb"))
