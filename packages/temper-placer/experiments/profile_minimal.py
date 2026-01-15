"""
Minimal profiling - step by step with immediate output.
"""

import sys
import time
from pathlib import Path

# Force unbuffered output
sys.stdout = sys.stderr

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("Starting profiling...", flush=True)

temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"
print(f"PCB: {temper_pcb.name}", flush=True)

# Stage 0: Parse PCB
print("\n[1/5] Parsing PCB...", flush=True)
start = time.time()
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
pcb = parse_kicad_pcb_v6(temper_pcb)
t_parse = time.time() - start
print(f"    Done: {t_parse:.2f}s - {len(pcb.components)} components", flush=True)

# Stage 2a: Routing Space
print("\n[2/5] Computing routing space...", flush=True)
start = time.time()
from temper_placer.router_v6.routing_space import compute_routing_space
routing_spaces = compute_routing_space(pcb, escape_vias=None)
t_routing = time.time() - start
print(f"    Done: {t_routing:.2f}s - {len(routing_spaces)} layers", flush=True)

# Stage 2b: Channel Skeleton
print("\n[3/5] Extracting channel skeletons...", flush=True)
start = time.time()
from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
skeletons = {}
for layer_name, rs in routing_spaces.items():
    print(f"    Processing {layer_name}...", flush=True)
    skeletons[layer_name] = extract_channel_skeleton(rs)
    print(f"      {skeletons[layer_name].graph.number_of_nodes()} nodes", flush=True)
t_skeleton = time.time() - start
print(f"    Done: {t_skeleton:.2f}s", flush=True)

# Stage 2c: Channel Widths
print("\n[4/5] Computing channel widths...", flush=True)
start = time.time()
from temper_placer.router_v6.channel_widths import compute_channel_widths
channel_widths = {}
for layer_name in routing_spaces.keys():
    print(f"    Processing {layer_name}...", flush=True)
    channel_widths[layer_name] = compute_channel_widths(skeletons[layer_name], routing_spaces[layer_name])
t_widths = time.time() - start
print(f"    Done: {t_widths:.2f}s", flush=True)

# Stage 2e: Layer Capacity
print("\n[5/5] Calculating layer capacity...", flush=True)
start = time.time()
from temper_placer.router_v6.layer_capacity import calculate_layer_capacity
layer_capacities = {}
for layer_name in routing_spaces.keys():
    print(f"    Processing {layer_name}...", flush=True)
    layer_capacities[layer_name] = calculate_layer_capacity(
        skeletons[layer_name], channel_widths[layer_name], pcb.design_rules
    )
t_capacity = time.time() - start
print(f"    Done: {t_capacity:.2f}s", flush=True)

# Summary
total = t_parse + t_routing + t_skeleton + t_widths + t_capacity
print("\n" + "=" * 50, flush=True)
print("SUMMARY", flush=True)
print("=" * 50, flush=True)
print(f"Parse PCB:        {t_parse:.2f}s", flush=True)
print(f"Routing Space:    {t_routing:.2f}s", flush=True)
print(f"Channel Skeleton: {t_skeleton:.2f}s", flush=True)
print(f"Channel Widths:   {t_widths:.2f}s", flush=True)
print(f"Layer Capacity:   {t_capacity:.2f}s", flush=True)
print("-" * 50, flush=True)
print(f"TOTAL:            {total:.2f}s", flush=True)
print("\nThis is what Benders needs (without Stage 3/4)!", flush=True)
