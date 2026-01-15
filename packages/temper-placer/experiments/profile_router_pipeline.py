"""
Profile Router V6 Pipeline to identify bottlenecks.

This script profiles each stage of the router pipeline to find
where the slowness exists in the Benders integration.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("Router V6 Pipeline Profiling")
print("=" * 70)

# Find PCB file
temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

if not temper_pcb.exists():
    pcb_dir = Path(__file__).parent.parent.parent.parent / "pcb"
    pcb_files = list(pcb_dir.glob("*.kicad_pcb"))
    if pcb_files:
        temper_pcb = pcb_files[0]
    else:
        print("❌ No PCB files found")
        sys.exit(1)

print(f"\n📄 PCB: {temper_pcb.name}")

stages = {}

# ============================================================
# METHOD 1: Full Pipeline (current approach - SLOW)
# ============================================================
print("\n" + "=" * 70)
print("METHOD 1: Full Pipeline (current Benders integration)")
print("=" * 70)

start_full = time.time()
from temper_placer.router_v6.pipeline import RouterV6Pipeline

pipeline = RouterV6Pipeline(
    verbose=False,
    enable_routability_analysis=False,
)

# This is what Benders currently calls
result = pipeline.run(temper_pcb)
full_time = time.time() - start_full

print(f"  Total time: {full_time:.2f}s")
print(f"  Components: {len(result.pcb.components)}")
print(f"  Layers: {len(result.stage2.skeletons)}")

stages["Full Pipeline"] = full_time

# ============================================================
# METHOD 2: Stage-by-stage (to find bottleneck)
# ============================================================
print("\n" + "=" * 70)
print("METHOD 2: Stage-by-Stage Profiling")
print("=" * 70)

# Stage 0: Parse PCB
print("\nStage 0: Parse PCB...")
start = time.time()
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
pcb = parse_kicad_pcb_v6(temper_pcb)
stages["0: Parse PCB"] = time.time() - start
print(f"  ⏱️  {stages['0: Parse PCB']:.2f}s - {len(pcb.components)} components, {len(pcb.nets)} nets")

# Stage 1: Escape Vias
print("\nStage 1: Escape Vias...")
start = time.time()
from temper_placer.router_v6.escape_via_generator import generate_escape_vias
escape_vias = generate_escape_vias(pcb, pcb.design_rules)
stages["1: Escape Vias"] = time.time() - start
print(f"  ⏱️  {stages['1: Escape Vias']:.2f}s - {len(escape_vias)} vias")

# Stage 2a: Routing Space
print("\nStage 2a: Routing Space...")
start = time.time()
from temper_placer.router_v6.routing_space import compute_routing_space
routing_spaces = {}
for layer in ["F.Cu", "B.Cu"]:
    routing_spaces[layer] = compute_routing_space(pcb, layer)
stages["2a: Routing Space"] = time.time() - start
print(f"  ⏱️  {stages['2a: Routing Space']:.2f}s")

# Stage 2b: Channel Skeleton
print("\nStage 2b: Channel Skeleton...")
start = time.time()
from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
skeletons = {}
for layer in ["F.Cu", "B.Cu"]:
    skeletons[layer] = extract_channel_skeleton(routing_spaces[layer])
stages["2b: Channel Skeleton"] = time.time() - start
print(f"  ⏱️  {stages['2b: Channel Skeleton']:.2f}s")
for layer, skel in skeletons.items():
    print(f"      {layer}: {skel.graph.number_of_nodes()} nodes, {skel.graph.number_of_edges()} edges")

# Stage 2c: Channel Widths
print("\nStage 2c: Channel Widths...")
start = time.time()
from temper_placer.router_v6.channel_widths import compute_channel_widths
channel_widths = {}
for layer in ["F.Cu", "B.Cu"]:
    channel_widths[layer] = compute_channel_widths(skeletons[layer], routing_spaces[layer])
stages["2c: Channel Widths"] = time.time() - start
print(f"  ⏱️  {stages['2c: Channel Widths']:.2f}s")

# Stage 2d: Occupancy Grid (optional for Max-Flow)
print("\nStage 2d: Occupancy Grid...")
start = time.time()
from temper_placer.router_v6.occupancy_grid import build_occupancy_grid
occupancy_grids = {}
for layer in ["F.Cu", "B.Cu"]:
    occupancy_grids[layer] = build_occupancy_grid(pcb, layer, resolution=0.5)
stages["2d: Occupancy Grid"] = time.time() - start
print(f"  ⏱️  {stages['2d: Occupancy Grid']:.2f}s")

# Stage 2e: Layer Capacity
print("\nStage 2e: Layer Capacity...")
start = time.time()
from temper_placer.router_v6.layer_capacity import calculate_layer_capacity
layer_capacities = {}
for layer in ["F.Cu", "B.Cu"]:
    layer_capacities[layer] = calculate_layer_capacity(
        skeletons[layer], channel_widths[layer], pcb.design_rules
    )
stages["2e: Layer Capacity"] = time.time() - start
print(f"  ⏱️  {stages['2e: Layer Capacity']:.2f}s")

# Stage 2f: Routing Demand
print("\nStage 2f: Routing Demand...")
start = time.time()
from temper_placer.router_v6.routing_demand import estimate_routing_demand
routing_demand = estimate_routing_demand(pcb, skeletons)
stages["2f: Routing Demand"] = time.time() - start
print(f"  ⏱️  {stages['2f: Routing Demand']:.2f}s")

# Stage 2g: Bottleneck Analysis
print("\nStage 2g: Bottleneck Analysis...")
start = time.time()
from temper_placer.router_v6.bottleneck_analysis import identify_bottlenecks
bottleneck_analysis = identify_bottlenecks(layer_capacities, routing_demand)
stages["2g: Bottleneck Analysis"] = time.time() - start
print(f"  ⏱️  {stages['2g: Bottleneck Analysis']:.2f}s")

# Stage 3: Topological Routing (NOT needed for Benders!)
print("\nStage 3: Topological Routing (NOT NEEDED FOR BENDERS)...")
start = time.time()
from temper_placer.router_v6.constraint_model import ModelBuilder
model_builder = ModelBuilder(pcb, skeletons, channel_widths)
constraint_model = model_builder.build()
stages["3a: Constraint Model"] = time.time() - start
print(f"  ⏱️  3a Constraint Model: {stages['3a: Constraint Model']:.2f}s")

start = time.time()
from temper_placer.router_v6.sat_model import build_sat_model
sat_model = build_sat_model(constraint_model)
stages["3b: SAT Model"] = time.time() - start
print(f"  ⏱️  3b SAT Model: {stages['3b: SAT Model']:.2f}s")

print("\n  ⏳ Stage 3c: Topology Solver (may take a while)...")
start = time.time()
from temper_placer.router_v6.topology_solver import solve_topology
solution = solve_topology(sat_model, timeout_sec=60)
stages["3c: Topology Solver"] = time.time() - start
print(f"  ⏱️  3c Topology Solver: {stages['3c: Topology Solver']:.2f}s")

# Stage 4: Geometric Realization (NOT needed for Benders!)
print("\nStage 4: Geometric Realization (NOT NEEDED FOR BENDERS)...")
if solution and solution.status == "SAT":
    start = time.time()
    from temper_placer.router_v6.topology_extraction import extract_topology_solution
    topology = extract_topology_solution(solution, constraint_model)
    stages["4a: Extract Topology"] = time.time() - start
    print(f"  ⏱️  4a Extract Topology: {stages['4a: Extract Topology']:.2f}s")
    
    start = time.time()
    from temper_placer.router_v6.channel_mapping import map_topology_to_channels
    channel_mapping = map_topology_to_channels(topology, skeletons)
    stages["4b: Channel Mapping"] = time.time() - start
    print(f"  ⏱️  4b Channel Mapping: {stages['4b: Channel Mapping']:.2f}s")
    
    start = time.time()
    from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding
    paths = run_astar_pathfinding(channel_mapping, occupancy_grids, pcb.design_rules)
    stages["4c: A* Pathfinding"] = time.time() - start
    print(f"  ⏱️  4c A* Pathfinding: {stages['4c: A* Pathfinding']:.2f}s")
else:
    print("  ⚠️  Skipping Stage 4 - topology solver didn't return SAT")
    stages["4a: Extract Topology"] = 0
    stages["4b: Channel Mapping"] = 0
    stages["4c: A* Pathfinding"] = 0

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("TIMING SUMMARY")
print("=" * 70)

# Calculate totals
stage2_total = sum(v for k, v in stages.items() if k.startswith("2"))
stage3_total = sum(v for k, v in stages.items() if k.startswith("3"))
stage4_total = sum(v for k, v in stages.items() if k.startswith("4"))
benders_needed = stages.get("0: Parse PCB", 0) + stage2_total

total_staged = sum(v for k, v in stages.items() if k != "Full Pipeline")

print(f"\n{'Stage':<30} {'Time (s)':>10} {'%':>8}")
print("-" * 50)

# Sort by time descending (exclude full pipeline)
sorted_stages = sorted(
    [(k, v) for k, v in stages.items() if k != "Full Pipeline"],
    key=lambda x: -x[1]
)

for stage, elapsed in sorted_stages:
    if total_staged > 0:
        pct = (elapsed / total_staged) * 100
    else:
        pct = 0
    bar = "█" * int(pct / 2)
    print(f"{stage:<30} {elapsed:>10.2f} {pct:>7.1f}% {bar}")

print("-" * 50)
print(f"{'Stage 2 (Channel Analysis)':<30} {stage2_total:>10.2f}")
print(f"{'Stage 3 (Topology - SKIP)':<30} {stage3_total:>10.2f}")
print(f"{'Stage 4 (Geometry - SKIP)':<30} {stage4_total:>10.2f}")
print("-" * 50)
print(f"{'TOTAL (staged)':<30} {total_staged:>10.2f}")
print(f"{'Full pipeline (comparison)':<30} {full_time:>10.2f}")

print("\n" + "=" * 70)
print("ANALYSIS FOR BENDERS OPTIMIZATION")
print("=" * 70)

print(f"""
What Benders ACTUALLY needs:
- Stage 0: Parse PCB         {stages.get('0: Parse PCB', 0):.2f}s
- Stage 2: Channel Analysis  {stage2_total:.2f}s
- TOTAL:                     {benders_needed:.2f}s

What current integration runs:
- Full pipeline:             {full_time:.2f}s
- Stage 3 (topology):        {stage3_total:.2f}s  ❌ NOT NEEDED
- Stage 4 (geometry):        {stage4_total:.2f}s  ❌ NOT NEEDED

🚀 Potential Speedup: {full_time / max(benders_needed, 0.01):.1f}x
   By skipping Stages 3 & 4

""")

print("=" * 70)
print("RECOMMENDATION")
print("=" * 70)

print("""
Create a lightweight function that ONLY runs:
1. Stage 0: Parse PCB
2. Stage 2: Channel extraction

Skip:
- Stage 1: Escape vias (not needed for Max-Flow)
- Stage 3: Topology solver (SAT solving - SLOW)
- Stage 4: Geometric realization (A* pathfinding)

Expected time: ~{:.1f}s (vs {:.1f}s current)
""".format(benders_needed, full_time))
