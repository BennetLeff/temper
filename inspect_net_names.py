import sys
from kiutils.board import Board

def main():
    board = Board.from_file("pre_routed_v5.kicad_pcb")
    target = "AC_N"
    print(f"Scanning for pads on net '{target}'...")
    
    found = False
    for fp in board.footprints:
        for pad in fp.pads:
            net_name = pad.net.name if pad.net else "None"
            if target in net_name or net_name == target:
                print(f"  Found Pad: FP='{fp.entryName}' Pad='{pad.number}' Net='{net_name}' Pos={pad.position.X},{pad.position.Y}")
                found = True
            elif "AC" in net_name: # Fuzzy
                 print(f"  Maybe? FP='{fp.entryName}' Pad='{pad.number}' Net='{net_name}'")

    if not found:
        print("No exact matches found!")

if __name__ == "__main__":
    main()
