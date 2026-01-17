#!/usr/bin/env python3
"""
Route board using RouterV6Pipeline and export to KiCad.
"""

import sys
from pathlib import Path

sys.path.insert(0, 'packages/temper-placer/src')

from temper_placer.router_v6.pipeline import RouterV6Pipeline
from temper_placer.io.kicad_writer import write_routes_direct
from temper_placer.io.kicad_drc import run_drc


def main():
    pcb_path = Path('pcb/temper.kicad_pcb')
    output_path = Path('pcb/temper_routed.kicad_pcb')
    drc_path = Path('pcb/temper_routed_drc.json')
    
    print("=" * 70)
    print(" Route Board with RouterV6Pipeline")
    print("=" * 70)
    
    # Run the router
    print("\n1. Running RouterV6Pipeline...")
    pipeline = RouterV6Pipeline(verbose=True)
    result = pipeline.run(pcb_path)
    
    if not result.stage4:
        print("ERROR: Stage 4 (routing) failed")
        return 1
    
    pathfinding = result.stage4.pathfinding_result
    print(f"\n   Routed: {pathfinding.success_count}")
    print(f"   Failed: {pathfinding.failure_count}")
    
    # Extract routes from pathfinding result
    print("\n2. Extracting routes...")
    routes = []
    vias = []
    
    # Get trace width from design rules (default 0.25mm)
    default_width = 0.25
    
    for net_name, path in pathfinding.routed_paths.items():
        # Handle both RoutePath and RoutePath3D
        if hasattr(path, 'layer_name'):
            # RoutePath - single layer
            layer = path.layer_name
            coords = path.coordinates
            
            if not coords or len(coords) < 2:
                continue
            
            # Convert coordinate list to segments
            for i in range(len(coords) - 1):
                start = coords[i]
                end = coords[i + 1]
                
                # Skip zero-length segments
                if abs(start[0] - end[0]) < 0.001 and abs(start[1] - end[1]) < 0.001:
                    continue
                
                routes.append({
                    'start': (start[0], start[1]),
                    'end': (end[0], end[1]),
                    'width': default_width,
                    'layer': layer,
                    'net': net_name
                })
        elif hasattr(path, 'segments'):
            # RoutePath3D - multi-layer with segments
            for seg in path.segments:
                if hasattr(seg, 'start') and hasattr(seg, 'end'):
                    routes.append({
                        'start': (seg.start[0], seg.start[1]),
                        'end': (seg.end[0], seg.end[1]),
                        'width': getattr(seg, 'width', default_width),
                        'layer': getattr(seg, 'layer', 'F.Cu'),
                        'net': net_name
                    })
            # Also extract vias
            if hasattr(path, 'vias'):
                for via in path.vias:
                    vias.append({
                        'position': via.position if hasattr(via, 'position') else via,
                        'width': getattr(via, 'diameter', 0.6),
                        'drill': getattr(via, 'drill', 0.3),
                        'layers': getattr(via, 'layers', ('F.Cu', 'B.Cu')),
                        'net': net_name
                    })
        elif hasattr(path, 'path') and path.path:
            # Grid-based path
            coords = path.path
            layer = getattr(path, 'layer', 'F.Cu')
            for i in range(len(coords) - 1):
                start = coords[i]
                end = coords[i + 1]
                if abs(start[0] - end[0]) < 0.001 and abs(start[1] - end[1]) < 0.001:
                    continue
                routes.append({
                    'start': (start[0], start[1]),
                    'end': (end[0], end[1]),
                    'width': default_width,
                    'layer': layer,
                    'net': net_name
                })
    
    print(f"   Extracted {len(routes)} segments from {len(pathfinding.routed_paths)} nets")
    
    if len(routes) == 0:
        print("\n   ERROR: No routes extracted!")
        return 1
    
    # Write routes to output file
    print(f"\n3. Writing to {output_path}...")
    write_routes_direct(
        template_pcb=pcb_path,
        output_pcb=output_path,
        routes=routes,
        vias=vias
    )
    print(f"   ✓ Written {len(routes)} segments, {len(vias)} vias")
    
    # Run DRC
    print(f"\n4. Running DRC...")
    drc_result = run_drc(str(output_path), str(drc_path))
    print(f"   Total violations: {len(drc_result.violations)}")
    
    # Categorize
    by_type = {}
    for v in drc_result.violations:
        t = v.type
        by_type[t] = by_type.get(t, 0) + 1
    
    print("\n   By type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1])[:10]:
        print(f"     {t}: {count}")
    
    # Count routing-related
    routing_types = ['shorting_items', 'clearance', 'tracks_crossing', 'hole_clearance', 'hole_to_hole']
    routing_count = sum(by_type.get(t, 0) for t in routing_types)
    print(f"\n   Routing-related: {routing_count}")
    
    print("\n" + "=" * 70)
    if routing_count == 0:
        print(" ✓ SUCCESS: No routing violations!")
    else:
        print(f" ⚠ {routing_count} routing violations")
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
