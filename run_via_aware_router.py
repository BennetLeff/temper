#!/usr/bin/env python3
"""
Run via-aware router on real Temper board and get actual DRC report.

This integrates the TDD-validated via-aware routing system with the
real board to produce a manufacturable PCB with 0 via violations.
"""

import sys
import json
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from shapely.geometry import box
from kiutils.board import Board

from temper_placer.router_v6.via_model import ViaSpec
from temper_placer.router_v6.via_planner import ViaPlanner
from temper_placer.router_v6.pad_layer_connector import Pad, PadLayerConnector
from temper_placer.router_v6.exact_geometry_router_via_aware import (
    ExactGeometryRouterViaAware, NetRoute
)
from temper_placer.io.kicad_drc import run_drc


def read_board_pads(kicad_file: Path) -> dict[str, list[Pad]]:
    """
    Read pads from KiCad file and group by net.
    
    Returns dict of net_name -> list of Pad objects
    """
    board = Board.from_file(str(kicad_file))
    
    nets_to_pads = {}
    
    for fp in board.footprints:
        ref = fp.entryName
        
        for pad in fp.pads:
            if not pad.net or not pad.net.name:
                continue
            
            net_name = pad.net.name
            
            # Get pad position (footprint position + pad position)
            fp_x = fp.position.X if fp.position else 0
            fp_y = fp.position.Y if fp.position else 0
            
            pad_x = (pad.position.X if pad.position else 0)
            pad_y = (pad.position.Y if pad.position else 0)
            
            # Apply rotation if needed (simplified - assumes 0 or 180)
            if fp.position and hasattr(fp.position, 'angle') and fp.position.angle == 180:
                pad_x = -pad_x
                pad_y = -pad_y
            
            abs_x = fp_x + pad_x
            abs_y = fp_y + pad_y
            
            # Get layers
            layers = []
            if pad.layers:
                layers = list(pad.layers)
            
            pad_obj = Pad(
                position=(abs_x, abs_y),
                layers=layers,
                net=net_name,
                ref=ref,
                number=pad.number or ""
            )
            
            if net_name not in nets_to_pads:
                nets_to_pads[net_name] = []
            nets_to_pads[net_name].append(pad_obj)
    
    return nets_to_pads


def export_routes_to_kicad(
    input_file: Path,
    output_file: Path,
    routes: dict[str, NetRoute]
) -> None:
    """
    Export routed tracks and vias to KiCad file.
    """
    board = Board.from_file(str(input_file))
    
    # Clear existing traces
    board.traceItems = []
    
    # Add tracks
    for net_name, route in routes.items():
        for track in route.tracks:
            from kiutils.items.brditems import Segment
            from kiutils.items.common import Position
            
            seg = Segment()
            seg.start = Position(X=track.start[0], Y=track.start[1])
            seg.end = Position(X=track.end[0], Y=track.end[1])
            seg.width = track.width
            seg.layer = track.layer
            seg.net = 0
            
            # Find net number
            for net in board.nets:
                if net.name == net_name:
                    seg.net = net.number
                    break
            
            board.traceItems.append(seg)
        
        # Add vias
        for via in route.vias:
            from kiutils.items.brditems import Via
            from kiutils.items.common import Position
            
            via_obj = Via()
            via_obj.position = Position(X=via.position[0], Y=via.position[1])
            via_obj.size = via.spec.diameter
            via_obj.drill = via.spec.drill
            via_obj.layers = via.layers
            via_obj.net = 0
            
            # Find net number
            for net in board.nets:
                if net.name == net_name:
                    via_obj.net = net.number
                    break
            
            board.traceItems.append(via_obj)
    
    board.to_file(str(output_file))


def main():
    """Run via-aware router on Temper board"""
    print("=" * 70)
    print(" VIA-AWARE ROUTER: REAL TEMPER BOARD")
    print("=" * 70)
    
    # Paths
    input_pcb = Path("pcb/temper.kicad_pcb")
    output_pcb = Path("pcb/temper_via_aware_output.kicad_pcb")
    drc_output = Path("pcb/temper_via_aware_drc.json")
    
    if not input_pcb.exists():
        print(f"✗ Input PCB not found: {input_pcb}")
        return 1
    
    print(f"\nInput: {input_pcb}")
    print(f"Output: {output_pcb}")
    print(f"DRC: {drc_output}")
    
    # Read board pads
    print("\n1. Reading board pads...")
    nets_to_pads = read_board_pads(input_pcb)
    
    # Filter signal nets (skip power/ground)
    signal_nets = {
        net: pads for net, pads in nets_to_pads.items()
        if len(pads) >= 2 and net not in [
            'GND', '+3V3', '+5V', '+12V', 'VCC', 'VBUS', 
            'unconnected', ''
        ] and not net.startswith('unconnected-')
    }
    
    print(f"   Total nets: {len(nets_to_pads)}")
    print(f"   Signal nets to route: {len(signal_nets)}")
    
    # Setup via-aware router
    print("\n2. Setting up via-aware router...")
    
    # Board outline (simplified - 150x100mm)
    board_area = box(0, 0, 150, 100)
    via_spec = ViaSpec.standard()
    via_planner = ViaPlanner(board_area, via_spec)
    pad_connector = PadLayerConnector(via_planner)
    router = ExactGeometryRouterViaAware(board_area, via_planner, pad_connector)
    
    print(f"   Via spec: {via_spec.diameter}mm dia, {via_spec.drill}mm drill")
    print(f"   Min via spacing: {via_spec.min_spacing}mm")
    
    # Route nets
    print("\n3. Routing signal nets...")
    
    routes = {}
    failed_nets = []
    
    # Prioritize USB and SPI nets (most problematic)
    priority_nets = [
        'USB_D+', 'USB_D-', 'SPI_CLK', 'SPI_MOSI', 'SPI_MISO',
        'SPI_CS_TEMP', 'I_SENSE'
    ]
    
    # Route priority nets first
    for net_name in priority_nets:
        if net_name in signal_nets:
            pads = signal_nets[net_name]
            print(f"   Routing {net_name} ({len(pads)} pads)...", end=" ")
            
            # Route on In1.Cu (inner layer)
            route = router.route_net(net_name, pads, 'In1.Cu')
            
            if route:
                routes[net_name] = route
                print(f"✓ ({len(route.tracks)} tracks, {len(route.vias)} vias)")
            else:
                failed_nets.append(net_name)
                print("✗ FAILED")
    
    # Route remaining nets
    for net_name, pads in signal_nets.items():
        if net_name in priority_nets:
            continue  # Already routed
        
        print(f"   Routing {net_name} ({len(pads)} pads)...", end=" ")
        
        route = router.route_net(net_name, pads, 'In1.Cu')
        
        if route:
            routes[net_name] = route
            print(f"✓ ({len(route.tracks)} tracks, {len(route.vias)} vias)")
        else:
            failed_nets.append(net_name)
            print("✗")
    
    # Summary
    print(f"\n   Routed: {len(routes)}/{len(signal_nets)} nets")
    print(f"   Failed: {len(failed_nets)} nets")
    if failed_nets:
        print(f"   Failed nets: {', '.join(failed_nets[:10])}")
        if len(failed_nets) > 10:
            print(f"                ...and {len(failed_nets) - 10} more")
    
    print(f"   Total vias placed: {via_planner.via_count}")
    
    # Export to KiCad
    print("\n4. Exporting to KiCad...")
    export_routes_to_kicad(input_pcb, output_pcb, routes)
    print(f"   ✓ Exported to {output_pcb}")
    
    # Run DRC
    print("\n5. Running KiCad DRC...")
    drc_result = run_drc(str(output_pcb), str(drc_output))
    
    if drc_result:
        with open(drc_output) as f:
            drc_data = json.load(f)
        
        violations = drc_data.get('violations', [])
        print(f"   Total violations: {len(violations)}")
        
        # Categorize violations
        via_violations = {
            'shorting': 0,
            'clearance': 0,
            'hole_clearance': 0
        }
        
        other_violations = {}
        
        for v in violations:
            vtype = v.get('type', 'unknown')
            
            if 'via' in v.get('description', '').lower():
                if 'short' in vtype:
                    via_violations['shorting'] += 1
                elif 'clearance' in vtype and 'hole' in vtype:
                    via_violations['hole_clearance'] += 1
                elif 'clearance' in vtype:
                    via_violations['clearance'] += 1
            else:
                other_violations[vtype] = other_violations.get(vtype, 0) + 1
        
        print("\n   VIA VIOLATIONS:")
        print(f"     Shorting: {via_violations['shorting']}")
        print(f"     Clearance: {via_violations['clearance']}")
        print(f"     Hole clearance: {via_violations['hole_clearance']}")
        total_via = sum(via_violations.values())
        print(f"     TOTAL: {total_via}")
        
        if other_violations:
            print("\n   OTHER VIOLATIONS:")
            for vtype, count in sorted(other_violations.items()):
                print(f"     {vtype}: {count}")
        
        print(f"\n   ✓ DRC report saved to {drc_output}")
        
        # Final verdict
        print("\n" + "=" * 70)
        if total_via == 0:
            print(" ✓ SUCCESS: 0 VIA VIOLATIONS")
        else:
            print(f" ⚠ {total_via} VIA VIOLATIONS REMAIN")
        print("=" * 70)
        
        return 0 if total_via == 0 else 1
    
    else:
        print("   ✗ DRC failed to run")
        return 1


if __name__ == '__main__':
    sys.exit(main())
