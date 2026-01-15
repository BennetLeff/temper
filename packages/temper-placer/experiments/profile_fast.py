"""
Fast profiling script - identifies where time is being spent.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("FAST Router Pipeline Profiling (Stages 0-2 only)")
print("=" * 70)

temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"
if not temper_pcb.exists():
    print(f"❌ PCB not found: {temper_pcb}")
    sys.exit(1)

print(f"\n📄 PCB: {temper_pcb.name}")

stages = {}
total_start = time.time()

# Stage 0: Parse PCB
print("\n📍 Stage 0: Parse PCB...")
start = time.time()
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
pcb = parse_kicad_pcb_v6(temper_pcb)
stages["Stage 0: Parse PCB"] = time.time() - start
print(f"   ⏱️  {stages['Stage 0: Parse PCB']:.2f}s")
print(f"   Components: {len(pcb.components)}, Nets: {len(pcb.nets)}")

# Stage 2a: Routing Space
print("\n📍 Stage 2a: Routing Space...")
start = time.time()
from temper_placer.router_v6.routing_space import compute_routing_space
# compute_routing_space returns dict[layer_name, RoutingSpace]
routing_spaces = compute_routing_space(pcb, escape_vias=None)
stages["Stage 2a: Routing Space"] = time.time() - start
print(f"   ⏱️  {stages['Stage 2a: Routing Space']:.2f}s")
print(f"   Layers: {list(routing_spaces.keys())}")

# Stage 2b: Channel Skeleton
print("\n📍 Stage 2b: Channel Skeleton...")
start = time.time()
from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
skeletons = {}
for layer_name, rs in routing_spaces.items():
    skeletons[layer_name] = extract_channel_skeleton(rs)
stages["Stage 2b: Channel Skeleton"] = time.time() - start
print(f"   ⏱️  {stages['Stage 2b: Channel Skeleton']:.2f}s")
for layer, skel in skeletons.items():
    print(f"      {layer}: {skel.graph.number_of_nodes()} nodes, {skel.graph.number_of_edges()} edges")

# Stage 2c: Channel Widths
print("\n📍 Stage 2c: Channel Widths...")
start = time.time()
from temper_placer.router_v6.channel_widths import compute_channel_widths
channel_widths = {}
for layer_name in routing_spaces.keys():
    channel_widths[layer_name] = compute_channel_widths(skeletons[layer_name], routing_spaces[layer_name])
stages["Stage 2c: Channel Widths"] = time.time() - start
print(f"   ⏱️  {stages['Stage 2c: Channel Widths']:.2f}s")

# Stage 2d: Occupancy Grid
print("\n📍 Stage 2d: Occupancy Grid...")
start = time.time()
from temper_placer.router_v6.occupancy_grid import build_occupancy_grid
occupancy_grids = {}
for layer_name in routing_spaces.keys():
    occupancy_grids[layer_name] = build_occupancy_grid(pcb, layer_name, resolution=0.5)
stages["Stage 2d: Occupancy Grid"] = time.time() - start
print(f"   ⏱️  {stages['Stage 2d: Occupancy Grid']:.2f}s")

# Stage 2e: Layer Capacity
print("\n📍 Stage 2e: Layer Capacity...")
start = time.time()
from temper_placer.router_v6.layer_capacity import calculate_layer_capacity
layer_capacities = {}
for layer_name in routing_spaces.keys():
    layer_capacities[layer_name] = calculate_layer_capacity(
        skeletons[layer_name], channel_widths[layer_name], pcb.design_rules
    )
stages["Stage 2e: Layer Capacity"] = time.time() - start
print(f"   ⏱️  {stages['Stage 2e: Layer Capacity']:.2f}s")

# Stage 2f: Routing Demand
print("\n📍 Stage 2f: Routing Demand...")
start = time.time()
from temper_placer.router_v6.routing_demand import estimate_routing_demand
routing_demand = estimate_routing_demand(pcb, skeletons)
stages["Stage 2f: Routing Demand"] = time.time() - start
print(f"   ⏱️  {stages['Stage 2f: Routing Demand']:.2f}s")

# Stage 2g: Bottleneck Analysis
print("\n📍 Stage 2g: Bottleneck Analysis...")
start = time.time()
from temper_placer.router_v6.bottleneck_analysis import identify_bottlenecks
bottleneck_analysis = identify_bottlenecks(layer_capacities, routing_demand)
stages["Stage 2g: Bottleneck Analysis"] = time.time() - start
print(f"   ⏱️  {stages['Stage 2g: Bottleneck Analysis']:.2f}s")

total_time = time.time() - total_start

# Summary
print("\n" + "=" * 70)
print("SUMMARY (What Benders NEEDS)")
print("=" * 70)

print(f"\n{'Stage':<30} {'Time (s)':>10}")
print("-" * 42)
for stage, elapsed in sorted(stages.items(), key=lambda x: -x[1]):
    pct = (elapsed / total_time) * 100
    bar = "█" * int(pct / 2)
    print(f"{stage:<30} {elapsed:>10.2f}  {bar}")
print("-" * 42)
print(f"{'TOTAL':<30} {total_time:>10.2f}")

print(f"""
✅ This is all Benders needs for Max-Flow analysis!
   Time: {total_time:.2f}s

❌ Current integration runs the FULL pipeline:
   - Stage 3: Topology Solver (SAT) - SLOW
   - Stage 4: Geometric Realization (A*) - SLOW
   
   These add 50-100+ seconds and are NOT NEEDED!
""")
