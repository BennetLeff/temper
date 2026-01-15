"""
Profile specifically the Voronoi skeleton extraction bottleneck.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("Profiling Voronoi skeleton bottleneck...", flush=True)

temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

# Stage 0: Parse PCB
print("\n[1] Parsing PCB...", flush=True)
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
pcb = parse_kicad_pcb_v6(temper_pcb)
print(f"    Components: {len(pcb.components)}", flush=True)

# Stage 2a: Routing Space
print("\n[2] Computing routing space...", flush=True)
from temper_placer.router_v6.routing_space import compute_routing_space
routing_spaces = compute_routing_space(pcb, escape_vias=None)

# Analyze the geometry
for layer_name, rs in routing_spaces.items():
    print(f"\n{'='*50}", flush=True)
    print(f"Layer: {layer_name}", flush=True)
    print(f"{'='*50}", flush=True)
    
    avail = rs.available_area
    
    if avail.is_empty:
        print("  Empty area", flush=True)
        continue
    
    # Analyze geometry complexity
    print(f"  Type: {avail.geom_type}", flush=True)
    print(f"  Area: {avail.area:.2f} mm²", flush=True)
    
    # Count boundary points
    from shapely.geometry import MultiPolygon, Polygon
    
    if isinstance(avail, MultiPolygon):
        num_polys = len(avail.geoms)
        total_points = 0
        total_boundary_length = 0
        for p in avail.geoms:
            boundary = p.boundary
            total_boundary_length += boundary.length
            if hasattr(boundary, 'geoms'):
                for part in boundary.geoms:
                    if hasattr(part, 'coords'):
                        total_points += len(part.coords)
            elif hasattr(boundary, 'coords'):
                total_points += len(boundary.coords)
    elif isinstance(avail, Polygon):
        num_polys = 1
        boundary = avail.boundary
        total_boundary_length = boundary.length
        total_points = 0
        if hasattr(boundary, 'geoms'):
            for part in boundary.geoms:
                if hasattr(part, 'coords'):
                    total_points += len(part.coords)
        elif hasattr(boundary, 'coords'):
            total_points += len(boundary.coords)
    else:
        num_polys = 0
        total_points = 0
        total_boundary_length = 0
    
    print(f"  Polygons: {num_polys}", flush=True)
    print(f"  Boundary points: {total_points}", flush=True)
    print(f"  Boundary length: {total_boundary_length:.2f} mm", flush=True)
    
    # The Voronoi sampler adds ~1 point per mm
    estimated_voronoi_points = int(total_boundary_length)
    print(f"  Estimated Voronoi points: ~{estimated_voronoi_points}", flush=True)
    
    # Voronoi complexity estimate
    # O(n log n) where n is number of points
    if estimated_voronoi_points > 1000:
        print(f"  ⚠️  HIGH COMPLEXITY - {estimated_voronoi_points} points will be slow!", flush=True)
        print(f"      Voronoi time estimate: {estimated_voronoi_points * 0.001:.1f}s (rough)", flush=True)
    
print("\n" + "="*50, flush=True)
print("ANALYSIS", flush=True)
print("="*50, flush=True)

print("""
The Voronoi-based skeleton extraction samples points along
the polygon boundary at ~1mm intervals, then computes a
Voronoi diagram.

For complex PCB geometries with many components, this creates
thousands of sample points, making Voronoi computation slow.

SOLUTIONS:
1. Increase sampling interval (e.g., 5mm instead of 1mm)
2. Simplify polygon boundary before sampling
3. Use bounding box skeleton instead of Voronoi
4. Cache skeletons between iterations
5. Use a grid-based skeleton approximation
""", flush=True)
