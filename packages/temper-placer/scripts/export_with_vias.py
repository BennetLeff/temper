#!/usr/bin/env python3
"""
Export router results with automatic via insertion at pad locations.

PROBLEM:
Router assigns nets to inner layers (In1.Cu, In2.Cu, B.Cu) but pads are on F.Cu.
Without vias, there's no electrical connection → DRC reports "unconnected".

SOLUTION:
For each routed net:
1. Check which layer the tracks are on
2. Check which layers the pads are on
3. If mismatch, insert via at each pad location to connect layers
"""

from pathlib import Path
from kiutils.board import Board
from kiutils.items.brditems import Via
from kiutils.items.common import Position
import sys

def get_pad_layer(pad):
    """Get primary copper layer for a pad."""
    layers = getattr(pad, 'layers', [])
    if not isinstance(layers, list):
        return None
    
    # Prefer F.Cu, then B.Cu, then inner layers
    copper = [l for l in layers if '.Cu' in l]
    if 'F.Cu' in copper:
        return 'F.Cu'
    if 'B.Cu' in copper:
        return 'B.Cu'
    if '*.Cu' in copper:
        return 'F.Cu'  # *.Cu means all layers, use F.Cu
    return copper[0] if copper else None

def add_vias_for_layer_changes(input_pcb: str, output_pcb: str):
    """Add vias at pad locations where routing layer differs from pad layer."""
    board = Board.from_file(input_pcb)
    
    print(f"Processing {input_pcb}")
    print(f"Nets: {len(board.nets)}")
    
    # Build net number → name mapping
    net_names = {net.number: net.name for net in board.nets}
    
    # For each net, find track layers and pad positions
    net_info = {}  # net_number → {track_layers: set, pads: [(x, y, layer)]}
    
    # Collect track layers
    for seg in board.traceItems:
        if not hasattr(seg, 'net') or seg.net == 0:
            continue
        if seg.net not in net_info:
            net_info[seg.net] = {'track_layers': set(), 'pads': []}
        net_info[seg.net]['track_layers'].add(seg.layer)
    
    # Collect pad positions and layers
    import math
    for fp in board.footprints:
        angle = math.radians(fp.position.angle or 0)
        for pad in fp.pads:
            if not pad.net or pad.net.number == 0:
                continue
            
            # Calculate absolute position
            px, py = pad.position.X, pad.position.Y
            abs_x = fp.position.X + px * math.cos(angle) - py * math.sin(angle)
            abs_y = fp.position.Y + px * math.sin(angle) + py * math.cos(angle)
            
            pad_layer = get_pad_layer(pad)
            if not pad_layer:
                continue
            
            net_num = pad.net.number
            if net_num not in net_info:
                net_info[net_num] = {'track_layers': set(), 'pads': []}
            net_info[net_num]['pads'].append((abs_x, abs_y, pad_layer))
    
    # Insert vias where needed
    vias_added = 0
    for net_num, info in net_info.items():
        track_layers = info['track_layers']
        if not track_layers:
            continue
        
        net_name = net_names.get(net_num, f"Net-{net_num}")
        
        # For each pad, check if its layer matches any track layer
        for pad_x, pad_y, pad_layer in info['pads']:
            # Check if we need a via
            needs_via = pad_layer not in track_layers
            
            if needs_via:
                # Insert via at pad location
                # Via connects all layers, so it bridges pad layer to track layer
                via = Via(
                    position=Position(X=pad_x, Y=pad_y),
                    size=0.8,  # 0.8mm via diameter (standard)
                    drill=0.4,  # 0.4mm drill (standard)
                    layers=['F.Cu', 'B.Cu'],  # Through-hole via
                    net=net_num,
                )
                board.traceItems.append(via)
                vias_added += 1
    
    print(f"Added {vias_added} vias")
    board.to_file(output_pcb)
    print(f"Saved to {output_pcb}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: export_with_vias.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.kicad_pcb', '_vias.kicad_pcb')
    
    add_vias_for_layer_changes(input_file, output_file)
