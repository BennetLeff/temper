#!/usr/bin/env python3
"""
Power Fanout: Add stitching vias for SMD pads on power nets.

This script:
1. Identifies all SMD pads on excluded power nets (GND, +3V3, etc.)
2. For each SMD pad, places a via adjacent to it
3. Adds a short stub trace connecting the pad center to the via

Usage:
    uv run python scripts/fanout_power.py input.kicad_pcb -o output.kicad_pcb
"""

import argparse
import re
import sys
import uuid
import math
from pathlib import Path
from dataclasses import dataclass

# Configuration
VIA_DRILL = 0.3  # mm
VIA_SIZE = 0.6   # mm (annular ring + drill)
STUB_WIDTH = 0.3 # mm trace width for stub
VIA_OFFSET = 0.8 # mm offset from pad center to via center

# Power nets to fanout (these were excluded from signal routing)
POWER_NETS = {
    'GND': 'In2.Cu',      # Ground plane layer
    'PGND': 'In2.Cu',
    'CGND': 'In2.Cu',
    '+3V3': 'In1.Cu',     # Power plane layer
    '+5V': 'In1.Cu',
    '+15V': 'In1.Cu',
    'VCC_BOOT': 'In1.Cu',
}

@dataclass
class PadInfo:
    """Information about a pad that needs fanout."""
    x: float
    y: float
    net_id: int
    net_name: str
    size_x: float
    size_y: float
    layer: str  # F.Cu or B.Cu
    fp_ref: str

def generate_tstamp():
    return str(uuid.uuid4())

def get_net_ids(content: str) -> dict[str, int]:
    """Extract net name to ID mapping."""
    nets = {}
    for match in re.finditer(r'\(net (\d+) "([^"]+)"\)', content):
        nets[match.group(2)] = int(match.group(1))
    return nets

def find_smd_power_pads(content: str, net_ids: dict[str, int]) -> list[PadInfo]:
    """Find all SMD pads on power nets."""
    pads = []
    
    # Target net IDs
    target_nets = {net_ids.get(name): name for name in POWER_NETS if name in net_ids}
    
    # Parse footprints
    fp_pattern = re.compile(
        r'\(footprint "([^"]+)".*?\(at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?\)',
        re.DOTALL
    )
    
    for fp_match in re.finditer(r'\(footprint "([^"]+)" \(layer "([^"]+)"\)(.*?)\n  \)', content, re.DOTALL):
        fp_name = fp_match.group(1)
        fp_layer = fp_match.group(2)
        fp_content = fp_match.group(3)
        
        # Get footprint position
        at_match = re.search(r'\(at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?\)', fp_content)
        if not at_match:
            continue
        fp_x, fp_y = float(at_match.group(1)), float(at_match.group(2))
        fp_angle = float(at_match.group(3)) if at_match.group(3) else 0.0
        
        # Get reference
        ref_match = re.search(r'\(fp_text reference "([^"]+)"', fp_content)
        fp_ref = ref_match.group(1) if ref_match else fp_name
        
        # Find pads in this footprint
        for pad_match in re.finditer(
            r'\(pad "([^"]+)" (smd|thru_hole) (\w+) \(at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?\) \(size ([\d.-]+) ([\d.-]+)\).*?\(net (\d+) "([^"]+)"\)',
            fp_content, re.DOTALL
        ):
            pad_type = pad_match.group(2)
            # Process both SMD and THT pads (THT still need connection on outer layers)
            # Skip THT only if we have via stitching (zones are on inner layers)
            
            pad_net_id = int(pad_match.group(9))
            pad_net_name = pad_match.group(10)
            
            if pad_net_id not in target_nets:
                continue  # Not a power net we care about
            
            # Relative position
            rel_x, rel_y = float(pad_match.group(4)), float(pad_match.group(5))
            
            # Rotate relative position by footprint angle
            rad = math.radians(fp_angle)
            rot_x = rel_x * math.cos(rad) - rel_y * math.sin(rad)
            rot_y = rel_x * math.sin(rad) + rel_y * math.cos(rad)
            
            # Absolute position
            abs_x = fp_x + rot_x
            abs_y = fp_y + rot_y
            
            # Pad size
            size_x, size_y = float(pad_match.group(7)), float(pad_match.group(8))
            
            # Determine layer (SMD pads are on the same layer as footprint)
            pad_layer = "F.Cu" if "F." in fp_layer else "B.Cu"
            
            pads.append(PadInfo(
                x=abs_x,
                y=abs_y,
                net_id=pad_net_id,
                net_name=pad_net_name,
                size_x=size_x,
                size_y=size_y,
                layer=pad_layer,
                fp_ref=fp_ref,
            ))
    
    return pads

def create_via(x: float, y: float, net_id: int) -> str:
    """Generate a via S-expression."""
    return f'  (via (at {x:.4f} {y:.4f}) (size {VIA_SIZE}) (drill {VIA_DRILL}) (layers "F.Cu" "B.Cu") (net {net_id}) (tstamp "{generate_tstamp()}"))\n'

def create_segment(x1: float, y1: float, x2: float, y2: float, width: float, layer: str, net_id: int) -> str:
    """Generate a trace segment S-expression."""
    return f'  (segment (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f}) (width {width}) (layer "{layer}") (net {net_id}) (tstamp "{generate_tstamp()}"))\n'

def compute_via_position(pad: PadInfo, board_center: tuple[float, float]) -> tuple[float, float]:
    """Compute optimal via position for a pad.
    
    Places via in the direction toward board center for maximum zone coverage.
    """
    # Direction from pad toward board center
    dx = board_center[0] - pad.x
    dy = board_center[1] - pad.y
    
    # Normalize direction
    dist = math.sqrt(dx*dx + dy*dy)
    if dist < 0.1:
        # Pad is at center, offset in +X
        dx, dy = 1.0, 0.0
    else:
        dx, dy = dx / dist, dy / dist
    
    # Offset from pad edge
    offset = VIA_OFFSET + max(pad.size_x, pad.size_y) / 2
    
    via_x = pad.x + dx * offset
    via_y = pad.y + dy * offset
    
    return (via_x, via_y)

def main():
    parser = argparse.ArgumentParser(description="Add power fanout vias for SMD pads")
    parser.add_argument("input_pcb", type=Path, help="Input .kicad_pcb file")
    parser.add_argument("-o", "--output", type=Path, help="Output .kicad_pcb file")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()
    
    if not args.output:
        args.output = args.input_pcb.with_stem(args.input_pcb.stem + "_fanout")
    
    print(f"Power Fanout: {args.input_pcb} -> {args.output}")
    
    content = args.input_pcb.read_text()
    net_ids = get_net_ids(content)
    
    print(f"Found {len(net_ids)} nets")
    
    # Find SMD pads on power nets
    pads = find_smd_power_pads(content, net_ids)
    print(f"Found {len(pads)} SMD pads on power nets")
    
    if not pads:
        print("No SMD power pads found. Nothing to do.")
        sys.exit(0)
    
    # Group by net for reporting
    by_net = {}
    for pad in pads:
        by_net.setdefault(pad.net_name, []).append(pad)
    
    for net_name, net_pads in sorted(by_net.items()):
        print(f"  {net_name}: {len(net_pads)} pads")
    
    # Extract board bounds for center calculation
    edge_match = re.search(r'\(gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(layer \"Edge\.Cuts\"\)', content)
    if edge_match:
        bx1, by1, bx2, by2 = map(float, edge_match.groups())
    else:
        # Fallback: estimate from pad positions
        bx1, by1 = min(p.x for p in pads), min(p.y for p in pads)
        bx2, by2 = max(p.x for p in pads), max(p.y for p in pads)
    
    board_center = ((bx1 + bx2) / 2, (by1 + by2) / 2)
    print(f"Board center: {board_center[0]:.1f}, {board_center[1]:.1f}")
    
    # Generate vias and stubs
    new_items = []
    for pad in pads:
        via_x, via_y = compute_via_position(pad, board_center)
        
        # Add via
        new_items.append(create_via(via_x, via_y, pad.net_id))
        
        # Add stub trace from pad to via
        new_items.append(create_segment(
            pad.x, pad.y, via_x, via_y,
            STUB_WIDTH, pad.layer, pad.net_id
        ))
    
    print(f"Generated {len(pads)} vias and {len(pads)} stub traces")
    
    if args.dry_run:
        print("\n--- DRY RUN: Would add these items ---")
        for item in new_items[:10]:
            print(item.strip())
        if len(new_items) > 10:
            print(f"... and {len(new_items) - 10} more")
        sys.exit(0)
    
    # Insert before the last closing parenthesis
    last_paren = content.rfind(')')
    new_content = content[:last_paren] + ''.join(new_items) + content[last_paren:]
    
    args.output.write_text(new_content)
    print(f"Wrote {args.output}")

if __name__ == "__main__":
    main()
