#!/usr/bin/env python3
"""
Pre-route critical power tracks (AC_L, AC_N) on Bottom Layer.

Input: unrouted_v4_fixed.kicad_pcb
Output: pre_routed_v5.kicad_pcb
"""

import sys
import uuid
from pathlib import Path

def add_segment(start: tuple[float, float], end: tuple[float, float], width: float, layer: str, net_id: int) -> str:
    """Generate a Kicad PCB segment S-expression."""
    return f'  (segment (start {start[0]} {start[1]}) (end {end[0]} {end[1]}) (width {width}) (layer "{layer}") (net {net_id}) (tstamp "{uuid.uuid4()}"))\n'

def main():
    input_path = Path("unrouted_v4_fixed.kicad_pcb")
    output_path = Path("pre_routed_v5.kicad_pcb")

    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    print(f"Reading {input_path}...")
    content = input_path.read_text()

    # Find the end of the nets section or start of segments to insert new ones
    # Usually segments are at the end, before the closing ')'
    # We'll just insert before the last ')'
    
    new_segments = []
    
    # --- Route AC_L (Net 19) ---
    # Path: (10, 125) -> (60, 125) -> (67, 129)
    new_segments.append(add_segment((10.0, 125.0), (60.0, 125.0), 2.0, "B.Cu", 19))
    new_segments.append(add_segment((60.0, 125.0), (67.0, 129.0), 2.0, "B.Cu", 19))
    
    # --- Route AC_N (Net 20) ---
    # Path: (10, 135) -> (90, 135) -> (90, 119) -> (82.24, 119)
    new_segments.append(add_segment((10.0, 135.0), (90.0, 135.0), 2.0, "B.Cu", 20))
    new_segments.append(add_segment((90.0, 135.0), (90.0, 119.0), 2.0, "B.Cu", 20))
    new_segments.append(add_segment((90.0, 119.0), (82.24, 119.0), 2.0, "B.Cu", 20))

    print(f"Injecting {len(new_segments)} manual segments...")
    
    # Insert before the last closing parenthesis
    last_paren_index = content.rfind(')')
    if last_paren_index == -1:
        print("Error: Malformed PCB file (no closing paren)")
        sys.exit(1)
        
    new_content = content[:last_paren_index] + "".join(new_segments) + content[last_paren_index:]
    
    print(f"Writing to {output_path}...")
    output_path.write_text(new_content)
    print("Done.")

if __name__ == "__main__":
    main()
