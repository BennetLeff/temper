#!/usr/bin/env python3
"""
Minimal via-aware integration test on real Temper board.

Tests via-aware routing on a subset of nets, exports to KiCad, runs DRC.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from kiutils.board import Board
from temper_placer.router_v6.stage0_data import ParsedPCB, DesignRules
from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter
from temper_placer.io.kicad_drc import run_drc
from temper_placer.io.kicad_writer import write_routes_to_pcb


def main():
    print("=" * 70)
    print(" VIA-AWARE INTEGRATION TEST - MINIMAL")
    print("=" * 70)
    
    pcb_path = Path("pcb/temper.kicad_pcb")
    output_path = Path("pcb/temper_via_test.kicad_pcb")
    drc_path = Path("pcb/temper_via_test_drc.json")
    
    # Parse board
    print("\n1. Parsing board...")
    board = Board.from_file(str(pcb_path))
    parsed_pcb = ParsedPCB.from_kicad_board(board)
    design_rules = DesignRules()
    
    print(f"   Components: {len(parsed_pcb.components)}")
    print(f"   Nets: {len(parsed_pcb.nets)}")
    
    # Create via-aware router
    print("\n2. Creating via-aware router...")
    router = ExactGeometryRouter(
        pcb=parsed_pcb,
        design_rules=design_rules,
        verbose=True,
        kicad_file=str(pcb_path)
    )
    
    print(f"   Via planner initialized: min spacing {router.via_planner.via_spec.min_spacing:.2f}mm")
    print(f"   Total vias: {router.via_planner.via_count}")
    
    # Get net pads (read from parsed_pcb)
    net_pads = {}
    for net_name, net_data in parsed_pcb.nets.items():
        if hasattr(net_data, 'pads'):
            net_pads[net_name] = net_data.pads
    
    # Test nets (simple 2-pad nets first)
    test_nets = [
        ('PWM_H', 'In1.Cu'),  # Power net, should work
        ('PWM_L', 'In1.Cu'),
        ('TEMP_SENSE', 'In1.Cu'),
    ]
    
    print("\n3. Routing test nets...")
    
    routes = {}
    for net_name, layer in test_nets:
        if net_name not in parsed_pcb.nets:
            print(f"   ⚠ {net_name}: Not found in PCB")
            continue
        
        # Get pad info from board
        pads_with_layers = []
        for fp in board.footprints:
            ref = fp.entryName if hasattr(fp, 'entryName') else str(fp.reference) if hasattr(fp, 'reference') else None
            if not ref:
                continue
            
            for pad in fp.pads:
                if not pad.net or pad.net.name != net_name:
                    continue
                
                # Get absolute position
                fp_x = fp.position.X if fp.position else 0
                fp_y = fp.position.Y if fp.position else 0
                pad_x = pad.position.X if pad.position else 0
                pad_y = pad.position.Y if pad.position else 0
                
                abs_x = fp_x + pad_x
                abs_y = fp_y + pad_y
                
                pads_with_layers.append((
                    (abs_x, abs_y),
                    list(pad.layers) if pad.layers else [],
                    ref,
                    pad.number or ""
                ))
        
        if len(pads_with_layers) < 2:
            print(f"   ⚠ {net_name}: Only {len(pads_with_layers)} pads")
            continue
        
        print(f"   Routing {net_name} on {layer} ({len(pads_with_layers)} pads)...")
        
        # Route with via-awareness
        route = router.route_net_with_vias(net_name, layer, pads_with_layers)
        
        if route:
            routes[net_name] = route
            print(f"     ✓ {len(route.segments)} segments, {len(route.vias)} vias")
        else:
            print(f"     ✗ Failed")
    
    print(f"\n   Routed: {len(routes)}/{len(test_nets)} nets")
    print(f"   Total vias placed: {router.via_planner.via_count}")
    
    # Export (use existing KiCad writer)
    print("\n4. Exporting to KiCad...")
    
    # Convert routes to SimpleTrace format for existing writer
    simple_traces = []
    simple_vias = []
    
    for net_name, route in routes.items():
        for seg in route.segments:
            simple_traces.append({
                'start': seg.start,
                'end': seg.end,
                'width': seg.width,
                'layer': seg.layer,
                'net': net_name
            })
        
        for via in route.vias:
            simple_vias.append({
                'position': via.position,
                'width': via.spec.diameter,
                'drill': via.spec.drill,
                'layers': via.layers,
                'net': net_name
            })
    
    print(f"   Exporting {len(simple_traces)} traces, {len(simple_vias)} vias...")
    
    # Use existing writer
    try:
        write_routes_to_pcb(
            template_pcb=pcb_path,
            output_pcb=output_path,
            routes=simple_traces,
            vias=simple_vias
        )
        print(f"   ✓ Exported to {output_path}")
    except Exception as e:
        print(f"   ✗ Export failed: {e}")
        return 1
    
    # Run DRC
    print("\n5. Running DRC...")
    
    try:
        run_drc(str(output_path), str(drc_path))
        
        with open(drc_path) as f:
            drc_data = json.load(f)
        
        violations = drc_data.get('violations', [])
        print(f"   Total violations: {len(violations)}")
        
        # Count via violations
        via_violations = 0
        for v in violations:
            desc = v.get('description', '').lower()
            if 'via' in desc:
                via_violations += 1
        
        print(f"   Via violations: {via_violations}")
        
        if via_violations == 0:
            print("\n" + "="*70)
            print(" ✓ SUCCESS: 0 VIA VIOLATIONS")
            print("="*70)
        else:
            print(f"\n⚠ {via_violations} via violations remain")
        
        return 0 if via_violations == 0 else 1
        
    except Exception as e:
        print(f"   ✗ DRC failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
