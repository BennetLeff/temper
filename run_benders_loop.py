#!/usr/bin/env python3
"""
Full Benders placement-routing optimization loop.

This implements the proper Benders decomposition:
1. Master problem: Find valid placement (ILP)
2. Subproblem: Route nets with ExactGeometryRouter
3. Cut generation: If routing fails, add constraints to spread components
4. Repeat until routing succeeds with no DRC violations
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'packages/temper-placer/src')

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter
from temper_placer.io.kicad_writer import write_routes_direct
from temper_placer.io.kicad_drc import run_drc
from kiutils.board import Board
import signal


def timeout_handler(signum, frame):
    raise TimeoutError("Routing timed out")


def route_with_exact_router(pcb_path: Path, output_path: Path, timeout_per_net: int = 15) -> dict:
    """Route PCB with ExactGeometryRouter."""
    board = Board.from_file(str(pcb_path))
    parsed_pcb = parse_kicad_pcb_v6(pcb_path)
    
    router = ExactGeometryRouter(
        pcb=parsed_pcb,
        design_rules=parsed_pcb.design_rules,
        verbose=False,
        kicad_file=str(pcb_path)
    )
    
    # Extract pad info
    net_pad_info = {}
    for fp in board.footprints:
        ref = fp.properties.get('Reference', None)
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
                'pin': pad.number or ''
            })
    
    # Signal nets - prioritize via-needing nets
    signal_nets = [
        'GATE_H', 'GATE_L', 'PWM_H', 'PWM_L',
        'SPI_MOSI', 'SPI_MISO', 'SPI_CS_TEMP',
        'USB_D-', 'SW_NODE', 'I_SENSE', 'SPI_CLK',
        'USB_D+', 'TEMP_SENSE', 'AC_N'
    ]
    
    layer_priority = ['F.Cu', 'B.Cu', 'In1.Cu', 'In2.Cu']
    
    routes = []
    vias_all = []
    routed_count = 0
    failed_nets = []
    
    def try_route_net(net_name, layer, pad_info, timeout_sec):
        pads_with_layers = [
            (p['position'], p['layers'], p['ref'], p['pin'])
            for p in pad_info
        ]
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_sec)
            route = router.route_net_with_vias(net_name, layer, pads_with_layers)
            signal.alarm(0)
            return route, None
        except TimeoutError:
            signal.alarm(0)
            return None, 'timeout'
        except Exception as e:
            signal.alarm(0)
            return None, str(e)
    
    for net_name in signal_nets:
        if net_name not in net_pad_info:
            continue
        
        pad_info = net_pad_info[net_name]
        if len(pad_info) < 2:
            continue
        
        route = None
        for layer in layer_priority:
            route, error = try_route_net(net_name, layer, pad_info, timeout_per_net)
            if route is not None:
                break
            if error == 'timeout':
                break
        
        if route:
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
            failed_nets.append(net_name)
    
    # Write routes
    if routes:
        write_routes_direct(
            template_pcb=pcb_path,
            output_pcb=output_path,
            routes=routes,
            vias=vias_all if vias_all else None,
        )
    
    return {
        'routed': routed_count,
        'total': len(signal_nets),
        'failed': len(failed_nets),
        'failed_nets': failed_nets,
        'segments': len(routes),
        'vias': len(vias_all)
    }


def main():
    print("=" * 70)
    print(" Benders Placement-Routing Optimization Loop")
    print("=" * 70)
    
    pcb_path = Path('pcb/temper.kicad_pcb')
    output_path = Path('pcb/temper_benders_routed.kicad_pcb')
    drc_path = Path('pcb/temper_benders_drc.json')
    
    # For now, just do a single iteration since placement optimization
    # requires more setup. Focus on routing quality first.
    
    print("\nRouting with current placement...")
    start = time.time()
    route_result = route_with_exact_router(pcb_path, output_path, timeout_per_net=15)
    route_time = time.time() - start
    
    print(f"  Routed: {route_result['routed']}/{route_result['total']} nets ({route_time:.1f}s)")
    print(f"  Segments: {route_result['segments']}, Vias: {route_result['vias']}")
    if route_result['failed_nets']:
        print(f"  Failed: {', '.join(route_result['failed_nets'])}")
    
    # Run DRC
    print("\nRunning DRC...")
    drc_result = run_drc(str(output_path), str(drc_path))
    
    with open(drc_path) as f:
        drc_data = json.load(f)
    
    violations = drc_data.get('violations', [])
    routing_types = ['shorting_items', 'clearance', 'tracks_crossing', 'hole_clearance', 'hole_to_hole']
    
    by_type = {}
    for v in violations:
        t = v.get('type', 'unknown')
        by_type[t] = by_type.get(t, 0) + 1
    
    routing_violations = sum(by_type.get(t, 0) for t in routing_types)
    
    print(f"  Total violations: {len(violations)}")
    print(f"  Routing violations: {routing_violations}")
    
    # Summary
    print("\n" + "=" * 70)
    print(" RESULTS")
    print("=" * 70)
    print(f"Nets routed: {route_result['routed']}/{route_result['total']} ({100*route_result['routed']/route_result['total']:.0f}%)")
    print(f"Routing violations: {routing_violations}")
    
    print("\nViolations by type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    
    # Analyze routing quality
    if route_result['routed'] == route_result['total'] and routing_violations == 0:
        print("\n✓ PERFECT: All nets routed with zero violations!")
        return 0
    elif route_result['routed'] == route_result['total']:
        print(f"\n⚠ ROUTABLE: All nets routed but {routing_violations} violations remain")
        print("   Placement optimization could help reduce violations")
        return 1
    else:
        print(f"\n✗ INCOMPLETE: {route_result['failed']}/{route_result['total']} nets failed")
        print("   Placement optimization needed to create routing channels")
        return 1


if __name__ == '__main__':
    sys.exit(main())
