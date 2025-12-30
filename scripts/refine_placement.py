#!/usr/bin/env python3
"""
Refine placement for routed_v3 failures.
Regenerated using kiutils for robustness.

Actions:
1. Strip all tracks (segments) and vias.
2. Move J_AC_IN closer to Bridge Rectifier.
"""

import sys
from pathlib import Path
from kiutils.board import Board
from kiutils.items.common import Position

def main():
    input_path = Path("routed_v3_clean.kicad_pcb")
    output_path = Path("unrouted_v4.kicad_pcb")

    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    print(f"Reading {input_path} using kiutils...")
    board = Board.from_file(str(input_path))

    # 1. Strip Routing
    print(f"Removing {len(board.traceItems)} trace items (segments/vias)...")
    board.traceItems = [] # Clear all traces and vias

    # 2. Relocate J_AC_IN
    # Target: (10, 125)
    target_ref = "J_AC_IN"
    moved = False
    for fp in board.footprints:
        # Check Reference property
        ref = None
        if hasattr(fp, "properties"):
            props = fp.properties
            if isinstance(props, dict):
                ref = props.get("Reference")
            elif isinstance(props, list):
                for p in props:
                    if hasattr(p, "name") and p.name == "Reference":
                        ref = p.value
                        break
        
        if ref == target_ref:
            print(f"Moving {ref} from ({fp.position.X}, {fp.position.Y}) to (10.0, 125.0)")
            fp.position.X = 10.0
            fp.position.Y = 125.0
            # Keep rotation same (likely 0 or 90/180/270)
            moved = True
            break
            
    if not moved:
        print(f"Warning: {target_ref} not found!")

    print(f"Writing to {output_path}...")
    board.to_file(str(output_path))
    print("Done.")

if __name__ == "__main__":
    main()