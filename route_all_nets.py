#!/usr/bin/env python3
"""
Route ALL 16 signal nets with via-aware router.
Test production readiness.
"""

import sys
from pathlib import Path

sys.path.insert(0, 'packages/temper-placer/src')

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter
from temper_placer.io.kicad_writer import write_routes_to_pcb
from temper_placer.io.kicad_drc import run_drc
from kiutils.board import Board
import signal


def timeout_handler(signum, frame):
    raise TimeoutError("Routing timed out")


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")
    output_path = Path("pcb/temper_all_nets_routed.kicad_pcb")
    drc_path = Path("pcb/temper_all_nets_drc.json")
    
    print("=" * 70)
    print(" PRODUCTION TEST: Route All 16 Signal Nets")
    print("=" * 70)
    print(f"\nInput: {pcb_path}")
    print(f"Output: {output_path}")
    print(f"DRC: {drc_path}")
    
    # Parse board
    print("\n1. Parsing board...")
    board = Board.from_file(str(pcb_path))
    parsed_pcb = parse_kicad_pcb_v6(pcb_path)
    design_rules = parsed_pcb.design_rules
    
    print(f"   Components: {len(parsed_pcb.components)}")
    print(f"   Nets: {len(parsed_pcb.nets)}")
    
    # Create router
    print("\n2. Creating via-aware router...")
    router = ExactGeometryRouter(
        pcb=parsed_pcb,
        design_rules=design_rules,
        verbose=False,  # Disable verbose for production run
        kicad_file=str(pcb_path)
    )
    print(f"   ✓ Router initialized")
    
    # Extract pad info
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
    
    # Signal nets to route
    signal_nets = [
        'AC_L', 'AC_N', 'GATE_H', 'SW_NODE', 'GATE_L', 
        'PWM_H', 'PWM_L', 'SHUTDOWN_N', 'I_SENSE', 
        'SPI_CLK', 'SPI_MOSI', 'SPI_MISO', 'SPI_CS_TEMP',
        'USB_D+', 'USB_D-', 'TEMP_SENSE'
    ]
    
    # Assign layers strategically for 4-layer board
    # F.Cu: High-speed signals (USB, SPI)
    # In1.Cu: Power signals (PWM, GATE)
    # In2.Cu: Analog signals (I_SENSE, TEMP)
    # B.Cu: AC/high-voltage signals
    net_layers = {
        'AC_L': 'B.Cu',
        'AC_N': 'B.Cu',
        'GATE_H': 'In1.Cu',
        'SW_NODE': 'In1.Cu',
        'GATE_L': 'In1.Cu',
        'PWM_H': 'In1.Cu',
        'PWM_L': 'In1.Cu',
        'SHUTDOWN_N': 'F.Cu',
        'I_SENSE': 'In2.Cu',
        'SPI_CLK': 'F.Cu',
        'SPI_MOSI': 'F.Cu',
        'SPI_MISO': 'F.Cu',
        'SPI_CS_TEMP': 'F.Cu',
        'USB_D+': 'F.Cu',
        'USB_D-': 'F.Cu',
        'TEMP_SENSE': 'In2.Cu',
    }
    
    print(f"\n4. Routing {len(signal_nets)} signal nets...")
    print("   (Timeout: 30s per net)\n")
    
    routes = []
    vias_all = []
    routed_count = 0
    failed_nets = []
    timeout_nets = []
    
    for net_name in signal_nets:
        layer = net_layers[net_name]
        
        if net_name not in net_pad_info:
            print(f"   ⚠ {net_name}: Not found in pad info")
            failed_nets.append(net_name)
            continue
        
        pad_info = net_pad_info[net_name]
        if len(pad_info) < 2:
            print(f"   ⚠ {net_name}: Only {len(pad_info)} pads")
            failed_nets.append(net_name)
            continue
        
        print(f"   Routing {net_name:15s} on {layer} ({len(pad_info)} pads)...", end=" ", flush=True)
        
        pads_with_layers = [
            (p['position'], p['layers'], p['ref'], p['pin'])
            for p in pad_info
        ]
        
        try:
            # Set 30 second timeout per net
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(30)
            
            route = router.route_net_with_vias(net_name, layer, pads_with_layers)
            signal.alarm(0)
            
            if route:
                print(f"✓ {len(route.segments)} seg, {len(route.vias)} vias")
                
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
                print(f"✗ Failed (no path)")
                failed_nets.append(net_name)
        
        except TimeoutError:
            signal.alarm(0)
            print(f"✗ Timeout (>30s)")
            timeout_nets.append(net_name)
        
        except Exception as e:
            signal.alarm(0)
            print(f"✗ Error: {e}")
            failed_nets.append(net_name)
    
    print(f"\n   Routed: {routed_count}/{len(signal_nets)} nets ({100*routed_count/len(signal_nets):.0f}%)")
    print(f"   Total segments: {len(routes)}")
    print(f"   Total vias: {len(vias_all)}")
    
    if timeout_nets:
        print(f"\n   Timeout nets ({len(timeout_nets)}): {', '.join(timeout_nets)}")
    if failed_nets:
        print(f"   Failed nets ({len(failed_nets)}): {', '.join(failed_nets)}")
    
    if routed_count == 0:
        print("\n✗ No nets routed successfully")
        return 1
    
    # Export
    print("\n5. Exporting to KiCad...")
    try:
        result = write_routes_to_pcb(
            template_pcb=pcb_path,
            output_pcb=output_path,
            routes=frozenset(type('Route', (), r) for r in routes),
            vias=frozenset(type('Via', (), v) for v in vias_all) if vias_all else None,
            clear_existing=True
        )
        print(f"   ✓ Exported {result.components_updated} traces")
        if vias_all:
            print(f"   ✓ Exported {len(vias_all)} vias")
    except Exception as e:
        print(f"   ✗ Export failed: {e}")
        return 1
    
    # Run DRC
    print("\n6. Running KiCad DRC...")
    try:
        run_drc(str(output_path), str(drc_path))
        
        # Parse DRC results
        import json
        with open(drc_path) as f:
            drc_data = json.load(f)
        
        total_violations = len(drc_data['violations'])
        
        # Count via-related violations
        via_violations = {
            'shorting': 0,
            'clearance': 0,
            'hole_clearance': 0,
            'hole_to_hole': 0,
            'other': 0
        }
        
        for v in drc_data['violations']:
            vtype = v['type']
            if 'via' in vtype.lower() or 'hole' in vtype.lower():
                if 'short' in vtype.lower():
                    via_violations['shorting'] += 1
                elif vtype == 'clearance':
                    # Check if involves via
                    desc = v.get('description', '').lower()
                    if 'via' in desc:
                        via_violations['clearance'] += 1
                elif vtype == 'hole_clearance':
                    via_violations['hole_clearance'] += 1
                elif vtype == 'hole_to_hole':
                    via_violations['hole_to_hole'] += 1
                else:
                    via_violations['other'] += 1
        
        via_total = sum(via_violations.values())
        
        print(f"   Total violations: {total_violations}")
        print(f"\n   VIA VIOLATIONS:")
        print(f"     Shorting: {via_violations['shorting']}")
        print(f"     Clearance: {via_violations['clearance']}")
        print(f"     Hole clearance: {via_violations['hole_clearance']}")
        print(f"     Hole-to-hole: {via_violations['hole_to_hole']}")
        print(f"     Other: {via_violations['other']}")
        print(f"     TOTAL: {via_total}")
        
        print(f"\n   ✓ DRC report: {drc_path}")
        
    except Exception as e:
        print(f"   ✗ DRC failed: {e}")
        return 1
    
    # Summary
    print("\n" + "=" * 70)
    if via_total == 0 and routed_count == len(signal_nets):
        print(" ✅ SUCCESS: All nets routed with 0 via violations!")
    elif via_total == 0:
        print(f" ⚠ {via_total} VIA VIOLATIONS, {routed_count}/{len(signal_nets)} nets routed")
    else:
        print(f" ⚠ {via_total} VIA VIOLATIONS on {routed_count}/{len(signal_nets)} nets")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
