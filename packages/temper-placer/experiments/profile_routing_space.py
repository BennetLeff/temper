"""
Profile routing space computation to find remaining bottleneck.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("Profiling routing space computation...", flush=True)

temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

# Parse PCB
print("\n[1] Parsing PCB...", flush=True)
start = time.time()
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
pcb = parse_kicad_pcb_v6(temper_pcb)
print(f"    {time.time() - start:.2f}s", flush=True)

# Profile routing space internals
print("\n[2] Computing routing space (detailed)...", flush=True)

from temper_placer.router_v6.obstacle_map import build_obstacle_map

print("    Building obstacle map...", flush=True)
start = time.time()
obstacle_map = build_obstacle_map(pcb, escape_vias=[])
print(f"    {time.time() - start:.2f}s", flush=True)

# Check the obstacle map
print(f"\n    Obstacle map type: {type(obstacle_map)}", flush=True)
if hasattr(obstacle_map, 'geom_type'):
    print(f"    Geometry type: {obstacle_map.geom_type}", flush=True)
if hasattr(obstacle_map, 'bounds'):
    print(f"    Bounds: {obstacle_map.bounds}", flush=True)

# Profile routing space layers
from temper_placer.router_v6.routing_space import compute_routing_space

print("\n    Computing routing space per layer...", flush=True)
start = time.time()
routing_spaces = compute_routing_space(pcb, escape_vias=None)
print(f"    {time.time() - start:.2f}s", flush=True)

print("\n" + "=" * 50, flush=True)
print("SUMMARY", flush=True)
print("=" * 50, flush=True)
print("""
Routing space computation is slow because:
1. It builds obstacle polygons for each component
2. It performs union operations on many polygons
3. Shapely geometry operations are expensive for complex shapes

Options to speed up:
1. Cache obstacle map between iterations
2. Simplify component polygons
3. Use rasterized obstacle map instead of vector
4. Skip routing space entirely (use component positions only)
""", flush=True)
