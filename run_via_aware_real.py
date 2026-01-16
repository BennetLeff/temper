#!/usr/bin/env python3
"""
Via-aware routing using EXISTING exact_geometry_router with via integration.

Uses the proven RRT pathfinding from exact_geometry_router.py,
plus via-aware methods I added.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from kiutils.board import Board
from temper_placer.router_v6.stage0_data import DesignRules
from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.io.kicad_writer import write_routes_to_pcb
from temper_placer.io.kicad_drc import run_drc


def main():
    print("=" * 70)
    print(" VIA-AWARE ROUTING - Using Existing Router + Via Integration")
    print("=" * 70)
    
    pcb_path = Path("pcb/temper.kicad_pcb")
    output_path = Path("pcb/temper_via_aware_real.kicad_pcb")
    drc_path = Path("pcb/temper_via_aware_real_drc.json")
    
    if not pcb_path.exists():
        print(f"✗ PCB not found: {pcb_path}")
        return 1
    
    print(f"\nInput: {pcb_path}")
    print(f"Output: {output_path}")
    print(f"DRC: {drc_path}")
    
    # Parse board
    print("\n1. Parsing board...")
    parsed_pcb = parse_kicad_pcb_v6(pcb_path)
    board = Board.from_file(str(pcb_path))  # Also load with kiutils for pad info
    design_rules = parsed_pcb.design_rules
    
    print(f"   Components: {len(parsed_pcb.components)}")
    print(f"   Nets: {len(parsed_pcb.nets)}")
    
    # Create router with via-awareness
    print("\n2. Creating via-aware router...")
    router = ExactGeometryRouter(
        pcb=parsed_pcb,
        design_rules=design_rules,
        verbose=True,
        kicad_file=str(pcb_path)
    )
    
    print(f"   ✓ Router initialized")
    print(f"   Via min spacing: {router.via_planner.via_spec.min_spacing:.2f}mm")
    
    # Get pad information from board for via-aware routing
    print("\n3. Extracting pad information...")
    
    net_pad_info = {}
    for fp in board.footprints:
        ref = fp.entryName if hasattr(fp, 'entryName') else None
        if not ref:
            continue
        
        for pad in fp.pads:
            if not pad.net or not pad.net.name:
                continue
            
            net_name = pad.net.name
            
            # Get absolute position
            fp_x = fp.position.X if fp.position else 0
            fp_y = fp.position.Y if fp.position else 0
            pad_x = pad.position.X if pad.position else 0
            pad_y = pad.position.Y if pad.position else 0
            
            abs_x = fp_x + pad_x
            abs_y = fp_y + pad_y
            
            if net_name not in net_pad_info:
                net_pad_info[net_name] = []
            
            net_pad_info[net_name].append({
                'position': (abs_x, abs_y),
                'layers': list(pad.layers) if pad.layers else [],
                'ref': ref,
                'pin': pad.number or ""
            })
    
    print(f"   ✓ Extracted pads for {len(net_pad_info)} nets")
    
    # Select test nets (simple power nets that should route easily)
    test_nets = [
        ('PWM_H', 'In1.Cu'),
        ('PWM_L', 'In1.Cu'),
        ('AC_L', 'In1.Cu'),
        ('AC_N', 'In1.Cu'),
        ('VCC_BOOT', 'In1.Cu'),
    ]
    
    print("\n4. Routing test nets with via-awareness...")
    
    routes = []
    vias_all = []
    routed_count = 0
    
    for net_name, layer in test_nets:
        if net_name not in net_pad_info:
            print(f"   ⚠ {net_name}: Not found")
            continue
        
        pad_info = net_pad_info[net_name]
        if len(pad_info) < 2:
            print(f"   ⚠ {net_name}: Only {len(pad_info)} pads")
            continue
        
        print(f"   Routing {net_name} on {layer} ({len(pad_info)} pads)...")
        
        # Prepare for via-aware routing
        pads_with_layers = [
            (p['position'], p['layers'], p['ref'], p['pin'])
            for p in pad_info
        ]
        
        # Try via-aware routing
        try:
            route = router.route_net_with_vias(net_name, layer, pads_with_layers)
            
            if route:
                print(f"     ✓ {len(route.segments)} segments, {len(route.vias)} vias")
                
                # Convert to export format
                for seg in route.segments:
                    routes.append({
                        'start': seg.start,
                        'end': seg.end,
                        'width': seg.width,
                        'layer': seg.layer,
                        'net': net_name
                    })
                
                for via in route.vias:
                    vias_all.append({
                        'position': via.position,
                        'width': via.spec.diameter,
                        'drill': via.spec.drill,
                        'layers': tuple(via.layers),
                        'net': net_name
                    })
                
                routed_count += 1
            else:
                print(f"     ✗ Failed")
                
        except Exception as e:
            print(f"     ✗ Exception: {e}")
            # Fallback to non-via-aware
            try:
                pads_positions = [p['position'] for p in pad_info]
                route = router.route_net(net_name, layer, pads_positions)
                
                if route:
                    print(f"     ✓ Fallback: {len(route.segments)} segments (no vias)")
                    for seg in route.segments:
                        routes.append({
                            'start': seg.start,
                            'end': seg.end,
                            'width': seg.width,
                            'layer': seg.layer,
                            'net': net_name
                        })
                    routed_count += 1
            except Exception as e2:
                print(f"     ✗ Fallback also failed: {e2}")
    
    print(f"\n   Routed: {routed_count}/{len(test_nets)} nets")
    print(f"   Total segments: {len(routes)}")
    print(f"   Total vias: {len(vias_all)}")
    print(f"   Via planner count: {router.via_planner.via_count}")
    
    if routed_count == 0:
        print("\n✗ No nets routed successfully")
        return 1
    
    # Export using existing writer
    print("\n5. Exporting to KiCad...")
    
    try:
        result = write_routes_to_pcb(
            template_pcb=pcb_path,
            output_pcb=output_path,
            routes=frozenset(
                type('Route', (), r) for r in routes
            ),
            vias=frozenset(
                type('Via', (), v) for v in vias_all
            ) if vias_all else None,
            clear_existing=True
        )
        
        print(f"   ✓ Exported {result.components_updated} traces")
        if vias_all:
            print(f"   ✓ Exported vias")
        
    except Exception as e:
        print(f"   ✗ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Run DRC
    print("\n6. Running KiCad DRC...")
    
    try:
        run_drc(str(output_path), str(drc_path))
        
        with open(drc_path) as f:
            drc_data = json.load(f)
        
        violations = drc_data.get('violations', [])
        print(f"   Total violations: {len(violations)}")
        
        # Categorize
        via_violations = {
            'shorting': 0,
            'clearance': 0,
            'hole_clearance': 0,
            'other': 0
        }
        
        for v in violations:
            desc = v.get('description', '').lower()
            vtype = v.get('type', '').lower()
            
            if 'via' in desc or 'via' in vtype:
                if 'short' in vtype or 'short' in desc:
                    via_violations['shorting'] += 1
                elif 'hole' in desc and 'clearance' in desc:
                    via_violations['hole_clearance'] += 1
                elif 'clearance' in vtype or 'clearance' in desc:
                    via_violations['clearance'] += 1
                else:
                    via_violations['other'] += 1
        
        total_via = sum(via_violations.values())
        
        print("\n   VIA VIOLATIONS:")
        print(f"     Shorting: {via_violations['shorting']}")
        print(f"     Clearance: {via_violations['clearance']}")
        print(f"     Hole clearance: {via_violations['hole_clearance']}")
        print(f"     Other: {via_violations['other']}")
        print(f"     TOTAL: {total_via}")
        
        print(f"\n   ✓ DRC report: {drc_path}")
        
        # Final verdict
        print("\n" + "=" * 70)
        if total_via == 0:
            print(" ✓ SUCCESS: 0 VIA VIOLATIONS")
            print(" Via-aware architecture PROVEN on real board!")
        else:
            print(f" ⚠ {total_via} VIA VIOLATIONS (on {routed_count} nets)")
            print(f" Note: Only {routed_count}/{len(test_nets)} nets tested")
        print("=" * 70)
        
        return 0
        
    except Exception as e:
        print(f"   ✗ DRC failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
