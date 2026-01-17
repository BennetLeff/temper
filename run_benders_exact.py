#!/usr/bin/env python3
"""
Run Benders optimization with ExactGeometryRouter for DRC-clean routing.

This integrates the placement optimization loop with our DRC-aware router.
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'packages/temper-placer/src')

from temper_placer.placement.benders_loop import BendersOptimizer, BendersStatus
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter
from temper_placer.io.kicad_writer import write_routes_direct
from temper_placer.io.kicad_drc import run_drc
from kiutils.board import Board
import signal


def timeout_handler(signum, frame):
    raise TimeoutError("Routing timed out")


def route_with_exact_router(pcb_path: Path, output_path: Path, timeout_per_net: int = 20) -> dict:
    """
    Route the PCB using ExactGeometryRouter with shorter timeouts.
    """
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
                'pin': pad.number or ''
            })
    
    # Signal nets to route - prioritize via-needing nets first
    signal_nets = [
        'GATE_H', 'GATE_L', 'PWM_H', 'PWM_L',
        'SPI_MOSI', 'SPI_MISO', 'SPI_CS_TEMP',
        'USB_D-',
        'SW_NODE', 'I_SENSE', 'SPI_CLK',
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
                break  # Don't try other layers if timeout
        
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
    print(" Benders + ExactGeometryRouter Integration")
    print("=" * 70)
    
    pcb_path = Path('pcb/temper.kicad_pcb')
    output_path = Path('pcb/temper_benders_routed.kicad_pcb')
    drc_path = Path('pcb/temper_benders_drc.json')
    
    # Step 1: Run Benders placement optimization
    print("\n1. Running Benders placement optimization...")
    start = time.time()
    
    optimizer = BendersOptimizer(
        component_data_json='packages/temper-placer/data/benders_input.json',
        max_iterations=1,
        pcb_file=str(pcb_path),
        verbose=False,
        use_router_feedback=False,
        require_drc_clean=False,
        check_routability=False,  # Skip for speed
    )
    
    benders_result = optimizer.optimize()
    benders_time = time.time() - start
    
    print(f"   Status: {benders_result.status}")
    print(f"   Movement: {benders_result.total_movement:.2f}mm")
    print(f"   Time: {benders_time:.1f}s")
    
    # Step 2: Route with ExactGeometryRouter
    print("\n2. Routing with ExactGeometryRouter...")
    start = time.time()
    route_result = route_with_exact_router(pcb_path, output_path, timeout_per_net=15)
    route_time = time.time() - start
    
    print(f"   Routed: {route_result['routed']}/{route_result['total']} nets")
    print(f"   Segments: {route_result['segments']}, Vias: {route_result['vias']}")
    print(f"   Time: {route_time:.1f}s")
    if route_result['failed_nets']:
        print(f"   Failed: {', '.join(route_result['failed_nets'])}")
    
    # Step 3: Run DRC
    print("\n3. Running DRC...")
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
    
    print(f"   Total violations: {len(violations)}")
    print(f"   Routing violations: {routing_violations}")
    
    # Summary
    print("\n" + "=" * 70)
    print(" RESULTS")
    print("=" * 70)
    print(f"Nets routed: {route_result['routed']}/{route_result['total']}")
    print(f"Routing violations: {routing_violations}")
    print(f"Total violations: {len(violations)}")
    
    print("\nViolations by type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    
    if routing_violations == 0:
        print("\n✓ SUCCESS: No routing violations!")
    
    return 0 if routing_violations == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
