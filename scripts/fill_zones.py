#!/usr/bin/env python3
"""
Fill all zones in a KiCad PCB file using the pcbnew Python API.

This script must be run with KiCad's Python interpreter or in an environment
where the pcbnew module is available.

Usage:
    python3 fill_zones.py input.kicad_pcb output.kicad_pcb
    
Or via KiCad's scripting console:
    exec(open('/path/to/fill_zones.py').read())
"""

import sys
from pathlib import Path

def fill_zones(input_path: str, output_path: str):
    """Load PCB, fill all zones, and save."""
    try:
        import pcbnew
    except ImportError:
        print("ERROR: pcbnew module not found.")
        print("This script must be run with KiCad's Python environment.")
        print("Try: /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 fill_zones.py ...")
        sys.exit(1)
    
    print(f"Loading {input_path}...")
    board = pcbnew.LoadBoard(input_path)
    
    print("Filling zones...")
    filler = pcbnew.ZONE_FILLER(board)
    zones = board.Zones()
    
    # In newer KiCad, Zones() returns a tuple/list directly
    zone_list = list(zones)
    
    if not zone_list:
        print("No zones found in the board.")
    else:
        print(f"Found {len(zone_list)} zones to fill.")
        filler.Fill(zone_list)
        print("Zones filled successfully.")
    
    print(f"Saving to {output_path}...")
    pcbnew.SaveBoard(output_path, board)
    print("Done!")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: fill_zones.py <input.kicad_pcb> <output.kicad_pcb>")
        sys.exit(1)
    
    fill_zones(sys.argv[1], sys.argv[2])
